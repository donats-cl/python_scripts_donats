"""Frida session management + event ingestion."""

from __future__ import annotations

import json
import shlex
import shutil
import sys
import time
from pathlib import Path

import frida
import psutil

from .store import Store

AGENT_PATH = Path(__file__).with_name("agent.js")
DEFAULT_SOURCES = {"socket": True, "schannel": True, "winhttp": True, "dns": True}


class CaptureError(RuntimeError):
    pass


def find_pid(name: str) -> int:
    matches: list[tuple[float, int]] = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            pname = (p.info.get("name") or "").lower()
            if pname == name.lower():
                matches.append((p.info.get("create_time") or 0, p.info["pid"]))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if not matches:
        raise CaptureError(f"process '{name}' not found")
    return max(matches)[1]


def list_processes(needle: str | None = None, limit: int = 60) -> list[dict]:
    out = []
    for p in psutil.process_iter(["pid", "name", "exe"]):
        try:
            info = p.info
            name = info.get("name") or ""
            if needle and needle.lower() not in name.lower() and needle.lower() not in str(info.get("exe") or "").lower():
                continue
            out.append({"pid": info["pid"], "name": name, "exe": info.get("exe") or ""})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    out.sort(key=lambda i: i["name"].lower())
    return out[:limit]


class Collector:
    """Turns frida messages into store rows."""

    def __init__(self, store: Store, verbose: bool = True):
        self.store = store
        self.verbose = verbose
        self.events = 0
        self.bytes = 0
        self.errors = 0
        self.flows = 0
        self.on_log = None

    def log(self, msg: str) -> None:
        if self.verbose:
            print(msg, file=sys.stderr, flush=True)
        if self.on_log:
            self.on_log(msg)

    def on_message(self, message: dict, data: bytes | None) -> None:
        try:
            if message.get("type") == "error":
                self.errors += 1
                self.log(f"[agent error] {message.get('description')}")
                return
            payload = message.get("payload") or {}
            kind = payload.get("type") if isinstance(payload, dict) else None
            if kind == "data":
                raw = data or b""
                self.store.add_chunk(
                    payload["fid"], payload["dir"], payload.get("source", "socket"),
                    raw, payload.get("size"), bool(payload.get("truncated")),
                )
                self.events += 1
                self.bytes += len(raw)
            elif kind == "flow_open":
                self.store.upsert_flow(payload["fid"], payload)
                self.flows += 1
            elif kind == "flow_close":
                self.store.end_flow(payload["fid"])
            elif kind == "dns":
                self.store.add_dns(payload.get("host") or "", payload.get("addrs") or [])
            elif kind == "log":
                self.log(f"[agent] {payload.get('msg')}")
            elif kind == "agent_ready":
                self.log(f"[agent] ready pid={payload.get('pid')} arch={payload.get('arch')}")
        except Exception as exc:  # never kill the frida thread
            self.errors += 1
            self.log(f"[collector] {type(exc).__name__}: {exc}")


class Capture:
    def __init__(
        self,
        db: str = "capture.db",
        pid: int | None = None,
        name: str | None = None,
        spawn: str | list[str] | None = None,
        cwd: str | None = None,
        max_chunk: int = 1024 * 1024,
        sources: dict[str, bool] | None = None,
        verbose: bool = True,
    ):
        self.store = Store(db, pid=pid, process=None)
        self.collector = Collector(self.store, verbose=verbose)
        self.requested_pid = pid
        self.name = name
        self.spawn = spawn
        self.cwd = cwd
        self.max_chunk = max_chunk
        self.sources = dict(DEFAULT_SOURCES)
        if sources:
            self.sources.update(sources)
        self.session: frida.core.Session | None = None
        self.script: frida.core.Script | None = None
        self.pid: int | None = None
        self.spawned = False
        self.verbose = verbose

    # ------------------------------------------------------------------ setup
    def _spawn_argv(self) -> list[str]:
        if isinstance(self.spawn, (list, tuple)):
            argv = list(self.spawn)
        else:
            argv = shlex.split(str(self.spawn), posix=False)
        if not argv:
            raise CaptureError("empty --spawn command")
        exe = shutil.which(argv[0]) or argv[0]
        if not Path(exe).exists():
            raise CaptureError(f"executable not found: {argv[0]}")
        argv[0] = exe
        return argv

    def start(self) -> int:
        if self.spawn:
            argv = self._spawn_argv()
            self.pid = frida.spawn(argv[0], argv=argv[1:], cwd=self.cwd)
            self.spawned = True
            self.session = frida.attach(self.pid)
        else:
            self.pid = self.requested_pid or (find_pid(self.name) if self.name else None)
            if not self.pid:
                raise CaptureError("specify one of --pid, --name, --spawn")
            self.session = frida.attach(self.pid)

        try:
            proc = psutil.Process(self.pid)
            proc_name = proc.name()
        except Exception:
            proc_name = "?"

        self.store.pid = self.pid
        self.store.process = proc_name
        self.store.set_target(self.pid, proc_name)

        cfg = {"maxChunk": self.max_chunk, "sources": self.sources}
        source = f"globalThis.__READNET_CFG__ = {json.dumps(cfg)};\n" + AGENT_PATH.read_text(encoding="utf-8")
        self.script = self.session.create_script(source, name="readnet-agent")
        self.script.on("message", self.collector.on_message)
        self.script.load()

        self.collector.log(
            f"[readnet] attached to {proc_name} ({self.pid})"
            + (f", spawned, resuming" if self.spawned else "")
        )
        if self.spawned:
            frida.resume(self.pid)
        return self.pid

    # ------------------------------------------------------------------- loop
    def wait(self, duration: float | None = None) -> None:
        started = time.monotonic()
        try:
            while True:
                if duration and time.monotonic() - started >= duration:
                    break
                if self.session is not None and self.pid:
                    if self.spawned:
                        if not psutil.pid_exists(self.pid):
                            break
                    else:
                        try:
                            if not psutil.pid_exists(self.pid):
                                break
                        except Exception:
                            break
                time.sleep(0.25)
        except KeyboardInterrupt:
            pass

    def stop(self) -> None:
        try:
            if self.script is not None:
                self.script.unload()
        except Exception:
            pass
        try:
            if self.session is not None:
                if self.spawned and self.pid:
                    try:
                        frida.kill(self.pid)
                    except Exception:
                        pass
                else:
                    self.session.detach()
        except Exception:
            pass
        self.store.close()
        c = self.collector
        if self.verbose:
            print(f"[readnet] stopped: flows={c.flows} chunks={c.events} bytes={c.bytes} errors={c.errors}",
                  file=sys.stderr, flush=True)
