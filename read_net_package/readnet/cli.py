"""readnet command line."""

from __future__ import annotations

import argparse
import json
import sys
import time
import webbrowser
from pathlib import Path

from . import __version__


def _add_capture_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--pid", type=int, help="target process id")
    p.add_argument("--name", help="target process name, e.g. chrome.exe (newest match)")
    p.add_argument("--spawn", help="start this command suspended, attach, then resume")
    p.add_argument("--cwd", help="working directory for --spawn")
    p.add_argument("--db", default="capture.db", help="sqlite file (default: capture.db)")
    p.add_argument("--duration", type=float, default=0, help="stop after N seconds (0 = until Ctrl+C)")
    p.add_argument("--max-chunk", type=int, default=1024 * 1024, help="max bytes stored per chunk")
    p.add_argument("--ui-port", type=int, default=8080, help="web UI port (0 = disabled)")
    p.add_argument("--host", default="127.0.0.1", help="web UI bind address")
    p.add_argument("--open", action="store_true", help="open the web UI in a browser")
    p.add_argument("--no-socket", action="store_true", help="disable raw winsock capture")
    p.add_argument("--no-schannel", action="store_true", help="disable TLS plaintext (Schannel) capture")
    p.add_argument("--no-winhttp", action="store_true", help="disable WinHTTP API capture")
    p.add_argument("--no-dns", action="store_true", help="disable DNS capture")
    p.add_argument("-q", "--quiet", action="store_true")


def cmd_capture(args: argparse.Namespace) -> int:
    from .frida_capture import Capture, CaptureError
    from .ui import serve_background

    if not (args.pid or args.name or args.spawn):
        print("error: specify --pid, --name or --spawn", file=sys.stderr)
        return 2

    sources = {
        "socket": not args.no_socket,
        "schannel": not args.no_schannel,
        "winhttp": not args.no_winhttp,
        "dns": not args.no_dns,
    }
    cap = Capture(
        db=args.db, pid=args.pid, name=args.name, spawn=args.spawn, cwd=args.cwd,
        max_chunk=args.max_chunk, sources=sources, verbose=not args.quiet,
    )
    server = None
    try:
        pid = cap.start()
    except CaptureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # frida permission / missing process
        print(f"attach failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("hint: run as Administrator and make sure the bitness matches (64-bit Frida -> 64-bit target).",
              file=sys.stderr)
        return 2

    if args.ui_port:
        try:
            server = serve_background(cap.store, host=args.host, port=args.ui_port)
            url = f"http://{args.host}:{args.ui_port}/"
            print(f"[readnet] UI: {url}  (db: {Path(args.db).resolve()})", file=sys.stderr, flush=True)
            if args.open:
                webbrowser.open(url)
        except Exception as exc:
            print(f"[readnet] UI failed to start: {exc}", file=sys.stderr)

    started = time.time()
    try:
        cap.wait(duration=args.duration)
    except KeyboardInterrupt:
        pass
    finally:
        cap.stop()
        if server is not None:
            server.should_exit = True

    s = cap.collector
    print(f"[readnet] done in {time.time() - started:.1f}s: {s.flows} flows, {s.events} chunks, "
          f"{s.bytes} bytes -> {args.db}", file=sys.stderr)
    return 0


def cmd_ui(args: argparse.Namespace) -> int:
    from .store import Store
    from .ui import serve

    if not Path(args.db).exists():
        print(f"error: db not found: {args.db}", file=sys.stderr)
        return 2
    store = Store(args.db)
    url = f"http://{args.host}:{args.port}/"
    print(f"[readnet] UI: {url}  (db: {Path(args.db).resolve()})", file=sys.stderr, flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        serve(store, host=args.host, port=args.port)
    except KeyboardInterrupt:
        pass
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    from .store import Store, to_jsonl

    if not Path(args.db).exists():
        print(f"error: db not found: {args.db}", file=sys.stderr)
        return 2
    store = Store(args.db)
    items = store.export_flows(max_chunk=args.max_chunk)
    if args.format == "json":
        text = json.dumps(items, ensure_ascii=False, indent=2, default=str)
    else:
        text = to_jsonl(items)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"[readnet] exported {len(items)} flows -> {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    from .frida_capture import list_processes

    procs = list_processes(needle=args.filter, limit=args.limit)
    if not procs:
        print("no processes found", file=sys.stderr)
        return 1
    for p in procs:
        print(f"{p['pid']:>7}  {p['name']:<32}  {p['exe']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="readnet", description="Per-process traffic capture with HTTP/JSON inspection")
    p.add_argument("--version", action="version", version=f"readnet {__version__}")
    sub = p.add_subparsers(dest="cmd")

    c = sub.add_parser("capture", help="attach to a process and record its traffic")
    _add_capture_args(c)
    c.set_defaults(func=cmd_capture)

    u = sub.add_parser("ui", help="serve the web UI for an existing capture.db")
    u.add_argument("--db", default="capture.db")
    u.add_argument("--host", default="127.0.0.1")
    u.add_argument("--port", type=int, default=8080)
    u.add_argument("--open", action="store_true")
    u.set_defaults(func=cmd_ui)

    e = sub.add_parser("export", help="dump flows to JSONL/JSON for offline analysis")
    e.add_argument("--db", default="capture.db")
    e.add_argument("-o", "--output", help="write to file instead of stdout")
    e.add_argument("--format", choices=["jsonl", "json"], default="jsonl")
    e.add_argument("--max-chunk", type=int, default=256 * 1024)
    e.set_defaults(func=cmd_export)

    ls = sub.add_parser("list", help="list processes")
    ls.add_argument("-f", "--filter", help="substring of process name/path")
    ls.add_argument("-n", "--limit", type=int, default=60)
    ls.set_defaults(func=cmd_list)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        parser.print_help()
        return 2
    return args.func(args)
