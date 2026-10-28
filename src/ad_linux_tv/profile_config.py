"""Derived view-only preferences in the dedicated TV Firefox profile, not personal profiles."""

import sys
from pathlib import Path

from .config import load_config
from .settings import atomic_write
from .view_config import view_fingerprint

BEGIN = "// BEGIN AD-LINUX-TV VIEW"
END = "// END AD-LINUX-TV VIEW"


def prepare_view_profile(config, path):
    path = Path(path)
    old = path.read_text() if path.exists() else ""
    # Mobile is the common default, including configurations with no view field.
    wanted = bool(config["services"])
    if not wanted and BEGIN not in old:
        return  # Legacy/default profile remains byte-for-byte untouched.
    kept = []
    inside = False
    for line in old.splitlines(keepends=True):
        if line.strip() == BEGIN:
            if inside:
                raise ValueError("invalid managed view preference block")
            inside = True
        elif line.strip() == END:
            if not inside:
                raise ValueError("invalid managed view preference block")
            inside = False
        elif not inside:
            kept.append(line)
    if inside:
        raise ValueError("unterminated managed view preference block")
    text = "".join(kept)
    if wanted:
        if text and not text.endswith("\n"):
            text += "\n"
        # Firefox setZoomSettings only verifies current scope; it cannot change it.
        # This dedicated-profile preference enables independent per-tab zoom.
        text += f'{BEGIN}\nuser_pref("browser.zoom.siteSpecific", false);\n{END}\n'
    if text != old:
        atomic_write(path, text)


def main():
    try:
        if len(sys.argv) != 3:
            raise ValueError("expected configuration and dedicated user.js path")
        config = load_config(sys.argv[1])
        prepare_view_profile(config, sys.argv[2])
        print(view_fingerprint(config))
    except (OSError, ValueError):
        print("Cannot prepare dedicated TV view preferences", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
