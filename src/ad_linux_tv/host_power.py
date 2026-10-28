"""Session-bound one-use confirmation for the fixed kiosk shutdown unit."""

import hashlib
import os
import secrets
import stat
import subprocess
import time
from pathlib import Path
from threading import Lock

UNIT = "ad-linux-tv-poweroff.service"
UNIT_PATH = Path("/etc/systemd/system") / UNIT


class PowerError(Exception):
    def __init__(self, status):
        self.status = status
        super().__init__("power request rejected")


def shutdown_available():
    if os.environ.get("AD_LINUX_TV_KIOSK") != "1":
        return False
    try:
        info = UNIT_PATH.lstat()
        return stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022
    except OSError:
        return False


def dispatch_shutdown():
    """Only one fixed privileged action. Tests must mock subprocess or inject an actuator."""
    try:
        result = subprocess.run(
            ["/usr/bin/sudo", "-n", "/usr/bin/systemctl", "--no-block", "start", UNIT],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return "requested" if result.returncode == 0 else "unavailable"
    except subprocess.TimeoutExpired:
        # The unit may already have started; never automatically retry.
        return "uncertain"
    except OSError:
        return "unavailable"


class HostPowerControl:
    def __init__(self, *, available=shutdown_available, actuator=None, clock=time.monotonic):
        self.available = available
        self.actuator = actuator or dispatch_shutdown
        self.clock = clock
        self.lock = Lock()
        self.challenges = {}
        self.phase = "idle"

    def status(self):
        with self.lock:
            return self._status()

    def _status(self):
        return {"available": self.available(), "phase": self.phase}

    @staticmethod
    def _owner(session):
        return hashlib.sha256(session.encode()).digest()

    def prepare(self, session):
        with self.lock:
            if self.phase != "idle":
                raise PowerError(409)
            if not self.available():
                raise PowerError(503)
            now = self.clock()
            self.challenges = {
                owner: record for owner, record in self.challenges.items() if record[1] > now
            }
            owner = self._owner(session)
            if owner not in self.challenges and len(self.challenges) >= 64:
                raise PowerError(503)
            nonce = secrets.token_urlsafe(32)
            self.challenges[owner] = (hashlib.sha256(nonce.encode()).digest(), now + 20)
            return {"challenge": nonce, "expires_in": 20}

    def confirm(self, session, challenge):
        if (
            not isinstance(challenge, str)
            or len(challenge) != 43
            or any(
                c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
                for c in challenge
            )
        ):
            raise PowerError(400)
        with self.lock:
            if self.phase != "idle":
                raise PowerError(409)
            record = self.challenges.pop(self._owner(session), None)
            digest = hashlib.sha256(challenge.encode()).digest()
            if (
                record is None
                or record[1] <= self.clock()
                or not secrets.compare_digest(record[0], digest)
            ):
                raise PowerError(409)
            if not self.available():
                raise PowerError(503)
            self.phase = "dispatching"
            self.challenges.clear()
        try:
            outcome = self.actuator()
        except Exception:
            outcome = "uncertain"
        with self.lock:
            self.phase = outcome if outcome in ("requested", "uncertain") else "idle"
            result = self._status()
        return (202 if outcome == "requested" else 503), result
