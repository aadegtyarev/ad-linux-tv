"""Validated, server-only configuration loading."""

import base64
import hashlib
import hmac
import re
from pathlib import Path

import yaml

from .yaml_config import load_yaml


class ConfigurationError(ValueError):
    """Expected user-facing validation error without input data."""


def load_config(path):
    try:
        data = load_yaml(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or set(data) != {
            "bind",
            "port",
            "page_size",
            "auth",
            "services",
        }:
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
        if not isinstance(auth, dict) or set(auth) != {"salt", "verifier"}:
            raise ConfigurationError("auth must contain salt and verifier")
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
            if not isinstance(service, dict) or set(service) != {"id", "name", "url"}:
                raise ConfigurationError("each service needs id, name and url")
            if (
                not isinstance(service["id"], str)
                or not re.fullmatch(r"[a-z0-9-]{1,32}", service["id"])
                or service["id"] in ids
            ):
                raise ConfigurationError("service ids must be unique safe identifiers")
            if not isinstance(service["name"], str) or not 1 <= len(service["name"]) <= 80:
                raise ConfigurationError("invalid service name")
            if not isinstance(service["url"], str):
                raise ConfigurationError("service URL must be a string")
            from urllib.parse import urlparse

            url = urlparse(service["url"])
            if any(ord(character) <= 32 or ord(character) == 127 for character in service["url"]):
                raise ConfigurationError("service URLs must not contain whitespace or controls")
            if (
                url.scheme != "https"
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
            ):
                raise ConfigurationError(
                    "service URLs must be safe HTTPS URLs without query or fragment"
                )
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
