#!/usr/bin/env python3
"""Review viewer server (localhost only). The page lives in the skill; the data in OUT_DIR.

Usage: serve.py OUT_DIR [PORT=8099]

GET  /             the viewer (assets/index.html from the skill)
GET  /<path>?ls    directory listing of OUT_DIR/<path> (viewer discovery)
GET  /<path>       files from OUT_DIR (*.review.yaml, fix-*.yaml)
GET  /api/info     {"root", "out_dir", "skill_dir", "listening": a watch.py heartbeat in the last 5 s}
GET  /api/usage    Claude plan usage: {"five_hour": {utilization, resets_at}, "seven_day": {...}}
POST /api/fix      {"key", "path", "mode": autofix|propose|instruct, "commit"} -> fix-queue.yaml
POST /api/skip     {"key"} -> "skipped" in fix-status.yaml
POST /api/reply    {"key", "text"} -> user message in fix-chat.yaml
"""
import functools
import http.server
import json
import os
import re
import sys
import time
import urllib.request
from urllib.parse import urlsplit

ASSETS = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(sys.argv[1])
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8099
QUEUE = os.path.join(OUT, "fix-queue.yaml")
CHAT = os.path.join(OUT, "fix-chat.yaml")
STATUS = os.path.join(OUT, "fix-status.yaml")
HEARTBEAT = os.path.join(OUT, ".listener")
MODES = ("autofix", "propose", "instruct")
KEY = re.compile(r"^[\w.:-]+#\d+$")
HOSTS = {f"localhost:{PORT}", f"127.0.0.1:{PORT}"}
CREDENTIALS = os.path.join(os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR", "~/.claude")), ".credentials.json")
_usage = {"at": 0, "data": None}


def listening():
    try:
        return time.time() - os.path.getmtime(HEARTBEAT) < 5
    except OSError:
        return False


def repo_root():
    d = OUT
    while d != "/":
        if os.path.exists(os.path.join(d, ".git")):
            return d
        d = os.path.dirname(d)
    return os.path.dirname(OUT)


# Same endpoint Claude Code's /usage reads; the token is refreshed on disk by Claude Code.
def usage():
    if time.time() - _usage["at"] < 60 and _usage["data"]:
        return _usage["data"]
    try:
        token = json.load(open(CREDENTIALS))["claudeAiOauth"]["accessToken"]
        req = urllib.request.Request("https://api.anthropic.com/api/oauth/usage", headers={
            "Authorization": f"Bearer {token}", "anthropic-beta": "oauth-2025-04-20"})
        raw = json.load(urllib.request.urlopen(req, timeout=10))
        data = {k: {"utilization": raw[k]["utilization"], "resets_at": raw[k]["resets_at"]}
                for k in ("five_hour", "seven_day") if raw.get(k)}
    except Exception as e:
        return {"error": type(e).__name__}
    _usage.update(at=time.time(), data=data)
    return data


def review_path(path):
    """Repo-relative review yaml under OUT, or ValueError."""
    out = os.path.realpath(OUT)
    full = os.path.realpath(os.path.join(out, path))
    if not (path.endswith(".review.yaml") and full.startswith(out + os.sep) and os.path.isfile(full)):
        raise ValueError
    return os.path.relpath(full, out)


class Handler(http.server.SimpleHTTPRequestHandler):
    # Pins the Host header so a DNS-rebinding page can't reach the API or the data.
    def parse_request(self):
        if not super().parse_request():
            return False
        if self.headers.get("Host") not in HOSTS:
            self.send_error(421, "Use http://localhost:%d/" % PORT)
            return False
        return True

    def send_head(self):
        url = urlsplit(self.path)
        if url.path in ("/", "/index.html") and url.query != "ls":
            self.path = "/index.html"
            self.directory = ASSETS
        path = self.translate_path(url.path)
        if url.query == "ls" and os.path.isdir(path):
            return self.list_directory(path)
        return super().send_head()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        route = urlsplit(self.path).path
        if route == "/api/info":
            return self._json(200, {"root": repo_root(), "out_dir": OUT, "skill_dir": os.path.dirname(ASSETS), "listening": listening()})
        if route == "/api/usage":
            return self._json(200, usage())
        super().do_GET()

    def do_POST(self):
        route = urlsplit(self.path).path
        if route not in ("/api/fix", "/api/reply", "/api/skip"):
            return self._json(404, {"error": "not found"})
        # Queued fixes and replies become code edits, so refuse cross-site posts.
        origin = self.headers.get("Origin", "")
        if origin and urlsplit(origin).netloc != self.headers.get("Host"):
            return self._json(403, {"error": "cross-origin"})
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self._json(415, {"error": "json only"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            if not isinstance(body, dict) or not KEY.match(str(body.get("key", ""))):
                raise ValueError
            if route == "/api/fix":
                mode = body.get("mode", "autofix")
                if mode not in MODES:
                    raise ValueError
                target, entry = QUEUE, {"key": body["key"], "path": review_path(str(body["path"])), "mode": mode,
                                         "commit": body.get("commit", True) is not False}
            elif route == "/api/skip":
                target, entry = STATUS, {"key": body["key"], "status": "skipped", "note": "Skipped by you"}
            else:
                text = str(body["text"]).strip()
                if not text:
                    raise ValueError
                target, entry = CHAT, {"key": body["key"], "from": "user", "text": text}
        except (ValueError, KeyError, TypeError):
            return self._json(400, {"error": "bad body"})
        entry["ts"] = time.time()
        with open(target, "a") as f:
            f.write("- " + json.dumps(entry) + "\n")
        self._json(200, {"ok": entry})

    def _json(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


print(f"http://localhost:{PORT}/  (data: {OUT})", flush=True)
http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(Handler, directory=OUT)).serve_forever()
