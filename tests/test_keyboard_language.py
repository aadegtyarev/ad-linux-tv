"""The TV keyboard must rotate the source order Squeekboard actually reads."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops/beelink/cycle-keyboard-language.sh"


def test_tv_language_button_rotates_sources_and_preserves_extra_state(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    state = tmp_path / "sources"
    current = tmp_path / "current"
    state.write_text("[('xkb', 'us'), ('xkb', 'ru')]", encoding="utf-8")
    command = fake_bin / "gsettings"
    command.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = get ]; then cat "$SOURCE_STATE"; exit; fi\n'
        'if [ "$3" = sources ]; then printf "%s" "$4" > "$SOURCE_STATE"; exit; fi\n'
        'if [ "$3" = current ]; then printf "%s" "$4" > "$CURRENT_STATE"; exit; fi\n'
        "exit 2\n",
        encoding="utf-8",
    )
    command.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "SOURCE_STATE": str(state),
        "CURRENT_STATE": str(current),
    }
    subprocess.run([str(SCRIPT)], env=env, check=True)
    assert state.read_text() == "[('xkb', 'ru'), ('xkb', 'us')]"
    assert current.read_text() == "0"
    subprocess.run([str(SCRIPT)], env=env, check=True)
    assert state.read_text() == "[('xkb', 'us'), ('xkb', 'ru')]"
    state.write_text("[('xkb', 'de')]", encoding="utf-8")
    assert subprocess.run([str(SCRIPT)], env=env, capture_output=True).returncode == 1
    assert state.read_text() == "[('xkb', 'de')]"
