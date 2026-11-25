'use strict';
/*
 * readnet agent: in-process (same-user) traffic sensor.
 *
 * Levels:
 *   socket   ws2_32 send/recv/sendto/recvfrom/WSASend/WSARecv -> raw bytes (may be TLS ciphertext)
 *   schannel EncryptMessage/DecryptMessage                    -> TLS plaintext
 *   winhttp  WinHttpOpenRequest/SendRequest/ReadData/WriteData -> HTTP(S) plaintext at API level
 *   dns      getaddrinfo/GetAddrInfoW                         -> host -> IP map
 *
 * Python injects globalThis.__READNET_CFG__ = {maxChunk, sources:{...}} before load.
 */

const DEFAULT_CFG = {
  maxChunk: 1024 * 1024,
  sources: { socket: true, schannel: true, winhttp: true, dns: true },
};
const CFG = Object.assign({}, DEFAULT_CFG, globalThis.__READNET_CFG__ || {});
CFG.sources = Object.assign({}, DEFAULT_CFG.sources, (globalThis.__READNET_CFG__ || {}).sources || {});

const PTR = Process.pointerSize;
const WSABUF_SIZE = PTR === 8 ? 16 : 8;
const SECBUFFER_SIZE = PTR === 8 ? 16 : 12;
const ADDRINFO_OFF = PTR === 8
  ? { family: 4, addrlen: 16, addr: 32, next: 40 }
  : { family: 4, addrlen: 16, addr: 24, next: 28 };

const sockets = new Map();        // handle string -> flow
const threadLastFlow = new Map(); // tid -> flow
const pendingTls = new Map();     // tid -> {dir, chunks:[ArrayBuffer]}
const winhttpConn = new Map();    // hConnect -> {host, port}
const winhttpReq = new Map();     // hRequest -> {flow, server, port, verb, path}
let seq = 0;

function log(msg, level) {
  send({ type: 'log', level: level || 'info', msg: String(msg) });
}

function resolveExport(modName, name) {
  try {
    const m = Process.findModuleByName(modName);
    if (m) {
      const a = m.findExportByName(name);
      if (a) return a;
    }
  } catch (e) { /* ignore */ }
  try { return Module.getGlobalExportByName(name); } catch (e) { /* ignore */ }
  return null;
}

function hook(modName, name, callbacks) {
  const addr = resolveExport(modName, name);
  if (!addr) return false;
  try {
    Interceptor.attach(addr, callbacks);
    return true;
  } catch (e) {
    log('hook ' + modName + '!' + name + ' failed: ' + e, 'warn');
    return false;
  }
}

/* ---------- addressing ---------- */

function ipv6ToString(bytes) {
  const groups = [];
  for (let i = 0; i < 16; i += 2) groups.push((bytes[i] << 8) | bytes[i + 1]);
  let best = -1, bestLen = 0, cur = -1, curLen = 0;
  for (let i = 0; i < 8; i++) {
    if (groups[i] === 0) {
      if (cur < 0) { cur = i; curLen = 1; } else curLen++;
      if (curLen > bestLen) { best = cur; bestLen = curLen; }
    } else { cur = -1; curLen = 0; }
  }
  const hex = groups.map(g => g.toString(16));
  if (bestLen < 2) return hex.join(':');
  return hex.slice(0, best).join(':') + '::' + hex.slice(best + bestLen).join(':');
}

function readSockaddr(ptr, len) {
  if (!ptr || ptr.isNull() || len < 2) return null;
  try {
    const family = ptr.readU16();
    if (family === 2 && len >= 8) { // AF_INET
      return {
        family: 'ipv4',
        addr: [ptr.add(4).readU8(), ptr.add(5).readU8(), ptr.add(6).readU8(), ptr.add(7).readU8()].join('.'),
        port: (ptr.add(2).readU8() << 8) | ptr.add(3).readU8(),
      };
    }
    if (family === 23 && len >= 24) { // AF_INET6
      const raw = ptr.add(8).readByteArray(16);
      return {
        family: 'ipv6',
        addr: ipv6ToString(new Uint8Array(raw)),
        port: (ptr.add(2).readU8() << 8) | ptr.add(3).readU8(),
      };
    }
  } catch (e) { /* ignore */ }
  return null;
}

function mkFlow(proto, source) {
  return {
    fid: 'f' + (++seq),
    proto: proto || 'tcp',
    laddr: '', lport: 0,
    raddr: '', rport: 0,
    source: source || 'socket',
  };
}

function flowOpen(f) {
  send({
    type: 'flow_open', fid: f.fid, proto: f.proto,
    laddr: f.laddr, lport: f.lport, raddr: f.raddr, rport: f.rport,
    source: f.source,
  });
}

let peerFn = null, localFn = null, addrLookupBusy = false;

function fillAddrs(f, handle) {
  if (addrLookupBusy) return;
  try {
    if (!peerFn) {
      const p = resolveExport('ws2_32.dll', 'getpeername');
      const l = resolveExport('ws2_32.dll', 'getsockname');
      if (!p || !l) return;
      peerFn = new NativeFunction(p, 'int', ['pointer', 'pointer', 'pointer']);
      localFn = new NativeFunction(l, 'int', ['pointer', 'pointer', 'pointer']);
    }
    addrLookupBusy = true;
    const buf = Memory.alloc(32);
    const plen = Memory.alloc(4);
    const s = ptr(handle);
    plen.writeInt(32);
    if (peerFn(s, buf, plen) === 0) {
      const a = readSockaddr(buf, 32);
      if (a) { f.raddr = a.addr; f.rport = a.port; }
    }
    plen.writeInt(32);
    if (localFn(s, buf, plen) === 0) {
      const a = readSockaddr(buf, 32);
      if (a) { f.laddr = a.addr; f.lport = a.port; }
    }
  } catch (e) {
    /* ignore */
  } finally {
    addrLookupBusy = false;
  }
}

function forSocket(handle) {
  let f = sockets.get(handle);
  if (f) return f;
  f = mkFlow('tcp', 'socket');
  sockets.set(handle, f);
  fillAddrs(f, handle);
  flowOpen(f);
  return f;
}

/* ---------- emitting ---------- */

function emitChunk(f, dir, ab, source, realSize) {
  if (!ab || ab.byteLength === 0) return;
  threadLastFlow.set(Process.getCurrentThreadId(), f);
  send({
    type: 'data', fid: f.fid, dir: dir, source: source,
    size: realSize === undefined ? ab.byteLength : realSize,
    truncated: realSize !== undefined && realSize > ab.byteLength,
  }, ab);
}

function emitData(f, dir, bufPtr, len, source) {
  if (len <= 0) return;
  const n = Math.min(len, CFG.maxChunk);
  const ab = bufPtr.readByteArray(n);
  emitChunk(f, dir, ab, source, len);
}

function concatAB(parts) {
  let total = 0;
  for (const p of parts) total += p.byteLength;
  const out = new Uint8Array(total);
  let off = 0;
  for (const p of parts) { out.set(new Uint8Array(p), off); off += p.byteLength; }
  return out.buffer;
}

function wsaParts(lpBuffers, count, total) {
  const parts = [];
  let left = total;
  for (let i = 0; i < count && left > 0; i++) {
    try {
      const base = lpBuffers.add(i * WSABUF_SIZE);
      const len = base.readU32();
      const buf = base.add(PTR === 8 ? 8 : 4).readPointer();
      const n = Math.min(len, left);
      if (n > 0 && !buf.isNull()) {
        const ab = buf.readByteArray(Math.min(n, CFG.maxChunk));
        if (ab) parts.push(ab);
        left -= n;
      }
    } catch (e) { break; }
  }
  return parts;
}

/* ---------- TLS plaintext (Schannel) ---------- */

function collectTls(tid, dir) {
  const p = pendingTls.get(tid);
  if (!p || p.dir !== dir || p.chunks.length === 0) return null;
  pendingTls.delete(tid);
  return p.chunks.length === 1 ? p.chunks[0] : concatAB(p.chunks);
}

function stashTls(dir, ab) {
  if (!ab) return;
  const tid = Process.getCurrentThreadId();
  const p = pendingTls.get(tid);
  if (p && p.dir === dir) p.chunks.push(ab);
  else pendingTls.set(tid, { dir: dir, chunks: [ab] });
}

function readSecBuffers(desc, wantedType) {
  const out = [];
  try {
    const cBuffers = desc.add(4).readU32();
    const pBuffers = desc.add(8).readPointer();
    for (let i = 0; i < cBuffers && i < 8; i++) {
      const b = pBuffers.add(i * SECBUFFER_SIZE);
      const cb = b.readU32();
      const type = b.add(4).readU32();
      const pv = b.add(8).readPointer();
      if (type === wantedType && cb > 0 && !pv.isNull()) out.push({ cb, pv });
    }
  } catch (e) { /* ignore */ }
  return out;
}

function hookTls() {
  const SECBUFFER_DATA = 1;

  hook('sspicli.dll', 'EncryptMessage', {
    onEnter(args) {
      this.ab = null;
      const bufs = readSecBuffers(args[2], SECBUFFER_DATA);
      const parts = [];
      for (const b of bufs) {
        const ab = b.pv.readByteArray(Math.min(b.cb, CFG.maxChunk));
        if (ab) parts.push(ab);
      }
      this.ab = parts.length === 0 ? null : (parts.length === 1 ? parts[0] : concatAB(parts));
    },
    onLeave(ret) {
      if (ret.toInt32() !== 0 || !this.ab) return;
      stashTls('out', this.ab);
      this.ab = null;
    },
  });

  hook('sspicli.dll', 'DecryptMessage', {
    onEnter(args) { this.desc = args[1]; },
    onLeave(ret) {
      if (ret.toInt32() !== 0) return;
      const bufs = readSecBuffers(this.desc, SECBUFFER_DATA);
      const parts = [];
      for (const b of bufs) {
        const ab = b.pv.readByteArray(Math.min(b.cb, CFG.maxChunk));
        if (ab) parts.push(ab);
      }
      if (parts.length === 0) return;
      const ab = parts.length === 1 ? parts[0] : concatAB(parts);
      const f = threadLastFlow.get(Process.getCurrentThreadId());
      if (f) emitChunk(f, 'in', ab, 'schannel', ab.byteLength);
      else stashTls('in', ab);
    },
  });
}

/* ---------- Winsock ---------- */

function hookSockets() {
  hook('ws2_32.dll', 'connect', {
    onEnter(args) {
      this.handle = args[0].toString();
      const sa = readSockaddr(args[1], args[2].toInt32());
      if (!sa) return;
      let f = sockets.get(this.handle);
      if (!f) { f = mkFlow('tcp', 'socket'); sockets.set(this.handle, f); }
      f.raddr = sa.addr;
      f.rport = sa.port;
      fillAddrs(f, this.handle);
      flowOpen(f);
    },
  });

  hook('ws2_32.dll', 'WSAConnect', {
    onEnter(args) {
      this.handle = args[0].toString();
      const sa = readSockaddr(args[1], args[2].toInt32());
      if (!sa) return;
      let f = sockets.get(this.handle);
      if (!f) { f = mkFlow('tcp', 'socket'); sockets.set(this.handle, f); }
      f.raddr = sa.addr;
      f.rport = sa.port;
      flowOpen(f);
    },
  });

  hook('ws2_32.dll', 'send', {
    onEnter(args) {
      this.handle = args[0].toString();
      this.buf = args[1];
      this.len = args[2].toInt32();
    },
    onLeave(ret) {
      const n = ret.toInt32();
      if (n <= 0) return;
      const f = forSocket(this.handle);
      const tls = collectTls(Process.getCurrentThreadId(), 'out');
      if (tls) emitChunk(f, 'out', tls, 'schannel', tls.byteLength);
      emitData(f, 'out', this.buf, n, 'socket');
    },
  });

  hook('ws2_32.dll', 'sendto', {
    onEnter(args) {
      this.handle = args[0].toString();
      this.buf = args[1];
      this.len = args[2].toInt32();
      this.sa = readSockaddr(args[4], args[5].toInt32());
    },
    onLeave(ret) {
      const n = ret.toInt32();
      if (n <= 0) return;
      const f = forSocket(this.handle);
      if (this.sa && (f.raddr === '' || f.rport === 0)) {
        f.proto = 'udp';
        f.raddr = this.sa.addr;
        f.rport = this.sa.port;
      }
      emitData(f, 'out', this.buf, n, 'socket');
    },
  });

  hook('ws2_32.dll', 'recv', {
    onEnter(args) {
      this.handle = args[0].toString();
      this.buf = args[1];
    },
    onLeave(ret) {
      const n = ret.toInt32();
      if (n > 0) emitData(forSocket(this.handle), 'in', this.buf, n, 'socket');
    },
  });

  hook('ws2_32.dll', 'recvfrom', {
    onEnter(args) {
      this.handle = args[0].toString();
      this.buf = args[1];
    },
    onLeave(ret) {
      const n = ret.toInt32();
      if (n > 0) emitData(forSocket(this.handle), 'in', this.buf, n, 'socket');
    },
  });

  hook('ws2_32.dll', 'WSASend', {
    onEnter(args) {
      this.handle = args[0].toString();
      this.bufs = args[1];
      this.count = args[2].toInt32();
      this.sentPtr = args[3];
    },
    onLeave(ret) {
      if (ret.toInt32() !== 0 || this.sentPtr.isNull()) return;
      const sent = this.sentPtr.readU32();
      if (!sent) return;
      const f = forSocket(this.handle);
      const tls = collectTls(Process.getCurrentThreadId(), 'out');
      if (tls) emitChunk(f, 'out', tls, 'schannel', tls.byteLength);
      const parts = wsaParts(this.bufs, this.count, sent);
      if (parts.length) emitChunk(f, 'out', parts.length === 1 ? parts[0] : concatAB(parts), 'socket', sent);
    },
  });

  hook('ws2_32.dll', 'WSARecv', {
    onEnter(args) {
      this.handle = args[0].toString();
      this.bufs = args[1];
      this.count = args[2].toInt32();
      this.recvdPtr = args[3];
    },
    onLeave(ret) {
      if (ret.toInt32() !== 0 || this.recvdPtr.isNull()) return;
      const n = this.recvdPtr.readU32();
      if (!n) return;
      const parts = wsaParts(this.bufs, this.count, n);
      if (parts.length) emitChunk(forSocket(this.handle), 'in', parts.length === 1 ? parts[0] : concatAB(parts), 'socket', n);
    },
  });

  hook('ws2_32.dll', 'closesocket', {
    onEnter(args) {
      const handle = args[0].toString();
      const f = sockets.get(handle);
      if (f) {
        send({ type: 'flow_close', fid: f.fid });
        sockets.delete(handle);
      }
    },
  });
}

/* ---------- WinHTTP ---------- */

function wide(p) {
  try { return p.isNull() ? '' : p.readUtf16String(); } catch (e) { return ''; }
}

function hookWinHttp() {
  hook('winhttp.dll', 'WinHttpConnect', {
    onEnter(args) { this.host = wide(args[1]); this.port = args[2].toInt32(); },
    onLeave(ret) {
      if (ret.isNull()) return;
      winhttpConn.set(ret.toString(), { host: this.host, port: this.port || 80 });
    },
  });

  hook('winhttp.dll', 'WinHttpOpenRequest', {
    onEnter(args) {
      this.conn = args[0].toString();
      this.verb = wide(args[1]) || 'GET';
      this.path = wide(args[2]) || '/';
    },
    onLeave(ret) {
      if (ret.isNull()) return;
      const c = winhttpConn.get(this.conn) || { host: '', port: 0 };
      const f = mkFlow('http', 'winhttp');
      f.raddr = c.host;
      f.rport = c.port;
      flowOpen(f);
      winhttpReq.set(ret.toString(), { f: f, server: c.host, port: c.port, verb: this.verb, path: this.path });
    },
  });

  hook('winhttp.dll', 'WinHttpSendRequest', {
    onEnter(args) {
      this.req = winhttpReq.get(args[0].toString());
      this.headers = wide(args[1]);
      this.bodyPtr = args[3];
      this.bodyLen = args[4].toInt32();
    },
    onLeave(ret) {
      if (ret.toInt32() === 0 || !this.req) return;
      const r = this.req;
      let head = r.verb + ' ' + r.path + ' HTTP/1.1\r\n';
      if (r.server) head += 'Host: ' + r.server + ((r.port && r.port !== 80 && r.port !== 443) ? ':' + r.port : '') + '\r\n';
      if (this.headers) head += this.headers + (this.headers.endsWith('\r\n') ? '' : '\r\n');
      head += '\r\n';
      const parts = [new TextEncoder().encode(head).buffer];
      if (this.bodyLen > 0 && this.bodyPtr && !this.bodyPtr.isNull()) {
        try {
          const ab = this.bodyPtr.readByteArray(Math.min(this.bodyLen, CFG.maxChunk));
          if (ab) parts.push(ab);
        } catch (e) { /* ignore */ }
      }
      emitChunk(r.f, 'out', parts.length === 1 ? parts[0] : concatAB(parts), 'winhttp');
    },
  });

  hook('winhttp.dll', 'WinHttpWriteData', {
    onEnter(args) {
      this.req = winhttpReq.get(args[0].toString());
      this.buf = args[1];
      this.len = args[2].toInt32();
    },
    onLeave(ret) {
      if (ret.toInt32() === 0 || !this.req || this.len <= 0) return;
      emitData(this.req.f, 'out', this.buf, this.len, 'winhttp');
    },
  });

  hook('winhttp.dll', 'WinHttpReadData', {
    onEnter(args) {
      this.req = winhttpReq.get(args[0].toString());
      this.buf = args[1];
      this.gotPtr = args[3];
    },
    onLeave(ret) {
      if (ret.toInt32() === 0 || !this.req || this.gotPtr.isNull()) return;
      const n = this.gotPtr.readU32();
      if (n > 0) emitData(this.req.f, 'in', this.buf, n, 'winhttp');
    },
  });

  hook('winhttp.dll', 'WinHttpCloseHandle', {
    onEnter(args) {
      const h = args[0].toString();
      const r = winhttpReq.get(h);
      if (r) { send({ type: 'flow_close', fid: r.f.fid }); winhttpReq.delete(h); }
      winhttpConn.delete(h);
    },
  });
}

/* ---------- DNS ---------- */

function readAddrInfo(ppResult) {
  const addrs = [];
  try {
    let node = ppResult.readPointer();
    for (let i = 0; i < 12 && !node.isNull(); i++) {
      const family = node.add(ADDRINFO_OFF.family).readS32();
      const addrPtr = node.add(ADDRINFO_OFF.addr).readPointer();
      const addrLen = node.add(ADDRINFO_OFF.addrlen).readU64().toNumber();
      if (!addrPtr.isNull() && (family === 2 || family === 23)) {
        const s = readSockaddr(addrPtr, addrLen || 16);
        if (s) addrs.push(s.addr);
      }
      node = node.add(ADDRINFO_OFF.next).readPointer();
    }
  } catch (e) { /* ignore */ }
  return addrs;
}

function hookDns() {
  hook('ws2_32.dll', 'getaddrinfo', {
    onEnter(args) {
      this.host = args[0].isNull() ? null : args[0].readAnsiString();
      this.pp = args[3];
    },
    onLeave(ret) {
      if (ret.toInt32() !== 0 || !this.host) return;
      send({ type: 'dns', host: this.host, addrs: this.pp.isNull() ? [] : readAddrInfo(this.pp) });
    },
  });

  hook('ws2_32.dll', 'GetAddrInfoW', {
    onEnter(args) {
      this.host = args[0].isNull() ? null : wide(args[0]);
      this.pp = args[3];
    },
    onLeave(ret) {
      if (ret.toInt32() !== 0 || !this.host) return;
      send({ type: 'dns', host: this.host, addrs: this.pp.isNull() ? [] : readAddrInfo(this.pp) });
    },
  });
}

/* ---------- boot ---------- */

if (CFG.sources.socket) hookSockets();
if (CFG.sources.schannel) hookTls();
if (CFG.sources.winhttp) hookWinHttp();
if (CFG.sources.dns) hookDns();

send({ type: 'agent_ready', pid: Process.id, arch: Process.arch });
log('agent ready');
