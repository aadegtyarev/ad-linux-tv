"""Installer preview safety tests."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASH = "/bin/bash" if Path("/bin/bash").exists() else "/usr/bin/bash"


def snapshot(home):
    return {path.relative_to(home): path.read_bytes() for path in home.rglob("*") if path.is_file()}


def test_dry_runs_preview_without_changing_home(tmp_path):
    home = tmp_path / "home"
    sentinel = home / ".config/ad-linux-tv/config.yaml"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("preserve me", encoding="utf-8")
    before = snapshot(home)
    env = {
        **os.environ,
        "HOME": str(home),
        "AD_LINUX_TV_XPI_URL": "https://release.example/bridge.xpi",
        "AD_LINUX_TV_XPI_SHA256": "a" * 64,
    }
    install = subprocess.run(
        [BASH, str(ROOT / "install.sh"), "--dry-run"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    remove = subprocess.run(
        [BASH, str(ROOT / "uninstall.sh"), "--dry-run"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert str(home / ".local/share/ad-linux-tv") in install.stdout
    assert str(sentinel) in install.stdout
    assert str(home / ".local/share/ad-linux-tv/ad-linux-tv-signed.xpi") in install.stdout
    assert "preserved" in remove.stdout
    assert snapshot(home) == before
