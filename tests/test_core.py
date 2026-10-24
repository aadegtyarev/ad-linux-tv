"""Configuration and command policy regression tests."""

import base64
import hashlib

import pytest
import yaml

from ad_linux_tv.config import load_config, verify_pin
from ad_linux_tv.defaults import default_services


def config_data():
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


def test_valid_config_and_pin(tmp_path):
    data = load_config(write_config(tmp_path, config_data()))
    assert verify_pin("1234", data["auth"])
    assert not verify_pin("bad", data["auth"])
    assert not verify_pin(1234, data["auth"])


def test_unknown_keys_and_invalid_service_fields_rejected(tmp_path):
    data = config_data() | {"secret_sentinel": "must-not-leak"}
    path = write_config(tmp_path, data)
    with pytest.raises(ValueError, match="expected bind") as error:
        load_config(path)
    assert "must-not-leak" not in str(error.value)
    data = config_data()
    data["services"][0]["url"] = "http://user:password@example.test"
    with pytest.raises(ValueError, match="safe HTTPS"):
        load_config(write_config(tmp_path, data))


def test_duplicate_yaml_keys_are_rejected(tmp_path):
    path = tmp_path / "duplicate.yaml"
    path.write_text("bind: 0.0.0.0\nbind: 127.0.0.1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid YAML syntax"):
        load_config(path)


def test_malformed_yaml_error_does_not_echo_secret(tmp_path):
    path = tmp_path / "malformed.yaml"
    path.write_text("pin: 'secret_sentinel\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid YAML syntax") as error:
        load_config(path)
    assert "secret_sentinel" not in str(error.value)


@pytest.mark.parametrize("field,value", [("port", 8766), ("page_size", 0), ("page_size", 101)])
def test_port_and_page_size_are_bounded(tmp_path, field, value):
    data = config_data()
    data[field] = value
    with pytest.raises(ValueError, match="Invalid configuration"):
        load_config(write_config(tmp_path, data))


def test_cli_starts_server_without_init_config(tmp_path, monkeypatch):
    import ad_linux_tv.cli as cli

    path = write_config(tmp_path, config_data())
    served = []
    monkeypatch.setattr("sys.argv", ["ad-linux-tv", "--config", str(path)])
    monkeypatch.setattr(cli, "serve", served.append)
    cli.main()
    assert len(served) == 1
    assert served[0]["port"] == 8765


def test_cli_init_config_creates_usable_private_config(tmp_path, monkeypatch):
    import ad_linux_tv.cli as cli

    path = tmp_path / "new-config.yaml"
    monkeypatch.setattr("sys.argv", ["ad-linux-tv", "init-config", "--config", str(path)])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: "test-pin-1234")
    cli.main()
    assert path.stat().st_mode & 0o777 == 0o600
    assert verify_pin("test-pin-1234", load_config(path)["auth"])
