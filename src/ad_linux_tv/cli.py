"""Command line entry point."""

import argparse
import base64
import os
import secrets
from pathlib import Path

from .config import load_config
from .config_write import create_config
from .defaults import default_services
from .listener import serve


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default=os.environ.get("AD_LINUX_TV_CONFIG", "~/.config/ad-linux-tv/config.yaml"),
    )
    parser.add_argument("init_config", nargs="?", choices=["init-config"], metavar="init-config")
    args = parser.parse_args()
    path = Path(args.config).expanduser()
    if args.init_config:
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
            "audio": {"browser": 100, "player": 100},
            "pointer": {"acceleration": 50},
            "services": default_services(),
        }
        create_config(path, data)
        return
    serve(load_config(path), path)
