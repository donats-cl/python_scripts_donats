import json
import os
import tempfile
import unittest

from readnet.store import Store, to_jsonl


class TestStore(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.store = Store(self.path, pid=42, process="demo.exe")

    def tearDown(self):
        self.store.close()
        try:
            os.unlink(self.path)
            for suffix in ("-wal", "-shm"):
                p = self.path + suffix
                if os.path.exists(p):
                    os.unlink(p)
        except OSError:
            pass

    def test_flow_and_chunks(self):
        self.store.upsert_flow("f1", {"proto": "tcp", "laddr": "127.0.0.1", "lport": 5555,
                                      "raddr": "1.1.1.1", "rport": 80, "source": "socket"})
        self.store.add_chunk("f1", "out", "socket", b"GET / HTTP/1.1\r\nHost: a\r\n\r\n")
        self.store.add_chunk("f1", "in", "socket", b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
        self.store.end_flow("f1")
        self.store.flush()

        flows = self.store.flows()
        self.assertEqual(len(flows), 1)
        self.assertEqual(flows[0]["out_chunks"], 1)
        self.assertEqual(flows[0]["out_bytes"], 27)

        detail = self.store.flow_detail("f1")
        self.assertEqual(detail["remote_addr"], "1.1.1.1")
        self.assertEqual(detail["parsed"]["request_count"], 1)
        self.assertEqual(detail["parsed"]["response_count"], 1)
        self.assertIsNotNone(detail["ended"])
        self.assertEqual(len(detail["chunks"]), 2)

    def test_dns_enrichment(self):
        self.store.upsert_flow("f2", {"proto": "tcp", "raddr": "9.9.9.9", "rport": 443})
        self.store.add_dns("api.example.com", ["9.9.9.9"])
        flows = self.store.flows()
        self.assertEqual(flows[0]["host"], "api.example.com")
        self.assertEqual(self.store.dns()[0]["addrs"], ["9.9.9.9"])

    def test_export(self):
        self.store.upsert_flow("f3", {"proto": "http", "raddr": "h", "rport": 80, "source": "winhttp"})
        self.store.add_chunk("f3", "out", "winhttp", b"GET / HTTP/1.1\r\n\r\n")
        self.store.flush()
        items = self.store.export_flows()
        self.assertEqual(len(items), 1)
        line = to_jsonl(items).strip()
        self.assertEqual(json.loads(line)["id"], "f3")

    def test_stats(self):
        s = self.store.stats()
        self.assertEqual(s["target"]["pid"], 42)
        self.assertEqual(s["flows"], 0)


if __name__ == "__main__":
    unittest.main()
