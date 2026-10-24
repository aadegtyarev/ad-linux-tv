"""Validation for client and HTTP host addresses."""

import ipaddress
import re
from urllib.parse import urlsplit

# This non-simple header blocks ordinary cross-site requests; it is not an authentication secret.
BRIDGE_HEADER = "X-AD-Linux-TV-Bridge"
BRIDGE_VALUE = "ad-linux-tv-v1"


def private_source(value):
    try:
        address = ipaddress.ip_address(value)
        if address.version == 6 and address.ipv4_mapped:
            address = address.ipv4_mapped
        if address.is_loopback:
            return True
        ranges = (
            (
                ipaddress.ip_network("10.0.0.0/8"),
                ipaddress.ip_network("172.16.0.0/12"),
                ipaddress.ip_network("192.168.0.0/16"),
            )
            if address.version == 4
            else (ipaddress.ip_network("fc00::/7"),)
        )
        return any(address in network for network in ranges)
    except ValueError:
        return False


def loopback_source(value):
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def loopback_host(host_header):
    try:
        host = urlsplit(f"//{host_header}").hostname
        return host == "localhost" or bool(host and ipaddress.ip_address(host).is_loopback)
    except ValueError:
        return False


def remote_url(host_header, port):
    if not isinstance(host_header, str) or any(
        ord(character) <= 32 or ord(character) == 127 for character in host_header
    ):
        return None
    try:
        parsed = urlsplit(f"//{host_header}")
        host = parsed.hostname
        given_port = parsed.port
        if (
            not host
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
            or given_port not in (None, port)
        ):
            return None
        try:
            address = ipaddress.ip_address(host)
            authority = f"[{address.compressed}]" if address.version == 6 else address.compressed
        except ValueError:
            labels = host.rstrip(".").split(".")
            label_pattern = re.compile(r"(?i)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
            if len(host) > 253 or not all(label_pattern.fullmatch(label) for label in labels):
                return None
            authority = host.lower()
        return f"http://{authority}:{port}/remote"
    except ValueError:
        return None
