"""Firefox MPRIS control must remain bounded and avoid other players."""

import json
import time
from threading import Event, Lock
from types import SimpleNamespace

import pytest

from ad_linux_tv.media_session import MediaMonitor, MediaSession, MediaUnavailable


class FakeBus:
    def __init__(self):
        self.calls = []
        self.playing = True
        self.playback_status = None
        self.next = False
        self.firefox = True
        self.title = "Long test video"

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        if argv[-1] == "list":
            data = [{"name": "org.mpris.MediaPlayer2.spotify"}]
            if self.firefox:
                data.append({"name": "org.mpris.MediaPlayer2.firefox.instance1"})
        elif "GetAll" in argv:
            metadata = {
                "xesam:title": {"type": "s", "data": self.title},
                "mpris:length": {"type": "x", "data": 120_000_000},
                "mpris:trackid": {"type": "o", "data": "/org/test/track/1"},
            }
            props = {
                "Metadata": {"type": "a{sv}", "data": metadata},
                "PlaybackStatus": {
                    "type": "s",
                    "data": self.playback_status or ("Playing" if self.playing else "Paused"),
                },
                "Position": {"type": "x", "data": 30_000_000},
                "CanControl": {"type": "b", "data": True},
                "CanPlay": {"type": "b", "data": True},
                "CanPause": {"type": "b", "data": True},
                "CanSeek": {"type": "b", "data": True},
                "CanGoNext": {"type": "b", "data": self.next},
                "CanGoPrevious": {"type": "b", "data": False},
            }
            data = {"type": "a{sv}", "data": [props]}
        else:
            return SimpleNamespace(returncode=0, stdout="")
        return SimpleNamespace(returncode=0, stdout=json.dumps(data))


def test_firefox_media_state_and_capabilities():
    bus = FakeBus()
    media = MediaSession(bus)
    state = media.status()
    assert state["title"] == "Long test video"
    assert state["position"] == 30
    assert state["duration"] == 120
    assert state["playing"] is True
    assert state["can_seek"] is True
    assert state["can_next"] is False
    assert not any("spotify" in str(call) for call in bus.calls[1:])

    with pytest.raises(ValueError):
        media.command("next")
    with pytest.raises(ValueError):
        media.command("seek", 121)
    with pytest.raises(ValueError):
        media.command("seek", True)
    media.command("seek", 45)
    assert any(
        "SetPosition" in call and call[-2:] == ["/org/test/track/1", "45000000"]
        for call in bus.calls
    )
    media.command("pause")
    assert any("Pause" in call for call in bus.calls)


def test_missing_firefox_player_does_not_select_other_app():
    bus = FakeBus()
    bus.firefox = False
    media = MediaSession(bus)
    assert media.status() == {"available": False}
    with pytest.raises(MediaUnavailable):
        media.command("play")
    assert not any("spotify" in str(call) for call in bus.calls[1:])


def test_stopped_firefox_session_does_not_keep_stale_phone_panel():
    bus = FakeBus()
    bus.playback_status = "Stopped"
    media = MediaSession(bus)
    assert media.status() == {"available": False}
    with pytest.raises(MediaUnavailable):
        media.command("play")


def test_media_poll_does_not_block_phone_status():
    entered = Event()
    release = Event()

    class SlowReader:
        def status(self):
            entered.set()
            release.wait(timeout=1)
            return {"available": True, "title": "Test"}

    monitor = MediaMonitor(SlowReader())
    assert entered.wait(timeout=1)
    assert monitor.status() == {"available": False}
    release.set()
    for _ in range(100):
        if monitor.status().get("available"):
            break
        time.sleep(0.01)
    assert monitor.status()["title"] == "Test"


def test_stale_media_identity_refuses_action_before_mpris_call():
    bus = FakeBus()
    media = MediaSession(bus)
    identity = media.status()["media_id"]
    assert len(identity) == 32
    media.command("pause", media_id=identity)
    count = sum("Pause" in call for call in bus.calls)
    bus.title = "Different Firefox media"
    with pytest.raises(ValueError, match="target changed"):
        media.command("pause", media_id=identity)
    assert sum("Pause" in call for call in bus.calls) == count
    for bad in (True, "", "x" * 32, "a" * 33):
        with pytest.raises(ValueError, match="identity"):
            media.command("pause", media_id=bad)
    # Older web clients are still compatible, but have no identity precondition.
    media.command("pause")


def test_command_acknowledgement_triggers_fast_background_reconciliation():
    ready, confirmed = Event(), Event()

    class DelayedReader:
        def __init__(self):
            self.commands = 0
            self.observations = 0

        def status(self):
            ready.set()
            if self.commands:
                self.observations += 1
            playing = self.observations < 2
            if not playing:
                confirmed.set()
            return {"available": True, "playing": playing}

        def command(self, action, position):
            assert action == "pause" and position is None
            self.commands += 1
            return {"available": True, "playing": True}  # Accepted but not yet observed.

    reader = DelayedReader()
    monitor = MediaMonitor(reader)
    assert ready.wait(timeout=1)
    assert monitor.command("pause")["playing"] is True
    assert confirmed.wait(timeout=2)
    for _ in range(100):
        if monitor.status().get("playing") is False:
            break
        time.sleep(0.001)
    assert monitor.status()["playing"] is False
    assert reader.commands == 1  # Poll again, never replay the command.


def test_poll_publication_holds_operation_lock_until_cache_is_updated():
    monitor = MediaMonitor.__new__(MediaMonitor)
    monitor.operation_lock = Lock()
    monitor.reader = SimpleNamespace(status=lambda: {"available": True, "playing": True})
    monitor.fast_until = 0

    class PublicationLock:
        def __enter__(self):
            assert monitor.operation_lock.locked()

        def __exit__(self, *_args):
            pass

    class OneIteration:
        def clear(self):
            pass

        def wait(self, _timeout):
            raise StopIteration

    monitor.lock = PublicationLock()
    monitor.wakeup = OneIteration()
    with pytest.raises(StopIteration):
        monitor._poll()
    assert monitor.state["playing"] is True
