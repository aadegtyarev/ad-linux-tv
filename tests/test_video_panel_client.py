"""The overlay rejects malformed local replies without trusting media data."""

import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "ops/kiosk/video_panel_client.py"
spec = importlib.util.spec_from_file_location("video_panel_client", PATH)
panel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(panel)


def state():
    return {
        "visible": True,
        "instance": "a" * 32,
        "opening": "b" * 32,
        "revision": 2,
        "available": True,
        "busy": False,
        "mode": "4:3",
        "mirror": True,
        "status": "choose",
    }


def test_local_request_uses_only_fixed_loopback_and_header(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def read(self, length):
            assert length == 2049
            return json.dumps(state()).encode()

    sent = []

    def open_request(message, timeout):
        sent.append(message)
        assert timeout == 1
        return Response()

    monkeypatch.setattr(panel.request, "urlopen", open_request)
    assert panel.local_request()["mode"] == "4:3"
    assert sent[0].full_url == panel.URL
    assert sent[0].get_header("Origin") == "http://127.0.0.1:8765"
    assert sent[0].get_header("X-ad-linux-tv-video-panel") == "video-panel-v1"


def test_transition_busy_is_a_valid_panel_status():
    item = state()
    item["status"] = "transition_busy"
    assert panel.validate_state(item)["status"] == "transition_busy"


def test_valid_panel_state_contains_no_media_identity():
    assert panel.validate_state(state()) == state()
    assert "media_id" not in state()


@pytest.mark.parametrize(
    "field,value",
    [
        ("visible", 1),
        ("instance", "bad"),
        ("opening", None),
        ("opening", "a" * 31),
        ("revision", True),
        ("revision", -1),
        ("available", 1),
        ("busy", 0),
        ("mode", "custom"),
        ("mirror", "yes"),
        ("status", "success"),
        ("media_id", "a" * 32),
    ],
)
def test_malformed_panel_state_fails_closed(field, value):
    item = state()
    item[field] = value
    with pytest.raises(panel.PanelUnavailable):
        panel.validate_state(item)


def test_hidden_panel_may_have_no_opening():
    item = state()
    item.update(visible=False, opening=None)
    assert panel.validate_state(item)["visible"] is False


def test_parent_guard_refuses_invalid_parent(monkeypatch):
    for value in ("", "0", "-1", "１２３"):
        monkeypatch.setenv("AD_TV_VIDEO_PANEL_PARENT", value)
        assert panel.bind_parent() is False


def test_parent_guard_checks_syscall_and_parent_identity(monkeypatch):
    class Libc:
        result = 0

        def prctl(self, *_args):
            return self.result

    libc = Libc()
    monkeypatch.setattr(panel.ctypes, "CDLL", lambda *_args, **_kwargs: libc)
    monkeypatch.setattr(panel.os, "getppid", lambda: 123)
    monkeypatch.setenv("AD_TV_VIDEO_PANEL_PARENT", "123")
    assert panel.bind_parent()
    monkeypatch.setenv("AD_TV_VIDEO_PANEL_PARENT", "456")
    assert not panel.bind_parent()
    libc.result = -1
    assert not panel.bind_parent()
