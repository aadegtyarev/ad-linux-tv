"""Explicit wake and immediate sleep reuse the timer, never real display power."""

import json

from conftest import command_headers, login
from conftest import request as http_request
from test_sleep_timer import PauseQueue, Scheduled

from ad_linux_tv.sleep_timer import DisplaySleepTimer


def timer_fixture(queue=None):
    calls = []
    timer = DisplaySleepTimer(
        queue or PauseQueue(),
        power=lambda enabled: calls.append(enabled) or True,
        browser_audio=lambda: False,
        other_audio=lambda: False,
        clock=lambda: 100,
        schedule=Scheduled,
    )
    return timer, calls


def test_immediate_sleep_is_async_idempotent_and_cancels_countdown():
    timer, calls = timer_fixture()
    timer.set(30)
    countdown = timer.job
    assert timer.sleep_now()["phase"] == "pausing"
    assert countdown.cancelled
    immediate = timer.job
    timer.sleep_now()
    assert timer.job is immediate and not calls
    countdown.callback(*countdown.args)
    assert not calls
    immediate.callback(*immediate.args)
    assert calls == [False]
    assert timer.status()["asleep"]
    timer.sleep_now()
    assert calls == [False]
    assert timer.wake(force=True)
    assert calls == [False, True]
    assert timer.queue.commands == ["player_pause"]


def test_wake_cancels_undispatched_immediate_sleep():
    timer, calls = timer_fixture()
    timer.sleep_now()
    old = timer.job
    assert timer.wake(force=True)
    old.callback(*old.args)
    assert calls == [True] and not timer.queue.commands


def test_explicit_wake_asserts_power_even_with_lost_idle_flag_and_keeps_countdown():
    timer, calls = timer_fixture()
    assert not timer.asleep
    assert timer.wake(force=True)
    assert calls == [True]
    timer.set(15)
    job = timer.job
    generation = timer.generation
    assert timer.wake(force=True)
    assert timer.status()["remaining_seconds"] == 900
    assert timer.generation == generation and timer.job is job
    assert calls == [True, True]
    timer.power = lambda enabled: False
    assert timer.wake(force=True) is False
    assert timer.status()["error"] == "display_unavailable"


def test_cancelled_pause_does_not_dispatch_a_late_probe():
    class CancellingQueue(PauseQueue):
        def result(self, _command):
            assert timer.wake()
            return {"outcome": "failed", "reason": "operation"}

    timer, calls = timer_fixture(CancellingQueue())
    timer.sleep_now()
    job = timer.job
    job.callback(*job.args)
    assert timer.queue.commands == ["player_pause"]
    assert not calls and timer.status()["phase"] == "idle"


def test_immediate_sleep_keeps_output_lit_if_audio_is_unverified():
    timer, calls = timer_fixture()
    timer.other_audio = lambda: True
    timer.sleep_now()
    job = timer.job
    job.callback(*job.args)
    assert not calls and timer.status()["error"] == "audio_active"


def test_timer_http_sleep_wake_strict_dto_and_forced_output(monkeypatch, request):
    timer, calls = timer_fixture()
    monkeypatch.setattr("ad_linux_tv.server.DisplaySleepTimer", lambda _queue: timer)
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    connection, port = request.getfixturevalue("endpoint")
    _response, data, cookie = login(connection, port)
    headers = command_headers(port, cookie, data["csrf"])
    for action in ({"sleep": 1}, {"wake": 1}, {"sleep": False}, {"sleep": True, "force": True}):
        response, _ = http_request(
            connection, "POST", "/api/display-timer", json.dumps(action), headers
        )
        assert response.status == 400
    response, _ = http_request(connection, "POST", "/api/display-timer", '{"wake":true}', headers)
    assert response.status == 200 and calls == [True]
    response, payload = http_request(
        connection, "POST", "/api/display-timer", '{"sleep":true}', headers
    )
    assert response.status == 202 and json.loads(payload)["phase"] == "pausing"
    assert calls == [True]
