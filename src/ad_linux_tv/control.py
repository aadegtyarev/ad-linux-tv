"""In-memory browser command queue and heartbeat state."""

import secrets
import time
from collections import deque
from threading import Lock

COMMANDS = {"open", "home", "back", "refresh", "up", "down", "left", "right", "ok"}
FAILURE_TTL_SECONDS = 300


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

    def push(self, command, service_id=None):
        if command not in COMMANDS or (command == "open") != (service_id is not None):
            raise ValueError("unsupported browser command")
        with self.lock:
            if len(self.items) == self.items.maxlen:
                raise QueueFullError("browser command queue is full")
            self.items.append(
                {
                    "id": secrets.token_urlsafe(12),
                    "command": command,
                    "service_id": service_id,
                }
            )

    def poll(self, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            self.last_seen = time.time()
            if not self.items or self.lease_until > now:
                return []
            self.lease_until = now + self.lease_seconds
            return [dict(self.items[0])]

    def acknowledge(self, command_id, outcome="completed", reason=None):
        with self.lock:
            if not self.items or self.items[0]["id"] != command_id:
                return False
            self.items.popleft()
            self.lease_until = 0
            self.last_seen = time.time()
            if outcome != "completed":
                self.last_command_failure = {
                    "outcome": outcome,
                    "reason": reason,
                    "recorded_at": time.monotonic(),
                }
            return True

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
        return {
            "extension_online": online,
            "pending_commands": pending,
            "last_command_failure": failure,
        }
