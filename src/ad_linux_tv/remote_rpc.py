"""Phone RPC adapter for the existing, separately maintained HTTP actions."""

import json

from .browser_media import choose_media
from .control import QueueFullError
from .media_session import MediaUnavailable, get_media_monitor
from .pages import get_response
from .post_routes import handle_post

GET_PATHS = frozenset(
    {"/api/services", "/api/status", "/api/audio", "/api/display-timer", "/api/power"}
)
POST_PATHS = frozenset(
    {
        "/api/command",
        "/api/input",
        "/api/pointer",
        "/api/audio",
        "/api/display-timer",
        "/api/settings",
        "/api/power",
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
        self.host_power = getattr(handler, "host_power", None)

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
        self.media = get_media_monitor()

    def media_status(self):
        store = getattr(self.queue, "browser_media", None)
        browser = store.status() if store is not None else None
        try:
            return choose_media(self.media.status(), browser)
        except MediaUnavailable:
            if browser is not None:
                return browser
            raise

    def dispatch(self, method, path, body):
        if not isinstance(method, str) or not isinstance(path, str):
            return 400, {}
        if path == "/api/media":
            if method == "GET" and body is None:
                try:
                    return 200, self.media_status()
                except MediaUnavailable:
                    return 503, {"available": False}
            if method == "POST" and isinstance(body, dict):
                if set(body) not in (
                    {"action"},
                    {"action", "position"},
                    {"action", "media_id"},
                    {"action", "position", "media_id"},
                ):
                    return 400, {}
                if "media_id" in body and (
                    not isinstance(body["media_id"], str)
                    or len(body["media_id"]) != 32
                    or any(char not in "0123456789abcdef" for char in body["media_id"])
                ):
                    return 400, {}
                try:
                    store = getattr(self.queue, "browser_media", None)
                    current = self.media_status() if store is not None and store.status() else {}
                    if current.get("source") == "html":
                        # New HTML operations always require the observed DOM identity.
                        self.queue.push_media(
                            body["action"], body.get("media_id"), body.get("position")
                        )
                        return 202, current  # Accepted, NOT playback/seek confirmation.
                    state = (
                        self.media.command(body["action"], body.get("position"), body["media_id"])
                        if "media_id" in body
                        else self.media.command(body["action"], body.get("position"))
                    )
                    return 200, state
                except ValueError:
                    return 409, {}
                except QueueFullError:
                    return 503, {}
                except MediaUnavailable:
                    return 503, {"available": False}
            return 400, {}
        if method == "GET" and path in GET_PATHS and body is None:
            if path == "/api/display-timer":
                return 200, self.display_timer.status()
            if path == "/api/power":
                power_control = getattr(self.handler, "host_power", None)
                return (200, power_control.status()) if power_control is not None else (503, {})
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
