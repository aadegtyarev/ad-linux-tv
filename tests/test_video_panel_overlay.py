"""Exercise real overlay control flow with GI and network replaced by inert stubs."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def overlay(monkeypatch):
    gi = ModuleType("gi")
    gi.require_version = Mock()
    repository = ModuleType("gi.repository")
    for name in ("Gdk", "GLib", "GLibUnix", "Gtk", "GtkLayerShell"):
        setattr(repository, name, SimpleNamespace())
    monkeypatch.setitem(sys.modules, "gi", gi)
    monkeypatch.setitem(sys.modules, "gi.repository", repository)
    client = ModuleType("video_panel_client")
    client.bind_parent = Mock()
    client.local_request = Mock()
    monkeypatch.setitem(sys.modules, "video_panel_client", client)
    spec = importlib.util.spec_from_file_location(
        "tv_video_panel_overlay", ROOT / "ops/kiosk/video-panel.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    panel = module.VideoPanel.__new__(module.VideoPanel)
    panel.stopped = False
    panel.inflight = False
    panel.offline = False
    panel.close_intent = None
    panel.state = None
    panel.window = SimpleNamespace(hide=Mock())
    panel._render = Mock()
    panel._request = Mock()
    return panel


def state(**changes):
    value = {
        "visible": True,
        "instance": "a" * 32,
        "opening": "b" * 32,
        "revision": 4,
        "available": True,
        "busy": False,
        "mode": "original",
        "mirror": False,
        "status": "choose",
    }
    value.update(changes)
    return value


def test_close_is_fenced_to_opening_and_does_not_apply(overlay):
    overlay.state = state()
    overlay._close(None)
    overlay.window.hide.assert_called_once()
    overlay._request.assert_called_once_with(
        {"action": "close", "instance": "a" * 32, "opening": "b" * 32}
    )


def test_disconnected_close_retries_only_the_same_opening(overlay):
    overlay.close_intent = ("a" * 32, "b" * 32)
    overlay._received(state(revision=8), False)
    overlay._request.assert_called_once_with(
        {"action": "close", "instance": "a" * 32, "opening": "b" * 32}
    )
    overlay._request.reset_mock()
    overlay._received(state(opening="c" * 32), False)
    assert overlay.close_intent is None
    overlay._request.assert_not_called()


def test_server_restart_invalidates_pending_close(overlay):
    overlay.close_intent = ("a" * 32, "b" * 32)
    overlay._received(state(instance="d" * 32), False)
    assert overlay.close_intent is None
    overlay._request.assert_not_called()


def test_offline_and_stale_signals_never_apply_or_change_choices(overlay):
    for changed in ({"available": False}, {"visible": False}, {"busy": True}):
        overlay.state = state(**changed)
        overlay._choose("4:3", True)
        overlay._apply(None)
    overlay.state = state()
    overlay._received(None, True)
    overlay._choose("4:3", True)
    overlay._apply(None)
    overlay._request.assert_not_called()


def test_late_callback_after_shutdown_does_nothing(overlay):
    overlay.stopped = True
    assert overlay._received(state(), False) is False
    overlay._render.assert_not_called()
    overlay._request.assert_not_called()
