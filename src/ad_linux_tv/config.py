"""Validated, server-only configuration loading."""
import base64
import hashlib
import hmac
import re
from pathlib import Path

import yaml

DEFAULT_SERVICES = [
    {"id": "vk", "name": "VK Видео", "url": "https://vk.com/video"},
    {"id": "kinopoisk", "name": "КиноПоиск", "url": "https://hd.kinopoisk.ru/"},
    {"id": "music", "name": "Яндекс Музыка", "url": "https://music.yandex.ru/"},
    {"id": "youtube", "name": "YouTube", "url": "https://www.youtube.com/"},
]


def load_config(path):
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or set(data) != {"bind", "port", "page_size", "auth", "services"}:
            raise ValueError("expected bind, port, page_size, auth and services")
        if not isinstance(data["bind"], str) or not data["bind"]:
            raise ValueError("bind must be an IP address")
        import ipaddress
        ipaddress.ip_address(data["bind"])
        if type(data["port"]) is not int or data["port"] != 8765:
            raise ValueError("port is fixed at 8765 for the Firefox bridge")
        if type(data["page_size"]) is not int or not 1 <= data["page_size"] <= 100:
            raise ValueError("page_size must be 1..100")
        auth = data["auth"]
        if not isinstance(auth, dict) or set(auth) != {"salt", "verifier"}:
            raise ValueError("auth must contain salt and verifier")
        for key in ("salt", "verifier"):
            base64.b64decode(auth[key], validate=True)
        if len(base64.b64decode(auth["salt"])) < 16 or len(base64.b64decode(auth["verifier"])) != 32:
            raise ValueError("invalid PIN verifier")
        services = data["services"]
        if not isinstance(services, list) or not services:
            raise ValueError("services must be a non-empty list")
        ids = set()
        for service in services:
            if not isinstance(service, dict) or set(service) != {"id", "name", "url"}:
                raise ValueError("each service needs id, name and url")
            if not re.fullmatch(r"[a-z0-9-]{1,32}", service["id"]) or service["id"] in ids:
                raise ValueError("service ids must be unique safe identifiers")
            if not isinstance(service["name"], str) or not 1 <= len(service["name"]) <= 80:
                raise ValueError("invalid service name")
            from urllib.parse import urlparse
            url = urlparse(service["url"])
            if url.scheme != "https" or not url.hostname or url.username or url.password:
                raise ValueError("service URLs must be safe HTTPS URLs")
            ids.add(service["id"])
        return data
    except yaml.YAMLError:
        raise ValueError("Invalid configuration: invalid YAML syntax") from None
    except Exception as exc:
        raise ValueError(f"Invalid configuration: {type(exc).__name__}: {exc}") from None


def verify_pin(pin, auth):
    if not isinstance(pin, str) or len(pin) > 128:
        return False
    salt = base64.b64decode(auth["salt"])
    expected = base64.b64decode(auth["verifier"])
    actual = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 310_000)
    return hmac.compare_digest(actual, expected)
