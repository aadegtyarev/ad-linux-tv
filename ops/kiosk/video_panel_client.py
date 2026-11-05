"""Bounded client for the focusless TV video panel's fixed local protocol."""

import ctypes
import json
import os
import re
import signal
from urllib import error, request

URL = "http://127.0.0.1:8765/api/local-video-panel"
HEADERS = {
    "Origin": "http://127.0.0.1:8765",
    "X-AD-Linux-TV-Video-Panel": "video-panel-v1",
}
MODES = frozenset({"original", "4:3", "16:9"})
STATUSES = frozenset({"unavailable", "choose", "changed", "pending", "completed", "unconfirmed"})


class PanelUnavailable(ValueError):
    """The panel must not treat a failed or malformed reply as success."""


def bind_parent():
    """Exit with the TV session even if its shell dies without running its trap."""
    value = os.environ.get("AD_TV_VIDEO_PANEL_PARENT", "")
    if len(value) > 10 or not value.isascii() or not value.isdecimal() or int(value) <= 1:
        return False
    parent = int(value)
    libc = ctypes.CDLL(None, use_errno=True)
    # Linux PR_SET_PDEATHSIG; no elevated privilege or persistent state.
    if libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
        return False
    return os.getppid() == parent


def validate_state(value):
    if not isinstance(value, dict) or set(value) != {
        "visible",
        "instance",
        "opening",
        "revision",
        "available",
        "busy",
        "mode",
        "mirror",
        "status",
    }:
        raise PanelUnavailable("invalid state")
    if (
        any(type(value[key]) is not bool for key in ("visible", "available", "busy", "mirror"))
        or not isinstance(value["instance"], str)
        or not re.fullmatch(r"[0-9a-f]{32}", value["instance"])
        or not (
            value["opening"] is None
            or (
                isinstance(value["opening"], str)
                and re.fullmatch(r"[0-9a-f]{32}", value["opening"])
            )
        )
        or (value["visible"] and value["opening"] is None)
        or type(value["revision"]) is not int
        or value["revision"] < 0
        or not isinstance(value["mode"], str)
        or value["mode"] not in MODES
        or not isinstance(value["status"], str)
        or value["status"] not in STATUSES
    ):
        raise PanelUnavailable("invalid state")
    return dict(value)


def local_request(body=None):
    headers = dict(HEADERS)
    payload = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(body, separators=(",", ":")).encode()
    message = request.Request(URL, data=payload, headers=headers)
    try:
        with request.urlopen(message, timeout=1) as response:
            # The server sends a small fixed DTO; reject oversized data.
            raw = response.read(2049)
            if len(raw) > 2048:
                raise PanelUnavailable("oversized response")
            return validate_state(json.loads(raw))
    except (OSError, ValueError, error.URLError) as exc:
        raise PanelUnavailable("local panel unavailable") from exc
