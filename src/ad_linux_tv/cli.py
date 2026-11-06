"""Command line entry point."""

import argparse
import base64
import os
import secrets
import signal
import sys
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
        choices=[
            "init-config",
            "enable-discovery",
            "disable-discovery",
            "ensure-discovery",
            "clear-tv-shortcuts",
        ],
        metavar="command",
    )
    parser.add_argument(
        "--discovery-name", default=None, help="empty name: follow the computer name"
    )
    args = parser.parse_args()
    path = Path(args.config).expanduser()
    if args.init_config == "clear-tv-shortcuts":
        # Recovery must work even if a malformed shortcut mapping blocks startup.
        # Run while the TV service is stopped to avoid concurrent config writes.
        from .settings import atomic_write
        from .yaml_config import load_yaml_for_shortcut_recovery

        try:
            data, removed = load_yaml_for_shortcut_recovery(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("invalid configuration")
            if removed:
                atomic_write(path, yaml.safe_dump(data, allow_unicode=True))
        except (OSError, ValueError, TypeError, RecursionError, yaml.YAMLError):
            print(
                "Cannot clear TV shortcuts: configuration is invalid or unavailable",
                file=sys.stderr,
            )
            raise SystemExit(1) from None
        return
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
