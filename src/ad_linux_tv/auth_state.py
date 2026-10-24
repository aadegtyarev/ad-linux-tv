"""Bounded in-memory rate-limit and authenticated-session state."""

import secrets
import time
from collections import OrderedDict
from threading import RLock


class RateLimiter:
    def __init__(self, max_clients=1024):
        self.clients = OrderedDict()
        self.max_clients = max_clients
        self.lock = RLock()

    def locked(self, client, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            _, until = self.clients.get(client, (0, 0))
            if until <= now:
                return False
            self.clients.move_to_end(client)
            return True

    def fail(self, client, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            attempts, _ = self.clients.get(client, (0, 0))
            delay = min(900, 2 ** min(attempts + 1, 9))
            self.clients[client] = (attempts + 1, now + delay)
            self.clients.move_to_end(client)
            while len(self.clients) > self.max_clients:
                self.clients.popitem(last=False)

    def clear(self, client):
        with self.lock:
            self.clients.pop(client, None)


class Sessions:
    def __init__(self, lifetime=43_200, max_sessions=4096):
        self.tokens = OrderedDict()
        self.csrf_tokens = {}
        self.lifetime = lifetime
        self.max_sessions = max_sessions
        self.lock = RLock()

    def create(self, now=None):
        now = time.time() if now is None else now
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.lock:
            self.tokens[token] = now
            self.csrf_tokens[token] = csrf
            while len(self.tokens) > self.max_sessions:
                expired, _ = self.tokens.popitem(last=False)
                self.csrf_tokens.pop(expired, None)
        return token, csrf

    def valid(self, token, now=None):
        now = time.time() if now is None else now
        with self.lock:
            issued = self.tokens.get(token)
            if issued is None or now - issued >= self.lifetime:
                self.tokens.pop(token, None)
                self.csrf_tokens.pop(token, None)
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
                return False
            return expected is not None and secrets.compare_digest(expected, csrf or "")
