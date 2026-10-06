"""Operator page for turning lab feeds on and off."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .feeds import DEFAULTS, LABELS, NOTES, messages, send

GUI = Path(__file__).with_name("gui") / "index.html"
HOST = "127.0.0.1"
PORT = 8770


class Bench:
    def __init__(self):
        self.started = time.monotonic()
        self.interval = 5.0
        self.feeds = {
            feed_id: {"enabled": False, "target": target, "last": "off"}
            for feed_id, target in DEFAULTS.items()
        }
        self._lock = threading.Lock()

    def elapsed(self) -> float:
        return max(0.0, time.monotonic() - self.started)

    def tick(self):
        elapsed = self.elapsed()
        payloads = messages(elapsed)
        with self._lock:
            chosen = [
                (feed_id, row["target"])
                for feed_id, row in self.feeds.items()
                if row["enabled"]
            ]
        for feed_id, target in chosen:
            mode, payload = payloads[feed_id]
            try:
                send(target, mode, payload)
                status = "sent"
            except OSError as exc:
                status = str(exc)[:180]
            with self._lock:
                self.feeds[feed_id]["last"] = status

    def state(self) -> dict:
        with self._lock:
            rows = []
            for feed_id, row in self.feeds.items():
                rows.append(
                    {
                        "id": feed_id,
                        "label": LABELS[feed_id],
                        "note": NOTES[feed_id],
                        "enabled": row["enabled"],
                        "target": row["target"],
                        "last": row["last"],
                    }
                )
            return {"ok": True, "interval": self.interval, "feeds": rows}

    def set_feed(self, feed_id: str, enabled: bool, target: str):
        with self._lock:
            row = self.feeds.get(feed_id)
            if row is None:
                return {"ok": False, "error": "unknown feed"}
            row["enabled"] = bool(enabled)
            if target:
                row["target"] = target.strip()
            row["last"] = "on" if row["enabled"] else "off"
        if enabled:
            self.tick()
        return self.state()

    def set_interval(self, seconds: float):
        with self._lock:
            self.interval = min(60.0, max(1.0, float(seconds)))
        return self.state()


def _loop(bench: Bench, stop: threading.Event):
    while not stop.is_set():
        with bench._lock:
            wait = bench.interval
        if stop.wait(wait):
            return
        try:
            bench.tick()
        except Exception:
            continue


def make_handler(bench: Bench):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def _json(self, code, body):
            raw = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _read(self):
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def do_GET(self):
            path = urlparse(self.path).path
            if path in ("/", "/gui"):
                raw = GUI.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            if path == "/api/state":
                self._json(200, bench.state())
                return
            self._json(404, {"ok": False, "error": "not found"})

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                body = self._read()
            except (ValueError, json.JSONDecodeError):
                self._json(400, {"ok": False, "error": "bad body"})
                return
            if path == "/api/feed":
                self._json(200, bench.set_feed(body.get("id") or "", bool(body.get("enabled")), body.get("target") or ""))
                return
            if path == "/api/interval":
                self._json(200, bench.set_interval(body.get("seconds") or 5))
                return
            self._json(404, {"ok": False, "error": "not found"})

    return Handler


def serve(port: int = PORT) -> ThreadingHTTPServer:
    bench = Bench()
    server = ThreadingHTTPServer((HOST, port), make_handler(bench))
    server.bench = bench
    stop = threading.Event()
    threading.Thread(target=_loop, args=(bench, stop), daemon=True).start()
    server.bench_stop = stop
    return server
