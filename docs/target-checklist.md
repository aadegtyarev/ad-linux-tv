# Beelink target checklist

Observed on Beelink SER10 Max with HDMI (2026-10-24):

- [x] Dedicated `ad-tv` labwc session renders the launcher at 1920×1200 without replacing the KDE user's profile.
- [x] Signed Firefox Snap bridge survives browser restart and reports connected.
- [x] Browser tile opens Yandex; YouTube loads through the dedicated Firefox profile's local Xray proxy.
- [x] Squeekboard can appear above the maximized Firefox window; English and Russian layouts render readable labels.
- [x] Yandex and YouTube provide a keyboard control on the connected touch monitor; the user opened the keyboard from Yandex's own icon.
- [x] The user touched the persistent «Клавиатура» control and Squeekboard opened; the «Плитки» control returned from YouTube in a script-level check.
- [x] Authenticated input API sends Cyrillic text to the focused Firefox field; unauthenticated input is rejected in automated tests.
- [x] Confirmed System → KDE stops the kiosk and starts SDDM; returning to the TV unit restores the bridge.
- [x] Killing the app server causes the kiosk unit to restart the complete session and restore the bridge.
- [x] Laptop on the private LAN can fetch `/remote` and `/api/qr`.
- [x] With Wi-Fi connected, disconnecting Ethernet changed the advertised address from `.105` to `.111` and regenerated QR; reconnecting Ethernet returned to `.105` and regenerated QR again.
- [x] HDMI sink selected for `ad-tv`; a short test sound was audible. The selection survived a TV session restart.
- [x] Firefox toolbar is hidden in the dedicated TV profile while Squeekboard remains visible; the touch overlay is placed in the lower right.
- [x] Focusing Firefox's hidden address bar reveals it; entering a URL in the managed Browser tab reaches that page and Home returns to the launcher.

Still to verify on the actual setup:

- [ ] Confirm physical touch on «Плитки» and repeat «Клавиатура» to dismiss it; test both keyboard languages, digits, symbols, and password fields on the touch monitor.
- [ ] Pair a real phone by QR, type with its native keyboard, use Home/Back/Refresh, test retry lockout and deny access from outside the trusted LAN.
- [ ] Change the DHCP lease to an unrelated address and confirm the QR/address refreshes and an already paired phone can reconnect; test packet loss during the change.
- [ ] After a real reboot, confirm default TV boot with HDMI; test no-HDMI console fallback, Ctrl+Alt+F2, `gui kde`, `gui off`, and `gui tv`.
- [ ] Test TV navigation with a remote or touch only, including all service tiles and third-party site controls.
- [ ] Confirm website playback audio, service logins/cookies across reboot, and DRM availability without bypasses; confirm behavior after Firefox updates.
- [ ] Complete signed XPI release/update and digest verification from the published artifact.

Treat the built-in HTTP remote as trusted-LAN only; keep its port off the public internet.
