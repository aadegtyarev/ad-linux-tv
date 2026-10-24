"""Strict browser-navigable HTTPS service URL validation."""

import ipaddress
import re
from urllib.parse import urlsplit

from .config_errors import ConfigurationError


def validate_service_url(value):
    if not isinstance(value, str) or any(ord(char) <= 32 or ord(char) == 127 for char in value):
        raise ConfigurationError("service URL must be a safe HTTPS URL")
    try:
        url = urlsplit(value)
        host = url.hostname
        port = url.port
    except ValueError:
        raise ConfigurationError("service URL has invalid host or port") from None
    if url.scheme != "https" or not url.netloc or not host or url.username or url.password:
        raise ConfigurationError("service URL must be a safe HTTPS URL")
    if port == 0 or url.query or url.fragment or "\\" in url.netloc:
        raise ConfigurationError("service URL has invalid port, query, or fragment")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        try:
            ascii_host = host.encode("idna").decode("ascii")
        except UnicodeError:
            raise ConfigurationError("service URL host is invalid") from None
        labels = ascii_host.rstrip(".").split(".")
        pattern = re.compile(r"(?i)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
        if not all(pattern.fullmatch(label) for label in labels):
            raise ConfigurationError("service URL host is invalid")
