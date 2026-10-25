"""Private settings shared by the local TV and paired phone."""

import base64
import hashlib
import json
import os
import re
import secrets
import subprocess
import tempfile
from pathlib import Path
from threading import RLock, Timer

import yaml


class SettingsError(ValueError):
    pass


def validate_proxy(value):
    if not isinstance(value, dict) or value.get("mode") not in ("system", "none", "custom"):
        raise SettingsError("invalid proxy mode")
    if value["mode"] != "custom":
        if set(value) != {"mode"}:
            raise SettingsError("invalid proxy fields")
        return dict(value)
    if set(value) != {"mode", "protocol", "host", "port"} or value["protocol"] not in (
        "http",
        "socks5",
    ):
        raise SettingsError("invalid custom proxy")
    host = value["host"]
    if (
        not isinstance(host, str)
        or not re.fullmatch(r"[A-Za-z0-9.:-]{1,253}", host)
        or host.startswith("-")
    ):
        raise SettingsError("invalid proxy host")
    if type(value["port"]) is not int or not 1 <= value["port"] <= 65535:
        raise SettingsError("invalid proxy port")
    return dict(value)


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as output:
            temporary = Path(output.name)
            os.fchmod(output.fileno(), 0o600)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def proxy_prefs(proxy):
    mode = proxy["mode"]
    bypass = "localhost, 127.0.0.1, 192.168.0.0/16, 10.0.0.0/8, 172.16.0.0/12"
    if mode == "system":
        return {"network.proxy.type": 5, "network.proxy.no_proxies_on": bypass}
    if mode == "none":
        return {"network.proxy.type": 0}
    host = proxy["host"]
    port = proxy["port"]
    prefs = {
        "network.proxy.type": 1,
        "network.proxy.no_proxies_on": bypass,
    }
    if proxy["protocol"] == "http":
        prefs.update(
            {
                "network.proxy.http": host,
                "network.proxy.http_port": port,
                "network.proxy.ssl": host,
                "network.proxy.ssl_port": port,
            }
        )
    else:
        prefs.update(
            {
                "network.proxy.socks": host,
                "network.proxy.socks_port": port,
                "network.proxy.socks_version": 5,
                "network.proxy.socks_remote_dns": True,
            }
        )
    return prefs


def write_proxy_profile(path, proxy):
    path = Path(path)
    existing = path.read_text() if path.exists() else ""
    kept = [
        line
        for line in existing.splitlines()
        if not line.lstrip().startswith('user_pref("network.proxy.')
    ]
    for key, value in proxy_prefs(proxy).items():
        kept.append(f"user_pref({json.dumps(key)}, {json.dumps(value)});")
    atomic_write(path, "\n".join(kept) + "\n")


class SettingsManager:
    def __init__(self, config, config_path, sessions, pin_file=None, profile=None):
        self.config = config
        self.path = Path(config_path) if config_path else None
        self.sessions = sessions
        self.pin_file = Path(pin_file) if pin_file else None
        self.profile = Path(profile or Path.home() / "snap/firefox/common/ad-linux-tv-profile")
        self.lock = RLock()
        self.magnified = False
        self.proxy_restart_required = False

    def proxy(self):
        if "proxy" in self.config:
            return self.config["proxy"]
        # Existing Beelink profile predates a config field and uses local Xray.
        try:
            prefs = (self.profile / "user.js").read_text()
            if (
                'user_pref("network.proxy.http", "127.0.0.1")' in prefs
                and 'user_pref("network.proxy.http_port", 1081)' in prefs
            ):
                return {"mode": "custom", "protocol": "http", "host": "127.0.0.1", "port": 1081}
        except OSError:
            pass
        return {"mode": "system"}

    def state(self):
        with self.lock:
            return {
                "require_pin": self.config["auth"].get("require_pin", True),
                "magnifier": self.magnified,
                "proxy": self.proxy(),
                "proxy_restart_required": self.proxy_restart_required,
                "pointer_acceleration": self.config.get("pointer", {}).get("acceleration", 50),
            }

    def audio_levels(self):
        with self.lock:
            return dict(self.config.get("audio", {"browser": 100, "player": 100}))

    def set_audio_level(self, name, value):
        if name not in ("browser", "player") or type(value) is not int or not 0 <= value <= 100:
            raise SettingsError("invalid audio level")
        with self.lock:
            levels = self.audio_levels()
            if levels[name] != value:
                levels[name] = value
                self._save_config(dict(self.config, audio=levels))

    def _save_config(self, candidate):
        if self.path is None:
            raise OSError("settings path unavailable")
        atomic_write(self.path, yaml.safe_dump(candidate, allow_unicode=True))
        self.config.clear()
        self.config.update(candidate)

    def update(self, action):
        if not isinstance(action, dict) or set(action) != {"setting", "value"}:
            raise SettingsError("invalid settings action")
        with self.lock:
            setting, value = action["setting"], action["value"]
            if setting == "pin":
                if (
                    not isinstance(value, dict)
                    or set(value) != {"enabled", "pin", "confirm"}
                    or type(value["enabled"]) is not bool
                ):
                    raise SettingsError("invalid PIN action")
                if value["enabled"]:
                    if self.pin_file is None:
                        raise OSError("PIN display unavailable")
                    pin = value["pin"]
                    if (
                        not isinstance(pin, str)
                        or not re.fullmatch(r"[0-9]{4}", pin)
                        or pin != value["confirm"]
                    ):
                        raise SettingsError("PIN must be four matching digits")
                    salt = secrets.token_bytes(16)
                    verifier = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 310_000)
                    auth = {
                        "salt": base64.b64encode(salt).decode(),
                        "verifier": base64.b64encode(verifier).decode(),
                        "require_pin": True,
                    }
                else:
                    if value["pin"] is not None or value["confirm"] is not None:
                        raise SettingsError("PIN fields must be empty")
                    if not self.config["auth"].get("require_pin", True):
                        return self.state()
                    auth = dict(self.config["auth"], require_pin=False)
                candidate = dict(self.config, auth=auth)
                old_pin = (
                    self.pin_file.read_text() if self.pin_file and self.pin_file.exists() else None
                )
                if value["enabled"] and self.pin_file:
                    atomic_write(self.pin_file, pin + "\n")
                try:
                    self._save_config(candidate)
                except OSError:
                    if self.pin_file:
                        if old_pin is None:
                            self.pin_file.unlink(missing_ok=True)
                        else:
                            atomic_write(self.pin_file, old_pin)
                    raise
                tag = hashlib.sha256(
                    (
                        auth["verifier"] if auth["require_pin"] else f"{auth['verifier']}:no-pin"
                    ).encode()
                ).hexdigest()
                self.sessions.reset(tag)
            elif setting == "proxy":
                proxy = validate_proxy(value)
                previous = self.proxy()
                if proxy != previous:
                    candidate = dict(self.config, proxy=proxy)
                    profile_path = self.profile / "user.js"
                    old_prefs = profile_path.read_text() if profile_path.exists() else None
                    write_proxy_profile(profile_path, proxy)
                    try:
                        self._save_config(candidate)
                    except OSError:
                        if old_prefs is None:
                            profile_path.unlink(missing_ok=True)
                        else:
                            atomic_write(profile_path, old_prefs)
                        raise
                    self.proxy_restart_required = True
            elif setting == "pointer_acceleration":
                if type(value) is not int or not 0 <= value <= 100:
                    raise SettingsError("invalid pointer acceleration")
                if value != self.config.get("pointer", {}).get("acceleration", 50):
                    self._save_config(dict(self.config, pointer={"acceleration": value}))
            elif setting == "magnifier":
                if type(value) is not bool:
                    raise SettingsError("invalid magnifier state")
                if value != self.magnified:
                    result = subprocess.run(
                        ["/usr/bin/wtype", "-k", "F9"], check=False, capture_output=True, timeout=2
                    )
                    if result.returncode:
                        raise OSError("magnifier unavailable")
                    self.magnified = value
            elif setting == "restart":
                if value is not True or not self.proxy_restart_required:
                    raise SettingsError("restart is not pending")

                def restart_kiosk():
                    try:
                        subprocess.run(
                            [
                                "/usr/bin/sudo",
                                "-n",
                                "/usr/bin/systemctl",
                                "--no-block",
                                "restart",
                                "ad-linux-tv-kiosk.service",
                            ],
                            check=False,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=5,
                        )
                    except (OSError, subprocess.TimeoutExpired):
                        pass

                timer = Timer(0.7, restart_kiosk)
                timer.daemon = True
                timer.start()
            else:
                raise SettingsError("unknown setting")
            return self.state()
