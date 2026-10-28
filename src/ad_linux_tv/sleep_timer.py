"""TV display timer: pause managed playback, then power down only the output."""

import json
import subprocess
import time
from threading import Lock, Timer

from . import audio, cec
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
        TypeError,
    ):
        return False


def _browser_audio_active():
    try:
        return audio.browser_audio_active()
    except audio.AudioUnavailable:
        # Without audio state, an unrecognized player cannot be declared silent.
        return True


def _other_audio_active():
    try:
        return audio.non_browser_audio_present()
    except audio.AudioUnavailable:
        return True


class DisplaySleepTimer:
    def __init__(
        self,
        queue,
        *,
        power=_set_output_power,
        browser_audio=_browser_audio_active,
        other_audio=_other_audio_active,
        clock=time.monotonic,
        schedule=Timer,
        cec_wake=None,
    ):
        self.queue = queue
        self.power = power
        self.browser_audio = browser_audio
        self.other_audio = other_audio
        self.clock = clock
        self.schedule = schedule
        self.cec_wake = cec_wake or cec.wake
        self.cec_result = "unavailable"
        self.lock = Lock()
        self.deadline = None
        self.minutes = 0
        self.asleep = False
        self.expiring = False
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
            "generation": self.generation,
            "asleep": self.asleep,
            "error": self.error,
            "cec_wake": self.cec_result,
            "phase": (
                "countdown"
                if self.deadline
                else "asleep"
                if self.asleep
                else "pausing"
                if self.expiring
                else "idle"
            ),
        }

    def set(self, minutes):
        if type(minutes) is not int or minutes not in PRESETS:
            raise ValueError("invalid display timer preset")
        with self.lock:
            if self.asleep:
                if not self.power(True):
                    self.error = "display_unavailable"
                    return self._status()
                self.asleep = False
            self.generation += 1
            if self.job is not None:
                self.job.cancel()
            self.job = None
            self.minutes = minutes
            self.deadline = self.clock() + minutes * 60 if minutes else None
            self.expiring = False
            self.error = None
            if minutes:
                generation = self.generation
                self.job = self.schedule(minutes * 60, self._expire, args=(generation,))
                self.job.daemon = True
                self.job.start()
            return self._status()

    def sleep_now(self):
        """Start the existing pause/silence pipeline without blocking a phone socket."""
        with self.lock:
            if self.asleep or self.expiring:
                return self._status()
            self.generation += 1
            if self.job is not None:
                self.job.cancel()
            self.deadline = None
            self.minutes = 0
            self.error = None
            self.expiring = True
            self.job = self.schedule(0, self._expire, args=(self.generation,))
            self.job.daemon = True
            self.job.start()
            return self._status()

    def wake(self, *, force=False, use_cec=False):
        with self.lock:
            request_cec = self.asleep or use_cec
            if not self.asleep and not self.expiring:
                # Explicit wake must assert real output power even if our cached
                # flag was lost/stale. It does not cancel an active countdown.
                if force and not self.power(True):
                    self.error = "display_unavailable"
                    return False
                if force:
                    self.error = None
                if request_cec:
                    self._wake_cec()
                return True
            self.generation += 1
            if self.job is not None:
                self.job.cancel()
            self.job = None
            self.deadline = None
            self.minutes = 0
            self.expiring = False
            if (self.asleep or force) and not self.power(True):
                self.error = "display_unavailable"
                return False
            self.asleep = False
            self.error = None
            if request_cec:
                self._wake_cec()
            return True

    def _wake_cec(self):
        try:
            result = self.cec_wake()
            self.cec_result = (
                result if result in ("requested", "unavailable", "uncertain") else "uncertain"
            )
        except Exception:
            self.cec_result = "uncertain"

    def _player_result(self, command, generation=None):
        try:
            with self.lock:
                if generation is not None and generation != self.generation:
                    return None
                command_id = self.queue.push(command)
        except QueueFullError:
            return None
        for _ in range(40):
            with self.lock:
                if generation is not None and generation != self.generation:
                    return None
            result = self.queue.result(command_id)
            if result:
                return result
            time.sleep(0.2)
        return None

    def _pause_playback(self, generation=None):
        result = self._player_result("player_pause", generation)
        if result is None:
            return "pause_unavailable"
        if result["outcome"] == "completed":
            return "audio_active" if self.browser_audio() or self.other_audio() else None
        if result["reason"] == "no_media":
            return "audio_active" if self.browser_audio() or self.other_audio() else None
        # Firefox's audible flag can lag behind a successful HTMLMediaElement.pause().
        # Confirm the element is no longer playing before accepting that case.
        probe = self._player_result("player_get", generation)
        if probe and probe["reason"] == "no_media":
            time.sleep(0.4)
            return "audio_active" if self.browser_audio() or self.other_audio() else None
        return "pause_unavailable"

    def _expire(self, generation):
        with self.lock:
            if generation != self.generation:
                return
            self.deadline = None
            self.job = None
            self.expiring = True
        pause_error = self._pause_playback(generation)
        if pause_error is not None:
            with self.lock:
                if generation == self.generation:
                    self.minutes = 0
                    self.expiring = False
                    self.error = pause_error
            return
        with self.lock:
            if generation != self.generation:
                return
            powered_off = self.power(False)
            self.minutes = 0
            self.expiring = False
            if powered_off:
                self.asleep = True
                self.error = None
            else:
                restored = self.power(True)
                self.asleep = not restored
                self.error = "display_unavailable"
