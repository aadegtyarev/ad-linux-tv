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
  printf 'Optional TV Firefox proxy: %s\n' 127.0.0.1:1081
  printf 'Compositor/input/audio packages: %s\n' 'labwc squeekboard wtype wlrctl oxygen-cursor-theme wlopm swayidle python3-gi gir1.2-gtklayershell-0.1 pulseaudio-utils'
  printf 'Compositor config: %s\n' /etc/ad-linux-tv/labwc/rc.xml
  printf 'Touch controls: %s\n' /usr/local/libexec/ad-linux-tv/touch-overlay.py
  printf 'TV timer overlay: %s\n' /usr/local/libexec/ad-linux-tv/timer-overlay.py
  printf 'Touch keyboard layouts: %s\n' /home/ad-tv/.local/share/squeekboard/keyboards
  printf 'System units: %s\n' /etc/systemd/system/ad-linux-tv-kiosk.service /etc/systemd/system/ad-linux-tv-boot.service
  printf 'KDE switch unit: %s\n' /etc/systemd/system/ad-linux-tv-switch-kde.service
  printf 'Confirmed host power unit (not started): %s\n' /etc/systemd/system/ad-linux-tv-poweroff.service
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
apt-get install -y labwc squeekboard wtype wlrctl oxygen-cursor-theme wlopm swayidle python3-gi gir1.2-gtklayershell-0.1 pulseaudio-utils
if ! "$ROOT/install-keyboard-layouts.sh" --install; then
  echo 'Custom keyboard labels unavailable; stock Squeekboard remains usable.' >&2
fi
install -d -o ad-tv -g ad-tv -m 700 /home/ad-tv/.config
install -d -o ad-tv -g ad-tv -m 700 /home/ad-tv/.config/ad-linux-tv
install -d -o ad-tv -g ad-tv -m 700 /home/ad-tv/snap /home/ad-tv/snap/firefox /home/ad-tv/snap/firefox/common
if [[ -f /home/ad-tv/.config/ad-linux-tv/config.yaml ]] && grep -q '^proxy:' /home/ad-tv/.config/ad-linux-tv/config.yaml; then
  echo 'TV proxy is configured in config.yaml; keeping that choice.'
elif python3 -c 'import socket; s=socket.socket(); s.settimeout(1); result=s.connect_ex(("127.0.0.1",1081)); s.close(); raise SystemExit(result)' ; then
  "$ROOT/configure-firefox.sh" --configure
else
  echo 'Local Xray proxy unavailable; run configure-firefox.sh --configure when it is ready.'
fi
install -d -m 755 /usr/local/libexec/ad-linux-tv
install -m 755 "$ROOT/has-monitor.sh" "$ROOT/boot-tv.sh" "$ROOT/start-compositor.sh" "$ROOT/tv-session.sh" "$ROOT/touch-controls.sh" "$ROOT/select-audio.sh" "$ROOT/touch-overlay.py" "$ROOT/timer-overlay.py" "$ROOT/cycle-keyboard-language.sh" "$ROOT/wake-display.sh" /usr/local/libexec/ad-linux-tv/
install -m 644 "$ROOT/timer_notice.py" /usr/local/libexec/ad-linux-tv/
install -d -m 755 /etc/ad-linux-tv/labwc
install -m 644 "$ROOT/labwc/rc.xml" /etc/ad-linux-tv/labwc/rc.xml
install -m 644 "$ROOT/ad-linux-tv-kiosk.service" "$ROOT/ad-linux-tv-boot.service" "$ROOT/ad-linux-tv-switch-kde.service" "$ROOT/ad-linux-tv-poweroff.service" /etc/systemd/system/
install -m 644 "$ROOT/ad-linux-tv-kiosk.pam" /etc/pam.d/ad-linux-tv-kiosk
visudo -cf "$ROOT/98-ad-linux-tv-gui.sudoers" >/dev/null
install -m 440 "$ROOT/98-ad-linux-tv-gui.sudoers" /etc/sudoers.d/98-ad-linux-tv-gui
visudo -cf "$ROOT/99-ad-linux-tv-poweroff.sudoers" >/dev/null
install -m 440 "$ROOT/99-ad-linux-tv-poweroff.sudoers" /etc/sudoers.d/99-ad-linux-tv-poweroff

gui=/home/adegtyarev/.local/bin/gui
if [[ -e "$gui" ]] && ! cmp -s "$ROOT/gui" "$gui"; then
  cp -p "$gui" "$gui.bak-$(date +%Y%m%d-%H%M%S)"
fi
install -o adegtyarev -g adegtyarev -m 755 "$ROOT/gui" "$gui"
systemctl daemon-reload
systemctl enable --now getty@tty2.service
echo 'TV integration staged. Application deployment and boot activation remain separate.'
