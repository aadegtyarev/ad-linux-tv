"""Command line entry point."""

import argparse
import base64
import os
import secrets
import signal
from pathlib import Path

import yaml

from .config import load_config
from .config_write import create_config
from .defaults import default_services
from .discovery import new_discovery
from .listener import serve


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default=os.environ.get("AD_LINUX_TV_CONFIG", "~/.config/ad-linux-tv/config.yaml"),
    )
    parser.add_argument(
        "init_config",
        nargs="?",
        choices=["init-config", "enable-discovery", "disable-discovery", "ensure-discovery"],
        metavar="command",
    )
    parser.add_argument(
        "--discovery-name", default=None, help="empty name: follow the computer name"
    )
    args = parser.parse_args()
    path = Path(args.config).expanduser()
    if args.init_config in ("enable-discovery", "disable-discovery", "ensure-discovery"):
        from .settings import atomic_write

        data = load_config(path)
        current = data.get("discovery")
        if current is not None and args.init_config == "ensure-discovery":
            return  # An existing choice, including a disabled one, is kept on upgrade.
        if current is None and args.init_config == "disable-discovery":
            return
        value = dict(current) if current else new_discovery()
        if args.discovery_name == "":
            value.pop("name", None)
        elif args.discovery_name is not None:
            value["name"] = args.discovery_name
        value["enabled"] = args.init_config != "disable-discovery"
        from .discovery import validate_discovery

        data["discovery"] = validate_discovery(value)
        atomic_write(path, yaml.safe_dump(data, allow_unicode=True))
        return
    if args.init_config == "init-config":
        salt = secrets.token_bytes(16)
        verifier = secrets.token_bytes(32)
        data = {
            "bind": "0.0.0.0",
            "port": 8765,
            "page_size": 12,
            "auth": {
                "salt": base64.b64encode(salt).decode(),
                "verifier": base64.b64encode(verifier).decode(),
                "require_pin": False,
            },
            "proxy": {"mode": "system"},
            "audio": {"browser": 100, "player": 100, "browser_muted": False},
            "pointer": {"acceleration": 50},
            "discovery": new_discovery(args.discovery_name or None),
            "services": default_services(),
        }
        create_config(path, data)
        return
    config = load_config(path)

    def terminate(_signum, _frame):
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, terminate)
    try:
        serve(config, path)
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGTERM, previous)
