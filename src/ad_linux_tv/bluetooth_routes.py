"""Private Bluetooth authority; principals never come from a client DTO."""

import hashlib
import json
import os

from . import security
from .bluetooth_manager import Principal
from .http_errors import BodyTimeout


def phone_principal(token, connection=None):
    return Principal("phone", hashlib.sha256(token.encode()).hexdigest(), connection)


def handle_bluetooth(handler, sessions, method):
    """Authenticate before touching inventory, including on the ordered phone socket."""
    host = handler.headers.get("Host", "")
    if not handler.private() or not security.direct_host(
        host, handler.connection.getsockname()[0], handler.server.server_port
    ):
        return handler.send(403, "{}")
    socket_principal = getattr(handler, "bluetooth_principal", None)
    local = (
        socket_principal is None
        and os.environ.get("AD_LINUX_TV_KIOSK") == "1"
        and security.loopback_source(handler.client_address[0])
        and host == f"127.0.0.1:{handler.server.server_port}"
        and (method == "GET" or handler.headers.get("X-TV-Launcher") == "1")
    )
    if local:
        if method == "POST" and not handler.valid_origin():
            return handler.send(403, "{}")
        principal = Principal("tv", "launcher")
    else:
        token = handler.authorized()
        if (
            not token
            or not handler.valid_origin()
            or not sessions.csrf_valid(token, handler.headers.get("X-CSRF-Token"))
        ):
            return handler.send(403, "{}")
        principal = phone_principal(token)
        if socket_principal is not None:
            if principal.owner != socket_principal.owner:
                return handler.send(403, "{}")
            principal = socket_principal
    manager = handler.bluetooth_manager
    if method == "GET":
        # GET is bodyless just like the socket allowlist. Do not leave unread
        # framing to become a second request on a persistent HTTP connection.
        try:
            length = int(handler.headers.get("Content-Length", "0"))
            if length > 2048:
                raise OverflowError
            if length != 0 or handler.headers.get("Transfer-Encoding"):
                raise ValueError
        except (ValueError, OverflowError) as error:
            handler.close_connection = True
            return handler.send(413 if isinstance(error, OverflowError) else 400, "{}")
        return handler.send(200, json.dumps({"state": manager.snapshot(principal)}))
    try:
        body = handler.read_payload()
        # RemoteRequest bypasses HTTP framing. Bound the decoded logical body too.
        if len(json.dumps(body, ensure_ascii=False).encode("utf-8")) > 2048:
            raise OverflowError
        status, envelope = manager.request(principal, body)
    except OverflowError:
        return handler.send(413, "{}")
    except BodyTimeout:
        return handler.send(408, "{}", headers=(("Connection", "close"),))
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return handler.send(400, "{}")
    return handler.send(status, json.dumps(envelope))
