"""Incremental HTTP/1.x stream parser (dependency-free).

One :class:`HttpStream` per direction of one flow.  Feed raw chunks, get back
completed request/response messages.  Tolerates keep-alive, chunked bodies,
Content-Length bodies and read-until-close bodies.
"""

from __future__ import annotations

import base64
import gzip
import json
import zlib

MAX_HEAD = 128 * 1024
MAX_BODY = 8 * 1024 * 1024

METHODS = {
    b"GET", b"POST", b"PUT", b"DELETE", b"HEAD", b"OPTIONS", b"PATCH", b"CONNECT",
    b"TRACE", b"PROPFIND", b"PROPPATCH", b"MKCOL", b"COPY", b"MOVE", b"LOCK",
    b"UNLOCK", b"REPORT", b"SEARCH", b"PRI",
}


class HttpStream:
    def __init__(self, is_request: bool, max_body: int = MAX_BODY):
        self.is_request = is_request
        self.max_body = max_body
        self.buf = bytearray()
        self.state = "head"          # head | body | chunked | eof
        self.cur: dict | None = None
        self.dead = False
        self.garbage = False
        self._remaining = 0
        self._chunk_left = 0
        self._chunk_state = "size"
        self.messages: list[dict] = []

    # ---------------------------------------------------------------- public
    def feed(self, data: bytes) -> list[dict]:
        if self.dead or not data:
            return []
        self.buf += data
        # TLS record?  no point buffering ciphertext as if it were HTTP
        if len(self.buf) >= 3 and self.buf[0] in (0x14, 0x15, 0x16, 0x17) and self.buf[1] == 0x03:
            self.garbage = True
            self.dead = True
            self.buf.clear()
            return []
        self.messages = []
        self._pump()
        return self.messages

    def finish(self) -> list[dict]:
        """Flush a partially received message (connection closed)."""
        out = []
        if self.cur is not None and not self.dead:
            if self.state in ("eof", "body", "chunked"):
                self.cur["complete"] = False
                out.append(self._emit())
                self.state = "head"
            else:
                self.cur = None
        self.messages = out
        return out

    # --------------------------------------------------------------- parsing
    def _pump(self) -> None:
        while not self.dead:
            if self.state == "head":
                idx = self.buf.find(b"\r\n\r\n")
                if idx < 0:
                    if len(self.buf) > MAX_HEAD:
                        self.garbage = True
                        self.dead = True
                    return
                raw = bytes(self.buf[:idx])
                del self.buf[: idx + 4]
                msg = self._parse_head(raw)
                if msg is None:
                    self.garbage = True
                    self.dead = True
                    return
                self.cur = msg
                framing = msg["framing"]
                if framing == "none":
                    self._emit()
                elif framing == "content-length":
                    self._remaining = msg["body_declared"] or 0
                    if self._remaining == 0:
                        self._emit()
                    else:
                        self.state = "body"
                elif framing == "chunked":
                    self.state = "chunked"
                    self._chunk_state = "size"
                else:
                    self.state = "eof"
            elif self.state == "body":
                if not self.buf:
                    return
                take = min(self._remaining, len(self.buf))
                self._append_body(bytes(self.buf[:take]))
                del self.buf[:take]
                self._remaining -= take
                if self._remaining == 0:
                    self._emit()
            elif self.state == "eof":
                if self.buf:
                    self._append_body(bytes(self.buf))
                    self.buf.clear()
                return
            elif self.state == "chunked":
                if self._pump_chunked() != "done":
                    return
                self._emit()
            else:  # pragma: no cover
                return

    def _parse_head(self, raw: bytes) -> dict | None:
        try:
            text = raw.decode("latin-1")
        except Exception:
            return None
        lines = text.split("\r\n")
        if not lines or not lines[0]:
            return None
        first = lines[0]
        msg: dict = {
            "kind": "request" if self.is_request else "response",
            "start_line": first,
            "headers": [],
            "body": b"",
            "body_omitted": 0,
            "complete": True,
        }
        if self.is_request:
            parts = first.split(" ")
            if len(parts) < 2 or parts[0].encode("latin-1", "ignore") not in METHODS:
                return None
            msg["method"] = parts[0]
            msg["target"] = parts[1]
            msg["version"] = parts[2] if len(parts) > 2 else "HTTP/1.0"
        else:
            parts = first.split(" ", 2)
            if not parts[0].startswith("HTTP/"):
                return None
            msg["version"] = parts[0]
            msg["status"] = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
            msg["reason"] = parts[2] if len(parts) > 2 else ""

        hdrs: dict[str, str] = {}
        for line in lines[1:]:
            if not line or ":" not in line:
                continue
            name, _, value = line.partition(":")
            name = name.strip()
            value = value.strip()
            msg["headers"].append([name, value])
            key = name.lower()
            hdrs[key] = (hdrs[key] + ", " + value) if key in hdrs else value
        msg["_hdrs"] = hdrs

        declared = None
        framing = "none"
        te = hdrs.get("transfer-encoding", "").lower()
        if "chunked" in te:
            framing = "chunked"
        elif "content-length" in hdrs:
            try:
                declared = max(0, int(hdrs["content-length"].split(",")[0]))
                framing = "content-length"
            except ValueError:
                framing = "none"
        elif not self.is_request:
            status = msg.get("status", 0)
            if status in (204, 304) or 100 <= status < 200:
                framing = "none"
            else:
                framing = "eof"
        msg["framing"] = framing
        msg["body_declared"] = declared
        msg["headers_dict"] = {k: v for k, v in hdrs.items() if not k.startswith("_")}
        del msg["_hdrs"]
        return msg

    def _pump_chunked(self) -> str:
        while True:
            if self._chunk_state == "size":
                idx = self.buf.find(b"\r\n")
                if idx < 0:
                    if len(self.buf) > 4096:
                        self.dead = True
                        return "error"
                    return "more"
                line = bytes(self.buf[:idx]).split(b";")[0].strip()
                del self.buf[: idx + 2]
                try:
                    size = int(line, 16)
                except ValueError:
                    self.dead = True
                    return "error"
                if size == 0:
                    self._chunk_state = "trailer"
                else:
                    self._chunk_left = size
                    self._chunk_state = "data"
            elif self._chunk_state == "data":
                if not self.buf:
                    return "more"
                take = min(self._chunk_left, len(self.buf))
                self._append_body(bytes(self.buf[:take]))
                del self.buf[:take]
                self._chunk_left -= take
                if self._chunk_left == 0:
                    self._chunk_state = "crlf"
            elif self._chunk_state == "crlf":
                if len(self.buf) < 2:
                    return "more"
                del self.buf[:2]
                self._chunk_state = "size"
            else:  # trailer
                if self.buf.startswith(b"\r\n"):
                    del self.buf[:2]
                    return "done"
                idx = self.buf.find(b"\r\n\r\n")
                if idx >= 0:
                    del self.buf[: idx + 4]
                    return "done"
                if len(self.buf) > MAX_HEAD:
                    self.dead = True
                    return "error"
                return "more"

    def _append_body(self, chunk: bytes) -> None:
        if self.cur is None:
            return
        room = self.max_body - len(self.cur["body"])
        if room <= 0:
            self.cur["body_omitted"] += len(chunk)
            return
        take = chunk[:room]
        self.cur["body"] += take
        self.cur["body_omitted"] += len(chunk) - len(take)

    def _emit(self) -> dict:
        msg = self.cur or {}
        msg.pop("_hdrs", None)
        self.cur = None
        self.state = "head"
        self.messages.append(msg)
        if not self.is_request and msg.get("status") == 200 and msg.get("method") == "CONNECT":
            self.dead = True
        return msg


# ------------------------------------------------------------------ rendering

def decode_body(body: bytes, headers: dict[str, str]) -> tuple[bytes, str | None]:
    enc = headers.get("content-encoding", "").lower()
    try:
        if "gzip" in enc:
            return gzip.decompress(body), "gzip"
        if "deflate" in enc:
            try:
                return zlib.decompress(body), "deflate"
            except zlib.error:
                return zlib.decompress(body, -zlib.MAX_WBITS), "deflate"
    except Exception:
        pass
    return body, None


def render_message(msg: dict, max_bytes: int = 256 * 1024) -> dict:
    """Turn a raw parsed message into a JSON-friendly dict for UI/export."""
    headers = msg.get("headers_dict") or {k.lower(): v for k, v in msg.get("headers", [])}
    raw_body: bytes = msg.get("body") or b""
    body, decoded_with = decode_body(raw_body, headers) if msg.get("complete") else (raw_body, None)
    out = {k: v for k, v in msg.items() if k in (
        "kind", "start_line", "method", "target", "version", "status", "reason",
        "headers", "framing", "body_declared", "complete", "body_omitted",
    )}
    out["headers_dict"] = headers
    out["body_len"] = len(raw_body)
    if msg.get("body_omitted"):
        out["body_truncated"] = True
    if decoded_with:
        out["decoded_with"] = decoded_with

    ctype = headers.get("content-type", "").lower()
    text: str | None = None
    json_obj = None
    if body:
        sample = body[:max_bytes]
        binary = _looks_binary(sample)
        if not binary:
            text = sample.decode("utf-8", "replace")
        if ("json" in ctype) or (not binary and sample.lstrip()[:1] in (b"{", b"[")):
            try:
                json_obj = json.loads(body[: 4 * 1024 * 1024].decode("utf-8", "replace"))
            except Exception:
                json_obj = None
    if text is not None:
        out["body_text"] = text[:max_bytes]
    elif body:
        out["body_b64"] = base64.b64encode(body[:max_bytes]).decode("ascii")
    if json_obj is not None:
        out["body_json"] = json_obj
    return out


def _looks_binary(sample: bytes) -> bool:
    if not sample:
        return False
    if b"\x00" in sample[:2048]:
        return True
    printable = sum(1 for b in sample[:2048] if 9 <= b <= 13 or 32 <= b < 127 or b >= 0xC0)
    return printable / min(len(sample), 2048) < 0.75


def parse_flow_chunks(
    out_chunks: list[bytes],
    in_chunks: list[bytes],
    max_body: int = MAX_BODY,
) -> dict:
    """Parse both directions of a flow and pair request/response by order."""
    req = HttpStream(True, max_body)
    res = HttpStream(False, max_body)
    requests: list[dict] = []
    responses: list[dict] = []
    for c in out_chunks:
        requests.extend(req.feed(c))
    for c in in_chunks:
        responses.extend(res.feed(c))
    requests.extend(req.finish())
    responses.extend(res.finish())

    exchanges = []
    for i in range(max(len(requests), len(responses))):
        item = {"index": i}
        if i < len(requests):
            item["request"] = render_message(requests[i])
        if i < len(responses):
            item["response"] = render_message(responses[i])
        exchanges.append(item)
    return {
        "exchanges": exchanges,
        "request_count": len(requests),
        "response_count": len(responses),
        "garbage": bool(req.garbage and res.garbage),
    }
