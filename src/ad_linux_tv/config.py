"""Validated, server-only configuration loading."""

import base64
import hashlib
import hmac
import re
from pathlib import Path

import yaml

from .audio import OUTPUT_ID
from .browser_locale import validate_browser
from .config_errors import ConfigurationError
from .discovery import validate_discovery
from .magnifier import validate_magnifier
from .service_url import validate_service_url
from .settings import SettingsError, validate_proxy
from .view_config import validate_view
from .yaml_config import load_yaml


def load_config(path):
    try:
        data = load_yaml(Path(path).read_text(encoding="utf-8"))
        if (
            not isinstance(data, dict)
            or not {"bind", "port", "page_size", "auth", "services"} <= set(data)
            or set(data)
            - {
                "bind",
                "port",
                "page_size",
                "auth",
                "services",
                "proxy",
                "audio",
                "pointer",
                "discovery",
                "magnifier",
                "view",
                "browser",
            }
        ):
            raise ConfigurationError("expected bind, port, page_size, auth and services")
        if not isinstance(data["bind"], str) or not data["bind"]:
            raise ConfigurationError("bind must be an IP address")
        import ipaddress

        ipaddress.ip_address(data["bind"])
        if type(data["port"]) is not int or data["port"] != 8765:
            raise ConfigurationError("port is fixed at 8765 for the Firefox bridge")
        if type(data["page_size"]) is not int or not 1 <= data["page_size"] <= 100:
            raise ConfigurationError("page_size must be 1..100")
        auth = data["auth"]
        if (
            not isinstance(auth, dict)
            or set(auth) - {"salt", "verifier", "require_pin"}
            or not {"salt", "verifier"} <= set(auth)
        ):
            raise ConfigurationError("auth must contain salt and verifier; require_pin is optional")
        if "require_pin" in auth and type(auth["require_pin"]) is not bool:
            raise ConfigurationError("auth.require_pin must be true or false")
        auth.setdefault("require_pin", True)
        proxy = data.get("proxy", {"mode": "system"})
        try:
            validate_proxy(proxy)
        except SettingsError as exc:
            raise ConfigurationError(str(exc)) from None
        levels = data.get("audio", {"browser": 100, "player": 100})
        if (
            not isinstance(levels, dict)
            or not {"browser", "player"} <= set(levels)
            or set(levels) - {"browser", "player", "browser_muted", "output"}
            or any(
                type(levels[name]) is not int or not 0 <= levels[name] <= 100
                for name in ("browser", "player")
            )
            or type(levels.get("browser_muted", False)) is not bool
            or (
                "output" in levels
                and not (
                    isinstance(levels["output"], str) and OUTPUT_ID.fullmatch(levels["output"])
                )
            )
        ):
            raise ConfigurationError(
                "audio levels must be 0..100, browser_muted boolean and output an output ID"
            )
        pointer = data.get("pointer", {"acceleration": 50})
        if (
            not isinstance(pointer, dict)
            or set(pointer) != {"acceleration"}
            or type(pointer["acceleration"]) is not int
            or not 0 <= pointer["acceleration"] <= 100
        ):
            raise ConfigurationError("pointer acceleration must be 0..100")
        if "view" in data:
            try:
                data["view"] = validate_view(data["view"])
            except ValueError as exc:
                raise ConfigurationError(str(exc)) from None
        if "browser" in data:
            try:
                data["browser"] = validate_browser(data["browser"])
            except ValueError as exc:
                raise ConfigurationError(str(exc)) from None
        if "magnifier" in data:
            try:
                data["magnifier"] = validate_magnifier(data["magnifier"])
            except ValueError as exc:
                raise ConfigurationError(str(exc)) from None
        if "discovery" in data:
            try:
                if data["discovery"] is None:
                    raise ValueError("null discovery")
                data["discovery"] = validate_discovery(data["discovery"])
            except (ValueError, TypeError, AttributeError):
                raise ConfigurationError("invalid discovery enabled/id/name") from None
        for key in ("salt", "verifier"):
            base64.b64decode(auth[key], validate=True)
        if (
            len(base64.b64decode(auth["salt"])) < 16
            or len(base64.b64decode(auth["verifier"])) != 32
        ):
            raise ConfigurationError("invalid PIN verifier")
        services = data["services"]
        if not isinstance(services, list) or not services:
            raise ConfigurationError("services must be a non-empty list")
        ids = set()
        for service in services:
            if (
                not isinstance(service, dict)
                or not {"id", "name", "url"} <= set(service)
                or set(service) - {"id", "name", "url", "color", "view"}
            ):
                raise ConfigurationError("each service needs id, name and url; color is optional")
            if (
                not isinstance(service["id"], str)
                or not re.fullmatch(r"[a-z0-9-]{1,32}", service["id"])
                or service["id"] in ids
            ):
                raise ConfigurationError("service ids must be unique safe identifiers")
            if not isinstance(service["name"], str) or not 1 <= len(service["name"]) <= 80:
                raise ConfigurationError("invalid service name")
            validate_service_url(service["url"])
            if "view" in service:
                try:
                    service["view"] = validate_view(service["view"])
                except ValueError as exc:
                    raise ConfigurationError(str(exc)) from None
            if "color" in service and (
                not isinstance(service["color"], str)
                or not re.fullmatch(r"#[0-9a-fA-F]{6}", service["color"])
            ):
                raise ConfigurationError("service color must be a six-digit hex color")
            ids.add(service["id"])
        return data
    except yaml.YAMLError:
        raise ValueError("Invalid configuration: invalid YAML syntax") from None
    except ConfigurationError as exc:
        raise ValueError(f"Invalid configuration: {exc}") from None
    except Exception:
        raise ValueError("Invalid configuration: invalid field value") from None


def verify_pin(pin, auth):
    if not isinstance(pin, str) or len(pin) > 128:
        return False
    salt = base64.b64decode(auth["salt"])
    expected = base64.b64decode(auth["verifier"])
    actual = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 310_000)
    return hmac.compare_digest(actual, expected)
