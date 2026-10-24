#!/usr/bin/env bash
set -euo pipefail
MODE=${1:---dry-run}
case "$MODE" in --dry-run|--install) ;; *) echo 'usage: install.sh [--dry-run|--install]' >&2; exit 2;; esac
DATA="$HOME/.local/share/ad-linux-tv"
CONFIG="$HOME/.config/ad-linux-tv/config.yaml"
AUTO="$HOME/.config/autostart/ad-linux-tv.desktop"
for path in "$DATA" "$CONFIG" "$AUTO"; do printf '%s %s\n' "$MODE" "$path"; done
[[ "$MODE" == --dry-run ]] && exit 0
ROOT=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$DATA" "$(dirname "$CONFIG")" "$(dirname "$AUTO")"
cp -R "$ROOT/src" "$ROOT/extension" "$DATA/"
cp "$ROOT/pyproject.toml" "$ROOT/run.sh" "$DATA/"
python3 -m venv "$DATA/venv"
"$DATA/venv/bin/pip" install "$DATA"
if [[ ! -e "$CONFIG" ]]; then "$DATA/venv/bin/python" -m ad_linux_tv.cli init-config --config "$CONFIG"; fi
cat > "$AUTO" <<EOF
[Desktop Entry]
Type=Application
Name=ad-linux-tv
Exec=$DATA/run.sh $CONFIG
X-GNOME-Autostart-enabled=true
EOF
chmod 600 "$CONFIG"
if [[ -n "${AD_LINUX_TV_XPI_URL:-}" || -n "${AD_LINUX_TV_XPI_SHA256:-}" ]]; then
  [[ -n "${AD_LINUX_TV_XPI_URL:-}" && -n "${AD_LINUX_TV_XPI_SHA256:-}" ]] || { echo 'Both XPI URL and SHA256 are required' >&2; exit 1; }
  command -v curl >/dev/null || { echo 'curl required to download signed XPI' >&2; exit 1; }
  tmp=$(mktemp); trap 'rm -f "$tmp"' EXIT
  curl --fail --location --proto '=https' --tlsv1.2 "$AD_LINUX_TV_XPI_URL" -o "$tmp"
  printf '%s  %s\n' "$AD_LINUX_TV_XPI_SHA256" "$tmp" | sha256sum --check --status || { echo 'XPI SHA256 mismatch' >&2; exit 1; }
  command -v xdg-open >/dev/null || { echo 'xdg-open unavailable; open verified XPI manually' >&2; exit 1; }
  cp "$tmp" "$DATA/ad-linux-tv-signed.xpi"
  xdg-open "$DATA/ad-linux-tv-signed.xpi"
else
  echo 'Signed XPI unavailable: release gate. Set AD_LINUX_TV_XPI_URL and AD_LINUX_TV_XPI_SHA256 after AMO signing.'
fi
