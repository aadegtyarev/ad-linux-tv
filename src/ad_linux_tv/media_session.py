"""Control the TV user's Firefox media session through MPRIS on D-Bus."""

import json
import os
import subprocess
import time
from threading import Lock, Thread

PLAYER_INTERFACE = "org.mpris.MediaPlayer2.Player"
PLAYER_PATH = "/org/mpris/MediaPlayer2"
PLAYER_PREFIX = "org.mpris.MediaPlayer2.firefox"
MAX_POSITION_SECONDS = 24 * 60 * 60


class MediaUnavailable(Exception):
    """Firefox has no usable media session or the session bus is unavailable."""


class MediaSession:
    def __init__(self, runner=subprocess.run):
        self.runner = runner

    def _call(self, *args):
        env = os.environ.copy()
        runtime = env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
        env["XDG_RUNTIME_DIR"] = runtime
        env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={runtime}/bus")
        try:
            result = self.runner(
                ["busctl", "--user", "--json=short", "--timeout=2s", *args],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
                env=env,
            )
            if result.returncode != 0:
                raise MediaUnavailable("session bus unavailable")
            return json.loads(result.stdout) if result.stdout.strip() else None
        except (OSError, subprocess.TimeoutExpired, ValueError) as error:
            raise MediaUnavailable("session bus unavailable") from error

    def _player(self):
        names = self._call("list")
        if not isinstance(names, list):
            raise MediaUnavailable("invalid session bus reply")
        matches = sorted(
            row["name"]
            for row in names
            if isinstance(row, dict)
            and isinstance(row.get("name"), str)
            and (row["name"] == PLAYER_PREFIX or row["name"].startswith(PLAYER_PREFIX + "."))
        )
        return matches[0] if matches else None

    @staticmethod
    def _value(properties, name, default=None):
        entry = properties.get(name)
        return entry.get("data", default) if isinstance(entry, dict) else default

    def _snapshot(self):
        player = self._player()
        if player is None:
            return {"available": False}, None, None
        reply = self._call(
            "call",
            player,
            PLAYER_PATH,
            "org.freedesktop.DBus.Properties",
            "GetAll",
            "s",
            PLAYER_INTERFACE,
        )
        try:
            properties = reply["data"][0]
            metadata = self._value(properties, "Metadata", [{}])[0]
            if not isinstance(metadata, dict):
                metadata = {}
            status = self._value(properties, "PlaybackStatus")
            if status not in ("Playing", "Paused", "Stopped"):
                raise ValueError("invalid playback state")
            can_control = self._value(properties, "CanControl") is True
            duration_us = self._value(metadata, "mpris:length")
            position_us = self._value(properties, "Position")
            track_id = self._value(metadata, "mpris:trackid")
            duration = (
                round(duration_us / 1_000_000)
                if type(duration_us) is int and 0 < duration_us <= MAX_POSITION_SECONDS * 1_000_000
                else None
            )
            position = (
                max(0, min(round(position_us / 1_000_000), duration))
                if duration is not None and type(position_us) is int
                else None
            )
            title = self._value(metadata, "xesam:title")
            title = " ".join(title.split())[:160] if isinstance(title, str) else ""
            seekable = (
                can_control
                and self._value(properties, "CanSeek") is True
                and duration is not None
                and position is not None
                and isinstance(track_id, str)
                and track_id.startswith("/")
            )
            state = {
                "available": True,
                "title": title or "Воспроизведение",
                "playing": status == "Playing",
                "position": position,
                "duration": duration,
                "can_play": can_control and self._value(properties, "CanPlay") is True,
                "can_pause": can_control and self._value(properties, "CanPause") is True,
                "can_seek": seekable,
                "can_next": can_control and self._value(properties, "CanGoNext") is True,
                "can_previous": can_control and self._value(properties, "CanGoPrevious") is True,
            }
            return state, player, track_id
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise MediaUnavailable("invalid player reply") from error

    def status(self):
        return self._snapshot()[0]

    def command(self, action, position=None):
        if action not in ("play", "pause", "next", "previous", "seek"):
            raise ValueError("invalid media action")
        if action == "seek":
            if type(position) is not int or not 0 <= position <= MAX_POSITION_SECONDS:
                raise ValueError("invalid media position")
        elif position is not None:
            raise ValueError("unexpected media position")
        state, player, track_id = self._snapshot()
        if not state["available"]:
            raise MediaUnavailable("no Firefox media session")
        capability = {
            "play": "can_play",
            "pause": "can_pause",
            "next": "can_next",
            "previous": "can_previous",
            "seek": "can_seek",
        }[action]
        if not state[capability] or (action == "seek" and position > state["duration"]):
            raise ValueError("unsupported media action")
        method = action.title() if action != "seek" else "SetPosition"
        args = ["call", player, PLAYER_PATH, PLAYER_INTERFACE, method]
        if action == "seek":
            args += ["ox", track_id, str(position * 1_000_000)]
        self._call(*args)
        return self.status()


class MediaMonitor:
    """Read D-Bus outside the ordered phone socket's pointer-command loop."""

    def __init__(self, reader=None):
        self.reader = reader or MediaSession()
        self.lock = Lock()
        self.operation_lock = Lock()
        self.state = {"available": False}
        self.updated = 0.0
        Thread(target=self._poll, daemon=True).start()

    def _poll(self):
        while True:
            try:
                with self.operation_lock:
                    state = self.reader.status()
            except MediaUnavailable:
                state = {"available": False}
            with self.lock:
                self.state = state
                self.updated = time.monotonic()
            time.sleep(2)

    def status(self):
        with self.lock:
            return dict(self.state) if time.monotonic() - self.updated < 6 else {"available": False}

    def command(self, action, position=None):
        with self.operation_lock:
            state = self.reader.command(action, position)
        with self.lock:
            self.state = state
            self.updated = time.monotonic()
        return state


_monitor = None
_monitor_lock = Lock()


def get_media_monitor():
    global _monitor
    with _monitor_lock:
        if _monitor is None:
            _monitor = MediaMonitor()
        return _monitor
