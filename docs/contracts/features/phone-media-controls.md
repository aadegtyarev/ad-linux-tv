# Feature contract: phone media controls

- Status: Approved in chat, 2026-10-25.

## Goal and user-visible behavior
- The phone remote shows a compact playback panel when Firefox reports controllable media. While visible, it gives a little screen height from the touchpad to that panel; without media, the original touchpad size returns.
- The panel shows the current track/video title when Firefox supplies it, otherwise «Воспроизведение». Long titles can be scrolled horizontally without moving the entire page. It shows play/pause, elapsed/total time and a position slider when seeking is possible. Previous and next control the current Firefox media session when the site supplies those actions. Unsupported actions are visibly disabled. It does not add a page-player mute button; output and Firefox-stream mute remain the explicit sound controls.
- The panel follows actual TV state, including playback changed locally or by the site. A missing player, failed connection or stale state hides/invalidates the panel instead of showing controls for another app.

## Scenarios and limits
- In an accessible Firefox HTML audio/video session, play/pause and seek use Firefox's MPRIS media session. Previous/next depend on the site's Media Session support. Live streams or media without finite duration have no position slider.
- MPRIS may be absent for WebAudio, DRM/restricted media or a site that does not expose a playable session; the phone keeps its normal remote controls.
- If more than one Firefox media session exists, control only the Firefox session selected by the TV's session bus; never control another app's player.

## Non-goals
- No service-specific selectors, DOM scraping, automatic sound unmute, local-file player, extra WebSocket, or changes to browser command delivery.

## Affected surfaces
- [Phone remote](../surfaces/phone-remote.md)
- [Kubuntu operation](../surfaces/linux-operation.md)

## Interfaces and constraints
- Reuse the authenticated `/api/remote-ws` transport. A narrow media route may be added to the existing dispatcher to carry state and bounded actions; keep same session, Origin and CSRF rules. Use Firefox's MPRIS player via the TV-user D-Bus session; commands must never be constructed through a shell.
- Player controls must not interfere with touchpad pointer motion or audio settings. Disable unsupported actions from reported MPRIS capabilities. Bound and escape the media title in the UI; do not log it or expose URLs.

## Acceptance and validation
- Tests cover authenticated media control, Firefox-only selection, unavailable player/capability/seek, state refresh and responsive layout. Verify CI tests and a live reference TV page. Check playback against at least one real service when available; report any physical-site limit explicitly.
