"""Bounded declarative service presentation, never arbitrary UA/headers/scripts."""

import hashlib
import json

DEFAULT_VIEW = {"mode": "desktop", "zoom": 125}


def validate_view(value):
    if (
        not isinstance(value, dict)
        or "mode" not in value
        or set(value) - {"mode", "zoom"}
        or value["mode"] not in ("desktop", "mobile")
    ):
        raise ValueError("view.mode must be desktop or mobile")
    zoom = value.get("zoom", 200 if value["mode"] == "mobile" else 100)
    if type(zoom) is not int or not 50 <= zoom <= 300:
        raise ValueError("view.zoom must be an integer50..300")
    return {"mode": value["mode"], "zoom": zoom}


def common_view(config):
    return validate_view(config.get("view", DEFAULT_VIEW))


def service_catalogue(config):
    default = common_view(config)
    return [
        dict(service, view=validate_view(service.get("view", default)))
        for service in config["services"]
    ]


def service_views(config):
    default = common_view(config)
    return [
        {
            "id": service["id"],
            "name": service["name"],
            "view": validate_view(service["view"]) if "view" in service else None,
            "effective_view": validate_view(service["view"])
            if "view" in service
            else dict(default),
        }
        for service in config["services"]
    ]


def view_fingerprint(config):
    values = [
        {"id": service["id"], "view": service["view"]} for service in service_catalogue(config)
    ]
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
