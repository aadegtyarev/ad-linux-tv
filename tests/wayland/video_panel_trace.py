#!/usr/bin/env python3
"""Trace synthetic widget state while running the actual kiosk panel and client."""

import importlib.util
import os
import signal
import sys
import time
from pathlib import Path

root = Path(os.environ["TEST_ROOT"])
sys.path.insert(0, str(root / "ops/kiosk"))
import video_panel_client  # noqa: E402

# Only redirect the fixed local endpoint; retain the production protocol and timeout.
video_panel_client.URL = "http://127.0.0.1:28765/api/local-video-panel"
video_panel_client.HEADERS["Origin"] = "http://127.0.0.1:28765"
request = video_panel_client.local_request


def delayed_request(body=None):
    # Delay the worker before the actual bounded request, simulating a slow Apply.
    if body and body.get("action") == "apply":
        print("TRACE_APPLY_WAIT", flush=True)
        time.sleep(1.2)
    if body is None:
        print("TRACE_POLL_BEGIN", flush=True)
    result = request(body)
    if body is None:
        print("TRACE_POLL_END", flush=True)
    return result


video_panel_client.local_request = delayed_request
spec = importlib.util.spec_from_file_location(
    "synthetic_video_panel", root / "ops/kiosk/video-panel.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
original = module.VideoPanel._mode_changed
original_request = module.VideoPanel._request
original_received = module.VideoPanel._received


def traced_request(self, body=None):
    before = self.apply_button.get_sensitive()
    original_request(self, body)
    if body is None and self.inflight and self.current_request is None:
        print("TRACE_POLL_REQUEST", int(before), int(self.apply_button.get_sensitive()), flush=True)


def traced_received(self, state, failed):
    poll = self.current_request is None and self.inflight and not self.stopped
    before = self.apply_button.get_sensitive()
    result = original_received(self, state, failed)
    if poll:
        print(
            "TRACE_POLL_RECEIVED",
            int(before),
            int(self.apply_button.get_sensitive()),
            "failed",
            int(failed),
            flush=True,
        )
    return result


module.VideoPanel._request = traced_request
module.VideoPanel._received = traced_received


def traced(self, button, mode):
    real = button.get_active() and not self.rendering
    if real:
        print("TRACE_TOGGLE_BEGIN", mode, "busy", self.inflight, flush=True)
    original(self, button, mode)
    if real:
        print("TRACE_TOGGLE_END", mode, "active", button.get_active(), flush=True)


module.VideoPanel._mode_changed = traced
if not module.bind_parent():
    raise SystemExit("parent unavailable")
panel = module.VideoPanel()
for key, widget in panel.choices.items():
    widget.connect(
        "button-press-event", lambda _w, _e, name=key: print("TRACE_PRESS", name, flush=True)
    )
    widget.connect(
        "button-release-event", lambda _w, _e, name=key: print("TRACE_RELEASE", name, flush=True)
    )


def sample():
    print(
        "TRACE_STATE",
        int(panel.choices["4:3"].get_active()),
        int(panel.choices["4:3"].get_sensitive()),
        int(panel.mirror.get_sensitive()),
        int(panel.apply_button.get_sensitive()),
        panel.status.get_text(),
        flush=True,
    )
    return True


def positions():
    for name, widget in (
        ("choice", panel.choices["4:3"]),
        ("apply", panel.apply_button),
        ("mirror", panel.mirror),
        ("ratio", panel.choices["16:9"]),
    ):
        x, y = widget.translate_coordinates(panel.window, 0, 0)
        allocation = widget.get_allocation()
        width = panel.window.get_allocation().width
        print(
            "TRACE_WIDGET",
            name,
            1280 - 18 - width + x + allocation.width // 2,
            80 + y + allocation.height // 2,
            flush=True,
        )
    return False


module.GLib.timeout_add(100, sample)
module.GLib.timeout_add(900, positions)
module.GLibUnix.signal_add(
    module.GLib.PRIORITY_DEFAULT,
    signal.SIGTERM,
    lambda *_: (module.Gtk.main_quit(), False)[1],
)
try:
    module.Gtk.main()
finally:
    panel.stop()
