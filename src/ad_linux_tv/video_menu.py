"""Current-video menu state; no transport, input capture or GTK dependencies.

A selection is only a proposal until the bridge reports completion for the same
freshly observed video. Closing a menu never replays an uncertain command.
"""

import secrets
import time
from threading import RLock

from .control import QueueFullError

MODES = frozenset({"original", "4:3", "16:9"})
RESULT_TIMEOUT = 7.0
OVERLAY_TIMEOUT = 3.0


class VideoMenu:
    def __init__(self, queue, clock=time.monotonic):
        self._queue = queue
        queue.video_menu = self
        self._clock = clock
        self._lock = RLock()
        self._instance = secrets.token_hex(16)
        self._opening = None
        self._visible = False
        self._target = None
        self._mode = "original"
        self._mirror = False
        self._pending = None
        self._reset_after_pending = False
        self._revision = 0
        self._status = "unavailable"
        self._overlay_seen = None
        self._home_openings = {}

    def push_home(self, service_id=None, volume=None):
        """Associate an admitted Home with the visible opening under the menu lock."""
        with self._lock:
            command_id = self._queue.push("home", service_id, volume)
            if self._visible:
                self._home_openings[command_id] = self._opening
            return command_id

    def acknowledge(self, command_id, outcome, reason, volume):
        # Menu-before-queue is also the order used by apply() and push_home().
        with self._lock:
            if not self._queue.acknowledge(command_id, outcome, reason, volume):
                return False
            opening = self._home_openings.pop(command_id, None)
            if outcome == "completed" and opening is not None and self._visible:
                if opening == self._opening:
                    self._visible = False
                    self._revision += 1
            return True

    def matches_instance(self, instance):
        return isinstance(instance, str) and secrets.compare_digest(instance, self._instance)

    def heartbeat(self):
        """Record a poll from the trusted local overlay, not proof it is visible."""
        with self._lock:
            self._overlay_seen = self._clock()

    def overlay_online(self):
        with self._lock:
            if self._overlay_seen is None:
                return False
            age = self._clock() - self._overlay_seen
            return 0 <= age <= OVERLAY_TIMEOUT

    def _observed_target(self):
        store = self._queue.browser_media
        state = store.status()
        if state is None or "video_geometry_v1" not in store.capabilities():
            return None
        return state.get("media_id")

    def _refresh(self):
        target = self._observed_target()
        if target != self._target:
            self._target = target
            self._revision += 1
            self._mode = "original"
            self._mirror = False
            self._status = "changed" if self._pending else "choose" if target else "unavailable"
        return target

    def _check_result(self):
        if self._pending is None:
            return
        command_id, target, deadline = self._pending
        result = self._queue.geometry_result(command_id)
        if result is not None:
            self._pending = None
            if self._observed_target() != target:
                self._refresh()
                self._status = "changed"
            elif result.get("id") == command_id and result.get("outcome") == "completed":
                self._status = "completed"
            else:
                self._status = "unavailable"
        elif self._clock() >= deadline:
            self._pending = None
            self._status = "unconfirmed"
        if self._pending is None and self._reset_after_pending:
            self._mode, self._mirror = "original", False
            self._revision += 1
            self._reset_after_pending = False
            if self._status == "completed":
                self._status = "choose" if self._target else "unavailable"

    def snapshot(self):
        with self._lock:
            if self._visible:
                self._refresh()
            self._check_result()
            return {
                "visible": self._visible,
                "instance": self._instance,
                "opening": self._opening,
                "revision": self._revision,
                "available": self._target is not None,
                "busy": self._pending is not None,
                "mode": self._mode,
                "mirror": self._mirror,
                "status": self._status,
            }

    def open(self):
        with self._lock:
            # A new phone-open request invalidates delayed overlay actions.
            self._opening = secrets.token_hex(16)
            self._revision += 1
            if not self._visible:
                self._check_result()
                if self._pending is None:
                    # The phone may have changed the picture while closed.
                    self._target = None
                    self._mode, self._mirror, self._status = "original", False, "unavailable"
                else:
                    self._reset_after_pending = True
            self._visible = True
            self._refresh()
            return self.snapshot()

    def close(self, opening=None):
        with self._lock:
            if opening is not None and opening != self._opening:
                raise ValueError("video menu changed")
            if self._visible:
                self._visible = False
                self._revision += 1
            return self.snapshot()

    def choose(self, mode, mirror, revision):
        with self._lock:
            self._refresh()
            self._check_result()
            if (
                not self._visible
                or type(revision) is not int
                or revision != self._revision
                or self._target is None
                or self._pending is not None
                or not isinstance(mode, str)
                or mode not in MODES
                or type(mirror) is not bool
            ):
                raise ValueError("video menu unavailable or invalid choice")
            self._mode, self._mirror, self._status = mode, mirror, "choose"
            self._revision += 1
            return self.snapshot()

    def apply(self, revision):
        with self._lock:
            expected = self._target
            self._refresh()
            self._check_result()
            if (
                not self._visible
                or type(revision) is not int
                or revision != self._revision
                or expected is None
                or self._target != expected
                or self._pending
            ):
                raise ValueError("video menu unavailable or changed")
            try:
                command_id = self._queue.push_geometry(expected, self._mode, self._mirror)
            except (ValueError, QueueFullError):
                self._status = "unavailable"
                return self.snapshot()
            self._pending = (command_id, expected, self._clock() + RESULT_TIMEOUT)
            self._revision += 1  # Consume the submitted proposal, even if its result is lost.
            self._status = "pending"
            return self.snapshot()
