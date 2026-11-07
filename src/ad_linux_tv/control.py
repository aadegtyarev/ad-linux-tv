"""In-memory browser command queue and heartbeat state."""

import secrets
import time
from collections import OrderedDict, deque
from threading import Lock

from .browser_media import BrowserMedia

GEOMETRY_FAILURE_REASONS = frozenset(
    {
        "geometry_eligibility",
        "geometry_viewport",
        "geometry_ancestor_style",
        "geometry_clipping",
        "geometry_transition",
        "geometry_video_transform",
        "geometry_post_write_current",
        "geometry_post_write_exception",
        "geometry_post_write_closed",
        "geometry_close_mutation",
        "geometry_close_playback",
        "geometry_close_check",
        "geometry_post_write_ownership",
        "geometry_presentation_matrix",
        "geometry_presentation_bounds",
        "geometry_presentation_ratio",
    }
)

COMMANDS = {
    "open",
    "home",
    "back",
    "refresh",
    "up",
    "down",
    "left",
    "right",
    "ok",
    "player_get",
    "player_set",
    "player_pause",
    "fullscreen",
}
FAILURE_TTL_SECONDS = 300
RESULT_TTL_SECONDS = 300
MAX_RESULTS = 128


class QueueFullError(Exception):
    """The bounded command queue cannot accept another command."""


class CommandQueue:
    def __init__(self):
        self.items = deque(maxlen=128)
        self.lock = Lock()
        self.last_seen = None
        self.lease_until = 0
        self.lease_seconds = 15
        self.last_command_failure = None
        self.geometry_notice_until = 0.0
        self.latest_geometry_id = None
        self.geometry_diagnostic = None
        self.results = OrderedDict()
        self.browser_media = BrowserMedia()

    def push(self, command, service_id=None, volume=None):
        if (
            command not in COMMANDS
            or (command == "open") != (service_id is not None)
            or (command == "player_set" and (type(volume) is not int or not 0 <= volume <= 100))
            or (command != "player_set" and volume is not None)
        ):
            raise ValueError("unsupported browser command")
        with self.lock:
            if len(self.items) == self.items.maxlen:
                raise QueueFullError("browser command queue is full")
            command_id = secrets.token_urlsafe(12)
            item = {"id": command_id, "command": command, "service_id": service_id}
            if command == "player_set":
                item["volume"] = volume
            self.items.append(item)
            return command_id

    def push_media(self, action, media_id, position=None):
        state = self.browser_media.status()
        if (
            state is None
            or state["media_id"] != media_id
            or action not in ("play", "pause", "seek")
            or (
                action == "seek"
                and (
                    type(position) is not int
                    or not state["can_seek"]
                    or not 0 <= position <= state["duration"]
                )
            )
            or (action != "seek" and position is not None)
        ):
            raise ValueError("HTML media unavailable or changed")
        with self.lock:
            if len(self.items) == self.items.maxlen:
                raise QueueFullError("browser command queue is full")
            command_id = secrets.token_urlsafe(12)
            self.items.append(
                {
                    "id": command_id,
                    "command": "media",
                    "service_id": None,
                    "action": action,
                    "media_id": media_id,
                    "position": position,
                    "deadline": int((time.time() + 5) * 1000),
                }
            )
            return command_id

    def push_geometry(self, media_id, mode, mirror):
        """Queue one fixed geometry request for the currently observed HTML video.

        This is an internal admission boundary, not an HTTP endpoint. The
        bridge must still revalidate the target and confirm the visual effect.
        """
        state = self.browser_media.status()
        if (
            state is None
            or state["media_id"] != media_id
            or "video_geometry_v1" not in self.browser_media.capabilities()
            or mode not in ("original", "4:3", "16:9")
            or type(mirror) is not bool
        ):
            raise ValueError("HTML video unavailable or changed")
        with self.lock:
            if len(self.items) == self.items.maxlen:
                raise QueueFullError("browser command queue is full")
            command_id = secrets.token_urlsafe(12)
            self.items.append(
                {
                    "id": command_id,
                    "command": "video_geometry",
                    "service_id": None,
                    "media_id": media_id,
                    "mode": mode,
                    "mirror": mirror,
                    "deadline": int((time.time() + 5) * 1000),
                }
            )
            self.latest_geometry_id = command_id
            self.geometry_diagnostic = None
            return command_id

    def poll(self, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            self.last_seen = time.time()
            if not self.items or self.lease_until > now:
                return []
            self.lease_until = now + self.lease_seconds
            return [dict(self.items[0])]

    def acknowledge(self, command_id, outcome="completed", reason=None, volume=None):
        with self.lock:
            if not self.items or self.items[0]["id"] != command_id:
                return False
            item = self.items[0]
            if reason is not None and not isinstance(reason, str):
                return False
            if (
                item["command"] == "video_geometry"
                and reason is not None
                and reason
                not in (
                    GEOMETRY_FAILURE_REASONS
                    | {
                        "invalid_id",
                        "invalid_command",
                        "retry_exhausted",
                        "interrupted",
                        "operation",
                        "no_media",
                        "unsupported",
                        "transition_busy",
                    }
                )
            ):
                return False
            if (reason == "transition_busy" or reason in GEOMETRY_FAILURE_REASONS) and (
                item["command"] != "video_geometry" or outcome != "failed"
            ):
                return False
            player = item["command"] in {"player_get", "player_set", "player_pause"}
            if (player and outcome == "completed") != (type(volume) is int and 0 <= volume <= 100):
                return False
            self.items.popleft()
            self.lease_until = 0
            self.last_seen = time.time()
            if player or item["command"] == "video_geometry":
                self.results[command_id] = {
                    "id": command_id,
                    "outcome": outcome,
                    "reason": reason,
                    "volume": volume,
                    "kind": item["command"],
                    "media_id": item.get("media_id"),
                    "recorded_at": time.monotonic(),
                }
                while len(self.results) > MAX_RESULTS:
                    self.results.popitem(last=False)
            if item["command"] == "video_geometry" and command_id == self.latest_geometry_id:
                self.geometry_diagnostic = (
                    {"reason": reason, "recorded_at": time.monotonic()}
                    if outcome == "failed" and reason in GEOMETRY_FAILURE_REASONS
                    else None
                )
            if item["command"] == "video_geometry" and outcome != "completed":
                self.geometry_notice_until = time.monotonic() + 5
            # No playing media is a normal discovery result, not a global remote failure.
            if outcome != "completed" and not (player and reason == "no_media"):
                self.last_command_failure = {
                    "outcome": outcome,
                    "reason": reason,
                    "recorded_at": time.monotonic(),
                }
            return True

    def result(self, command_id):
        with self.lock:
            value = self.results.get(command_id)
            if not value:
                return None
            if time.monotonic() - value["recorded_at"] >= RESULT_TTL_SECONDS:
                del self.results[command_id]
                return None
            return {key: value[key] for key in ("id", "outcome", "reason", "volume")}

    def geometry_notice(self):
        with self.lock:
            return time.monotonic() < self.geometry_notice_until

    def geometry_result(self, command_id):
        """Expose only geometry receipts, not unrelated internal queue results."""
        with self.lock:
            value = self.results.get(command_id)
            if not value or value["kind"] != "video_geometry":
                return None
            if time.monotonic() - value["recorded_at"] >= RESULT_TTL_SECONDS:
                del self.results[command_id]
                return None
            if value["outcome"] == "completed":
                ready, observed_id = self.browser_media.geometry_observation_after(
                    value["recorded_at"]
                )
                if not ready:
                    return None
                if observed_id != value["media_id"]:
                    value["outcome"], value["reason"] = "failed", "no_media"
                    self.geometry_notice_until = time.monotonic() + 5
            return {key: value[key] for key in ("id", "outcome", "reason")}

    def geometry_failure_reason(self):
        """Return only a fresh fixed diagnostic from the latest failure."""
        with self.lock:
            diagnostic = self.geometry_diagnostic
            if diagnostic and time.monotonic() - diagnostic["recorded_at"] < FAILURE_TTL_SECONDS:
                return diagnostic["reason"]
            self.geometry_diagnostic = None
            return None

    def status(self):
        with self.lock:
            online = self.last_seen is not None and time.time() - self.last_seen < 30
            pending = len(self.items)
            failure = self.last_command_failure
            if failure and time.monotonic() - failure["recorded_at"] >= FAILURE_TTL_SECONDS:
                self.last_command_failure = None
                failure = None
            if failure:
                failure = {key: failure[key] for key in ("outcome", "reason")}
                if failure["reason"] in GEOMETRY_FAILURE_REASONS:
                    failure["reason"] = "unsupported"
        capabilities = self.browser_media.capabilities()
        return {
            "bridge_protocol": 1 if capabilities else None,
            "bridge_capabilities": capabilities,
            "extension_online": online,
            "pending_commands": pending,
            "last_command_failure": failure,
        }
