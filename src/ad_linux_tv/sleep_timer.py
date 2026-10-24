"""TV display timer: pause managed playback, then power down only the output."""

import json
import subprocess
import time
from threading import Lock, Timer

from . import audio
from .control import QueueFullError

PRESETS = (0, 15, 30, 60, 90, 120)


def _set_output_power(enabled):
    try:
        subprocess.run(
            ["/usr/bin/wlopm", "--on" if enabled else "--off", "*"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=4,
        )
        state = subprocess.run(
            ["/usr/bin/wlopm", "--json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=4,
        )
        outputs = json.loads(state.stdout)
        return bool(outputs) and all(
            entry["power-mode"] == ("on" if enabled else "off") for entry in outputs
        )
    except (
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        ValueError,
        KeyError,
    ):
        return False


def _browser_audio_active():
    try:
        return audio.get_state()["browser_volume"] is not None
    except audio.AudioUnavailable:
        # Without audio state, an unrecognized player cannot be declared silent.
        return True


class DisplaySleepTimer:
    def __init__(
        self,
        queue,
        *,
        power=_set_output_power,
        browser_audio=_browser_audio_active,
        clock=time.monotonic,
        schedule=Timer,
    ):
        self.queue = queue
        self.power = power
        self.browser_audio = browser_audio
        self.clock = clock
        self.schedule = schedule
        self.lock = Lock()
        self.deadline = None
        self.minutes = 0
        self.asleep = False
        self.error = None
        self.generation = 0
        self.job = None

    def status(self):
        with self.lock:
            return self._status()

    def _status(self):
        remaining = max(0, round(self.deadline - self.clock())) if self.deadline else 0
        return {
            "minutes": self.minutes,
            "remaining_seconds": remaining,
            "asleep": self.asleep,
            "error": self.error,
            "phase": "countdown" if self.deadline else "asleep" if self.asleep else "idle",
        }

    def set(self, minutes):
        if type(minutes) is not int or minutes not in PRESETS:
            raise ValueError("invalid display timer preset")
        if self.asleep and not self.wake():
            return self.status()
        with self.lock:
            self.generation += 1
            if self.job is not None:
                self.job.cancel()
            self.job = None
            self.minutes = minutes
            self.deadline = self.clock() + minutes * 60 if minutes else None
            self.error = None
            if minutes:
                generation = self.generation
                self.job = self.schedule(minutes * 60, self._expire, args=(generation,))
                self.job.daemon = True
                self.job.start()
            return self._status()

    def wake(self):
        with self.lock:
            if not self.asleep:
                return True
            self.generation += 1
            if self.job is not None:
                self.job.cancel()
            self.job = None
            self.deadline = None
            self.minutes = 0
            asleep = self.asleep
        if asleep and not self.power(True):
            with self.lock:
                self.error = "display_unavailable"
            return False
        with self.lock:
            self.asleep = False
            self.error = None
        return True

    def _pause_playback(self):
        try:
            command_id = self.queue.push("player_pause")
        except QueueFullError:
            return False
        for _ in range(40):
            result = self.queue.result(command_id)
            if result:
                if result["outcome"] == "completed":
                    return True
                if result["reason"] == "no_media":
                    return not self.browser_audio()
                return False
            time.sleep(0.2)
        return False

    def _expire(self, generation):
        with self.lock:
            if generation != self.generation:
                return
            self.deadline = None
            self.job = None
        if not self._pause_playback():
            with self.lock:
                if generation == self.generation:
                    self.minutes = 0
                    self.error = "pause_unavailable"
            return
        with self.lock:
            if generation != self.generation:
                return
        powered_off = self.power(False)
        with self.lock:
            if generation != self.generation:
                if powered_off:
                    self.power(True)
                return
            self.minutes = 0
            self.asleep = powered_off
            self.error = None if powered_off else "display_unavailable"
