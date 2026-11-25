"""SQLite persistence for captured flows, raw chunks and DNS lookups."""

from __future__ import annotations

import base64
import json
import sqlite3
import threading
import time
from typing import Any, Iterable

from .http_parse import parse_flow_chunks

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS flows (
    id          TEXT PRIMARY KEY,
    pid         INTEGER,
    process     TEXT,
    proto       TEXT,
    local_addr  TEXT,
    local_port  INTEGER,
    remote_addr TEXT,
    remote_port INTEGER,
    host        TEXT,
    source      TEXT,
    started     REAL,
    ended       REAL,
    out_bytes   INTEGER DEFAULT 0,
    in_bytes    INTEGER DEFAULT 0,
    out_chunks  INTEGER DEFAULT 0,
    in_chunks   INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_flows_started ON flows(started DESC);
CREATE INDEX IF NOT EXISTS ix_flows_remote  ON flows(remote_addr);
CREATE TABLE IF NOT EXISTS chunks (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    flow_id   TEXT NOT NULL,
    ts        REAL,
    dir       TEXT,
    source    TEXT,
    size      INTEGER,
    truncated INTEGER DEFAULT 0,
    data      BLOB
);
CREATE INDEX IF NOT EXISTS ix_chunks_flow ON chunks(flow_id, id);
CREATE TABLE IF NOT EXISTS dns (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    ts    REAL,
    pid   INTEGER,
    host  TEXT,
    addrs TEXT
);
CREATE INDEX IF NOT EXISTS ix_dns_host ON dns(host);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


class Store:
    def __init__(self, path: str, pid: int | None = None, process: str | None = None):
        self.path = path
        self.pid = pid
        self.process = process
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False, timeout=15)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)
        self._dirty = 0
        self._last_commit = time.time()
        if pid is not None:
            self._db.execute(
                "INSERT INTO meta(key, value) VALUES('target', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (json.dumps({"pid": pid, "process": process, "started": time.time()}),),
            )
            self._db.commit()

    # ------------------------------------------------------------------ write
    def set_target(self, pid: int, process: str | None, **extra) -> None:
        payload = {"pid": pid, "process": process, "started": time.time()}
        payload.update(extra)
        with self._lock:
            self._db.execute(
                "INSERT INTO meta(key, value) VALUES('target', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (json.dumps(payload),),
            )
            self._db.commit()

    def upsert_flow(self, fid: str, data: dict) -> None:
        with self._lock:
            self._db.execute(
                """
                INSERT INTO flows(id, pid, process, proto, local_addr, local_port,
                                  remote_addr, remote_port, host, source, started)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    local_addr  = COALESCE(NULLIF(excluded.local_addr, ''), flows.local_addr),
                    local_port  = CASE WHEN excluded.local_port > 0 THEN excluded.local_port ELSE flows.local_port END,
                    remote_addr = COALESCE(NULLIF(excluded.remote_addr, ''), flows.remote_addr),
                    remote_port = CASE WHEN excluded.remote_port > 0 THEN excluded.remote_port ELSE flows.remote_port END,
                    host        = COALESCE(excluded.host, flows.host)
                """,
                (
                    fid, self.pid, self.process, data.get("proto", "tcp"),
                    data.get("laddr", ""), data.get("lport", 0),
                    data.get("raddr", ""), data.get("rport", 0),
                    data.get("host"), data.get("source", "socket"),
                    time.time(),
                ),
            )
            self._maybe_commit()

    def add_chunk(self, fid: str, direction: str, source: str,
                  data: bytes, size: int | None = None, truncated: bool = False) -> None:
        size = len(data) if size is None or size < 0 else size
        with self._lock:
            self._db.execute(
                "INSERT INTO chunks(flow_id, ts, dir, source, size, truncated, data) VALUES(?,?,?,?,?,?,?)",
                (fid, time.time(), direction, source, size, int(bool(truncated)), data),
            )
            col = "out" if direction == "out" else "in"
            self._db.execute(
                f"UPDATE flows SET {col}_bytes = {col}_bytes + ?, {col}_chunks = {col}_chunks + 1 WHERE id = ?",
                (len(data), fid),
            )
            self._maybe_commit()

    def end_flow(self, fid: str) -> None:
        with self._lock:
            self._db.execute("UPDATE flows SET ended = ? WHERE id = ? AND ended IS NULL", (time.time(), fid))
            self._maybe_commit()

    def add_dns(self, host: str, addrs: Iterable[str]) -> None:
        addrs = [a for a in addrs if a]
        with self._lock:
            self._db.execute(
                "INSERT INTO dns(ts, pid, host, addrs) VALUES(?,?,?,?)",
                (time.time(), self.pid, host, json.dumps(addrs)),
            )
            if addrs:
                marks = ",".join("?" for _ in addrs)
                self._db.execute(
                    f"UPDATE flows SET host = ? WHERE host IS NULL AND remote_addr IN ({marks})",
                    (host, *addrs),
                )
            self._maybe_commit()

    def _maybe_commit(self) -> None:
        self._dirty += 1
        if self._dirty >= 50 or (time.time() - self._last_commit) > 0.8:
            self._db.commit()
            self._dirty = 0
            self._last_commit = time.time()

    def flush(self) -> None:
        with self._lock:
            self._db.commit()
            self._dirty = 0

    def close(self) -> None:
        with self._lock:
            try:
                self.flush()
                self._db.close()
            except Exception:
                pass

    # ------------------------------------------------------------------- read
    def _rows(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._db.execute(sql, args).fetchall())

    def stats(self) -> dict:
        with self._lock:
            flows = self._db.execute("SELECT COUNT(*) FROM flows").fetchone()[0]
            chunks = self._db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            dns = self._db.execute("SELECT COUNT(*) FROM dns").fetchone()[0]
            size = self._db.execute("SELECT COALESCE(SUM(size),0) FROM chunks").fetchone()[0]
            meta = self._db.execute("SELECT value FROM meta WHERE key='target'").fetchone()
        return {
            "db": self.path,
            "flows": flows,
            "chunks": chunks,
            "dns": dns,
            "bytes": size,
            "target": json.loads(meta["value"]) if meta else None,
        }

    def flows(self, limit: int = 500, query: str | None = None) -> list[dict]:
        sql = "SELECT * FROM flows"
        args: list[Any] = []
        if query:
            q = f"%{query}%"
            sql += (" WHERE process LIKE ? OR remote_addr LIKE ? OR host LIKE ?"
                    " OR local_addr LIKE ? OR proto LIKE ? OR id LIKE ?")
            args = [q] * 6
        sql += " ORDER BY started DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self._rows(sql, tuple(args))]

    def dns(self, limit: int = 300) -> list[dict]:
        rows = self._rows("SELECT * FROM dns ORDER BY id DESC LIMIT ?", (limit,))
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["addrs"] = json.loads(d["addrs"] or "[]")
            except Exception:
                d["addrs"] = []
            out.append(d)
        return out

    def flow_chunks(self, fid: str, max_chunk: int = 256 * 1024, max_chunks: int = 2000) -> list[dict]:
        rows = self._rows(
            "SELECT id, ts, dir, source, size, truncated, data FROM chunks WHERE flow_id = ? ORDER BY id LIMIT ?",
            (fid, max_chunks + 1),
        )
        too_many = len(rows) > max_chunks
        out = []
        for r in rows[:max_chunks]:
            data = r["data"] or b""
            cut = data[:max_chunk]
            out.append({
                "id": r["id"], "ts": r["ts"], "dir": r["dir"], "source": r["source"],
                "size": r["size"], "truncated": bool(r["truncated"]) or len(cut) < len(data),
                "b64": base64.b64encode(cut).decode("ascii"),
            })
        if too_many:
            out.append({"id": -1, "ts": 0, "dir": "", "source": "", "size": 0,
                        "truncated": True, "b64": "", "note": f"list cut at {max_chunks} chunks"})
        return out

    def flow_detail(self, fid: str, max_chunk: int = 256 * 1024) -> dict | None:
        rows = self._rows("SELECT * FROM flows WHERE id = ?", (fid,))
        if not rows:
            return None
        flow = dict(rows[0])
        chunks = self.flow_chunks(fid, max_chunk=max_chunk)
        raw: dict[tuple[str, str], list[bytes]] = {}
        for c in chunks:
            if c["id"] < 0 or not c["b64"]:
                continue
            key = (c["dir"], c["source"])
            raw.setdefault(key, []).append(base64.b64decode(c["b64"]))

        parsed = None
        best_score = -1
        for source in ("winhttp", "schannel", "socket"):
            outs = raw.get(("out", source))
            ins = raw.get(("in", source))
            if not outs and not ins:
                continue
            try:
                candidate = parse_flow_chunks(outs or [], ins or [])
            except Exception:
                continue
            score = candidate["request_count"] + candidate["response_count"]
            candidate["parsed_source"] = source
            if score > best_score:
                best_score = score
                parsed = candidate
        if parsed is None:
            parsed = {"exchanges": [], "request_count": 0, "response_count": 0, "parsed_source": None}

        dns = self._rows("SELECT host, addrs FROM dns WHERE ? != '' AND addrs LIKE ? ORDER BY id DESC LIMIT 10",
                         (flow.get("remote_addr") or "", f"%{flow.get('remote_addr')}%"))
        hosts = []
        for r in dns:
            if r["host"] not in hosts:
                hosts.append(r["host"])

        flow["hosts"] = hosts
        flow["parsed"] = parsed
        flow["chunks"] = chunks
        return flow

    def get_meta(self) -> dict:
        return self.stats()

    # ----------------------------------------------------------------- export
    def export_flows(self, max_chunk: int = 256 * 1024) -> list[dict]:
        out = []
        for f in self.flows(limit=100000):
            detail = self.flow_detail(f["id"], max_chunk=max_chunk)
            if detail:
                out.append(detail)
        return out


def to_jsonl(items: list[dict]) -> str:
    return "\n".join(json.dumps(i, ensure_ascii=False, default=str) for i in items) + "\n"
