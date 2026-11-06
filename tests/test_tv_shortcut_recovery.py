"""Fixed offline recovery removes only shortcut settings, including malformed values."""

import subprocess
import sys

import yaml
from test_config_edges import make_data


def run_clear(path):
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "from ad_linux_tv.cli import main; main()",
            "--config",
            str(path),
            "clear-tv-shortcuts",
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )


def test_clear_shortcuts_recovers_malformed_mapping_without_touching_other_settings(tmp_path):
    path = tmp_path / "config.yaml"
    original = dict(make_data(), tv_shortcuts={"video_panel": ["invalid"]})
    path.write_text(yaml.safe_dump(original))
    result = run_clear(path)
    assert result.returncode == 0 and not result.stdout and not result.stderr
    expected = dict(original)
    del expected["tv_shortcuts"]
    assert yaml.safe_load(path.read_text()) == expected
    assert path.stat().st_mode & 0o777 == 0o600
    before = path.read_bytes()
    assert run_clear(path).returncode == 0
    assert path.read_bytes() == before


def test_recovery_discards_only_duplicate_shortcut_subtree(tmp_path):
    path = tmp_path / "config.yaml"
    original = make_data()
    path.write_text(
        yaml.safe_dump(original)
        + "tv_shortcuts:\n  magnifier: XF86Launch1\n  magnifier: XF86Launch2\n"
    )
    result = run_clear(path)
    assert result.returncode == 0 and not result.stdout and not result.stderr
    assert yaml.safe_load(path.read_text()) == original


def test_recovery_removes_six_action_mapping_before_downgrade(tmp_path):
    path = tmp_path / "config.yaml"
    original = make_data()
    selected = {
        "ok": "XF86Launch1",
        "volume_up": "XF86Launch2",
        "volume_down": "XF86Launch3",
        "video_panel": "XF86Launch4",
        "magnifier": "XF86Launch5",
        "fullscreen": "XF86Launch6",
    }
    path.write_text(yaml.safe_dump(dict(original, tv_shortcuts=selected)))
    result = run_clear(path)
    assert result.returncode == 0 and not result.stderr
    assert yaml.safe_load(path.read_text()) == original


def test_recovery_rejects_other_duplicates_without_leaking_contents(tmp_path):
    path = tmp_path / "config.yaml"
    before = (
        "auth:\n  verifier: SECRET_MARKER_1\n  verifier: SECRET_MARKER_2\n"
        "tv_shortcuts:\n  magnifier: XF86Launch1\n"
    )
    path.write_text(before)
    result = run_clear(path)
    assert result.returncode != 0 and not result.stdout
    assert "SECRET_MARKER" not in result.stderr and "Traceback" not in result.stderr
    assert "configuration is invalid or unavailable" in result.stderr
    assert path.read_text() == before
