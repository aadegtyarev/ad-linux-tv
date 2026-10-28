# Native countdown window repair — 28 October 2026

## Result

The own kiosk's native upper-left countdown panel is restored. A private narrow capture of the real Wayland output showed the new clock glyph and **15 мин** after installation. During the same unchanged countdown, the panel automatically expanded at1:48 with **Экран скоро погаснет** and the existing **Свернуть / Изменить / Отменить** buttons. These observations use the actual GTK window, not a browser DOM or mock screenshot. No private image or raw terminal contents are shipped or sent.

The operator explicitly authorized the parent to set the timer, inspect the screen, then wake/set another cycle and perform benign live checks. The first successful15-minute cycle expired normally before repair. The post-repair cycle used one explicit wake without CEC and one15-minute setting; no uncertain write was replayed, timer reset/cancellation, video launch, sound test or host shutdown was used. The passive same-generation observer then confirmed normal expiry at04:44:44 UTC: remaining0, asleep, no error. It issued no POST, input or wake action. Evidence is recorded with the final release receipt.

## Failure and bounded fix

Source and installed script hashes matched, GTK/GI dependencies existed, the server was healthy and an idle overlay process could remain alive. Those facts did not establish active rendering. An authorized crop during a real countdown showed the expected panel absent. Filtered dedicated-kiosk diagnostics then identified repeated `gtkiconhelper.c:495` assertions, failed image loading, `gdk-pixbuf-error-quark`, `image-missing`, `glycin/bwrap` and timer-script attribution. The timer's sole themed `Gtk.Image` alarm was implicated at first render.

The fix replaces that image lookup with a compact GTK text clock `◷` and a local24px style. Count text remains26/30px. It removes this panel's dependency on the failing theme/pixbuf path; it does **not** disable or change the system image-loader sandbox, packages, themes or security policy. No new rendering dependency was added.

TimerNotice, request/auth/DTO handling, presets, server deadlines/generations, warning threshold/dismissal, callbacks, layer/anchors, focus policy, geometry and media/sleep/CEC behavior are unchanged. The only installed software change is the external timer script; the package remains server0.1.0/build8a95389cf0c507a6 and the [same-QR APK delivery](android-apk-download-2026-10-27.md) remains intact.

## Review and deployment

- Previous timer script SHA-256: `5264156c235597c2aafc62c3ff4c072e0763b0a123ae1d5a28572ad93ddeb2e0`.
- Reviewed replacement: `324582deddbab8cf943bfd8903221121b7f723d179717d22f13797c6706d52e8`.
- New focused tests: `bf48ad5047126a1343ce413fc7b8f8094382197b2dd24030521f04bcf32798d6`.
- Exact parent publication literal: `e94a318606c6f82e6d10b58e98df4ceb85c592147f962fa3d32fb46aa5d1fb6d`.

One isolated source writer changed only `ops/kiosk/timer-overlay.py` and added `tests/test_timer_overlay.py`. A fresh independent reviewer reran12 normal and12 optimized cases, scoped Ruff/format/compile, real old-constructor negative control and229-file guard:228 protected files unchanged, the one allowed existing script change and explicit new test only. Twelve unprivileged real-filesystem tests exercised the exact publisher, including corrupt-copy refusal before exposure and post-replace failure truthfulness. No mock test is claimed as native rendering acceptance.

The parent verified the literal in memory and executed it under trusted system Python. It checked the known old root-owned0755 regular single-link script and safe ancestors, saved one bounded private rollback copy, copied the replacement once to its own same-directory temp, verified copied bytes/mode before exposure and atomically replaced only `/usr/local/libexec/ad-linux-tv/timer-overlay.py`. Private backup/receipt are under `/var/lib/ad-linux-tv/timer-window-icon-transaction`, root0700/files0600. Existing private ancestry and successful app transaction markers were retained.

The publication exited0 at04:28 UTC. The existing supervisor loaded the new child automatically; no PID signal or whole-kiosk restart was needed. Current main process, timer model, wrapper and normally signed Firefox0.4.1 remained unchanged. The new UID1002/Python3.14 timer child was stable across observations. No setup command, dependency installation, unit/session/module/sudoers/profile/configuration/native/APK/signing change occurred.

The first source attempt stopped on expected no-Git-lane metadata exit128 without edits. Parent clarified that this is expected, explicitly supplied the canonical read-only development toolchain and renewed the same protocol. No Git initialization, index/config writes, provider/tool-mode fallback or production child access followed.

## Other live checks

A fresh isolated **sandboxed headless Chromium** used the installed backend at393×851; it did not inspect the existing TV Firefox or phone profiles. Actual results:

- PIN-free MAIN link visible, still visible after session-restored reload;48px toolbar, flexible563px pad and no horizontal overflow.
- Settings/About displays server0.1.0/build8a, hides the native-app row in a normal browser and wraps without overflow.
- Common desktop125 and all six per-site inherited snapshots display correctly when switching local form scope. No save, PIN/proxy change or restart was requested.
- Explicit browser APK download completed with all8,800,658 bytes/fullfe6 hash.
- Timer generation, minutes and phase remained unchanged; only remaining time decreased.

These are installed-backend/browser checks, **not** Android installation/lifecycle/notification acceptance or physical phone layout. No real media/title/URL, raw cookie/session/PIN or private browser data is included in reports. No site playback/DRM, video fullscreen/reflection, sound-policy or full host-shutdown acceptance is inferred.

Canonical regression after integration passed **289 Python,176 Node, Ruff/format68**, and the then47-file shipped-docs/link/Mermaid check. Final documentation checks are in the release receipt. Safe reviewed inputs, publisher, receipts and sanitized live outcomes are frozen under `.cache/releases/timer-window-icon-20261028/`; private captures remain outside distributables.

## Remaining acceptance boundaries

Actual warning/button rendering is observed, but clicking Change/Cancel, hover behavior, generation rearm and placement above a real fullscreen video were not actuated in this live cycle. Their unchanged behavior has source/mock coverage. Physical HDMI-panel/CEC behavior and Android installation remain separate; the operator's TV panel was powered off during remote inspection. After the confirmed04:44 asleep checkpoint, a later04:53/04:55 read found idle/awake with no error. No additional wake/reset/cancel was sent; the cause of that later transition is unassigned and retained as a separate observation, not silently called persistent sleep acceptance or patched here. The timer fix does not repair the global GTK image-loader environment or unrelated media work.
