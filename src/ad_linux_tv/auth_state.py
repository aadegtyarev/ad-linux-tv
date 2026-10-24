"""Bounded in-memory rate-limit and authenticated-session state."""

import secrets
import time
from collections import OrderedDict
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
