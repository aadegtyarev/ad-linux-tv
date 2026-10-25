"""Firefox MPRIS control must remain bounded and avoid other players."""

import json
import time
from threading import Event
from types import SimpleNamespace

import pytest

from ad_linux_tv.media_session import MediaMonitor, MediaSession, MediaUnavailable


class FakeBus:
    def __init__(self):
        self.calls = []
        self.playing = True
        self.next = False
        self.firefox = True

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        if argv[-1] == "list":
            data = [{"name": "org.mpris.MediaPlayer2.spotify"}]
            if self.firefox:
                data.append({"name": "org.mpris.MediaPlayer2.firefox.instance1"})
        elif "GetAll" in argv:
            metadata = {
                "xesam:title": {"type": "s", "data": "Long test video"},
                "mpris:length": {"type": "x", "data": 120_000_000},
                "mpris:trackid": {"type": "o", "data": "/org/test/track/1"},
            }
            props = {
                "Metadata": {"type": "a{sv}", "data": [metadata]},
                "PlaybackStatus": {"type": "s", "data": "Playing" if self.playing else "Paused"},
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
