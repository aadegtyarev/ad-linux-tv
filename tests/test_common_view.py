"""Common mobile defaults are derived; explicit service overrides stay authoritative."""

from copy import deepcopy

import pytest
from test_config_edges import make_data, write_config
from test_settings import manager

from ad_linux_tv.config import load_config
from ad_linux_tv.settings import SettingsError
from ad_linux_tv.view_config import common_view, service_catalogue, view_fingerprint


def test_desktop_default_is_derived_without_rewriting_private_configuration(tmp_path):
    data = make_data()
    path = write_config(tmp_path, data)
    before = path.read_bytes()
    config = load_config(path)
    snapshot = deepcopy(config)
    assert common_view(config) == {"mode": "desktop", "zoom": 125}
    assert all(row["view"] == common_view(config) for row in service_catalogue(config))
    assert config == snapshot and path.read_bytes() == before


def test_common_parameters_do_not_replace_explicit_service_exceptions(tmp_path):
    data = make_data()
    data["view"] = {"mode": "desktop", "zoom": 125}
    data["services"][0]["view"] = {"mode": "mobile", "zoom": 210}
    data["services"].append({"id": "second", "name": "Second", "url": "https://example.org/"})
    config = load_config(write_config(tmp_path, data))
    rows = service_catalogue(config)
    assert rows[0]["view"] == {"mode": "mobile", "zoom": 210}
    assert rows[-1]["view"] == {"mode": "desktop", "zoom": 125}
    changed = deepcopy(config)
    changed["view"]["zoom"] = 150
    assert view_fingerprint(changed) != view_fingerprint(config)
    changed = deepcopy(config)
    changed["auth"]["verifier"] = "opaque"
    assert view_fingerprint(changed) == view_fingerprint(config)


def test_common_view_saves_resets_and_does_not_revoke_sessions(tmp_path):
    settings, sessions, path, profile = manager(tmp_path)
    token, _ = sessions.create()
    before_auth = deepcopy(settings.config["auth"])
    before_profile = (profile / "user.js").read_bytes()
    state = settings.update({"setting": "view", "value": {"mode": "desktop", "zoom": 125}})
    assert state["view"] == {"mode": "desktop", "zoom": 125}
    assert not state["view_restart_required"] and not state["view_profile_ready"]
    assert load_config(path)["view"] == state["view"]
    assert settings.config["auth"] == before_auth and sessions.valid(token)
    assert (profile / "user.js").read_bytes() == before_profile
    reset = settings.update({"setting": "view", "value": None})
    assert reset["view"] == {"mode": "desktop", "zoom": 125}
    assert "view" not in load_config(path)


def test_service_view_override_inherit_and_snapshot_is_private(tmp_path):
    settings, _sessions, path, _profile = manager(tmp_path)
    rows = settings.state()["service_views"]
    assert len(rows) == len(settings.config["services"])
    assert rows[0]["view"] is None
    assert rows[0]["effective_view"] == {"mode": "desktop", "zoom": 125}
    assert set(rows[0]) == {"id", "name", "view", "effective_view"}
    before_auth = deepcopy(settings.config["auth"])
    settings.update(
        {
            "setting": "service_view",
            "value": {"id": rows[0]["id"], "view": {"mode": "mobile", "zoom": 180}},
        }
    )
    assert settings.state()["service_views"][0]["view"] == {"mode": "mobile", "zoom": 180}
    stored = load_config(path)
    assert stored["services"][0]["view"] == {"mode": "mobile", "zoom": 180}
    assert settings.config["auth"] == before_auth
    settings.update({"setting": "service_view", "value": {"id": rows[0]["id"], "view": None}})
    assert "view" not in load_config(path)["services"][0]
    assert settings.state()["service_views"][0]["effective_view"] == {
        "mode": "desktop",
        "zoom": 125,
    }


@pytest.mark.parametrize(
    "value",
    [
        {"id": "unknown", "view": None},
        {"id": "unknown", "view": {"mode": "desktop"}},
        {"id": "x", "view": None, "extra": 1},
        {"id": "x", "view": {"mode": "desktop", "zoom": True}},
    ],
)
def test_service_view_rejects_invalid_target_without_mutation(tmp_path, value):
    settings, _, path, _ = manager(tmp_path)
    before = path.read_bytes()
    with pytest.raises(SettingsError):
        settings.update({"setting": "service_view", "value": value})
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "value",
    [
        True,
        {},
        {"mode": "mobile", "zoom": True},
        {"mode": "desktop", "zoom": 301},
        {"mode": "mobile", "script": "forbidden"},
    ],
)
def test_common_view_invalid_update_leaves_config_unchanged(tmp_path, value):
    settings, _, path, _ = manager(tmp_path)
    before = path.read_bytes()
    with pytest.raises(SettingsError):
        settings.update({"setting": "view", "value": value})
    assert path.read_bytes() == before
