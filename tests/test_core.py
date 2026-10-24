"""Configuration and command policy regression tests."""
import base64
import hashlib

import pytest

from ad_linux_tv.config import DEFAULT_SERVICES, load_config, verify_pin
from ad_linux_tv.control import CommandQueue


def config(tmp_path):
    salt = b"0123456789abcdef"
    verifier = hashlib.pbkdf2_hmac("sha256", b"1234", salt, 310_000)
    file = tmp_path / "config.yaml"
    import yaml
    file.write_text(yaml.safe_dump({"bind":"127.0.0.1", "port":8765, "page_size":12,
        "auth":{"salt":base64.b64encode(salt).decode(), "verifier":base64.b64encode(verifier).decode()},
        "services":DEFAULT_SERVICES}, allow_unicode=True))
    return file


def test_valid_config_and_pin(tmp_path):
    data = load_config(config(tmp_path))
    assert verify_pin("1234", data["auth"])
    assert not verify_pin("bad", data["auth"])


def test_unknown_config_key_rejected(tmp_path):
    path = config(tmp_path)
    path.write_text(path.read_text() + "secret: value\n")
    with pytest.raises(ValueError, match="Invalid configuration"):
        load_config(path)


def test_queue_only_accepts_allowlisted_commands():
    q = CommandQueue()
    q.push("home")
    assert q.poll() == [{"command":"home", "service_id":None}]
    with pytest.raises(ValueError): q.push("exec", "https://evil.test")
