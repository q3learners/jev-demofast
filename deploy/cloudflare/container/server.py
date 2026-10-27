"""The hosted service's job server, inside the container: one demo at a time, from a public URL and a prompt.

The Worker in front of it (deploy/cloudflare/src/worker.js) handles who may use it; this server only runs demos.
  POST /runs {"url", "prompt", "voice"} → {"id"}       409 while another run is going
  GET  /runs/<id>                     → status, log tail, the founder's script, the narration, the verdict
  GET  /runs/<id>/video               → the MP4
Each run is `jev-demofast demo` in a subprocess (the prompt is one argument; no shell). Addresses that resolve to the
container itself or a private network are refused: the container's own Chrome listens on 127.0.0.1.
"""
import ipaddress
import json
import os
import re
import secrets
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

DATA = os.environ.get("JDF_DATA", "/data/runs")
MAX_SECONDS = int(os.environ.get("JDF_MAX_SECONDS", "600"))
PROMPT_MAX = 500
BODY_MAX = 10_000
VOICE = re.compile(r"^[a-z][a-z-]{1,30}$")
RUN_ID = re.compile(r"^[0-9a-f]{12}$")
LOG_TAIL = 80


class Busy(Exception):
    """Another demo is still running."""


def _resolve(host):
    return [info[4][0] for info in socket.getaddrinfo(host, None)]


def check_url(url, resolve=_resolve):
    """None if the demo may start here; else why not. Public http(s) sites only."""
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        return "use an http or https address"
    try:
        addresses = resolve(u.hostname)
    except (OSError, UnicodeError):
        return f"{u.hostname} doesn't resolve"
    for a in addresses:
        ip = ipaddress.ip_address(a.split("%")[0])
        if not ip.is_global:
            return f"{u.hostname} is a private or local address"
    return None


def check_prompt(prompt):
    if not prompt or not prompt.strip():
        return "say what the demo should show"
    if len(prompt) > PROMPT_MAX:
        return f"keep the prompt under {PROMPT_MAX} characters"
    if prompt.lstrip().startswith("-"):
        return "start the prompt with a word, not '-'"
    return None


def check_voice(voice):
    return None if voice and VOICE.match(voice) else "unknown voice"


def command(prompt, url, voice, work):
    # "--" ends the options: whatever the prompt says, it is the prompt, never a flag such as --index or --music.
    return ["jev-demofast", "demo", "--url", url, "--fresh", "--voice", voice, "--out", os.path.join(work, "demo.mp4"),
            "--", prompt]


def _spawn(cmd, log):
    with open(log, "w") as out:
        return subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)


def _read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return None


class Runs:
    def __init__(self, data=DATA, spawn=_spawn, max_seconds=MAX_SECONDS):
        self.data, self.spawn, self.max_seconds = data, spawn, max_seconds
        self.lock, self.current, self.procs = threading.Lock(), None, {}
        os.makedirs(data, exist_ok=True)

    def start(self, url, prompt, voice):
        with self.lock:
            if self.current and self.procs[self.current].poll() is None:
                raise Busy(self.current)
            rid = secrets.token_hex(6)
            work = os.path.join(self.data, rid)
            os.makedirs(work)
            with open(os.path.join(work, "meta.json"), "w") as f:
                json.dump({"url": url, "prompt": prompt, "voice": voice, "started": time.time()}, f)
            self.procs[rid] = self.spawn(command(prompt, url, voice, work), os.path.join(work, "log.txt"))
            self.current = rid
            threading.Thread(target=self._watch, args=(rid,), daemon=True).start()
            return rid

    def _watch(self, rid):
        """Stop a run that goes over the time limit."""
        proc, deadline = self.procs[rid], time.time() + self.max_seconds
        while proc.poll() is None and time.time() < deadline:
            time.sleep(1)
        if proc.poll() is None and hasattr(proc, "kill"):
            proc.kill()
            with open(os.path.join(self.data, rid, "log.txt"), "a") as f:
                f.write(f"\nstopped: the run went over {self.max_seconds // 60} minutes\n")

    def status(self, rid):
        if not RUN_ID.match(rid or "") or not os.path.isdir(os.path.join(self.data, rid)):
            return None
        work = os.path.join(self.data, rid)
        meta = json.loads(_read(os.path.join(work, "meta.json")) or "{}")
        log = (_read(os.path.join(work, "log.txt")) or "").splitlines()
        proc = self.procs.get(rid)
        code = proc.poll() if proc else -1  # a run from before a restart: its process is gone
        video = os.path.exists(os.path.join(work, "demo.mp4"))
        state = "running" if code is None else "done" if code == 0 and video else "failed"
        verdict = next((line for line in reversed(log) if line.startswith("verified:")), "")
        narration = _read(os.path.join(work, "demo.run", "narration.txt")) or ""
        return {"id": rid, **meta, "status": state, "video": video,
                "verified": verdict.startswith("verified: True") if verdict else None,
                "story": (_read(os.path.join(work, "demo.run", "story.txt")) or "").strip() or None,
                "narration": [m.group(1).strip() for m in re.finditer(r"^\d\d — .*\n(.+)$", narration, re.M)],
                "error": next((line for line in reversed(log) if re.match(r"(blocked|error|stopped):", line)),
                              log[-1] if state == "failed" and log else None),
                "log": log[-LOG_TAIL:]}


class Handler(BaseHTTPRequestHandler):
    runs = None

    def _json(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parts = self.path.strip("/").split("/")
        if parts in ([""], ["ping"], ["health"]):  # Cloudflare's start-up check fetches http://ping/
            return self._json(200, {"ok": True})
        if len(parts) >= 2 and parts[0] == "runs":
            st = self.runs.status(parts[1])
            if st is None:
                return self._json(404, {"error": "no such run"})
            if parts[2:] == ["video"]:
                if not st["video"]:
                    return self._json(404, {"error": "no video yet"})
                path = os.path.join(self.runs.data, parts[1], "demo.mp4")
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(os.path.getsize(path)))
                self.end_headers()
                with open(path, "rb") as f:
                    while chunk := f.read(1 << 16):
                        self.wfile.write(chunk)
                return None
            return self._json(200, st)
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path.rstrip("/") != "/runs":
            return self._json(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._json(400, {"error": "bad Content-Length"})
        if not 0 <= length <= BODY_MAX:
            return self._json(413, {"error": f"send at most {BODY_MAX} bytes"})
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json(400, {"error": "send JSON"})
        url, prompt, voice = str(body.get("url", "")), str(body.get("prompt", "")), str(body.get("voice", "apollo"))
        problem = check_url(url) or check_prompt(prompt) or check_voice(voice)
        if problem:
            return self._json(400, {"error": problem})
        try:
            return self._json(202, {"id": self.runs.start(url, prompt.strip(), voice)})
        except Busy as busy:
            return self._json(409, {"error": "another demo is still recording", "id": str(busy)})

    def log_message(self, fmt, *args):  # one line per request, no bodies
        print(f"{self.command} {self.path} {args[1] if len(args) > 1 else ''}", flush=True)


def main():
    Handler.runs = Runs()
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), Handler).serve_forever()


if __name__ == "__main__":
    main()
