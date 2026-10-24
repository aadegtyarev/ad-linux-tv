#!/usr/bin/env bash
set -euo pipefail

MODE=${1:---dry-run}
case "$MODE" in
  --dry-run|--install|--activate) ;;
  *) echo 'usage: setup.sh [--dry-run|--install|--activate]' >&2; exit 2 ;;
esac
ROOT=$(cd "$(dirname "$0")" && pwd)

preview() {
  printf 'TV user: %s\n' ad-tv
  printf 'Application: %s\n' /home/ad-tv/.local/share/ad-linux-tv
  printf 'Config: %s\n' /home/ad-tv/.config/ad-linux-tv/config.yaml
  printf 'Firefox profile/XPI: %s\n' /home/ad-tv/snap/firefox/common
  printf 'Compositor package: %s\n' cage
  printf 'System units: %s\n' /etc/systemd/system/ad-linux-tv-kiosk.service /etc/systemd/system/ad-linux-tv-boot.service
  printf 'PAM: %s\n' /etc/pam.d/ad-linux-tv-kiosk
  printf 'Control scripts: %s\n' /usr/local/libexec/ad-linux-tv /home/adegtyarev/.local/bin/gui
  printf 'Sudoers: %s\n' /etc/sudoers.d/98-ad-linux-tv-gui
  printf 'Console fallback: %s\n' getty@tty2.service
  printf 'Source checkout is preserved: %s\n' /home/adegtyarev/Develop/Hobby/ad-linux-tv
}

if [[ "$MODE" == --dry-run ]]; then preview; exit 0; fi
if (( EUID != 0 )); then echo 'Run with sudo for --install or --activate.' >&2; exit 1; fi

if [[ "$MODE" == --activate ]]; then
  for path in \
    /home/ad-tv/.local/share/ad-linux-tv/run.sh \
    /home/ad-tv/.config/ad-linux-tv/config.yaml \
    /home/ad-tv/snap/firefox/common/ad-linux-tv-signed.xpi; do
    if [[ ! -f "$path" ]]; then printf 'Missing: %s\n' "$path" >&2; exit 1; fi
  done
  if systemctl is-active --quiet beelink-display.service; then
    echo 'The existing HDMI controller is active; disable it before TV boot activation.' >&2
    exit 1
  fi
  systemctl enable ad-linux-tv-boot.service
  echo 'TV mode will be attempted on the next boot when a display is connected.'
  exit 0
fi

if id -u ad-tv >/dev/null 2>&1; then
  [[ $(getent passwd ad-tv | cut -d: -f6) == /home/ad-tv ]] || {
    echo 'Existing ad-tv user has an unexpected home; stopping.' >&2; exit 1;
  }
else
  useradd --create-home --home-dir /home/ad-tv --shell /usr/sbin/nologin --user-group ad-tv
fi
apt-get install -y cage
install -d -o ad-tv -g ad-tv -m 700 /home/ad-tv/.config/ad-linux-tv
install -d -o ad-tv -g ad-tv -m 700 /home/ad-tv/snap/firefox/common
install -d -m 755 /usr/local/libexec/ad-linux-tv
install -m 755 "$ROOT/has-monitor.sh" "$ROOT/boot-tv.sh" /usr/local/libexec/ad-linux-tv/
install -m 644 "$ROOT/ad-linux-tv-kiosk.service" "$ROOT/ad-linux-tv-boot.service" /etc/systemd/system/
install -m 644 "$ROOT/ad-linux-tv-kiosk.pam" /etc/pam.d/ad-linux-tv-kiosk
visudo -cf "$ROOT/98-ad-linux-tv-gui.sudoers" >/dev/null
install -m 440 "$ROOT/98-ad-linux-tv-gui.sudoers" /etc/sudoers.d/98-ad-linux-tv-gui

gui=/home/adegtyarev/.local/bin/gui
if [[ -e "$gui" ]] && ! cmp -s "$ROOT/gui" "$gui"; then
  cp -p "$gui" "$gui.bak-$(date +%Y%m%d-%H%M%S)"
fi
install -o adegtyarev -g adegtyarev -m 755 "$ROOT/gui" "$gui"
systemctl daemon-reload
systemctl enable --now getty@tty2.service
echo 'TV integration staged. Application deployment and boot activation remain separate.'
