import socket


class URL:
    def __init__(self, url: str):
        self.scheme, url = url.split("://", 1)
        assert self.scheme == "http"
        url += "/" if not "/" in url else ""
        self.host, url = url.split("/", 1)
        self.path = "/" + url

    def request(self):
        s: socket.socket = socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP
        )
        s.connect((self.host, 80))

        req = f"GET {self.path} HTTP/1.0\r\nHost: {self.host}\r\n\r\n"
        s.send(req.encode('utf-8'))

        res = s.makefile("r", encoding='utf-8', newline='\r\n')
        statusline = res.readline()
        version, status, expl = statusline.split(" ", 2)
        # print(statusline)
        res_headers = {}
        while True:
            line = res.readline()
            if line == "\r\n": break
            header, value = line.split(":", 1)
            res_headers[header.casefold()] = value.strip()

        assert "transfer-encoding" not in res_headers
        assert "content-encoding" not in res_headers

        content = res.read()
        s.close()
        return content

def show(body):
    in_tag = False
    for c in body:
        if c == "<":
            in_tag = True
        elif c == ">":
            in_tag = False
        elif not in_tag:
            print(c, end="")

if __name__ == '__main__':
    url: URL = URL("http://browser.engineering/http.html#displaying-the-html")
    cont = url.request()
    print(cont)
    show(cont)
