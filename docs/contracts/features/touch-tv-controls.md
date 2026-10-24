# Feature contract: Touch TV controls

- Status: Implemented; real-phone, DHCP lease and numeric keyboard checks pending
- Date: 2026-10-24
- Approval: User requested virtual keyboard for logins/search, phone text entry on a TV without touch, a browser tile opening Yandex search, a discreet System control away from service tiles, and QR/IP refresh when Ethernet changes to Wi-Fi. Later user requests added touch controls, removal of the visible Firefox toolbar, better phone-only navigation, and HDMI audio. On physical testing, the lower controls obstructed video scrubbing; user chose compact upper-right controls that hide when a window enters fullscreen and when no touchscreen is connected.

## Goal and user-visible behavior

The TV session supports text entry from the touchscreen in Firefox pages, including login forms and search. Home includes a Browser tile that opens a managed Firefox tab at Yandex search and permits ordinary navigation. System appears as a small corner control separate from service tiles and retains its confirmed KDE switch.

## Scenarios and edges

- Touching a text field brings up a keyboard; the keyboard can enter Latin letters, Cyrillic letters, digits and symbols needed for accounts and search, then be dismissed. Manually opening Squeekboard from the touch control keeps it visible during temporary focus loss in numeric code fields until the user closes it with the keyboard icon.
- The authenticated phone remote can send text, Enter and Backspace to the focused Firefox field using the phone’s own keyboard; no typed text is retained by the TV server.
- The Browser tile opens `https://ya.ru/`; Home from the phone remote returns to the launcher and closes the managed browser tab as with other services.
- System remains reachable by touch and the phone remote's arrows/OK. Its KDE action still requires a second confirmation.
- A failed server process must not leave a working looking browser pointing at a dead localhost page.
- When the active LAN address changes, the displayed address and QR image change without restarting the TV session.
- The TV profile hides browser chrome while keeping the screen keyboard usable. The Home, keyboard and sound touch controls sit next to each other at the upper right, occupy only their own small input area, and hide when a window enters fullscreen or no touchscreen is connected. The phone remote can open a managed Browser tab and navigate directly to an HTTP(S) address using its native keyboard.
- A detected HDMI audio sink is selected for the TV user, without changing the KDE user's default audio device.

## Non-goals

- Password storage, automatic login, text injection without authenticated phone access, or changing the KDE user's own desktop configuration.
- Guaranteeing that third-party websites support arrow/OK navigation or DRM playback.

## Affected surfaces

- [TV launcher](../surfaces/tv-launcher.md): Browser and System placement/navigation.
- [Configuration](../surfaces/configuration.md): default Browser service; existing schema unchanged.
- [Kubuntu operation](../surfaces/kubuntu-operation.md): touch keyboard and kiosk startup reliability.
- [Phone remote](../surfaces/phone-remote.md): authenticated text input, advertised LAN address and QR refresh.

## Interfaces and constraints

- Preserve the signed extension and its existing permissions; no XPI changes for this feature.
- Preserve the dedicated `ad-tv` user, source checkout, KDE/SDDM path, and console/SSH recovery.
- Keyboard entry must work on third-party Firefox pages, not only the local launcher.
- Keep the kiosk browser profile persistent and private.

## Acceptance criteria

- A touch user can type into Firefox login/search fields with an on-screen keyboard on the HDMI display.
- An authenticated phone user can type into the focused Firefox field from the phone’s native keyboard; without bridge, an actionable error appears.
- Browser tile opens Yandex and remains navigable as a normal tab; Home returns to launcher.
- System is visually separate from service tiles and reachable by touch and remote navigation; KDE still requires confirmation.
- Restarting the TV session leaves localhost service and Firefox running together or exits to recovery.
- Removing Ethernet with Wi-Fi connected updates the home address and QR to the Wi-Fi address without server restart.
- Browser chrome is absent on the home screen, and Squeekboard still appears above Firefox. The upper-right touch targets remain reachable with the keyboard shown and disappear in fullscreen or without a touchscreen. An HDMI test sound is audible.

## Validation

- Run relevant Python/Node/shell checks and dry-run; visually inspect a rendered launcher.
- Verify touch keyboard and browser text input on Beelink, plus phone text input, System navigation, session restart, and LAN address refresh.
- Observed on Beelink: Yandex and YouTube expose their own touch keyboard controls, and the user opened Squeekboard with the persistent overlay button; authenticated API text reaches Firefox; the overlay Home script returned to the launcher; System switches to KDE and back; killing the server restarts the full session; Ethernet disconnect/reconnect changes the advertised address and QR between `.105` and `.111`. Physical Home/dismissal, a real phone, and a fresh DHCP lease remain to be checked.
