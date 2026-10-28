"""Existing CEC only; all device/tool access and commands are mocked."""

import stat
import subprocess
from types import SimpleNamespace

import pytest

from ad_linux_tv import cec
from ad_linux_tv.cec import wake as attempt_wake
from ad_linux_tv.sleep_timer import DisplaySleepTimer


def test_absent_adapter_does_not_run_any_command(monkeypatch):
    monkeypatch.setattr(cec, "available_adapter", lambda: None)
    monkeypatch.setattr(
        cec.subprocess, "run", lambda *a, **kw: pytest.fail("unexpected CEC command")
    )
    assert attempt_wake() == "unavailable"


@pytest.mark.parametrize(
    "outcome,expected",
    [(0, "requested"), (1, "unavailable"), ("timeout", "uncertain"), ("missing", "unavailable")],
)
def test_fixed_directed_wake_is_bounded_and_never_retried(monkeypatch, outcome, expected):
    calls = []
    monkeypatch.setattr(cec, "available_adapter", lambda: "/dev/cec0")

    def run(command, **kwargs):
        calls.append(command)
        assert kwargs["timeout"] == 3 and kwargs["check"] is False
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(command, 3)
        if outcome == "missing":
            raise FileNotFoundError()
        return SimpleNamespace(returncode=outcome)

    monkeypatch.setattr(cec.subprocess, "run", run)
    assert attempt_wake() == expected
    assert calls == [["/usr/bin/cec-ctl", "--device", "/dev/cec0", "--to", "0", "--image-view-on"]]


def test_adapter_lookup_is_bounded_and_rejects_regular_files(monkeypatch):
    paths = []
    monkeypatch.setattr(cec, "TOOL", SimpleNamespace(is_file=lambda: True))
    monkeypatch.setattr(cec.os, "access", lambda *args: True)

    def device(path):
        paths.append(path)
        return SimpleNamespace(lstat=lambda: SimpleNamespace(st_mode=stat.S_IFREG | 0o600))

    monkeypatch.setattr(cec, "Path", device)
    assert cec.available_adapter() is None
    assert paths == [f"/dev/cec{i}" for i in range(4)]


def test_idle_user_activity_does_not_repeat_cec_but_explicit_wake_can_request_it():
    commands = []
    timer = DisplaySleepTimer(
        None, power=lambda on: True, cec_wake=lambda: commands.append("wake") or "requested"
    )
    assert timer.wake(force=True) and commands == []
    assert timer.wake(force=True, use_cec=True) and commands == ["wake"]
    assert timer.status()["cec_wake"] == "requested"
    timer.asleep = True
    assert timer.wake() and commands == ["wake", "wake"]
