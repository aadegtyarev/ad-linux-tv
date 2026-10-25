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
- [x] Firefox toolbar is hidden in the dedicated TV profile while Squeekboard remains visible; adjacent touch controls sit in the upper right and disappeared/reappeared when Firefox toggled fullscreen via F11.
- [x] Focusing Firefox's hidden address bar reveals it; entering a URL in the managed Browser tab reaches that page and Home returns to the launcher.
- [x] A real reboot with HDMI started the TV session automatically; the bridge, LAN remote and HDMI sink returned.
- [x] The phone audio API accepted an authenticated LAN session, reported HDMI at 100%, and accepted volume, unmute and HDMI selection; the saved preference is mode 0600. The colored service tiles were confirmed on Beelink.
- [x] The pairing PIN was detected visually under QR on the TV home screen; local retrieval succeeded, public service data omitted it, and forged-Host LAN retrieval returned 403.
- [x] With `auth.require_pin: false`, the TV shows “PIN не нужен”; a fresh LAN browser receives a session without PIN, invalid CSRF is rejected, and a foreign Host cannot bootstrap a session.
- [x] The new phone Tab button focused elements in KION and Kinopoisk through the live remote; Enter was delivered in KION. A 390 px mobile viewport showed Tab, Shift+Tab and Enter below the touchpad without overlap. YouTube loaded with the new remote; its Tab order reaches video cards only after many navigation controls.
- [x] Opened all six service tiles on Beelink and checked keyboard focus: Kinopoisk, KION, YouTube, VK Video, Yandex Music and Browser. Tab visibly focused a menu or control in Kinopoisk, KION, VK Video and Browser; repeated Tab reached a YouTube video card. Yandex Music accepted the key, but no visible focus change was established. On Kinopoisk and VK Video, ArrowDown scrolled content while focus stayed on the previous control; ArrowRight did not select an adjacent Kinopoisk card. Kinopoisk card click opened its details.
- [x] After moving phone controls to one WebSocket, the user confirmed the real-phone cursor has almost no jerks and that scrolling works well. The TV launcher serves a visible System button on an ordinary TV; automated navigation confirms arrows and bridge OK stay on tiles, while pointer click opens System.
- [x] Signed bridge 0.3.1 was copied to the dedicated Firefox profile and Firefox reports it active. Its source files match the unsigned archive submitted for signing; the manifest content matches after JSON parsing.
- [x] Two Firefox audio streams for the same Kinopoisk film survived the bridge update; pausing the visible player left one stream active. Restarting the TV kiosk cleared both streams. Bridge updates now require a TV-session restart before playback checks.
- [x] TV System now fits the 1360×768 target screen without a scrollbar and shows PIN, magnifier and Firefox proxy controls. The built-in labwc 2.5× magnifier visibly activated on the TV and was switched off again. The live settings API reports PIN off and retains the existing local Xray proxy; phone WebSocket settings read/write passed without changing either preference.

Still to verify on the actual setup:

- [ ] Tap the on-keyboard `EN → RU` / `RU → EN` key and confirm both directions, then enter several digits in a third-party code field after manually opening the keyboard; confirm it stays visible until closed. Confirm physical touch on «Плитки» and repeat «Клавиатура» to dismiss it; test both keyboard languages, digits, symbols, and password fields on the touch monitor.
- [ ] Confirm the overlay hides when the touchscreen is unplugged and that YouTube's own fullscreen video triggers the same behavior as F11.
- [ ] Open the remote on a real phone without PIN, type with its native keyboard, use Home/Back/Refresh, and confirm a second phone can scan the QR shown in the first phone's Menu. In PIN-required mode, test retry lockout; deny access from outside the trusted LAN in both modes.
- [ ] Change the DHCP lease to an unrelated address and confirm the QR/address refreshes. Check that the phone redirects while its old connection still works, and that a fresh QR scan restores access after an abrupt break; test packet loss during the change.
- [ ] Confirm Back is the leftmost button below the pad at phone width. Check that arrow/Tab navigation makes a pad tap send Enter, while cursor movement makes it click at the pointer; test Kinopoisk, KION and YouTube, including cards below the first screen.
- [ ] Test no-HDMI console fallback, Ctrl+Alt+F2, `gui kde`, `gui off`, and `gui tv` after reboot.
- [ ] Test TV navigation with a remote or touch only, including all service tiles and third-party site controls. On each of the six services, start playback, switch service or return Home, and verify background playback stops.
- [ ] Touch the sound icon and adjust the single output slider during playback; confirm the panel stays open while dragging. Check the same level in remote/System, mute, and output selection with a connected Bluetooth speaker or other output. Confirm Firefox stream and managed HTML media are normalized to 100% while the chosen output level stays unchanged. Confirm website playback audio, service logins/cookies across reboot, and DRM availability without bypasses; confirm behavior after Firefox updates.
- [ ] Set, replace and cancel the display timer from the phone remote, touch overlay and TV System. During playing video, confirm it pauses before HDMI turns off; wake with touch and with a phone command, and confirm the video does not resume. Check that an unavailable bridge/player leaves HDMI lit with a useful message.
- [ ] On each of the six services, confirm playback stops on Home and service switching with signed bridge 0.3.1 active.
- [ ] On a real phone, open Menu → Settings and verify PIN enable/change/disable, magnifier toggle, and proxy mode/restart. Check the TV pairing display and phone relogin after PIN change. Test an actual proxy change and restoring the local Xray setting; confirm websites and LAN pult work afterward.

Treat the built-in HTTP remote as trusted-LAN only; keep its port off the public internet.
