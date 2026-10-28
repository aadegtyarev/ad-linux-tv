"""Offline public build metadata, file selection and snapshot isolation."""

import os
from pathlib import Path

import pytest

from ad_linux_tv import build_info


def package(root):
    root.mkdir()
    (root / "module.py").write_text("print('public')\n")
    (root / "static").mkdir()
    (root / "static" / "app.js").write_text("public();")
    return root


def test_fingerprint_content_not_location_or_mtime(tmp_path):
    left = package(tmp_path / "left")
    right = package(tmp_path / "right")
    os.utime(right / "module.py", (1, 1))
    expected = build_info.package_fingerprint(left)
    assert len(expected) == 16 and expected != "unknown"
    assert build_info.package_fingerprint(right) == expected
    (right / "static" / "app.js").write_text("changed();")
    assert build_info.package_fingerprint(right) != expected
    (right / "static" / "app.js").write_text("public();")
    (right / "module.py").write_text("changed = True")
    assert build_info.package_fingerprint(right) != expected


def test_selection_never_reads_private_or_symlink_files(tmp_path, monkeypatch):
    root = package(tmp_path / "pkg")
    expected = build_info.package_fingerprint(root)
    for name in ("config.yaml", "cookies.sqlite", "credentials.json", "notes.txt"):
        (root / name).write_text("SECRET")
        (root / "static" / name).write_text("SECRET")
    for name in ("profile", "__pycache__"):
        (root / name).mkdir()
        (root / name / "private.py").write_text("SECRET")
    (root / "static" / ".private").mkdir()
    (root / "static" / ".private" / "secret.js").write_text("SECRET")
    (root / "private.py").symlink_to(root / "config.yaml")
    (root / "static" / "secret.js").symlink_to(root / "config.yaml")
    (root / "static" / "linked").symlink_to(root / "profile", target_is_directory=True)
    original = Path.read_bytes
    reads = []

    def read(path):
        reads.append(path.relative_to(root).as_posix())
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", read)
    assert build_info.package_fingerprint(root) == expected
    assert sorted(reads) == ["module.py", "static/app.js"]
    (root / "static" / "tone.wav").write_bytes(b"audio")
    assert build_info.package_fingerprint(root) != expected


def test_missing_and_unreadable_package(tmp_path, monkeypatch):
    assert build_info.package_fingerprint(tmp_path / "absent") == "unknown"
    root = package(tmp_path / "pkg")

    def denied(path):
        raise PermissionError("secret path must not escape")

    monkeypatch.setattr(Path, "read_bytes", denied)
    assert build_info.package_fingerprint(root) == "unknown"


@pytest.mark.parametrize("value", [None, "", "x" * 81, "private\npath", "0.2.5+public"])
def test_version_bounds_and_cache(value, monkeypatch):
    build_info._installed_info.cache_clear()
    calls = []
    monkeypatch.setattr(build_info.metadata, "version", lambda name: value)
    monkeypatch.setattr(build_info, "package_fingerprint", lambda root: calls.append(root) or "abc")
    try:
        info = build_info.server_info()
        assert info == {"version": value if value == "0.2.5+public" else "unknown", "build": "abc"}
        info["build"] = "corrupted"
        assert build_info.server_info()["build"] == "abc"
        assert len(calls) == 1
    finally:
        build_info._installed_info.cache_clear()


@pytest.mark.parametrize("error", [build_info.metadata.PackageNotFoundError, OSError, ValueError])
def test_missing_metadata_is_safe(error, monkeypatch):
    build_info._installed_info.cache_clear()

    def missing(name):
        raise error("private detail")

    monkeypatch.setattr(build_info.metadata, "version", missing)
    monkeypatch.setattr(build_info, "package_fingerprint", lambda root: "actual-build")
    try:
        assert build_info.server_info() == {"version": "unknown", "build": "actual-build"}
    finally:
        build_info._installed_info.cache_clear()


def test_settings_metadata_preserves_private_state_and_sessions(tmp_path):
    from test_settings import manager

    settings, sessions, path, _profile = manager(tmp_path)
    token, _csrf = sessions.create()
    original = path.read_bytes()
    settings.config["proxy"] = {"mode": "none"}
    state = settings.state()
    assert set(state["server"]) == {"version", "build"}
    assert all(
        isinstance(value, str) and 1 <= len(value) <= 80 for value in state["server"].values()
    )
    assert "auth" not in state and "verifier" not in str(state)
    state["server"]["version"] = "corrupted"
    state["proxy"]["mode"] = "corrupted"
    state["view"]["zoom"] = 50
    state["service_views"][0]["effective_view"]["zoom"] = 50
    fresh = settings.state()
    assert fresh["server"]["version"] != "corrupted"
    assert fresh["proxy"] == {"mode": "none"}
    assert fresh["view"]["zoom"] == 125
    assert fresh["service_views"][0]["effective_view"]["zoom"] == 125
    assert path.read_bytes() == original
    assert sessions.valid(token)
