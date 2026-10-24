"""Bounded login and authenticated browser-command POST routes."""

import json
import os
import subprocess
from urllib.parse import urlparse

from . import audio
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
    if path == "/api/system/kde":
        expected_host = f"127.0.0.1:{handler.server.server_port}"
        if (
            not local_ui
            or handler.headers.get("Host") != expected_host
            or os.environ.get("AD_LINUX_TV_KIOSK") != "1"
        ):
            return handler.send(403, "{}")
        try:
            if handler.read_payload() != {}:
                return handler.send(400, "{}")
            result = subprocess.run(
                [
                    "/usr/bin/sudo",
                    "-n",
                    "/usr/bin/systemctl",
                    "--no-block",
                    "start",
                    "ad-linux-tv-switch-kde.service",
                ],
                check=False,
                capture_output=True,
                timeout=5,
            )
        except OverflowError:
            return handler.send(413, "{}")
        except BodyTimeout:
            return handler.send(408, "{}", headers=(("Connection", "close"),))
        except (OSError, subprocess.TimeoutExpired):
            return handler.send(503, "{}")
        except Exception:
            return handler.send(400, "{}")
        return handler.send(202 if result.returncode == 0 else 503, "{}")
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
    if path == "/api/input":
        if (
            not token
            or not sessions.csrf_valid(token, handler.headers.get("X-CSRF-Token"))
            or os.environ.get("AD_LINUX_TV_KIOSK") != "1"
        ):
            return handler.send(403, "{}")
        return handle_input(handler)
    if path == "/api/audio":
        local_audio = local_ui and handler.headers.get("Host") == (
            f"127.0.0.1:{handler.server.server_port}"
        )
        if (
            os.environ.get("AD_LINUX_TV_KIOSK") != "1"
            or not (local_audio or token)
            or (
                not local_audio
                and not sessions.csrf_valid(token, handler.headers.get("X-CSRF-Token"))
            )
        ):
            return handler.send(403, "{}")
        try:
            result = audio.apply(handler.read_payload())
        except OverflowError:
            return handler.send(413, "{}")
        except BodyTimeout:
            return handler.send(408, "{}", headers=(("Connection", "close"),))
        except audio.AudioUnavailable:
            return handler.send(503, "{}")
        except Exception:
            return handler.send(400, "{}")
        return handler.send(200, json.dumps(result))
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


def handle_input(handler):
    try:
        data = handler.read_payload()
        if not isinstance(data, dict) or len(data) != 1:
            raise ValueError("invalid input")
        if "text" in data:
            value = data["text"]
            if not isinstance(value, str) or not 1 <= len(value) <= 512 or not value.isprintable():
                raise ValueError("invalid text")
            command = ["/usr/bin/wtype", "-"]
            payload = value.encode("utf-8")
        elif data.get("key") in ("enter", "backspace", "tab", "shift-tab", "address", "escape"):
            key = data["key"]
            command = {
                "enter": ["/usr/bin/wtype", "-k", "Return"],
                "backspace": ["/usr/bin/wtype", "-k", "BackSpace"],
                "tab": ["/usr/bin/wtype", "-k", "Tab"],
                "shift-tab": ["/usr/bin/wtype", "-M", "shift", "-k", "Tab"],
                "address": ["/usr/bin/wtype", "-M", "ctrl", "-k", "l"],
                "escape": ["/usr/bin/wtype", "-k", "Escape"],
            }[key]
            payload = None
        else:
            raise ValueError("invalid key")
        result = subprocess.run(
            command,
            input=payload,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except OverflowError:
        return handler.send(413, "{}")
    except BodyTimeout:
        return handler.send(408, "{}", headers=(("Connection", "close"),))
    except (OSError, subprocess.TimeoutExpired):
        return handler.send(503, "{}")
    except Exception:
        return handler.send(400, "{}")
    return handler.send(200 if result.returncode == 0 else 503, "{}")


def handle_ack(handler, queue):
    if not handler.valid_bridge():
        return handler.send(403, "{}")
    try:
        data = handler.read_payload()
        if not isinstance(data, dict) or set(data) != {"id", "outcome", "reason"}:
            raise ValueError("invalid acknowledgement")
        outcome, reason = data["outcome"], data["reason"]
        reasons = {"invalid_id", "invalid_command", "retry_exhausted", "interrupted", "operation"}
        if outcome not in {"completed", "failed", "uncertain"}:
            raise ValueError("invalid acknowledgement outcome")
        if (outcome == "completed" and reason is not None) or (
            outcome != "completed" and reason not in reasons
        ):
            raise ValueError("invalid acknowledgement reason")
        if not isinstance(data["id"], str) or not queue.acknowledge(data["id"], outcome, reason):
            return handler.send(409, "{}")
    except OverflowError:
        return handler.send(413, "{}")
    except BodyTimeout:
        return handler.send(408, "{}", headers=(("Connection", "close"),))
    except Exception:
        return handler.send(400, "{}")
    return handler.send(200, "{}")
