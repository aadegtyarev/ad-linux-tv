#!/usr/bin/env bash
set -euo pipefail

MODE=${1:---dry-run}
case "$MODE" in
  --dry-run|--configure) ;;
  *) echo 'usage: configure-firefox.sh [--dry-run|--configure]' >&2; exit 2 ;;
esac
PROFILE=/home/ad-tv/snap/firefox/common/ad-linux-tv-profile
printf '%s TV Firefox proxy 127.0.0.1:1081 and compact browser toolbar in %s\n' "$MODE" "$PROFILE"
[[ "$MODE" == --dry-run ]] && exit 0
(( EUID == 0 )) || { echo 'Run with sudo for --configure.' >&2; exit 1; }
python3 - <<'PY'
import socket
with socket.socket() as connection:
    connection.settimeout(1)
    try:
        connection.connect(("127.0.0.1", 1081))
    except OSError:
        raise SystemExit("Local Xray proxy is unavailable at 127.0.0.1:1081") from None
PY
install -d -o ad-tv -g ad-tv -m 700 /home/ad-tv/snap /home/ad-tv/snap/firefox /home/ad-tv/snap/firefox/common "$PROFILE" "$PROFILE/chrome"
PROFILE_PATH="$PROFILE" python3 - <<'PY_PROFILE'
import os
from pathlib import Path

profile = Path(os.environ["PROFILE_PATH"])
user_js = profile / "user.js"
managed = {
    "network.proxy.type": "1",
    "network.proxy.http": '"127.0.0.1"',
    "network.proxy.http_port": "1081",
    "network.proxy.ssl": '"127.0.0.1"',
    "network.proxy.ssl_port": "1081",
    "network.proxy.no_proxies_on": '"localhost, 127.0.0.1, 192.168.0.0/16, 10.0.0.0/8, 172.16.0.0/12"',
    "toolkit.legacyUserProfileCustomizations.stylesheets": "true",
}
existing = user_js.read_text() if user_js.exists() else ""
kept = [line for line in existing.splitlines()
        if not any(line.lstrip().startswith(f'user_pref("{key}"') for key in managed)]
kept.extend(f'user_pref("{key}", {value});' for key, value in managed.items())
user_js.write_text("\n".join(kept) + "\n")
css = profile / "chrome/userChrome.css"
rule = "#TabsToolbar, #PersonalToolbar { visibility: collapse !important; }"
old_css = css.read_text() if css.exists() else ""
if rule not in old_css:
    css.write_text(old_css.rstrip() + "\n" + rule + "\n")
PY_PROFILE
chown ad-tv:ad-tv "$PROFILE/user.js" "$PROFILE/chrome/userChrome.css"
chmod 600 "$PROFILE/user.js" "$PROFILE/chrome/userChrome.css"
echo 'Dedicated TV Firefox profile configured; restart the TV session to apply it.'
