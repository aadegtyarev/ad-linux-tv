"""Ephemeral selected-output volume indicator state and bounded observation."""

import math
import os
import re
import select
import subprocess
import threading
import time
from collections import deque

VOLUME_TIMEOUT = 2.5
_VOLUME = re.compile(r"\AVolume:\s+([0-9]+(?:\.[0-9]+)?)(?:\s+\[MUTED\])?\s*\Z")
_SINK_EVENT = re.compile(rb"\AEvent '(?:change|new|remove)' on (?:sink|server) #\d+\r?\Z")


def parse_volume(output):
    """Return a bounded percentage from wpctl, or None for an unknown level."""
    if not isinstance(output, str) or len(output) > 128:
        return None
    match = _VOLUME.fullmatch(output)
    if match is None:
        return None
    value = float(match.group(1))
    if not math.isfinite(value) or not 0 <= value <= 1:
        return None
    return round(value * 100)


class VolumeNotice:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._level = None
        self._until = 0.0
        self._last_at = float("-inf")

    def observe(self, level, observed_at=None):
        now = self._clock()
        observed_at = now if observed_at is None else observed_at
        if (
            type(observed_at) not in (int, float)
            or not math.isfinite(observed_at)
            or observed_at > now
            or observed_at < self._last_at
        ):
            return self.snapshot()
        self._last_at = observed_at
        if type(level) is not int or not 0 <= level <= 100:
            self._level = None
            self._until = 0.0
        elif self._level is None:
            self._level = level
        elif level != self._level:
            self._level = level
            self._until = observed_at + VOLUME_TIMEOUT
        return self.snapshot()

    def snapshot(self):
        return {
            "visible": self._level is not None and self._clock() < self._until,
            "level": self._level,
        }


class VolumeWatcher:
    """Observe the default sink off the GTK thread; never record audio or titles."""

    def __init__(self):
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._values = deque(maxlen=8)
        self._process = None
        self._thread = None

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name="volume-watch")
        self._thread.start()

    def drain(self):
        with self._lock:
            values = list(self._values)
            self._values.clear()
        return values

    def _publish(self, value):
        with self._lock:
            self._values.append((time.monotonic(), value))

    @staticmethod
    def _read_volume(env):
        try:
            result = subprocess.run(
                [
                    "/usr/bin/setpriv",
                    "--pdeathsig=TERM",
                    "/usr/bin/wpctl",
                    "get-volume",
                    "@DEFAULT_AUDIO_SINK@",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=1,
                env=env,
            )
            return parse_volume(result.stdout)
        except (OSError, subprocess.SubprocessError):
            return None

    def _run(self):
        env = dict(os.environ, LC_ALL="C")
        while not self._stop.is_set():
            process = None
            try:
                # Ensure the subscriber dies if the overlay process crashes.
                process = subprocess.Popen(
                    ["/usr/bin/setpriv", "--pdeathsig=TERM", "/usr/bin/pactl", "subscribe"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    bufsize=0,
                    env=env,
                )
                with self._lock:
                    self._process = process
                if self._stop.is_set():
                    break
                self._publish(self._read_volume(env))
                next_reconcile = time.monotonic() + 1
                next_event_read = 0.0
                pending = b""
                while not self._stop.is_set():
                    delay = max(0, min(0.5, next_reconcile - time.monotonic()))
                    ready, _, _ = select.select([process.stdout], [], [], delay)
                    changed = False
                    if ready:
                        chunk = os.read(process.stdout.fileno(), 4096)
                        if not chunk:
                            break
                        pending += chunk
                        if len(pending) > 8192:
                            raise OSError("oversized subscription line")
                        lines = pending.split(b"\n")
                        pending = lines.pop()
                        changed = any(_SINK_EVENT.fullmatch(line) for line in lines)
                    now = time.monotonic()
                    if now >= next_reconcile or (changed and now >= next_event_read):
                        self._publish(self._read_volume(env))
                        now = time.monotonic()
                        next_reconcile = now + 1
                        next_event_read = now + 0.1
            except (OSError, ValueError):
                pass
            finally:
                if process is not None:
                    if process.poll() is None:
                        try:
                            process.terminate()
                        except ProcessLookupError:
                            pass
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        try:
                            process.kill()
                        except ProcessLookupError:
                            pass
                        process.wait()
                    if process.stdout is not None:
                        process.stdout.close()
                with self._lock:
                    self._process = None
            if not self._stop.is_set():
                self._publish(None)
                self._stop.wait(2)

    def close(self):
        self._stop.set()
        with self._lock:
            process = self._process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2)
            if self._thread.is_alive() and process is not None and process.poll() is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                self._thread.join(timeout=1)
