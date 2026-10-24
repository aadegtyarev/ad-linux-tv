"""Command line entry point."""
import argparse
import base64
import getpass
import hashlib
import os
import secrets
from pathlib import Path

import yaml

from .config import DEFAULT_SERVICES, load_config
from .server import serve


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=os.environ.get("AD_LINUX_TV_CONFIG", "~/.config/ad-linux-tv/config.yaml"))
    parser.add_argument("init-config", nargs="?", choices=["init-config"])
    args = parser.parse_args()
    path = Path(args.config).expanduser()
    if args.init_config:
        pin = getpass.getpass("Choose remote PIN: ")
        if not 4 <= len(pin) <= 128:
            parser.error("PIN must contain 4..128 characters")
        salt = secrets.token_bytes(16)
        verifier = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 310_000)
        data = {"bind": "0.0.0.0", "port": 8765, "page_size": 12,
                "auth": {"salt": base64.b64encode(salt).decode(), "verifier": base64.b64encode(verifier).decode()},
                "services": DEFAULT_SERVICES}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
        path.chmod(0o600)
        return
    serve(load_config(path))
