"""Display timer safety and authenticated control."""

import json
from threading import Event, Thread

from conftest import command_headers, login, request

from ad_linux_tv.sleep_timer import DisplaySleepTimer


class Scheduled:
    def __init__(self, _delay, callback, args):
        self.callback = callback
        self.args = args
        self.cancelled = False

    def start(self):
        pass

    def cancel(self):
        self.cancelled = True


class PauseQueue:
    def __init__(self, outcome="completed", reason=None):
        self.outcome = outcome
        self.reason = reason
        self.commands = []

    def push(self, command):
        self.commands.append(command)
        return "pause-id"

    def result(self, _command_id):
        return {"outcome": self.outcome, "reason": self.reason}


def test_timer_pauses_before_output_off_then_wakes_without_resuming():
    queue = PauseQueue()
    power_calls = []
    timer = DisplaySleepTimer(
        queue,
        power=lambda enabled: power_calls.append(enabled) or True,
        browser_audio=lambda: False,
        other_audio=lambda: False,
        clock=lambda: 100,
        schedule=Scheduled,
    )
    assert timer.set(15)["remaining_seconds"] == 900
    assert timer.wake() is True
    assert timer.status()["remaining_seconds"] == 900
    timer.job.callback(*timer.job.args)
    assert queue.commands == ["player_pause"]
    assert power_calls == [False]
    assert timer.status()["asleep"] is True
    assert timer.wake() is True
    assert power_calls == [False, True]
    assert timer.status()["phase"] == "idle"
    assert queue.commands == ["player_pause"]


def test_timer_preserves_lit_output_if_playback_cannot_be_paused():
    queue = PauseQueue("failed", "operation")
    power_calls = []
    timer = DisplaySleepTimer(
        queue,
        power=lambda enabled: power_calls.append(enabled) or True,
        other_audio=lambda: False,
        clock=lambda: 100,
        schedule=Scheduled,
    )
    timer.set(15)
    timer.job.callback(*timer.job.args)
    assert power_calls == []
    assert timer.status()["error"] == "pause_unavailable"
    queue.outcome = "completed"
    timer.other_audio = lambda: True
    timer.set(15)
    timer.job.callback(*timer.job.args)
    assert power_calls == []
    assert timer.status()["error"] == "audio_active"
    queue.outcome = "failed"
    queue.reason = "no_media"
    timer.browser_audio = lambda: True
    timer.set(30)
    timer.job.callback(*timer.job.args)
    assert power_calls == []
    assert timer.status()["error"] == "audio_active"


def test_audible_flag_lag_is_accepted_only_after_player_stops():
    class LagQueue(PauseQueue):
        def result(self, command_id):
            if command_id == "player_pause":
                return {"outcome": "failed", "reason": "operation"}
            return {"outcome": "failed", "reason": "no_media"}

        def push(self, command):
            self.commands.append(command)
            return command

    queue = LagQueue()
    power_calls = []
    timer = DisplaySleepTimer(
        queue,
        power=lambda enabled: power_calls.append(enabled) or True,
        browser_audio=lambda: False,
        other_audio=lambda: False,
        clock=lambda: 100,
        schedule=Scheduled,
    )
    timer.set(15)
    timer.job.callback(*timer.job.args)
    assert queue.commands == ["player_pause", "player_get"]
    assert power_calls == [False]
    assert timer.status()["asleep"] is True


def test_cancelled_deadline_cannot_turn_output_off():
    power_calls = []
    timer = DisplaySleepTimer(
        PauseQueue(),
        power=lambda enabled: power_calls.append(enabled) or True,
        other_audio=lambda: False,
        clock=lambda: 100,
        schedule=Scheduled,
    )
    timer.set(15)
    old_job = timer.job
    timer.set(0)
    assert old_job.cancelled
    old_job.callback(*old_job.args)
    assert power_calls == []
    assert timer.status()["minutes"] == 0


def test_wake_during_output_transition_restores_image():
    off_started = Event()
    allow_off_to_finish = Event()
    power_calls = []

    def power(enabled):
        power_calls.append(enabled)
        if not enabled:
            off_started.set()
            assert allow_off_to_finish.wait(2)
        return True

    timer = DisplaySleepTimer(
        PauseQueue(),
        power=power,
        browser_audio=lambda: False,
        other_audio=lambda: False,
        clock=lambda: 100,
        schedule=Scheduled,
    )
    timer.set(15)
    job = timer.job
    expiry = Thread(target=lambda: job.callback(*job.args))
    expiry.start()
    assert off_started.wait(2)
    waking = Thread(target=timer.wake)
    waking.start()
    allow_off_to_finish.set()
    expiry.join(timeout=2)
    waking.join(timeout=2)
    assert not expiry.is_alive() and not waking.is_alive()
    assert power_calls == [False, True]
    assert timer.status()["phase"] == "idle"


def test_phone_action_during_pause_cancels_pending_screen_off():
    waiting = Event()
    release = Event()
    power_calls = []

    class SlowPause(PauseQueue):
        def result(self, command_id):
            waiting.set()
            assert release.wait(2)
            return super().result(command_id)

    timer = DisplaySleepTimer(
        SlowPause(),
        power=lambda enabled: power_calls.append(enabled) or True,
        other_audio=lambda: False,
        clock=lambda: 100,
        schedule=Scheduled,
    )
    timer.set(15)
    job = timer.job
    expiry = Thread(target=lambda: job.callback(*job.args))
    expiry.start()
    assert waiting.wait(2)
    assert timer.status()["phase"] == "pausing"
    assert timer.wake()
    release.set()
    expiry.join(timeout=2)
    assert not expiry.is_alive()
    assert power_calls == []
    assert timer.status()["phase"] == "idle"


def test_uncertain_power_off_is_rolled_back_before_reporting_failure():
    power_calls = []

    def power(enabled):
        power_calls.append(enabled)
        return enabled

    timer = DisplaySleepTimer(
        PauseQueue(),
        power=power,
        browser_audio=lambda: False,
        other_audio=lambda: False,
        clock=lambda: 100,
        schedule=Scheduled,
    )
    timer.set(15)
    timer.job.callback(*timer.job.args)
    assert power_calls == [False, True]
    assert timer.status()["asleep"] is False
    assert timer.status()["error"] == "display_unavailable"


def test_display_timer_http_requires_kiosk_and_phone_csrf(endpoint, monkeypatch):
    import ad_linux_tv.post_routes as post_routes
    import ad_linux_tv.server as server

    connection, port = endpoint
    local = {"Origin": f"http://127.0.0.1:{port}", "Content-Type": "application/json"}
    response, _ = request(connection, "POST", "/api/display-timer", '{"minutes":15}', local)
    assert response.status == 403
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    response, payload = request(connection, "POST", "/api/display-timer", '{"minutes":15}', local)
    assert response.status == 200 and json.loads(payload)["minutes"] == 15
    response, payload = request(connection, "GET", "/api/display-timer")
    assert response.status == 200 and json.loads(payload)["minutes"] == 15

    _, auth, cookie = login(connection, port)
    monkeypatch.setattr(post_routes, "loopback_source", lambda _source: False)
    monkeypatch.setattr(server.security, "loopback_source", lambda _source: False)
    remote = command_headers(port, cookie, auth["csrf"], origin=f"http://192.168.1.5:{port}")
    remote["Host"] = f"192.168.1.5:{port}"
    denied = {**remote, "X-CSRF-Token": "wrong"}
    response, _ = request(connection, "POST", "/api/display-timer", '{"minutes":30}', denied)
    assert response.status == 403
    response, payload = request(connection, "POST", "/api/display-timer", '{"minutes":30}', remote)
    assert response.status == 200 and json.loads(payload)["minutes"] == 30
    response, _ = request(connection, "POST", "/api/display-timer", '{"minutes":1}', remote)
    assert response.status == 400
