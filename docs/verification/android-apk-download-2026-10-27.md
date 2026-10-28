# APK download through the existing TV QR — 27 October 2026

## Delivered on the own kiosk

Server0.1.0/build **`8a95389cf0c507a6`** now serves Android **0.2.5/code6** through the existing TV QR. No QR payload, pairing flow, native permissions or Firefox signature changed.

Use a normal phone camera to open the QR's `/remote` address. The browser offers the APK before PIN entry and keeps a compact link on its main remote after PIN-free entry or session restoration. Browser controls remain usable without installing anything. Refresh an already loaded page to receive the new UI. A device-bound native page suppresses the link and directs the user to a normal camera/browser: older native versions cannot download APK paths inside their WebView.

The user must explicitly download the file and handle Android's ordinary installation prompts. Publication is not proof that the phone installed or upgraded the app, retained its data, or passed camera/scanner/profile/lifecycle checks.

## Exact payload and runtime boundary

- Route: `GET /download/ad-linux-tv-remote-0.2.5-code6.apk`.
- Curated file: `/usr/local/share/ad-linux-tv/android/ad-linux-tv-remote-0.2.5-code6.apk`, root:root **0444**, regular, single-link, beneath trusted non-writable/non-symlink directories.
- APK:8,800,658 bytes; SHA-256 `fe6e335f6b88a1500f1702c6a6bbb57ba0e5b91f849efc9e406a833ce563fa71`.
- Server wheel: `ad_linux_tv-0.1.0-py3-none-any.whl`; SHA-256 `91661d41b692a605f542798582d1ee23f4bc85f218d2e5be81559332fb2f94de`;48 runtime files/54 unique safe members. APK bytes are separate from the package fingerprint.

The fixed public binary needs no PIN/session/Origin for ordinary navigation, but requires a private/loopback source and the existing connection-local direct Host check. This does not relax control authentication, Origin, CSRF or device/profile fences. QR, version and hash metadata are not authentication; trusted-LAN HTTP remains unencrypted.

The handler verifies type, root ownership, all file write bits clear, link count, size and hash through the same opened descriptor. Missing, unsafe or corrupt files fail closed with generic503. Two active transfers maximum, bounded chunks, five-second write and60-second total deadlines protect control-worker headroom. No generic file server, directory listing, availability endpoint or HEAD/Range/resume/update-feed guarantee was added.

## Deployment and preservation

The parent copied exactly the independently reviewed helper, wheel and unchanged RAW manifest into `/var/lib/ad-linux-tv-staging/apk-download-app-9b70c6d1`, root:TV0750/files0640, and verified copied identities before execution. The helper SHA is `8557363050bb5b08b8c58990030372fd7a1944e3cc26f59fbf3bb9d75e260df1`; RAW manifest SHA is `656b2aaacd7fb07ef3b5fab2b7fafdebad7967f93fe39147374d0694530244ed`.

After a current read-only timer snapshot showed no active countdown and a warning in the operator chat, the updater stopped/started only the own kiosk. Its actual result was exit0, `App transaction succeeded.` The fresh private `/var/lib/ad-linux-tv/apk-download-app-transaction` receipt is `deployed`. The previous successful `settings-app-transaction` remains historical evidence and must not be replayed or deleted. Existing `/var/lib/ad-linux-tv` remains root:root0700.

Installation ran as `ad-tv` with its existing Python3.14.4/venv/pip, offline and without dependency changes. Installed48 runtime files and source mirror match the reviewed bytes. Wrapper and normally signed Firefox0.4.1 hashes/modes, configuration/auth/session/preferences comparisons and autostart policy were preserved; profile cookie/history/form databases were not read or copied. No whole-host reboot, other-unit provisioning, power/media/input/CEC or timer set/cancel/wake test occurred.

### Integration defects caught before acceptance

The first deployment review found B1: ten malformed ZIP fixtures passed for the wrong outer identity refusal. Test-only corrections repinned coherent temporary manifests and asserted actual structural guards. A fresh full independent review reproduced RED/GREEN traces before approving the final helper/procedure. Production guards and immutable payload bytes were not weakened.

The historical publication recipe then produced0644, while the actual artifact verifier requires all file write bits clear. Real HTTP checks returned503, so app deployment was not called completed download delivery. A separately reviewed, fixed-path, held-descriptor operation verified the exact root-owned single-link APK and narrowed only its metadata from0644 to0444. It wrote no bytes, replaced nothing and required no second app install/restart. That literal's SHA is `3a9ecc30cb4654f686f7ecdcb1b1cc561ad7392835c845571ca9da79ed055b9e`. The corrected future atomic-publication recipe sets0444 before rename; its SHA is `4f3edd7e25804fa047da5df921f00d49c719ba37d29ff6e631eb4e7e2222bd71`. Do not reuse the old0644 recipe.

Parent staging's inline check also reported refusal after three completed copies. Independent read-only descriptor checks confirmed every copied hash, ancestor, owner, mode, link count and exact inventory before any helper execution; no copy/writer retry occurred. A separate read-only HTTP probe initially used the wrong `/static/remote.js` path; the real asset route is `/remote.js`. Neither probe caused an app redeployment or private-state restoration.

## Evidence and remaining gates

Source/canonical checks passed280 Python,176 Node, Ruff/format67 and the then45-file shipped-docs check. Independent deployment checks passed48 normal and48 optimized cases, separately reran the original37-method subset, and exercised actual service/schema/publication boundaries. The permission correction passed17 cases per mode, including the actual verifier rejecting0644 and reading fullfe6 after0444, without replacing critical predicates. Synthetic browser checks cover32 states; native main rectangles stay unchanged and the browser link costs36px. These are not physical phone/TV checks.

At20:45 UTC the installed endpoint returned **200**, the APK MIME type, fixed attachment filename, exact Content-Length, no-store, nosniff and connection close. A complete body read matched all8,800,658 bytes and fullfe6 SHA. Wrong Host and unauthenticated power reads remained403. The listener is the own UID1002/Python3.14 descendant of the current kiosk main process; the poweroff unit remains inactive.

Safe receipts, reviewed manifests and frozen payloads are under `.cache/releases/s09-apk-download-20261027/`; external source/deployment/mode-review evidence is under the parent-managed `agent-lanes` cache. Cached files are not a root trust boundary: execution still requires trusted root staging and copied-byte checks.

Actual camera download, Android update/data retention, installed phone version and native scanner/profile/lifecycle acceptance remain open. The missing TV countdown window is a separate subsequent repair; this APK delivery does not establish its cause or resolution.
