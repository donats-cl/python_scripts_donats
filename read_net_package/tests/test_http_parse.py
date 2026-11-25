import unittest

from readnet.http_parse import HttpStream, parse_flow_chunks, render_message


def req(raw: bytes):
    s = HttpStream(True)
    return s.feed(raw)


class TestHttpStream(unittest.TestCase):
    def test_simple_request(self):
        msgs = req(b"GET /a?b=1 HTTP/1.1\r\nHost: x\r\n\r\n")
        self.assertEqual(len(msgs), 1)
        m = msgs[0]
        self.assertEqual(m["method"], "GET")
        self.assertEqual(m["target"], "/a?b=1")
        self.assertEqual(m["body"], b"")

    def test_content_length_body_split(self):
        s = HttpStream(True)
        self.assertEqual(s.feed(b"POST /p HTTP/1.1\r\nContent-Length: 5\r\n\r\nhe"), [])
        msgs = s.feed(b"llo")
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["body"], b"hello")

    def test_chunked(self):
        raw = (b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
               b"5\r\nhello\r\n6\r\n world\r\n0\r\n\r\n")
        msgs = HttpStream(False).feed(raw)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["body"], b"hello world")
        self.assertFalse(msgs[0]["body_omitted"])

    def test_keepalive_two_messages(self):
        raw = (b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"
               b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
        msgs = HttpStream(False).feed(raw)
        self.assertEqual([m["status"] for m in msgs], [200, 404])

    def test_read_until_close(self):
        s = HttpStream(False)
        self.assertEqual(s.feed(b"HTTP/1.0 200 OK\r\n\r\npart1"), [])
        msgs = s.finish()
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["body"], b"part1")
        self.assertFalse(msgs[0]["complete"])

    def test_garbage(self):
        s = HttpStream(True)
        self.assertEqual(s.feed(b"\x16\x03\x01\x02\x00" + b"x" * 300), [])
        self.assertTrue(s.garbage or s.dead)

    def test_no_body_statuses(self):
        msgs = HttpStream(False).feed(b"HTTP/1.1 204 No Content\r\n\r\n")
        self.assertEqual(msgs[0]["status"], 204)
        self.assertEqual(msgs[0]["body"], b"")

    def test_render_json(self):
        raw = (b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 9\r\n\r\n"
               b'{"a": 1}\n')
        m = render_message(HttpStream(False).feed(raw)[0])
        self.assertEqual(m["body_json"], {"a": 1})
        self.assertEqual(m["body_len"], 9)

    def test_render_gzip(self):
        import gzip
        body = gzip.compress(b'{"ok":true}')
        raw = (b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nContent-Type: application/json\r\n"
               b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
        m = render_message(HttpStream(False).feed(raw)[0])
        self.assertEqual(m["body_json"], {"ok": True})

    def test_pairing(self):
        out = [b"GET /x HTTP/1.1\r\nHost: h\r\n\r\n"]
        ins = [b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nhi"]
        parsed = parse_flow_chunks(out, ins)
        self.assertEqual(parsed["request_count"], 1)
        self.assertEqual(parsed["response_count"], 1)
        self.assertEqual(parsed["exchanges"][0]["request"]["target"], "/x")
        self.assertEqual(parsed["exchanges"][0]["response"]["body_text"], "hi")


if __name__ == "__main__":
    unittest.main()
