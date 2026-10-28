"""Derived view and language preferences in the dedicated TV Firefox profile only."""

import sys
from pathlib import Path

from .browser_locale import browser_locale, locale_profile_text, replace_block
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
    # Firefox setZoomSettings only verifies current scope; it cannot change it.
    # This dedicated-profile preference enables independent per-tab zoom.
    body = 'user_pref("browser.zoom.siteSpecific", false);\n' if wanted else None
    text = replace_block(old, BEGIN, END, body)
    if text != old:
        atomic_write(path, text)


def prepare_locale_profile(config, path):
    path = Path(path)
    old = path.read_text() if path.exists() else ""
    text = locale_profile_text(old, browser_locale(config))
    if text != old:
        atomic_write(path, text)


def main():
    try:
        if len(sys.argv) != 3:
            raise ValueError("expected configuration and dedicated user.js path")
        config = load_config(sys.argv[1])
        prepare_view_profile(config, sys.argv[2])
        prepare_locale_profile(config, sys.argv[2])
        print(view_fingerprint(config))
    except (OSError, ValueError):
        print("Cannot prepare dedicated TV profile preferences", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
