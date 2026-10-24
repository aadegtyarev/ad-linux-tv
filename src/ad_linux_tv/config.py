"""Validated, server-only configuration loading."""

import base64
import hashlib
import hmac
import re
from pathlib import Path

import yaml

from .config_errors import ConfigurationError
from .service_url import validate_service_url
from .yaml_config import load_yaml


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
            if (
                not isinstance(service, dict)
                or not {"id", "name", "url"} <= set(service)
                or set(service) - {"id", "name", "url", "color"}
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
