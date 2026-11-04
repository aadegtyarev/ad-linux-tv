"""Browser search choice is explicit, reversible and limited to the configured tile."""

import pytest
import yaml
from test_config_edges import make_data

from ad_linux_tv.auth_state import Sessions
from ad_linux_tv.browser_search import SEARCH_URLS
from ad_linux_tv.config import load_config
from ad_linux_tv.service_url import validate_service_url
from ad_linux_tv.settings import SettingsError, SettingsManager
from ad_linux_tv.view_config import service_catalogue, view_fingerprint


def setup_manager(tmp_path, custom=None, present=True):
    data = make_data()
    if custom is not None:
        data["services"][-1]["url"] = custom
    if not present:
        data["services"] = data["services"][:-1]
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True))
    sessions = Sessions(storage_path=tmp_path / "sessions.json", auth_tag="keep")
    settings = SettingsManager(load_config(path), path, sessions, profile=tmp_path / "profile")
    return settings, sessions, path


def browser_url(config):
    return next(s["url"] for s in service_catalogue(config) if s["id"] == "browser")


def test_legacy_default_and_custom_read_without_mutation(tmp_path):
    custom = "https://custom.example/path"
    settings, _, path = setup_manager(tmp_path, custom)
    before = path.read_bytes()
    assert settings.state()["browser_search"] is None
    assert settings.state()["browser_search_custom"] is True
    assert settings.state()["browser_search_available"] is True
    assert browser_url(settings.config) == custom
    assert path.read_bytes() == before
    assert "browser_search" not in load_config(path)


def test_default_remains_yandex(tmp_path):
    settings, _, path = setup_manager(tmp_path)
    assert browser_url(settings.config) == "https://ya.ru/"
    assert settings.state()["browser_search_custom"] is False
    assert "browser_search" not in load_config(path)


@pytest.mark.parametrize("provider", list(SEARCH_URLS))
def test_explicit_choice_is_persistent_reversible_and_does_not_mutate_services(tmp_path, provider):
    custom = "https://custom.example/path"
    settings, sessions, path = setup_manager(tmp_path, custom)
    token, _ = sessions.create()
    services = [dict(s) for s in settings.config["services"]]
    fingerprint = view_fingerprint(settings.config)
    settings.update({"setting": "browser_search", "value": provider})
    assert browser_url(settings.config) == SEARCH_URLS[provider]
    assert settings.config["services"] == services
    assert load_config(path)["services"] == services
    assert load_config(path)["browser_search"] == provider
    assert sessions.valid(token)
    assert view_fingerprint(settings.config) == fingerprint
    validate_service_url(SEARCH_URLS[provider])
    settings.update({"setting": "browser_search", "value": None})
    assert "browser_search" not in load_config(path)
    assert browser_url(settings.config) == custom
    assert settings.config["services"] == services
    assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("invalid", ["", "Google", "https://evil.example/", True, 1, [], {}])
def test_reject_invalid_action_and_config_without_writes(tmp_path, invalid):
    settings, _, path = setup_manager(tmp_path)
    before = path.read_bytes()
    with pytest.raises(SettingsError):
        settings.update({"setting": "browser_search", "value": invalid})
    assert path.read_bytes() == before
    data = yaml.safe_load(before)
    data["browser_search"] = invalid
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match="browser search provider"):
        load_config(path)


def test_absent_browser_never_adds_or_modifies_service(tmp_path):
    settings, _, path = setup_manager(tmp_path, present=False)
    before = path.read_bytes()
    assert settings.state()["browser_search_available"] is False
    with pytest.raises(SettingsError, match="unavailable"):
        settings.update({"setting": "browser_search", "value": "google"})
    assert path.read_bytes() == before


def test_local_settings_api_updates_catalogue_without_weakening_origin(tmp_path, monkeypatch):
    import json
    import threading
    from http.client import HTTPConnection

    from ad_linux_tv.listener import make_server
    from ad_linux_tv.server import make_handler

    settings, _, path = setup_manager(tmp_path, "https://custom.example/path")
    monkeypatch.setenv("AD_LINUX_TV_KIOSK", "1")
    server = make_server("127.0.0.1", 0, make_handler(settings.config, path))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    connection = HTTPConnection("127.0.0.1", server.server_port)
    action = json.dumps({"setting": "browser_search", "value": "google"})
    try:
        connection.request("POST", "/api/settings", action, {"Origin": "http://evil.example"})
        response = connection.getresponse()
        assert response.status == 403
        response.read()
        assert "browser_search" not in load_config(path)
        origin = f"http://127.0.0.1:{server.server_port}"
        connection.request("POST", "/api/settings", action, {"Origin": origin})
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read())["browser_search"] == "google"
        connection.request("GET", "/api/services")
        response = connection.getresponse()
        catalogue = json.loads(response.read())["services"]
        assert (
            next(item["url"] for item in catalogue if item["id"] == "browser")
            == SEARCH_URLS["google"]
        )
        assert load_config(path)["services"][-1]["url"] == "https://custom.example/path"
    finally:
        connection.close()
        server.shutdown()


def test_invalid_extra_action_field_and_unrelated_urls_rejected(tmp_path):
    settings, _, path = setup_manager(tmp_path)
    before = path.read_bytes()
    with pytest.raises(SettingsError):
        settings.update({"setting": "browser_search", "value": "google", "url": "https://x/"})
    assert path.read_bytes() == before
    data = yaml.safe_load(before)
    data["services"][-1]["url"] = "https://example.com/?query=private"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match="service URL"):
        load_config(path)
