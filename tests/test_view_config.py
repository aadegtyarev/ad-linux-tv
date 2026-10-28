"""Declarative view configuration has no arbitrary UA, header or script surface."""

import pytest
from test_config_edges import make_data, write_config

from ad_linux_tv.config import load_config
from ad_linux_tv.view_config import validate_view


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        {},
        {"mode": "auto"},
        {"mode": []},
        {"mode": "mobile", "zoom": None},
        {"mode": "mobile", "zoom": True},
        {"mode": "mobile", "zoom": 49},
        {"mode": "mobile", "zoom": 301},
        {"mode": "mobile", "ua": "arbitrary"},
        {"mode": "desktop", "script": "not allowed"},
    ],
)
def test_view_rejects_unbounded_or_unknown_configuration(value):
    with pytest.raises(ValueError):
        validate_view(value)


def test_view_absence_preserves_legacy_and_explicit_values_normalize(tmp_path):
    data = make_data()
    path = write_config(tmp_path, data)
    before = path.read_bytes()
    assert all("view" not in service for service in load_config(path)["services"])
    assert path.read_bytes() == before
    data["services"][0]["view"] = {"mode": "mobile"}
    path = write_config(tmp_path, data)
    assert load_config(path)["services"][0]["view"] == {"mode": "mobile", "zoom": 200}
    assert validate_view({"mode": "desktop"}) == {"mode": "desktop", "zoom": 100}
    assert validate_view({"mode": "desktop", "zoom": 125}) == {"mode": "desktop", "zoom": 125}
    data["services"][0]["view"] = {"mode": "mobile", "zoom": "200"}
    with pytest.raises(ValueError):
        load_config(write_config(tmp_path, data))
