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
    assert str(home / "snap/firefox/common/ad-linux-tv-profile") in install.stdout
    assert str(home / "snap/firefox/common/ad-linux-tv-signed.xpi") in install.stdout
    assert "preserved" in remove.stdout
    assert snapshot(home) == before


def test_tv_install_preview_keeps_existing_autostart_untouched(tmp_path):
    home = tmp_path / "home"
    autostart = home / ".config/autostart/ad-linux-tv.desktop"
    autostart.parent.mkdir(parents=True)
    autostart.write_text("existing", encoding="utf-8")
    before = snapshot(home)
    result = subprocess.run(
        [BASH, str(ROOT / "install.sh"), "--dry-run", "--no-autostart"],
        env={**os.environ, "HOME": str(home)},
        capture_output=True,
        text=True,
        check=True,
    )
    assert f"--dry-run remove {autostart}" in result.stdout
    assert snapshot(home) == before


def test_install_rejects_conflicting_modes_before_writing(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    result = subprocess.run(
        [BASH, str(ROOT / "install.sh"), "--dry-run", "--install"],
        env={**os.environ, "HOME": str(home)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert snapshot(home) == {}


def test_kiosk_run_stops_server_when_firefox_exits(tmp_path):
    home = tmp_path / "home"
    data = home / ".local/share/ad-linux-tv"
    venv_bin = data / "venv/bin"
    fake_bin = tmp_path / "bin"
    venv_bin.mkdir(parents=True)
    fake_bin.mkdir()
    stopped = tmp_path / "stopped"
    args = tmp_path / "firefox-args"
    server = venv_bin / "ad-linux-tv"
    server.write_text(
        "#!/bin/sh\ntrap 'printf stopped > \"$STOPPED\"; exit 0' TERM\n"
        "while :; do sleep 0.1; done\n",
        encoding="utf-8",
    )
    python = venv_bin / "python"
    python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    firefox = fake_bin / "firefox"
    firefox.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$FIREFOX_ARGS"\n', encoding="utf-8")
    for script in (server, python, firefox):
        script.chmod(0o755)
    result = subprocess.run(
        [BASH, str(ROOT / "run.sh")],
        env={
            **os.environ,
            "HOME": str(home),
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "AD_LINUX_TV_KIOSK": "1",
            "STOPPED": str(stopped),
            "FIREFOX_ARGS": str(args),
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 1
    assert stopped.read_text(encoding="utf-8") == "stopped"
    browser_args = args.read_text(encoding="utf-8")
    assert "--kiosk" in browser_args
    assert str(home / "snap/firefox/common/ad-linux-tv-profile") in browser_args


def test_uninstall_preserves_source_config_and_firefox_profile(tmp_path):
    home = tmp_path / "home"
    source = home / "Develop/Hobby/ad-linux-tv/README.md"
    config = home / ".config/ad-linux-tv/config.yaml"
    profile = home / "snap/firefox/common/ad-linux-tv-profile/prefs.js"
    installed = home / ".local/share/ad-linux-tv/run.sh"
    for path in (source, config, profile, installed):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("keep", encoding="utf-8")
    subprocess.run(
        [BASH, str(ROOT / "uninstall.sh"), "--remove"],
        env={**os.environ, "HOME": str(home)},
        capture_output=True,
        text=True,
        check=True,
    )
    assert not installed.exists()
    assert all(path.read_text(encoding="utf-8") == "keep" for path in (source, config, profile))


def test_first_tv_audio_start_sets_hdmi_full_without_overriding_saved_volume(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "pactl-calls"
    pactl = fake_bin / "pactl"
    pactl.write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        '  "list short sinks") printf \x271\\talsa_output.test.hdmi-stereo\\tPipeWire\\n\x27 ;;\n'
        "  info) printf \x27Default Sink: alsa_output.test.hdmi-stereo\\n\x27 ;;\n"
        '  *) printf \x27%s\\n\x27 "$*" >> "$PACTL_LOG" ;;\n'
        "esac\n",
        encoding="utf-8",
    )
    pactl.chmod(0o755)
    preference = tmp_path / "audio-output.txt"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "PACTL_LOG": str(log),
        "AD_LINUX_TV_AUDIO_FILE": str(preference),
    }
    script = ROOT / "ops/kiosk/select-audio.sh"
    subprocess.run([BASH, str(script)], env=env, check=True, timeout=3)
    assert "set-sink-volume alsa_output.test.hdmi-stereo 100%" in log.read_text()
    preference.write_text("alsa_output.test.hdmi-stereo\n")
    log.unlink()
    subprocess.run([BASH, str(script)], env=env, check=True, timeout=3)
    assert not log.exists()
