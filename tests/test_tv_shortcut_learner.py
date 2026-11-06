"""A bounded learner returns only eligible keys to its initiating socket."""

import subprocess

import pytest

from ad_linux_tv.tv_shortcut_learner import ShortcutLearner, ShortcutLearningError


class FakeTimer:
    def __init__(self, delay, callback, args):
        self.delay, self.callback, self.args = delay, callback, args
        self.daemon = False
        self.cancelled = False

    def start(self):
        pass

    def cancel(self):
        self.cancelled = True

    def fire(self):
        self.callback(*self.args)


class FakeProcess:
    def __init__(self, output=b"XF86Launch1\n"):
        self.returncode = None
        self.output = output
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def wait(self, timeout):
        assert timeout <= 1
        if self.returncode is None:
            raise subprocess.TimeoutExpired("child", timeout)
        return self.returncode

    def kill(self):
        self.returncode = -9

    def communicate(self):
        return self.output, None


def fixture(monkeypatch):
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    now = [100.0]
    started = []

    def popen(argv, **kwargs):
        process = FakeProcess()
        started.append((argv, kwargs, process))
        return process

    return ShortcutLearner(popen=popen, clock=lambda: now[0], timer_factory=FakeTimer), started, now


def test_only_owner_can_poll_or_cancel_and_ready_result_is_consumed(monkeypatch):
    learner, started, _now = fixture(monkeypatch)
    identifier = learner.start("socket-a")
    argv, kwargs, child = started[0]
    assert argv == ["/usr/bin/python3", "/usr/local/libexec/ad-linux-tv/learn-tv-shortcut.py"]
    assert kwargs["stderr"] == subprocess.DEVNULL and kwargs["stdin"] == subprocess.DEVNULL
    assert learner.result("socket-a", identifier) == {"state": "waiting"}
    with pytest.raises(ShortcutLearningError):
        learner.result("socket-b", identifier)
    assert not learner.retire("socket-b", identifier)
    with pytest.raises(ShortcutLearningError, match="busy"):
        learner.start("socket-b")
    child.returncode = 0
    assert learner.result("socket-a", identifier) == {"state": "ready", "key": "XF86Launch1"}
    with pytest.raises(ShortcutLearningError):
        learner.result("socket-a", identifier)


def test_invalid_or_text_output_is_discarded_without_returning_it(monkeypatch):
    learner, started, _now = fixture(monkeypatch)
    identifier = learner.start("socket-a")
    child = started[0][2]
    child.output = b"secret typed text"
    child.returncode = 0
    assert learner.result("socket-a", identifier) == {"state": "unavailable"}


def test_cancel_on_tv_is_reported_without_a_key(monkeypatch):
    learner, started, _now = fixture(monkeypatch)
    identifier = learner.start("socket-a")
    child = started[0][2]
    child.output = b""
    child.returncode = 2
    assert learner.result("socket-a", identifier) == {"state": "cancelled"}


def test_timeout_and_owner_retirement_kill_the_child(monkeypatch):
    learner, started, now = fixture(monkeypatch)
    identifier = learner.start("socket-a")
    now[0] += 19
    assert learner.result("socket-a", identifier) == {"state": "unavailable"}
    assert started[0][2].terminated
    identifier = learner.start("socket-a")
    assert learner.retire("socket-a", identifier)
    assert started[1][2].terminated
    learner.start("socket-a")
    timer = learner._active["timer"]
    timer.fire()
    assert started[2][2].terminated and learner._active is None


def test_captured_phone_retirement_cancels_only_the_old_learner(monkeypatch):
    learner, started, _now = fixture(monkeypatch)
    identifier = learner.start("socket-a")
    old = learner.snapshot()
    assert old == ("socket-a", identifier)
    assert learner.retire(*old)
    assert started[0][2].terminated
    with pytest.raises(ShortcutLearningError):
        learner.result("socket-a", identifier)
    learner.start("socket-b")
    assert not learner.retire(*old)
    assert not started[1][2].terminated


def test_authorization_watchdog_retires_invalidated_idle_learner(monkeypatch):
    learner, started, _now = fixture(monkeypatch)
    allowed = [True]
    learner.start("socket-a", lambda: allowed[0])
    first = learner._active["watchdog"]
    first.fire()
    assert not started[0][2].terminated
    second = learner._active["watchdog"]
    assert second is not first
    allowed[0] = False
    second.fire()
    assert started[0][2].terminated
    assert learner._active is None


def test_authorization_watchdog_failure_is_fail_closed(monkeypatch):
    learner, started, _now = fixture(monkeypatch)

    def failed():
        raise RuntimeError("unavailable")

    learner.start("socket-a", failed)
    learner._active["watchdog"].fire()
    assert started[0][2].terminated
    assert learner.snapshot() is None


def test_learning_is_disabled_outside_tv_kiosk(monkeypatch):
    learner, started, _now = fixture(monkeypatch)
    monkeypatch.delenv("AD_LINUX_TV_KIOSK")
    with pytest.raises(ShortcutLearningError):
        learner.start("socket-a")
    assert not started
