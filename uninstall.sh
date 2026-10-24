#!/usr/bin/env bash
set -euo pipefail
MODE=${1:---dry-run}
case "$MODE" in --dry-run|--remove) ;; *) echo 'usage: uninstall.sh [--dry-run|--remove]' >&2; exit 2;; esac
for path in "$HOME/.local/share/ad-linux-tv" "$HOME/.config/autostart/ad-linux-tv.desktop"; do printf '%s %s\n' "$MODE" "$path"; done
echo 'Configuration is preserved: ~/.config/ad-linux-tv/config.yaml'
echo 'Firefox profile and signed XPI are preserved: ~/snap/firefox/common/'
if [[ "$MODE" == --remove ]]; then rm -rf "$HOME/.local/share/ad-linux-tv" "$HOME/.config/autostart/ad-linux-tv.desktop"; fi
