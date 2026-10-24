"""In-memory browser command queue and heartbeat state."""
from collections import deque
from threading import Lock
import time

COMMANDS = {"open", "home", "back", "refresh", "up", "down", "left", "right", "ok"}


class CommandQueue:
    def __init__(self):
        self.items = deque(maxlen=128)
        self.lock = Lock()
        self.last_seen = None

    def push(self, command, service_id=None):
        if command not in COMMANDS or (command == "open") != (service_id is not None):
            raise ValueError("unsupported browser command")
        with self.lock:
            self.items.append({"command": command, "service_id": service_id})

    def poll(self):
        with self.lock:
            self.last_seen = time.time()
            values = list(self.items)
            self.items.clear()
            return values

    def status(self):
        return {"extension_online": self.last_seen is not None and time.time() - self.last_seen < 30}
