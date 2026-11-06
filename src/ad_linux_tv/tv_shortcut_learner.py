"""Bounded, session-scoped GTK key selection; no background keyboard listener."""

import os
import secrets
import subprocess
import time
from threading import RLock, Timer

from .tv_shortcut_keys import KEYSYMS

LEARNER = "/usr/local/libexec/ad-linux-tv/learn-tv-shortcut.py"
DEADLINE = 18.0
AUTH_CHECK_INTERVAL = 0.25


class ShortcutLearningError(ValueError):
    pass


class ShortcutLearner:
    def __init__(self, popen=subprocess.Popen, clock=time.monotonic, timer_factory=Timer):
        self._popen = popen
        self._clock = clock
        self._timer_factory = timer_factory
        self._lock = RLock()
        self._active = None

    def _stop(self, active):
        active["timer"].cancel()
        if active.get("watchdog") is not None:
            active["watchdog"].cancel()
        process = active["process"]
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
                process.wait(timeout=1)
        process.communicate()

    def _expire(self, identifier):
        with self._lock:
            active = self._active
            if active is None or active["id"] != identifier:
                return
            self._active = None
            self._stop(active)

    def _watch_authorization(self, owner, identifier, validator):
        # Never acquire the session lock while holding the learner lock.
        try:
            authorized = validator()
        except Exception:
            authorized = False
        if not authorized:
            self.retire(owner, identifier)
            return
        with self._lock:
            active = self._active
            if active is None or active["owner"] != owner or active["id"] != identifier:
                return
            watchdog = self._timer_factory(
                AUTH_CHECK_INTERVAL, self._watch_authorization, args=(owner, identifier, validator)
            )
            watchdog.daemon = True
            active["watchdog"] = watchdog
            try:
                watchdog.start()
            except RuntimeError:
                self._active = None
                self._stop(active)

    def start(self, owner, validator=None):
        if owner is None or os.environ.get("AD_LINUX_TV_KIOSK") != "1":
            raise ShortcutLearningError("unavailable")
        with self._lock:
            if self._active is not None:
                raise ShortcutLearningError("busy")
            identifier = secrets.token_hex(16)
            env = dict(os.environ, AD_TV_VIDEO_PANEL_PARENT=str(os.getpid()))
            try:
                process = self._popen(
                    ["/usr/bin/python3", LEARNER],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                    env=env,
                )
            except OSError:
                raise ShortcutLearningError("unavailable") from None
            timer = self._timer_factory(DEADLINE, self._expire, args=(identifier,))
            timer.daemon = True
            self._active = {
                "id": identifier,
                "owner": owner,
                "process": process,
                "deadline": self._clock() + DEADLINE,
                "timer": timer,
                "watchdog": None,
            }
            try:
                timer.start()
                if validator is not None:
                    watchdog = self._timer_factory(
                        AUTH_CHECK_INTERVAL,
                        self._watch_authorization,
                        args=(owner, identifier, validator),
                    )
                    watchdog.daemon = True
                    self._active["watchdog"] = watchdog
                    watchdog.start()
            except RuntimeError:
                active = self._active
                self._active = None
                self._stop(active)
                raise ShortcutLearningError("unavailable") from None
            return identifier

    def result(self, owner, identifier):
        with self._lock:
            active = self._active
            if active is None or active["owner"] != owner or active["id"] != identifier:
                raise ShortcutLearningError("unavailable")
            if self._clock() >= active["deadline"]:
                self._active = None
                self._stop(active)
                return {"state": "unavailable"}
            if active["process"].poll() is None:
                return {"state": "waiting"}
            self._active = None
            active["timer"].cancel()
            if active["watchdog"] is not None:
                active["watchdog"].cancel()
            output, _ = active["process"].communicate()
            try:
                key = output.decode("ascii").strip()
            except (AttributeError, UnicodeError):
                key = ""
            if active["process"].returncode == 2:
                return {"state": "cancelled"}
            if active["process"].returncode != 0 or key not in KEYSYMS:
                return {"state": "unavailable"}
            return {"state": "ready", "key": key}

    def snapshot(self):
        """Capture the exact in-flight operation before an auth generation changes."""
        with self._lock:
            active = self._active
            return (active["owner"], active["id"]) if active is not None else None

    def retire(self, owner, identifier=None):
        with self._lock:
            active = self._active
            if active is None or active["owner"] != owner:
                return False
            if identifier is not None and active["id"] != identifier:
                return False
            self._active = None
            self._stop(active)
            return True
