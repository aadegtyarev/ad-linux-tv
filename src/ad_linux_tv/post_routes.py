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


def handle_post(handler, config, queue, sessions, failures, display_timer):
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
            cookie = f"session={token}; HttpOnly; SameSite=Strict; Path=/"
            cookie += f"; Max-Age={sessions.lifetime}"
            return handler.send(200, json.dumps({"csrf": csrf}), headers=(("Set-Cookie", cookie),))
        finally:
            failures.complete(ip, attempt)
    token = handler.authorized()
    if not handler.private() or (not local_ui and not token):
        return handler.send(403, "{}")
    if path == "/api/display-timer":
        exact_local = local_ui and handler.headers.get("Host") == (
            f"127.0.0.1:{handler.server.server_port}"
        )
        if os.environ.get("AD_LINUX_TV_KIOSK") != "1" or not (
            exact_local
            or (token and sessions.csrf_valid(token, handler.headers.get("X-CSRF-Token")))
        ):
            return handler.send(403, "{}")
        try:
            action = handler.read_payload()
            if action == {"wake": True}:
                okay = display_timer.wake()
            elif isinstance(action, dict) and set(action) == {"minutes"}:
                result = display_timer.set(action["minutes"])
                okay = result["error"] is None
            else:
                raise ValueError("invalid timer action")
        except OverflowError:
            return handler.send(413, "{}")
        except BodyTimeout:
            return handler.send(408, "{}", headers=(("Connection", "close"),))
        except (TypeError, ValueError):
            return handler.send(400, "{}")
        return handler.send(200 if okay else 503, json.dumps(display_timer.status()))
    if path in ("/api/input", "/api/pointer"):
        if (
            not token
            or not sessions.csrf_valid(token, handler.headers.get("X-CSRF-Token"))
            or os.environ.get("AD_LINUX_TV_KIOSK") != "1"
        ):
            return handler.send(403, "{}")
        if display_timer.status()["asleep"] and not display_timer.wake():
            return handler.send(503, "{}")
        return handle_input(handler) if path == "/api/input" else handle_pointer(handler)
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
        if display_timer.status()["asleep"] and not display_timer.wake():
            return handler.send(503, "{}")
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
    if display_timer.status()["asleep"] and not display_timer.wake():
        return handler.send(503, "{}")
    try:
        data = handler.read_payload()
        if set(data) - {"command", "service_id", "volume"}:
            raise ValueError("unknown command fields")
        command = data["command"]
        service = data.get("service_id")
        service_ids = {entry["id"] for entry in config["services"]}
        if command == "open" and service not in service_ids:
            raise ValueError("unknown service id")
        command_id = queue.push(command, service, data.get("volume"))
    except OverflowError:
        return handler.send(413, "{}")
    except BodyTimeout:
        return handler.send(408, "{}", headers=(("Connection", "close"),))
    except QueueFullError:
        return handler.send(503, "{}")
    except Exception:
        return handler.send(400, "{}")
    return handler.send(202, json.dumps({"id": command_id}))


def firefox_active():
    focused = subprocess.run(
        [
            "/usr/bin/wlrctl",
            "toplevel",
            "find",
            "app_id:firefox_firefox",
            "app_id:firefox",
            "state:active",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=2,
        check=False,
    )
    return focused.returncode == 0


def handle_pointer(handler):
    try:
        data = handler.read_payload()
        if not isinstance(data, dict):
            raise ValueError("invalid pointer action")
        if set(data) == {"dx", "dy"}:
            dx, dy = data["dx"], data["dy"]
            if (
                type(dx) is not int
                or type(dy) is not int
                or not -600 <= dx <= 600
                or not -600 <= dy <= 600
                or (dx == 0 and dy == 0)
            ):
                raise ValueError("invalid pointer movement")
            command = ["/usr/bin/wlrctl", "pointer", "move", str(dx), str(dy)]
        elif data == {"click": True}:
            command = ["/usr/bin/wlrctl", "pointer", "click"]
        elif set(data) == {"scroll"}:
            amount = data["scroll"]
            if type(amount) is not int or not -64 <= amount <= 64 or amount == 0:
                raise ValueError("invalid pointer scroll")
            command = ["/usr/bin/wlrctl", "pointer", "scroll", str(amount), "0"]
        else:
            raise ValueError("invalid pointer action")
        if not firefox_active():
            return handler.send(503, "{}")
        result = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
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
        elif data.get("key") in (
            "enter",
            "backspace",
            "tab",
            "shift-tab",
            "address",
            "escape",
            "browser-back",
            "browser-forward",
            "up",
            "down",
            "left",
            "right",
            "ok",
            "system",
            "video-fullscreen",
        ):
            key = data["key"]
            command = {
                "enter": ["/usr/bin/wtype", "-k", "Return"],
                "backspace": ["/usr/bin/wtype", "-k", "BackSpace"],
                "tab": ["/usr/bin/wtype", "-k", "Tab"],
                "shift-tab": ["/usr/bin/wtype", "-M", "shift", "-k", "Tab"],
                "address": ["/usr/bin/wtype", "-M", "ctrl", "-k", "l"],
                "escape": ["/usr/bin/wtype", "-k", "Escape"],
                "browser-back": ["/usr/bin/wtype", "-M", "alt", "-k", "Left", "-m", "alt"],
                "browser-forward": ["/usr/bin/wtype", "-M", "alt", "-k", "Right", "-m", "alt"],
                "up": ["/usr/bin/wtype", "-k", "Up"],
                "down": ["/usr/bin/wtype", "-k", "Down"],
                "left": ["/usr/bin/wtype", "-k", "Left"],
                "right": ["/usr/bin/wtype", "-k", "Right"],
                "ok": ["/usr/bin/wtype", "-k", "Return"],
                "system": ["/usr/bin/wtype", "-k", "F8"],
                "video-fullscreen": ["/usr/bin/wtype", "-k", "f"],
            }[key]
            payload = None
            if key in (
                "browser-back",
                "browser-forward",
                "up",
                "down",
                "left",
                "right",
                "ok",
                "system",
                "video-fullscreen",
            ):
                if not firefox_active():
                    return handler.send(503, "{}")
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
        if (
            not isinstance(data, dict)
            or not {"id", "outcome", "reason"} <= set(data)
            or set(data) - {"id", "outcome", "reason", "volume"}
        ):
            raise ValueError("invalid acknowledgement")
        outcome, reason = data["outcome"], data["reason"]
        reasons = {
            "invalid_id",
            "invalid_command",
            "retry_exhausted",
            "interrupted",
            "operation",
            "no_media",
        }
        if outcome not in {"completed", "failed", "uncertain"}:
            raise ValueError("invalid acknowledgement outcome")
        if (outcome == "completed" and reason is not None) or (
            outcome != "completed" and reason not in reasons
        ):
            raise ValueError("invalid acknowledgement reason")
        if not isinstance(data["id"], str) or not queue.acknowledge(
            data["id"], outcome, reason, data.get("volume")
        ):
            return handler.send(409, "{}")
    except OverflowError:
        return handler.send(413, "{}")
    except BodyTimeout:
        return handler.send(408, "{}", headers=(("Connection", "close"),))
    except Exception:
        return handler.send(400, "{}")
    return handler.send(200, "{}")
