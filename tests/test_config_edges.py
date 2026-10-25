"""Targeted validation and first-write config regressions."""

import base64
import hashlib

import pytest
import yaml

from ad_linux_tv.config import load_config
from ad_linux_tv.config_write import create_config
from ad_linux_tv.defaults import default_services


def make_data():
    salt = b"0123456789abcdef"
    verifier = hashlib.pbkdf2_hmac("sha256", b"1234", salt, 310_000)
    return {
        "bind": "127.0.0.1",
        "port": 8765,
        "page_size": 12,
        "auth": {
            "salt": base64.b64encode(salt).decode(),
            "verifier": base64.b64encode(verifier).decode(),
        },
        "services": default_services(),
    }


def write_config(tmp_path, data):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def test_pin_requirement_is_optional_and_strict(tmp_path):
    data = make_data()
    assert load_config(write_config(tmp_path, data))["auth"]["require_pin"] is True
    data["auth"]["require_pin"] = False
    assert load_config(write_config(tmp_path, data))["auth"]["require_pin"] is False
    data["auth"]["require_pin"] = "false"
    with pytest.raises(ValueError, match="require_pin"):
        load_config(write_config(tmp_path, data))


@pytest.mark.parametrize(
    "url", ["https://example.test:broken/", "https://example.test:65536/", "https://bad_host/"]
)
def test_browser_invalid_https_urls_are_rejected(tmp_path, url):
    data = make_data()
    data["services"][0]["url"] = url
    with pytest.raises(ValueError, match="service URL"):
        load_config(write_config(tmp_path, data))


def test_default_services_are_isolated_between_configurations():
    first = default_services()
    first[0]["name"] = "mutated"
    assert default_services()[0]["name"] == "VK Видео"


def test_generated_config_is_private_atomic_and_never_overwrites(tmp_path):
    path = tmp_path / "new-config.yaml"
    create_config(path, make_data())
    assert path.stat().st_mode & 0o777 == 0o600
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        create_config(path, {"auth": {"verifier": "changed"}})
    assert path.read_bytes() == before
