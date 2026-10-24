# Feature contract: Phone remote redesign

- Status: Complete; phone behavior and target operation verified
- Date: 2026-10-24
- Approval: User requested a complete phone remote redesign resembling a physical TV remote, with responsive layout, working arrows, and rare controls moved off the main screen.

## Goal and user-visible behavior

The paired phone opens a compact, familiar remote: Home, Back, a large shared touchpad with painted directional keys, pointer movement, tap-to-click, two-finger scroll, and immediate volume and text access. The primary controls fit common phone widths and heights without burying them below setup panels. Advanced controls live in a separate menu. Pressed buttons visibly acknowledge touch immediately, before a network response. The TV System sound settings offer a three-note chime for the selected output. The TV System button appears only with a touchscreen; arrows never move focus from tiles into System. The phone Menu opens System on the TV without an extension update.

## Scenarios and edges

- Short taps on the four visible edge arrows send keys to the active Firefox page; dragging anywhere on the surface moves the TV cursor, a pad tap activates the focused item after arrows or clicks at the cursor after pointer movement after arrows or clicks at the cursor after pointer movement, a tap elsewhere clicks the cursor position, and a two-finger swipe scrolls. A drag beginning on an arrow remains a pointer drag. When Firefox is not active, the phone explains that the TV window must be opened.
- The main remote preserves Home, Back, volume and mute, and fast phone-keyboard text entry. The menu retains service launch, URL entry, audio output, Firefox stream volume, Forward and Refresh. It offers a video-fullscreen shortcut for sites that support F and an Escape button; for other sites the touchpad can click the player fullscreen control.
- A short or narrow viewport keeps tap targets reachable; landscape may scroll. Status and errors stay visible without displacing the pad.
- Pairing still uses PIN, show/hide eye, session and CSRF. Reconnection requires login again if the session expires.

## Non-goals

- Site-specific player controls, voice control, or DRM changes.

## Affected surfaces

- [Phone remote](../surfaces/phone-remote.md): visual hierarchy, navigation and input behavior.
- [TV launcher](../surfaces/tv-launcher.md): sound check in System.

## Interfaces and constraints

- Authenticated `/api/input` accepts directional and OK keys. Authenticated `/api/pointer` accepts bounded move, click and scroll actions. Both require Firefox to be the active window; pointer clicks still land at the compositor cursor position, including over a focusless TV overlay. Existing `/api/command` remains for Home, service opening and refresh. No extension signing required.
- Keep the current LAN authentication, Origin/CSRF checks, and no storage of typed text.

## Acceptance criteria

- At 320x568, 393x852 and landscape phone viewports, Home, Back, touchpad, volume and keyboard access are readily reachable, without a sticky browser toolbar or the audio configuration block above the touchpad.
- Edge-arrow taps do not activate the launcher when a site is open. Pointer drag/click navigates ordinary desktop website controls without needing arrow-key support.
- All advanced features remain discoverable under one menu, and keyboard entry remains available with the native phone keyboard.
- A button tap has immediate visual feedback; a server error and pending/failure status appear in the fixed header indicator without covering or moving controls. Rapid D-pad taps preserve order. TV System plays a short three-note chime through the currently selected output or reports why it could not.

## Validation

- Run Node and Python tests, lint, a browser screenshot at multiple viewport sizes, Beelink dry-run and live phone/TV verification where possible.
