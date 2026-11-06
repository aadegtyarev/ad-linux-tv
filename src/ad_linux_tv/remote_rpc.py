"""Phone RPC adapter for the existing, separately maintained HTTP actions."""

import json
import os
import re
from http.client import HTTPMessage

from .bluetooth_routes import handle_bluetooth, phone_principal
from .browser_media import choose_media
from .control import QueueFullError
from .media_session import MediaUnavailable, get_media_monitor
from .pages import get_response
from .post_routes import handle_post
from .tv_shortcut_learner import ShortcutLearningError

GET_PATHS = frozenset(
    {
        "/api/services",
        "/api/status",
        "/api/audio",
        "/api/display-timer",
        "/api/power",
        "/api/bluetooth",
    }
)
POST_PATHS = frozenset(
    {
        "/api/bluetooth",
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

    def __init__(self, handler, path, body, csrf, principal=None):
        self.handler = handler
        self.path = path
        self.body = body
        self.client_address = handler.client_address
        self.server = handler.server
        self.connection = handler.connection
        self.bluetooth_manager = getattr(handler, "bluetooth_manager", None)
        self.tv_shortcut_learner = getattr(handler, "tv_shortcut_learner", None)
        self.bluetooth_principal = principal
        self.headers = HTTPMessage()
        for name, value in handler.headers.items():
            self.headers[name] = value
        # HTTPMessage preserves case-insensitive lookup and duplicate order.
        # Assignment appends, so remove every client spelling before inserting authority.
        del self.headers["X-CSRF-Token"]
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
        self,
        handler,
        config,
        queue,
        sessions,
        failures,
        display_timer,
        static,
        csrf,
        settings=None,
        principal=None,
    ):
        self.handler = handler
        self.bluetooth_manager = getattr(handler, "bluetooth_manager", None)
        self.bluetooth_principal = principal
        self.config = config
        self.queue = queue
        self.sessions = sessions
        self.failures = failures
        self.display_timer = display_timer
        self.static = static
        self.csrf = csrf
        self.settings = settings
        self.media = get_media_monitor()

    def _learner_authorized(self):
        with self.sessions.lock:
            token = self.handler.authorized()
            return bool(
                token
                and self.bluetooth_principal is not None
                and phone_principal(token).owner == self.bluetooth_principal.owner
                and self.sessions.csrf_valid(token, self.csrf)
            )

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
        if path == "/api/bluetooth":
            if not (
                (method == "GET" and body is None) or (method == "POST" and isinstance(body, dict))
            ):
                return 400, {}
            request = RemoteRequest(self.handler, path, body, self.csrf, self.bluetooth_principal)
            handle_bluetooth(request, self.sessions, method)
            status, payload = request.response
            return status, json.loads(payload)
        if path == "/api/tv-shortcut-learn":
            if method != "POST" or not isinstance(body, dict):
                return 400, {}
            learner = getattr(self.handler, "tv_shortcut_learner", None)
            if learner is None or self.bluetooth_principal is None:
                return 503, {"error": "unavailable"}
            action = body.get("action")
            valid_start = action == "start" and set(body) == {"action"}
            valid_existing = (
                action in ("result", "cancel")
                and set(body) == {"action", "id"}
                and isinstance(body["id"], str)
                and re.fullmatch(r"[0-9a-f]{32}", body["id"])
            )
            if not (valid_start or valid_existing):
                return 400, {}
            try:
                # Serialize all learner access with session invalidation, not
                # just the initial admission of the focused capture window.
                with self.sessions.lock:
                    token = self.handler.authorized()
                    if (
                        not token
                        or phone_principal(token).owner != self.bluetooth_principal.owner
                        or not self.sessions.csrf_valid(token, self.csrf)
                    ):
                        return 403, {}
                    if valid_start:
                        return 202, {
                            "id": learner.start(self.bluetooth_principal, self._learner_authorized)
                        }
                    if action == "result":
                        return 200, learner.result(self.bluetooth_principal, body["id"])
                    if learner.retire(self.bluetooth_principal, body["id"]):
                        return 200, {"state": "cancelled"}
                    return 409, {"error": "unavailable"}
            except ShortcutLearningError as error:
                return (409 if str(error) == "busy" else 503), {"error": str(error)}
        if path == "/api/tv-video-panel":
            if method != "POST" or body != {"action": "open"}:
                return 400, {}
            menu = getattr(self.handler, "tv_video_menu", None)
            if os.environ.get("AD_LINUX_TV_KIOSK") != "1" or not menu or not menu.overlay_online():
                return 503, {"error": "panel_unavailable"}
            menu.open()
            return 202, {"accepted": True}
        if path == "/api/video-geometry":
            # The dispatcher is only reached after the socket session, Origin,
            # source and CSRF have been checked. No CSS or scripts come from
            # the client; acknowledgement is distinct from queue admission.
            if method == "GET" and body is None:
                store = self.queue.browser_media
                media = store.status()
                available = media is not None and "video_geometry_v1" in store.capabilities()
                return 200, {
                    "available": available,
                    "media_id": media["media_id"] if available else None,
                }
            if method != "POST" or not isinstance(body, dict):
                return 400, {}
            if set(body) == {"action", "id"} and body["action"] == "result":
                command_id = body["id"]
                if not isinstance(command_id, str) or not re.fullmatch(
                    r"[A-Za-z0-9_-]{16,64}", command_id
                ):
                    return 400, {}
                result = self.queue.geometry_result(command_id)
                return (200, result) if result else (202, {})
            if set(body) != {"action", "media_id", "mode", "mirror"} or body["action"] != "apply":
                return 400, {}
            try:
                command_id = self.queue.push_geometry(
                    body["media_id"], body["mode"], body["mirror"]
                )
            except ValueError:
                return 409, {}
            except QueueFullError:
                return 503, {}
            return 202, {"id": command_id}
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
            request = RemoteRequest(self.handler, path, body, self.csrf, self.bluetooth_principal)
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
