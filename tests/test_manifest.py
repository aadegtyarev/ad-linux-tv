"""Firefox match-pattern and packaged manifest validation."""

import json
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def valid_match_pattern(pattern):
    authority = pattern.split("://", 1)[1].split("/", 1)[0]
    return ":" not in authority


def test_manifest_uses_portless_patterns_and_packages_exact_declarations(tmp_path):
    source = json.loads((ROOT / "extension/manifest.json").read_text(encoding="utf-8"))
    patterns = source["host_permissions"] + source["content_scripts"][0]["matches"]
    assert all(valid_match_pattern(pattern) for pattern in patterns)
    assert not valid_match_pattern("http://127.0.0.1:8765/*")
    archive_path = tmp_path / "bridge.zip"
    subprocess.run(
        [str(ROOT / "extension/package.sh"), str(archive_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    with zipfile.ZipFile(archive_path) as archive:
        packaged = json.loads(archive.read("manifest.json"))
        assert packaged == source
        assert packaged["host_permissions"] == ["http://127.0.0.1/*"]
        assert packaged["content_scripts"][0]["matches"] == ["http://127.0.0.1/*"]
