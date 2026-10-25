#!/usr/bin/env bash
set -euo pipefail

if command -v gsettings >/dev/null 2>&1; then
  sources=$(gsettings get org.gnome.desktop.input-sources sources 2>/dev/null || true)
  case "$sources" in
    "[('xkb', 'us'), ('xkb', 'ru')]"|"[('xkb', 'ru'), ('xkb', 'us')]") ;;
    *) gsettings set org.gnome.desktop.input-sources sources "[('xkb', 'us'), ('xkb', 'ru')]" || true ;;
  esac
  gsettings set org.gnome.desktop.input-sources current 0 || true
fi
/usr/local/libexec/ad-linux-tv/select-audio.sh &
/usr/bin/wlopm --on '*' >/dev/null 2>&1 || true
(
  while :; do
    /usr/bin/swayidle -w timeout 1 true resume /usr/local/libexec/ad-linux-tv/wake-display.sh || true
    sleep 2
  done
) &
idle=$!
(
  while :; do
    /usr/bin/squeekboard || true
    sleep 2
  done
) &
osk=$!
(
  while :; do
    /usr/local/libexec/ad-linux-tv/touch-overlay.py || true
    sleep 2
  done
) &
bar=$!
(
  while :; do
    /usr/local/libexec/ad-linux-tv/timer-overlay.py || true
    sleep 2
  done
) &
timer=$!
trap 'kill "$osk" "$bar" "$timer" "$idle" 2>/dev/null || true; wait "$osk" "$bar" "$timer" "$idle" 2>/dev/null || true; /usr/bin/wlopm --on "*" >/dev/null 2>&1 || true' EXIT
/home/ad-tv/.local/share/ad-linux-tv/run.sh /home/ad-tv/.config/ad-linux-tv/config.yaml
