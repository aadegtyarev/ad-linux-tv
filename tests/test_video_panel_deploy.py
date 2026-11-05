"""The existing kiosk update stages the panel and announces session activation."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_existing_kiosk_update_includes_panel_assets():
    source = (ROOT / "ops/kiosk/deploy.sh").read_text()
    assert '"$ROOT/ops/kiosk/tv-session.sh"' in source
    assert '"$ROOT/ops/kiosk/video-panel.py"' in source
    assert '"$ROOT/ops/kiosk/video_panel_client.py"' in source
    assert "/usr/local/libexec/ad-linux-tv/" in source
    assert source.index('"$stage/install.sh" --install') < source.index(
        '"$ROOT/ops/kiosk/video-panel.py"'
    )


def test_existing_kiosk_update_installs_the_panel_in_fake_root(tmp_path):
    if not shutil.which("fakeroot"):
        pytest.skip("fakeroot unavailable")
    root = tmp_path / "source"
    kiosk = root / "ops/kiosk"
    kiosk.mkdir(parents=True)
    for name in (
        "deploy.sh",
        "tv-session.sh",
        "video-panel.py",
        "video_panel_client.py",
    ):
        shutil.copy2(ROOT / "ops/kiosk" / name, kiosk / name)
    (kiosk / "configure-firefox.sh").write_text("#!/bin/sh\nexit 0\n")
    (kiosk / "configure-firefox.sh").chmod(0o755)
    for name in ("src", "extension"):
        (root / name).mkdir()
    for name in ("install.sh", "run.sh", "pyproject.toml"):
        (root / name).write_text("fixture\n")
    fake = tmp_path / "bin"
    fake.mkdir()
    dest = tmp_path / "installed"
    dest.mkdir()
    commands = {
        "id": '#!/bin/sh\n[ "$1" = -u ] && [ "$2" = ad-tv ] && exit 0\nexit 1\n',
        "chown": "#!/bin/sh\nexit 0\n",
        "runuser": '#!/bin/sh\nprintf \'%s\\n\' "$*" > "$FAKE_CALLS"\n',
        "install": (
            '#!/bin/sh\nset -eu\n[ "$1" = -m ]; mode=$2; shift 2\n'
            'while [ "$#" -gt 1 ]; do src=$1; shift; '
            '/bin/cp "$src" "$FAKE_DEST/${src##*/}"; '
            '/bin/chmod "$mode" "$FAKE_DEST/${src##*/}"; done\n'
            '[ "$1" = /usr/local/libexec/ad-linux-tv/ ]\n'
        ),
    }
    for name, content in commands.items():
        path = fake / name
        path.write_text(content)
        path.chmod(0o755)
    calls = tmp_path / "calls"
    env = dict(
        os.environ, PATH=f"{fake}:{os.environ['PATH']}", FAKE_DEST=str(dest), FAKE_CALLS=str(calls)
    )
    subprocess.run(
        ["fakeroot", str(kiosk / "deploy.sh"), "--install"], env=env, check=True, timeout=15
    )
    assert "--install --no-autostart" in calls.read_text()
    for name in (
        "tv-session.sh",
        "video-panel.py",
        "video_panel_client.py",
    ):
        assert (dest / name).read_bytes() == (kiosk / name).read_bytes()


def test_kiosk_update_dry_run_announces_panel_without_installing():
    result = subprocess.run(
        [str(ROOT / "ops/kiosk/deploy.sh"), "--dry-run"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert "current-video panel" in result.stdout
    assert "next TV session" in result.stdout
