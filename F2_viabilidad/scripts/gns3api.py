"""Minimal GNS3 3.0 REST client + IOU console helper for the F2 tests."""
import json, socket, time, urllib.request, re

BASE = "http://127.0.0.1:3082/v3"
_tok = None


def _req(method, path, body=None):
    global _tok
    if _tok is None and not path.startswith("/access"):
        _tok = _req("POST", "/access/users/authenticate",
                    {"username": "admin", "password": "admin"})["access_token"]
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if _tok:
        r.add_header("Authorization", "Bearer " + _tok)
    with urllib.request.urlopen(r, timeout=120) as f:
        txt = f.read()
    return json.loads(txt) if txt else None


get = lambda p: _req("GET", p)
post = lambda p, b=None: _req("POST", p, b if b is not None else {})
put = lambda p, b: _req("PUT", p, b)
delete = lambda p: _req("DELETE", p)


def project(name):
    for p in get("/projects"):
        if p["name"] == name:
            return p
    return None


def nodes(pid):
    return {n["name"]: n for n in get(f"/projects/{pid}/nodes")}


class Console:
    """Raw telnet to an IOU console (GNS3 telnet proxy). Strips IAC sequences."""

    def __init__(self, port, host="127.0.0.1"):
        self.s = socket.create_connection((host, port), timeout=5)
        self.s.settimeout(0.3)
        self.buf = b""

    def _read(self, t):
        end = time.time() + t
        out = b""
        while time.time() < end:
            try:
                d = self.s.recv(65536)
                if not d:
                    break
                out += d
            except socket.timeout:
                pass
        return re.sub(rb"\xff[\xfb-\xfe].|\xff\xfa.*?\xff\xf0", b"", out, flags=re.S).decode(errors="replace")

    def cmd(self, line, timeout=60):
        self.s.sendall(line.encode() + b"\r")
        out, end = "", time.time() + timeout
        while time.time() < end:
            chunk = self._read(0.6)
            out += chunk
            if "--More--" in chunk:
                self.s.sendall(b" ")
                continue
            if chunk == "" and re.search(r"\S+[>#]\s*$", out):
                break
        return out

    def wake(self):
        for _ in range(3):
            self.s.sendall(b"\r")
            o = self._read(1.0)
            if re.search(r"[>#]\s*$", o.strip() + " "):
                return o
        return o

    def close(self):
        self.s.close()
