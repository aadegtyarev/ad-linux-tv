# iOS: keep the web remote, hide Android invitations — 28 October 2026

## Delivered behavior

The same TV QR still opens `/remote`. Recognized iPhone/iPad/iPod browsers no longer show the Android APK invitation before PIN, on MAIN after PIN-free/session restoration, or in Menu. This includes iPadOS Safari's desktop-style Macintosh/MacIntel identity with multiple touch points. Web controls and authentication remain available. Refresh an already loaded page to receive the change.

Android and ordinary desktop/unknown-browser behavior is unchanged. Device-bound Android pages retain the existing scanner/browser guidance and pairing/profile fences. No iOS app, automatic download, install, redirect or browser-to-app credential handoff was added.

Detection uses local browser hints only. It is a presentation heuristic, not proof of OS/native identity or authentication; spoofed or missing hints can change invitation visibility, not authority. The fixed APK GET remains available under its existing private-source/direct-Host rules, including when a user types its URL directly. No User-Agent server gate, new request, persisted platform identifier or telemetry was added.

## Scope and checks

Only `static/remote.js` changed in the package; the other47 runtime files are byte-identical to the previous8a release. Two test files cover actual template/script behavior for classic iOS, CriOS, desktop-style iPad, ordinary Mac/Windows/Linux/Android, absent hints, before-PIN/MAIN/Menu/restoration and bound/invalid contexts. The existing no-wake and binding/bootstrap checks remain.

Canonical checks passed **289 Python,178 Node, Ruff/format68** and the then49-file docs/link/Mermaid check. The independent final gate reran41 normal and41 optimized deployer methods,178 Node and13 focused tests, verified actual current91661 baseline restoration, all48 runtime/54 safe wheel members, RECORD, metadata, fingerprint and the minimal helper delta. The first review correctly blocked an older71029 fixture mislabeled as current91661; an explicit digest-checked current-baseline fixture corrected that test, without changing production guards. Historical rejected build modes and test corrections remain in private build/review evidence; no unapproved artifact was deployed.

After deployment, fresh sandboxed Chromium contexts with simulated iPhone, classic iPad and desktop-style iPad hints verified hidden invitations on MAIN/Menu/restoration, usable controls,48px toolbar and no overflow. Android and ordinary Mac retained the link. Their pad heights were about599px and563px respectively at393×851. Timer state was unchanged by these read-only UI checks. This is installed-page/browser emulation, **not physical Safari/iPhone/iPad acceptance**.

## Installed payload and preservation

- Server0.1.0/build **`b8799eb2b67487f7`**.
- Complete wheel SHA-256 `1a7ff9ae5d525ca5b90b7b0f377bf779ff23645325b3d8f40c6b6b3b164c5a4f`.
- Pinned RAW manifest `1b3dab54435c349ea15f86655136b1c66e8096ca0c96cbc083e35000c53d8278`.
- Release-specific reviewed updater `fd8d645547c174526649a5cba078547ca2f884ecf4bb1d2504d65c4da863ec8a`.

The parent warned before the own-kiosk restart and verified there was no active countdown. Exactly three copied authority files were root-locked/hash-checked in `/var/lib/ad-linux-tv-staging/ios-apk-ui-app-6e80a1b4` before isolated execution. The actual updater exited0 with `App transaction succeeded.` Its new private `/var/lib/ad-linux-tv/ios-apk-ui-app-transaction` receipt is deployed; previous successful transactions and root0700 private ancestry remain untouched. No retry or old-marker replay occurred.

Installed48 runtime files and source mirror, served JS and public build match the reviewed payload. The [APK0.2.5](android-apk-download-2026-10-27.md) remains exact8,800,658/fe6, root0444, with successful full GET/headers; wrong Host and unauthenticated power reads remain403. The [native timer script324](timer-window-icon-2026-10-28.md), wrapperdd2, normally signed Firefox0.4.1/XPI5397, private configuration/auth/sessions/preferences and autostart policy were preserved. No APK rebuild/signing, new package/permission/service, timer action, content playback or whole-host reboot occurred.

Frozen inputs, reviews and sanitized receipts live under `.cache/releases/ios-apk-ui-20261028/`; they exclude private browser profiles/cookies and screenshots. As always, mutable user-owned cache ancestry is not root execution authority: copied reviewed bytes under trusted root ancestry are required.
