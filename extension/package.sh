#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")" && pwd)
OUT=${1:-"$ROOT/ad-linux-tv-unsigned.zip"}
python3 -m json.tool "$ROOT/manifest.json" >/dev/null
python3 - <<'PY' "$ROOT/manifest.json"
import json, sys
m=json.load(open(sys.argv[1], encoding="utf-8"))
assert m["manifest_version"] == 3
assert m["background"].get("scripts") == [
    "tab_storage.js", "player_volume.js", "player_media.js", "view_policy.js", "owned_tabs.js", "command_ledger.js", "tabs.js", "bridge.js", "background.js"
]
assert "service_worker" not in m["background"]
version = tuple(map(int, m["browser_specific_settings"]["gecko"]["strict_min_version"].split(".")))
assert version >= (157, 0)
assert m["browser_specific_settings"]["gecko"]["data_collection_permissions"]["required"] == ["none"]
assert m["host_permissions"] == ["http://127.0.0.1/*", "http://*/*", "https://*/*"]
assert "scripting" in m["permissions"]
assert m["content_scripts"][0]["matches"] == ["http://127.0.0.1/*"]
PY
(cd "$ROOT" && zip -q -j "$OUT" manifest.json tab_storage.js player_volume.js player_media.js view_policy.js owned_tabs.js command_ledger.js tabs.js bridge.js background.js launcher.js)
python3 - <<'PY' "$OUT" "$ROOT/manifest.json"
import json, sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as archive:
    assert json.loads(archive.read("manifest.json")) == json.load(open(sys.argv[2], encoding="utf-8"))
PY
sha256sum "$OUT"
echo 'Unsigned development archive only; Firefox stable installation requires AMO-signed XPI.' >&2
