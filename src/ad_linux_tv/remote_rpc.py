"""Phone RPC adapter for the existing, separately maintained HTTP actions."""

import json

from .pages import get_response
from .post_routes import handle_post

GET_PATHS = frozenset({"/api/services", "/api/status", "/api/audio", "/api/display-timer"})
POST_PATHS = frozenset(
    {
        "/api/command",
        "/api/input",
        "/api/pointer",
        "/api/audio",
        "/api/display-timer",
        "/api/settings",
    }
)


class RemoteRequest:
    """Adapt one socket message to the existing route boundary."""

    def __init__(self, handler, path, body, csrf):
        self.handler = handler
        self.path = path
        self.body = body
        self.client_address = handler.client_address
        self.server = handler.server
        self.headers = dict(handler.headers)
        self.headers["X-CSRF-Token"] = csrf
        self.response = None

    def private(self):
        return self.handler.private()

    def valid_origin(self, local_ui=False):
        return self.handler.valid_origin(local_ui)

    def authorized(self):
        return self.handler.authorized()

    def read_payload(self):
        return self.body

    def send(self, status, body, kind="application/json", headers=()):
        self.response = (status, body)
        return None


class RemoteDispatcher:
    """Keep one phone transport while reusing the established action handlers."""

    def __init__(
        self, handler, config, queue, sessions, failures, display_timer, static, csrf, settings=None
    ):
        self.handler = handler
        self.config = config
        self.queue = queue
        self.sessions = sessions
        self.failures = failures
        self.display_timer = display_timer
        self.static = static
        self.csrf = csrf
        self.settings = settings

    def dispatch(self, method, path, body):
        if not isinstance(method, str) or not isinstance(path, str):
            return 400, {}
        if method == "GET" and path in GET_PATHS and body is None:
            if path == "/api/display-timer":
                return 200, self.display_timer.status()
            previous = self.handler.path
            try:
                self.handler.path = path
                status, payload, _kind = get_response(
                    self.handler, self.config, self.queue, self.static
                )
            finally:
                self.handler.path = previous
            return status, json.loads(payload)
        if (
            method == "GET"
            and path == "/api/settings"
            and body is None
            and self.settings is not None
        ):
            return 200, self.settings.state()
        if method == "POST" and path in POST_PATHS and isinstance(body, dict):
            request = RemoteRequest(self.handler, path, body, self.csrf)
            handle_post(
                request,
                self.config,
                self.queue,
                self.sessions,
                self.failures,
                self.display_timer,
                self.settings,
            )
            status, payload = request.response
            return status, json.loads(payload)
        return 400, {}
