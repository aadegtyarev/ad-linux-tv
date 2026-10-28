#!/usr/bin/env bash
set -euo pipefail

MODE=${1:---dry-run}
case "$MODE" in
  --dry-run|--install|--activate) ;;
  *) echo 'usage: setup.sh [--dry-run|--install|--activate]' >&2; exit 2 ;;
esac
ROOT=$(cd "$(dirname "$0")" && pwd)
SOURCE=$(cd "$ROOT/../.." && pwd)
# The administrator gets the `gui` helper and may switch sessions from a console.
ADMIN=${AD_LINUX_TV_ADMIN:-${SUDO_USER:-}}
PACKAGES='labwc squeekboard wtype wlrctl oxygen-cursor-theme wlopm swayidle python3-gi python3-gi-cairo gir1.2-gtklayershell-0.1 pulseaudio-utils pipewire pipewire-pulse wireplumber python3-venv fonts-noto-core fonts-noto-color-emoji curl'

preview() {
  printf 'TV user: %s\n' ad-tv
  printf 'Application: %s\n' /home/ad-tv/.local/share/ad-linux-tv
  printf 'Config: %s\n' /home/ad-tv/.config/ad-linux-tv/config.yaml
  printf 'Firefox profile/XPI: %s\n' /home/ad-tv/snap/firefox/common
  printf 'Packages: %s\n' "$PACKAGES"
  printf 'Firefox: %s\n' 'snap firefox (installed if missing)'
  "$ROOT/configure-firefox.sh" --dry-run
  printf 'Compositor config: %s\n' /etc/ad-linux-tv/labwc/rc.xml
  printf 'Touch controls: %s\n' /usr/local/libexec/ad-linux-tv/touch-overlay.py
  printf 'TV timer overlay: %s\n' /usr/local/libexec/ad-linux-tv/timer-overlay.py
  printf 'Touch keyboard layouts: %s\n' /home/ad-tv/.local/share/squeekboard/keyboards
  printf 'System units: %s\n' /etc/systemd/system/ad-linux-tv-kiosk.service /etc/systemd/system/ad-linux-tv-boot.service
  printf 'KDE switch unit: %s\n' /etc/systemd/system/ad-linux-tv-switch-kde.service
  printf 'Confirmed host power unit (not started): %s\n' /etc/systemd/system/ad-linux-tv-poweroff.service
  printf 'PAM: %s\n' /etc/pam.d/ad-linux-tv-kiosk
  printf 'Administrator: %s\n' "${ADMIN:-unknown, run with sudo or set AD_LINUX_TV_ADMIN}"
  printf 'Control scripts: %s\n' /usr/local/libexec/ad-linux-tv "~$ADMIN/.local/bin/gui"
  printf 'Sudoers: %s\n' /etc/sudoers.d/98-ad-linux-tv-gui
  printf 'Console fallback: %s\n' getty@tty2.service
  printf 'Source checkout is preserved: %s\n' "$SOURCE"
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
  systemctl enable ad-linux-tv-boot.service
  echo 'TV mode will be attempted on the next boot when a display is connected.'
  exit 0
fi

if [[ -z $ADMIN || $ADMIN == root ]] || ! id -u "$ADMIN" >/dev/null 2>&1; then
  echo 'Run from the administrator account with sudo, or set AD_LINUX_TV_ADMIN.' >&2
  exit 1
fi
if id -u ad-tv >/dev/null 2>&1; then
  [[ $(getent passwd ad-tv | cut -d: -f6) == /home/ad-tv ]] || {
    echo 'Existing ad-tv user has an unexpected home; stopping.' >&2; exit 1;
  }
else
  useradd --create-home --home-dir /home/ad-tv --shell /usr/sbin/nologin --user-group ad-tv
fi
# shellcheck disable=SC2086
apt-get install -y $PACKAGES
snap list firefox >/dev/null 2>&1 || snap install firefox
if ! "$ROOT/install-keyboard-layouts.sh" --install; then
  echo 'Custom keyboard labels unavailable; stock Squeekboard remains usable.' >&2
fi
install -d -o ad-tv -g ad-tv -m 700 /home/ad-tv/.config
install -d -o ad-tv -g ad-tv -m 700 /home/ad-tv/.config/ad-linux-tv
install -d -o ad-tv -g ad-tv -m 700 /home/ad-tv/snap /home/ad-tv/snap/firefox /home/ad-tv/snap/firefox/common
"$ROOT/configure-firefox.sh" --configure
install -d -m 755 /usr/local/libexec/ad-linux-tv
install -m 755 "$ROOT/has-monitor.sh" "$ROOT/boot-tv.sh" "$ROOT/start-compositor.sh" "$ROOT/tv-session.sh" "$ROOT/touch-controls.sh" "$ROOT/select-audio.sh" "$ROOT/touch-overlay.py" "$ROOT/timer-overlay.py" "$ROOT/cycle-keyboard-language.sh" "$ROOT/wake-display.sh" /usr/local/libexec/ad-linux-tv/
install -m 644 "$ROOT/timer_notice.py" /usr/local/libexec/ad-linux-tv/
install -d -m 755 /etc/ad-linux-tv/labwc
install -m 644 "$ROOT/labwc/rc.xml" /etc/ad-linux-tv/labwc/rc.xml
install -m 644 "$ROOT/ad-linux-tv-kiosk.service" "$ROOT/ad-linux-tv-boot.service" "$ROOT/ad-linux-tv-switch-kde.service" "$ROOT/ad-linux-tv-poweroff.service" /etc/systemd/system/
install -m 644 "$ROOT/ad-linux-tv-kiosk.pam" /etc/pam.d/ad-linux-tv-kiosk
sudoers=$(mktemp)
sed "s/@ADMIN@/$ADMIN/g" "$ROOT/98-ad-linux-tv-gui.sudoers" > "$sudoers"
visudo -cf "$sudoers" >/dev/null
install -m 440 "$sudoers" /etc/sudoers.d/98-ad-linux-tv-gui
rm -f "$sudoers"
visudo -cf "$ROOT/99-ad-linux-tv-poweroff.sudoers" >/dev/null
install -m 440 "$ROOT/99-ad-linux-tv-poweroff.sudoers" /etc/sudoers.d/99-ad-linux-tv-poweroff

admin_home=$(getent passwd "$ADMIN" | cut -d: -f6)
runuser -u "$ADMIN" -- mkdir -p "$admin_home/.local/bin"
gui=$admin_home/.local/bin/gui
if [[ -e "$gui" ]] && ! cmp -s "$ROOT/gui" "$gui"; then
  cp -p "$gui" "$gui.bak-$(date +%Y%m%d-%H%M%S)"
fi
install -o "$ADMIN" -g "$(id -gn "$ADMIN")" -m 755 "$ROOT/gui" "$gui"
systemctl daemon-reload
systemctl enable --now getty@tty2.service
echo 'TV integration staged. Application deployment and boot activation remain separate.'
