"""Bounded login and authenticated browser-command POST routes."""

import json
from urllib.parse import urlparse

from .config import verify_pin
from .control import QueueFullError
from .http_errors import BodyTimeout
from .security import loopback_source


def handle_post(handler, config, queue, sessions, failures):
    path = urlparse(handler.path).path
    if path == "/extension/ack":
        return handle_ack(handler, queue)
    local_ui = loopback_source(handler.client_address[0])
    if not handler.valid_origin(local_ui):
        return handler.send(403, "{}")
    if path == "/api/login":
        if not handler.private():
            return handler.send(403, "{}")
        ip = handler.client_address[0]
        if not failures.reserve(ip):
            return handler.send(429, "{}")
        attempt = None
        try:
            try:
                pin = handler.read_payload().get("pin")
            except OverflowError:
                return handler.send(413, "{}")
            except BodyTimeout:
                return handler.send(408, "{}", headers=(("Connection", "close"),))
            except Exception:
                return handler.send(400, "{}")
            attempt = verify_pin(pin, config["auth"])
            if not attempt:
                return handler.send(401, "{}")
            token, csrf = sessions.create()
            cookie = f"session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200"
            return handler.send(200, json.dumps({"csrf": csrf}), headers=(("Set-Cookie", cookie),))
        finally:
            failures.complete(ip, attempt)
    token = handler.authorized()
    if not handler.private() or (not local_ui and not token):
        return handler.send(403, "{}")
    if not local_ui and not sessions.csrf_valid(token, handler.headers.get("X-CSRF-Token")):
        return handler.send(403, "{}")
    try:
        data = handler.read_payload()
        if set(data) - {"command", "service_id"}:
            raise ValueError("unknown command fields")
        command = data["command"]
        service = data.get("service_id")
        service_ids = {entry["id"] for entry in config["services"]}
        if command == "open" and service not in service_ids:
            raise ValueError("unknown service id")
        queue.push(command, service)
    except OverflowError:
        return handler.send(413, "{}")
    except BodyTimeout:
        return handler.send(408, "{}", headers=(("Connection", "close"),))
    except QueueFullError:
        return handler.send(503, "{}")
    except Exception:
        return handler.send(400, "{}")
    return handler.send(202, "{}")


def handle_ack(handler, queue):
    if not handler.valid_bridge():
        return handler.send(403, "{}")
    try:
        data = handler.read_payload()
        if not isinstance(data, dict) or set(data) != {"id"}:
            raise ValueError("invalid acknowledgement")
        if not queue.acknowledge(data["id"]):
            return handler.send(409, "{}")
    except OverflowError:
        return handler.send(413, "{}")
    except BodyTimeout:
        return handler.send(408, "{}", headers=(("Connection", "close"),))
    except Exception:
        return handler.send(400, "{}")
    return handler.send(200, "{}")
