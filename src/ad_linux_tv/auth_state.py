"""Bounded in-memory rate-limit and authenticated-session state."""

import json
import os
import secrets
import stat
import tempfile
import time
from collections import OrderedDict
from pathlib import Path
from threading import RLock


class RateLimiter:
    def __init__(self, max_clients=1024, max_per_client=2, max_inflight=16):
        self.clients = OrderedDict()
        self.max_clients = max_clients
        self.max_per_client = max_per_client
        self.max_inflight = max_inflight
        self.inflight = 0
        self.lock = RLock()

    def reserve(self, client, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            attempts, until, active = self.clients.get(client, (0, 0, 0))
            if until > now or active >= self.max_per_client or self.inflight >= self.max_inflight:
                return False
            if client not in self.clients and len(self.clients) >= self.max_clients:
                stale = next((key for key, value in self.clients.items() if value[2] == 0), None)
                if stale is None:
                    return False
                del self.clients[stale]
            self.clients[client] = (attempts, until, active + 1)
            self.clients.move_to_end(client)
            self.inflight += 1
            return True

    def complete(self, client, success, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            attempts, until, active = self.clients.get(client, (0, 0, 0))
            if active:
                active -= 1
                self.inflight -= 1
            if success:
                attempts, until = 0, 0
            elif success is False and (not until or until <= now):
                attempts += 1
                until = now + min(900, 2 ** min(attempts, 9))
            self.clients[client] = (attempts, until, active)
            self.clients.move_to_end(client)

    def locked(self, client, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            return self.clients.get(client, (0, 0, 0))[1] > now


class Sessions:
    def __init__(
        self, lifetime=14 * 24 * 60 * 60, max_sessions=4096, storage_path=None, auth_tag=None
    ):
        self.tokens = OrderedDict()
        self.csrf_tokens = {}
        self.lifetime = lifetime
        self.max_sessions = max_sessions
        self.lock = RLock()
        self.storage_path = Path(storage_path) if storage_path else None
        self.auth_tag = auth_tag
        self._load()

    def _load(self):
        if self.storage_path is None or not self.auth_tag:
            return
        try:
            info = self.storage_path.lstat()
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_mode & 0o077
                or info.st_size > 1_000_000
            ):
                return
            data = json.loads(self.storage_path.read_text())
            if data.get("auth_tag") != self.auth_tag:
                self._save()
                return
            if not isinstance(data.get("sessions"), list):
                return
            now = time.time()
            for item in data["sessions"][-self.max_sessions :]:
                if (
                    not isinstance(item, list)
                    or len(item) != 3
                    or not all(
                        isinstance(value, str) and 20 <= len(value) <= 128
                        for value in (item[0], item[1])
                    )
                    or type(item[2]) not in (int, float)
                    or not 0 <= now - item[2] < self.lifetime
                ):
                    continue
                token, csrf, issued = item
                self.tokens[token] = issued
                self.csrf_tokens[token] = csrf
        except (OSError, ValueError, TypeError, AttributeError):
            return

    def _save(self):
        if self.storage_path is None or not self.auth_tag:
            return
        temporary = None
        try:
            self.storage_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", dir=self.storage_path.parent, delete=False
            ) as stream:
                temporary = Path(stream.name)
                os.fchmod(stream.fileno(), 0o600)
                json.dump(
                    {
                        "auth_tag": self.auth_tag,
                        "sessions": [
                            [token, self.csrf_tokens[token], issued]
                            for token, issued in self.tokens.items()
                        ],
                    },
                    stream,
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.storage_path)
        except OSError:
            pass
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def create(self, now=None):
        now = time.time() if now is None else now
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.lock:
            self.tokens[token] = now
            self.csrf_tokens[token] = csrf
            while len(self.tokens) > self.max_sessions:
                expired, _ = self.tokens.popitem(last=False)
                self.csrf_tokens.pop(expired, None)
            self._save()
        return token, csrf

    def valid(self, token, now=None):
        now = time.time() if now is None else now
        with self.lock:
            issued = self.tokens.get(token)
            if issued is None or now - issued >= self.lifetime:
                self.tokens.pop(token, None)
                self.csrf_tokens.pop(token, None)
                self._save()
                return False
            self.tokens.move_to_end(token)
            return True

    def csrf_valid(self, token, csrf, now=None):
        now = time.time() if now is None else now
        with self.lock:
            expected = self.csrf_tokens.get(token)
            issued = self.tokens.get(token)
            if issued is None or now - issued >= self.lifetime:
                self.tokens.pop(token, None)
                self.csrf_tokens.pop(token, None)
                self._save()
                return False
            return expected is not None and secrets.compare_digest(expected, csrf or "")

    def csrf_for(self, token):
        if not self.valid(token):
            return None
        with self.lock:
            return self.csrf_tokens.get(token)

    def reset(self, auth_tag):
        with self.lock:
            self.auth_tag = auth_tag
            self.tokens.clear()
            self.csrf_tokens.clear()
            self._save()
