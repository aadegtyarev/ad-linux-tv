"""The labwc helper can invoke only three fixed local operations."""

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_helper_invokes_only_fixed_local_actions_without_printing_responses(tmp_path):
    capture = tmp_path / "arguments"
    fake_curl = tmp_path / "curl"
    fake_curl.write_text(
        "#!/usr/bin/env python3\nimport json, os, sys\n"
        "open(os.environ['CAPTURE'], 'w').write(json.dumps(sys.argv[1:]))\n"
    )
    fake_curl.chmod(0o755)
    source = (
        (ROOT / "ops/kiosk/tv-shortcut.sh").read_text().replace("/usr/bin/curl", str(fake_curl))
    )
    script = tmp_path / "helper"
    script.write_text(source)
    script.chmod(0o755)
    env = dict(os.environ, CAPTURE=str(capture))
    cases = {
        "video_panel": ("http://127.0.0.1:8765/api/local-video-panel", {"action": "open"}),
        "magnifier": (
            "http://127.0.0.1:8765/api/settings",
            {"setting": "magnifier_toggle", "value": True},
        ),
        "fullscreen": ("http://127.0.0.1:8765/api/command", {"command": "fullscreen"}),
    }
    for action, (url, payload) in cases.items():
        result = subprocess.run(
            [str(script), action], env=env, text=True, capture_output=True, timeout=5
        )
        assert result.returncode == 0 and not result.stdout
        args = json.loads(capture.read_text())
        assert args[-1] == url and "--output" in args and "/dev/null" in args
        assert json.loads(args[args.index("--data") + 1]) == payload
        assert "Origin: http://127.0.0.1:8765" in args
        capture.unlink()
    for args in ([], ["fullscreen", "extra"], ["unknown"], [";echo bad"]):
        result = subprocess.run([str(script), *args], env=env, capture_output=True, timeout=5)
        assert result.returncode == 2 and not capture.exists()
