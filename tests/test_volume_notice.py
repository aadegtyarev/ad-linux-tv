import importlib.util
import os
import subprocess
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("volume_notice", ROOT / "ops/kiosk/volume_notice.py")
volume = importlib.util.module_from_spec(spec)
spec.loader.exec_module(volume)


@pytest.mark.parametrize(
    "output,expected",
    [
        ("Volume: 0.35", 35),
        ("Volume: 1.00 [MUTED]\n", 100),
        ("Volume: 0.00", 0),
        ("Volume: 1.01", None),
        ("Volume: nan", None),
        ("unknown", None),
        (None, None),
    ],
)
def test_parse_only_bounded_known_volume(output, expected):
    assert volume.parse_volume(output) == expected


def test_initial_baseline_does_not_flash_and_changes_extend_expiry():
    now = [10.0]
    notice = volume.VolumeNotice(clock=lambda: now[0])
    assert notice.observe(35) == {"visible": False, "level": 35}
    assert notice.observe(35) == {"visible": False, "level": 35}
    assert notice.observe(40) == {"visible": True, "level": 40}
    now[0] += 2
    assert notice.observe(45) == {"visible": True, "level": 45}
    now[0] += 2
    assert notice.snapshot()["visible"]
    now[0] += 0.5
    assert notice.snapshot() == {"visible": False, "level": 45}


def test_delayed_or_out_of_order_observations_do_not_revive_stale_indicator():
    now = [10.0]
    notice = volume.VolumeNotice(clock=lambda: now[0])
    notice.observe(35, observed_at=10)
    now[0] = 20
    assert notice.observe(40, observed_at=11) == {"visible": False, "level": 40}
    assert notice.observe(50, observed_at=10) == {"visible": False, "level": 40}
    assert notice.observe(50, observed_at=21) == {"visible": False, "level": 40}


def test_unavailable_level_hides_and_recovery_is_a_new_baseline():
    notice = volume.VolumeNotice(clock=lambda: 10)
    notice.observe(35)
    assert notice.observe(40)["visible"]
    assert notice.observe(None) == {"visible": False, "level": None}
    assert notice.observe(70) == {"visible": False, "level": 70}
    for invalid in (-1, 101, True, "35"):
        assert notice.observe(invalid) == {"visible": False, "level": None}


class FakeProcess:
    def __init__(self):
        read_fd, self.write_fd = os.pipe()
        self.stdout = os.fdopen(read_fd, "rb", buffering=0)
        self.running = True

    def poll(self):
        return None if self.running else 0

    def emit(self, value):
        os.write(self.write_fd, value)

    def terminate(self):
        if self.running:
            self.running = False
            os.close(self.write_fd)

    def kill(self):
        self.terminate()

    def wait(self, timeout=None):
        return 0


def test_sink_events_are_observed_and_close_stops_idle_subscriber(monkeypatch):
    watcher = volume.VolumeWatcher()
    process = FakeProcess()
    initial, changed = threading.Event(), threading.Event()
    calls, commands = [], []

    def popen(args, **kwargs):
        commands.append((args, kwargs))
        return process

    def read(_env):
        calls.append(1)
        if len(calls) == 1:
            initial.set()
            return 35
        changed.set()
        return 40

    monkeypatch.setattr(volume.subprocess, "Popen", popen)
    monkeypatch.setattr(watcher, "_read_volume", read)
    watcher.start()
    assert initial.wait(1)
    process.emit(b"Event 'change' on sink-input #9\nEvent 'change' on sink #2\n")
    assert changed.wait(1)
    watcher.close()
    assert [value for _, value in watcher.drain()] == [35, 40]
    assert commands[0][0] == ["/usr/bin/setpriv", "--pdeathsig=TERM", "/usr/bin/pactl", "subscribe"]
    assert commands[0][1]["stdin"] is subprocess.DEVNULL
    assert not process.running and not watcher._thread.is_alive()
    for value in range(100):
        watcher._publish(value)
    assert [value for _, value in watcher.drain()] == list(range(92, 100))


def test_reconciliation_catches_change_missed_before_subscription_ready(monkeypatch):
    watcher = volume.VolumeWatcher()
    process = FakeProcess()
    changed = threading.Event()
    calls = []

    def read(_env):
        calls.append(1)
        if len(calls) == 1:
            return 35  # Change occurs before the subscriber is registered.
        changed.set()
        return 40  # No event arrives; periodic reconciliation must detect it.

    monkeypatch.setattr(volume.subprocess, "Popen", lambda *_args, **_kwargs: process)
    monkeypatch.setattr(watcher, "_read_volume", read)
    watcher.start()
    assert changed.wait(2.5)
    watcher.close()
    assert [value for _, value in watcher.drain()] == [35, 40]


def test_setup_includes_parent_death_wrapper_dependency():
    assert "util-linux" in (ROOT / "ops/kiosk/setup.sh").read_text()


def test_wpctl_read_is_fixed_bounded_and_failure_is_unknown(monkeypatch):
    calls = []

    class Result:
        stdout = "Volume: 0.40\n"

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return Result()

    monkeypatch.setattr(volume.subprocess, "run", run)
    assert volume.VolumeWatcher._read_volume({"LC_ALL": "C"}) == 40
    assert calls[0][0] == [
        "/usr/bin/setpriv",
        "--pdeathsig=TERM",
        "/usr/bin/wpctl",
        "get-volume",
        "@DEFAULT_AUDIO_SINK@",
    ]
    assert calls[0][1]["timeout"] == 1

    def fail(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("wpctl", 1)

    monkeypatch.setattr(volume.subprocess, "run", fail)
    assert volume.VolumeWatcher._read_volume({}) is None
