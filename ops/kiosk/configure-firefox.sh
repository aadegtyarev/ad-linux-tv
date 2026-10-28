#!/usr/bin/env bash
set -euo pipefail

MODE=${1:---dry-run}
case "$MODE" in
  --dry-run|--configure) ;;
  *) echo 'usage: configure-firefox.sh [--dry-run|--configure]' >&2; exit 2 ;;
esac
COMMON=/home/ad-tv/snap/firefox/common
PROFILE=$COMMON/ad-linux-tv-profile
XPI=$COMMON/ad-linux-tv-signed.xpi
BRIDGE_ID=ad-linux-tv@aadegtyarev.github.io
LANGPACKS=(ru)
printf '%s dedicated TV Firefox profile %s: hidden browser chrome, signed bridge from %s, language packs %s\n' \
  "$MODE" "$PROFILE" "$XPI" "${LANGPACKS[*]}"
[[ "$MODE" == --dry-run ]] && exit 0
(( EUID == 0 )) || { echo 'Run with sudo for --configure.' >&2; exit 1; }

install -d -o ad-tv -g ad-tv -m 700 /home/ad-tv/snap /home/ad-tv/snap/firefox "$COMMON" "$PROFILE" "$PROFILE/chrome" "$PROFILE/extensions"

# Browser chrome and extension policy are kiosk behavior; the proxy is a separate setting.
PROFILE_PATH="$PROFILE" python3 - <<'PY_PROFILE'
import os
from pathlib import Path

profile = Path(os.environ["PROFILE_PATH"])
user_js = profile / "user.js"
managed = {
    "toolkit.legacyUserProfileCustomizations.stylesheets": "true",
    # Enable the signed bridge and language packs placed in this profile without a prompt.
    # Firefox still enforces the add-on signature.
    "extensions.autoDisableScopes": "0",
    # The fullscreen button reaches the page through the bridge, not a user gesture.
    "full-screen-api.allow-trusted-requests-only": "false",
    "full-screen-api.warning.timeout": "0",
    # A TV has no click before playback; without this sites such as KION start muted.
    "media.autoplay.default": "0",
}
existing = user_js.read_text() if user_js.exists() else ""
kept = [line for line in existing.splitlines()
        if not any(line.lstrip().startswith(f'user_pref("{key}"') for key in managed)]
kept.extend(f'user_pref("{key}", {value});' for key, value in managed.items())
user_js.write_text("\n".join(kept) + "\n")
css = profile / "chrome/userChrome.css"
old_css = css.read_text() if css.exists() else ""
managed_rules = (
    "#TabsToolbar, #PersonalToolbar { visibility: collapse !important; }",
    "#TabsToolbar, #PersonalToolbar, #nav-bar { visibility: collapse !important; }",
    "#nav-bar { margin-top: -40px !important; opacity: 0 !important; pointer-events: none !important; }",
    "#nav-bar:focus-within { margin-top: 0 !important; opacity: 1 !important; pointer-events: auto !important; }",
)
kept_css = [line for line in old_css.splitlines() if line not in managed_rules]
css.write_text("\n".join(kept_css + [managed_rules[0], *managed_rules[2:]]) + "\n")
PY_PROFILE
chown ad-tv:ad-tv "$PROFILE/user.js" "$PROFILE/chrome/userChrome.css"
chmod 600 "$PROFILE/user.js" "$PROFILE/chrome/userChrome.css"

if [[ -f "$XPI" ]]; then
  install -o ad-tv -g ad-tv -m 600 "$XPI" "$PROFILE/extensions/$BRIDGE_ID.xpi"
  echo 'Signed bridge placed in the dedicated profile.'
else
  echo "No signed bridge at $XPI; Firefox tab control stays unavailable until one is supplied."
fi

# Language packs must match the installed Firefox version exactly.
version=$(sed -n 's/^Version=//p' /snap/firefox/current/usr/lib/firefox/application.ini 2>/dev/null || true)
case $(uname -m) in
  x86_64) platform=linux-x86_64 ;;
  aarch64) platform=linux-aarch64 ;;
  *) platform= ;;
esac
if [[ -z $version || -z $platform ]]; then
  echo 'Firefox Snap version or platform unknown; language packs skipped.' >&2
  exit 0
fi
base="https://releases.mozilla.org/pub/firefox/releases/$version"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
if ! curl -fsS --proto '=https' --tlsv1.2 -o "$tmp/SHA256SUMS" "$base/SHA256SUMS"; then
  echo "Firefox $version checksums unavailable; language packs skipped." >&2
  exit 0
fi
for locale in "${LANGPACKS[@]}"; do
  expected=$(awk -v name="$platform/xpi/$locale.xpi" '$2 == name {print $1}' "$tmp/SHA256SUMS")
  if [[ -z $expected ]] || ! curl -fsS --proto '=https' --tlsv1.2 -o "$tmp/$locale.xpi" "$base/$platform/xpi/$locale.xpi"; then
    echo "Firefox $version language pack $locale unavailable; skipped." >&2
    continue
  fi
  if ! printf '%s  %s\n' "$expected" "$tmp/$locale.xpi" | sha256sum --check --status; then
    echo "Language pack $locale checksum mismatch; skipped." >&2
    continue
  fi
  install -o ad-tv -g ad-tv -m 600 "$tmp/$locale.xpi" "$PROFILE/extensions/langpack-$locale@firefox.mozilla.org.xpi"
  echo "Firefox $version language pack $locale installed."
done
echo 'Dedicated TV Firefox profile configured; restart the TV session to apply it.'
