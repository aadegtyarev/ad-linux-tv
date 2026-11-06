"""Fixed local-only channel between the TV video panel and its server model."""

import json
import os

from . import security, strict_json
from .http_errors import BodyTimeout

PANEL_PATH = "/api/local-video-panel"
HEADER = "X-AD-Linux-TV-Video-Panel"
HEADER_VALUE = "video-panel-v1"


def trusted_overlay(handler):
    """Do not expose panel actions to LAN clients or cross-origin browser pages."""
    host = f"127.0.0.1:{handler.server.server_port}"
    return (
        os.environ.get("AD_LINUX_TV_KIOSK") == "1"
        and security.loopback_source(handler.client_address[0])
        and handler.headers.get_all("Host") == [host]
        and handler.headers.get_all("Origin") == [f"http://{host}"]
        and handler.headers.get_all(HEADER) == [HEADER_VALUE]
    )


def handle_local_panel(handler, menu, method):
    if not trusted_overlay(handler):
        return handler.send(403, "{}")
    if method == "GET":
        menu.heartbeat()
        return handler.send(200, json.dumps(menu.snapshot()))
    if method != "POST":
        return handler.send(405, "{}")
    try:
        body = handler.read_payload()
        if not isinstance(body, dict):
            raise TypeError("invalid panel action")
        action = body.get("action")
        if action == "open":
            if set(body) != {"action"}:
                raise TypeError("invalid panel action")
            if not menu.overlay_online():
                return handler.send(503, "{}")
            return handler.send(200, json.dumps(menu.open()))
        if action == "close":
            valid_shape = set(body) == {"action", "instance", "opening"} and isinstance(
                body.get("opening"), str
            )
        elif action == "apply":
            valid_shape = set(body) == {"action", "instance", "revision"}
        elif action == "choose":
            valid_shape = set(body) == {"action", "instance", "revision", "mode", "mirror"}
        else:
            valid_shape = False
        if not valid_shape or (action != "close" and type(body.get("revision")) is not int):
            raise TypeError("invalid panel action")
        if not menu.matches_instance(body.get("instance")):
            raise ValueError("panel instance changed")
        if action == "close":
            state = menu.close(body["opening"])
        elif action == "choose":
            state = menu.choose(body["mode"], body["mirror"], body["revision"])
        else:
            state = menu.apply(body["revision"])
    except OverflowError:
        return handler.send(413, "{}")
    except BodyTimeout:
        return handler.send(408, "{}", headers=(("Connection", "close"),))
    except (TypeError, json.JSONDecodeError, strict_json.DuplicateJSONError):
        return handler.send(400, "{}")
    except ValueError:
        return handler.send(409, "{}")
    return handler.send(200, json.dumps(state))
