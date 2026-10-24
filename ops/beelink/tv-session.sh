#!/usr/bin/env bash
set -euo pipefail

if command -v gsettings >/dev/null 2>&1; then
  gsettings set org.gnome.desktop.input-sources sources "[('xkb', 'us'), ('xkb', 'ru')]" || true
fi
/usr/local/libexec/ad-linux-tv/select-audio.sh &
(
  while :; do
    /usr/bin/squeekboard || true
    sleep 2
  done
) &
osk=$!
(
  while :; do
    /usr/bin/waybar -c /etc/ad-linux-tv/waybar/config.jsonc -s /etc/ad-linux-tv/waybar/style.css || true
    sleep 2
  done
) &
bar=$!
trap 'kill "$osk" "$bar" 2>/dev/null || true; wait "$osk" "$bar" 2>/dev/null || true' EXIT
/home/ad-tv/.local/share/ad-linux-tv/run.sh /home/ad-tv/.config/ad-linux-tv/config.yaml
