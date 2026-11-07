#!/usr/bin/env python3
"""Synthetic server used only by the private headless Wayland test."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

lock = threading.Lock()
state = {
    "visible": True,
    "instance": "a" * 32,
    "opening": "b" * 32,
    "revision": 1,
    "available": True,
    "busy": False,
    "mode": "original",
    "mirror": False,
    "status": "choose",
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def output(self, status):
        data = json.dumps(state).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def valid(self):
        return (
            self.path == "/api/local-video-panel"
            and self.headers.get("Origin") == "http://127.0.0.1:28765"
            and self.headers.get("X-AD-Linux-TV-Video-Panel") == "video-panel-v1"
        )

    def do_GET(self):
        time.sleep(0.35)
        with lock:
            self.output(200 if self.valid() else 403)

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        print("fixture_received", data.get("action"), flush=True)
        if data.get("action") == "apply":
            print("fixture_apply_started", flush=True)
            time.sleep(0.4)
        else:
            time.sleep(0.55)
        with lock:
            if not self.valid() or data.get("instance") != state["instance"]:
                self.output(403)
                return
            action = data.get("action")
            if action == "choose" and data.get("revision") == state["revision"]:
                state.update(mode=data["mode"], mirror=data["mirror"], status="choose")
            elif action == "apply" and data.get("revision") == state["revision"]:
                state.update(status="completed")
            elif action == "close" and data.get("opening") == state["opening"]:
                state.update(visible=False)
            else:
                self.output(409)
                return
            state["revision"] += 1
            print(
                "fixture_action",
                action,
                "mode",
                state["mode"],
                "mirror",
                state["mirror"],
                flush=True,
            )
            self.output(200)


server = ThreadingHTTPServer(("127.0.0.1", 28765), Handler)
print("fixture_server_ready", flush=True)
server.serve_forever()
