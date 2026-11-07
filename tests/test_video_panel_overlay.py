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
    panel.current_request = None
    panel.draft = None
    panel.notice = None
    panel.close_sent = False
    panel.offline = False
    panel.close_intent = None
    panel.state = None
    panel.window = SimpleNamespace(hide=Mock())
    panel.apply_button = Mock()
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


def test_poll_keeps_selection_and_sends_only_after_matching_reply(overlay):
    overlay.state = state()
    overlay.inflight = True
    overlay._choose("4:3", False)
    assert overlay.draft == ("4:3", False)
    overlay._request.assert_not_called()
    overlay._received(state(), False)
    assert overlay._request.call_args.args[0]["mode"] == "4:3"


def test_rapid_selection_coalesces_after_confirmed_choice(overlay):
    overlay.state = state()
    overlay.inflight = True
    overlay.current_request = {"action": "choose", "revision": 4, "mode": "4:3", "mirror": False}
    overlay._choose("16:9", True)
    overlay._received(state(revision=5, mode="4:3"), False)
    assert overlay._request.call_args.args[0] == {
        "action": "choose",
        "instance": "a" * 32,
        "revision": 5,
        "mode": "16:9",
        "mirror": True,
    }


@pytest.mark.parametrize(
    "change",
    [
        {"revision": 5},
        {"opening": "c" * 32},
        {"instance": "d" * 32},
        {"available": False},
        {"visible": False},
    ],
)
def test_poll_changed_fence_discards_draft(overlay, change):
    overlay.state = state()
    overlay.draft = ("4:3", False)
    overlay._received(state(**change), False)
    assert overlay.draft is None
    overlay._request.assert_not_called()
    assert overlay.notice


def test_new_opening_discards_draft_without_claiming_video_changed(overlay):
    overlay.state = state()
    overlay.draft = ("4:3", False)
    overlay._received(state(opening="c" * 32), False)
    assert overlay.draft is None
    assert overlay.notice == "Выбор не сохранён. Проверьте настройки заново."
    overlay._request.assert_not_called()


def test_lost_choice_is_not_replayed(overlay):
    overlay.state = state()
    overlay.draft = ("16:9", True)
    overlay.current_request = {"action": "choose"}
    overlay._received(None, True)
    overlay._received(state(revision=5, mode="4:3"), False)
    overlay._request.assert_not_called()
    assert overlay.draft is None


def test_close_during_poll_discards_selection_and_is_fenced(overlay):
    overlay.state = state()
    overlay.inflight = True
    overlay.draft = ("4:3", False)
    overlay._close(None)
    overlay._received(state(opening="c" * 32), False)
    overlay._request.assert_not_called()
    assert overlay.draft is None


def test_lost_close_is_not_replayed(overlay):
    overlay.state = state()
    overlay.close_intent = ("a" * 32, "b" * 32)
    overlay.close_sent = True
    overlay.current_request = {"action": "close"}
    overlay._received(None, True)
    overlay._received(state(), False)
    overlay._request.assert_not_called()
    assert overlay.close_intent


def test_request_never_renders_inside_gtk_toggle(overlay):
    import queue

    overlay.state = state()
    overlay.jobs = queue.Queue(maxsize=1)
    overlay._request = overlay.__class__._request.__get__(overlay)
    overlay._choose("4:3", False)
    overlay._render.assert_not_called()
    assert overlay.jobs.get_nowait()[0]["mode"] == "4:3"


def test_poll_render_keeps_controls_enabled_and_draft(overlay):
    overlay.state = state()
    overlay.inflight = True
    overlay.draft = ("4:3", True)
    overlay.rendering = False
    overlay.window = SimpleNamespace(hide=Mock(), get_visible=Mock(return_value=True))
    overlay.choices = {mode: Mock() for mode in ("original", "4:3", "16:9")}
    overlay.mirror = Mock()
    overlay.status = Mock()
    overlay.apply_button = Mock()
    overlay.close_button = Mock()
    overlay._render = overlay.__class__._render.__get__(overlay)
    overlay._render()
    overlay.choices["4:3"].set_active.assert_called_once_with(True)
    overlay.mirror.set_active.assert_called_once_with(True)
    for button in overlay.choices.values():
        button.set_sensitive.assert_called_once_with(True)
    overlay.apply_button.set_sensitive.assert_called_once_with(False)
    overlay.close_button.set_sensitive.assert_called_once_with(True)


@pytest.mark.parametrize("choice", [False, True])
def test_delayed_request_disables_apply_without_rendering(overlay, choice):
    import queue

    overlay.state = state()
    overlay.jobs = queue.Queue(maxsize=1)
    overlay._request = overlay.__class__._request.__get__(overlay)
    if choice:
        overlay._choose("4:3", False)
    else:
        overlay.tick()
    overlay.apply_button.set_sensitive.assert_called_once_with(False)
    overlay._render.assert_not_called()
    overlay._apply(None)
    assert overlay.jobs.qsize() == 1


def test_failed_poll_recovers_and_reopen_has_current_status(overlay):
    overlay.state = state()
    overlay._received(None, True)
    assert overlay.offline
    overlay._received(state(), False)
    assert not overlay.offline
    assert overlay.notice is None
    overlay._received(state(visible=False, revision=5), False)
    overlay._received(state(opening="c" * 32, revision=6, status="completed"), False)
    assert overlay.notice is None


def test_failed_write_notice_survives_recovery_but_not_new_opening(overlay):
    overlay.state = state()
    overlay.current_request = {"action": "apply"}
    overlay._received(None, True)
    notice = overlay.notice
    assert notice
    overlay._received(state(revision=5, status="unconfirmed"), False)
    assert overlay.notice == notice
    overlay._received(state(visible=False, revision=6), False)
    overlay._received(state(opening="c" * 32, revision=7, status="choose"), False)
    assert overlay.notice is None


def test_delayed_poll_reply_reenables_apply(overlay):
    import queue

    overlay.state = state()
    overlay.rendering = False
    overlay.jobs = queue.Queue(maxsize=1)
    overlay.window = SimpleNamespace(hide=Mock(), get_visible=Mock(return_value=True))
    overlay.choices = {mode: Mock() for mode in ("original", "4:3", "16:9")}
    overlay.mirror = Mock()
    overlay.status = Mock()
    overlay.close_button = Mock()
    overlay._request = overlay.__class__._request.__get__(overlay)
    overlay._render = overlay.__class__._render.__get__(overlay)
    overlay.tick()
    overlay.apply_button.set_sensitive.assert_called_with(False)
    overlay._received(state(), False)
    overlay.apply_button.set_sensitive.assert_called_with(True)


def test_apply_disables_choices_without_render_and_supersedes_old_notice(overlay):
    import queue

    overlay.state = state()
    overlay.notice = "Предыдущий запрос не подтверждён."
    overlay.jobs = queue.Queue(maxsize=1)
    overlay.choices = {mode: Mock() for mode in ("original", "4:3", "16:9")}
    overlay.mirror = Mock()
    overlay.status = Mock()
    overlay._request = overlay.__class__._request.__get__(overlay)
    overlay._apply(None)
    assert overlay.notice is None
    overlay.status.set_text.assert_called_once_with("Применяем настройки…")
    for button in overlay.choices.values():
        button.set_sensitive.assert_called_once_with(False)
        button.set_active.assert_not_called()
    overlay.mirror.set_sensitive.assert_called_once_with(False)
    overlay.mirror.set_active.assert_not_called()
    overlay._render.assert_not_called()
    assert overlay.jobs.get_nowait()[0] == {
        "action": "apply",
        "instance": "a" * 32,
        "revision": 4,
    }
    overlay._choose("4:3", True)
    assert overlay.draft is None


def test_apply_result_supersedes_old_notice_and_failure_reports_new_uncertainty(overlay):
    import queue

    overlay.state = state()
    overlay.notice = "Старое сообщение"
    overlay.jobs = queue.Queue(maxsize=1)
    overlay.window = SimpleNamespace(hide=Mock(), get_visible=Mock(return_value=True))
    overlay.rendering = False
    overlay.choices = {mode: Mock() for mode in ("original", "4:3", "16:9")}
    overlay.mirror = Mock()
    overlay.status = Mock()
    overlay.close_button = Mock()
    overlay._request = overlay.__class__._request.__get__(overlay)
    overlay._render = overlay.__class__._render.__get__(overlay)
    overlay._apply(None)
    overlay.jobs.get_nowait()
    overlay._received(state(revision=5, status="completed"), False)
    overlay.status.set_text.assert_called_with("Запрос выполнен. Проверьте изображение.")
    for button in overlay.choices.values():
        button.set_sensitive.assert_called_with(True)
    overlay._apply(None)
    overlay.jobs.get_nowait()
    overlay._received(None, True)
    assert overlay.notice == "Не удалось подтвердить запрос. Проверьте настройки заново."


def test_poll_failure_with_draft_warns_after_recovery_without_replay(overlay):
    overlay.state = state()
    overlay.inflight = True
    overlay._choose("4:3", True)
    assert overlay.draft == ("4:3", True)
    overlay._received(None, True)
    assert overlay.draft is None
    assert overlay.offline
    assert overlay.notice == "Выбор не сохранён. Проверьте настройки заново."
    overlay._received(state(), False)
    assert not overlay.offline
    assert overlay.notice == "Выбор не сохранён. Проверьте настройки заново."
    overlay._request.assert_not_called()
    overlay._received(state(opening="c" * 32, revision=5), False)
    assert overlay.notice is None
    overlay._request.assert_not_called()
