# Feature contract: video fullscreen button

Status: approved 2026-10-28, in progress.

## Goal and user-visible behavior
One button on the phone remote and on the TV touch panel toggles the video on the current service page between fullscreen and normal view. Nothing happens automatically: opening a service or starting playback never enters fullscreen, so the user can still pick another video.

## Scenarios
- A video is on the page and nothing is fullscreen: the button makes the video's player fullscreen. The bridge picks the largest visible video, preferring one that plays, and fullscreens its outermost ancestor with the same box (the site's player), so site controls and subtitles stay; otherwise the `<video>` itself.
- Something is fullscreen: the same button exits fullscreen.
- No owned service tab or no visible video: nothing changes; the phone shows «Видео не найдено».
- Bridge without the capability (0.4.1 and older): the server answers 409 and the phone says the bridge needs updating.
- Touch panel while fullscreen: the full panel stays hidden over video, but the exit button and the volume button remain, so touch-only users can leave fullscreen and adjust the sound.

## Non-goals
Automatic fullscreen; site-specific scripts or selectors; fullscreen for unmanaged tabs; changing F11 browser-window fullscreen; DRM or player bypasses.

## Affected surfaces
[TV launcher](../surfaces/tv-launcher.md) (touch panel), [phone remote](../surfaces/phone-remote.md), [Linux operation](../surfaces/linux-operation.md) (profile preference), bridge protocol in `docs/bridge-protocol.md`.

## Interfaces and constraints
- New queue command `fullscreen` through existing `POST /api/command` (session + CSRF for the phone, loopback for the kiosk), accepted only while the bridge reports capability `video_fullscreen_v1`.
- Bridge 0.4.2 adds the capability and a fixed injected function; no new permissions, no page data leaves the tab beyond a frame score.
- `configure-firefox.sh` sets `full-screen-api.allow-trusted-requests-only=false` and `full-screen-api.warning.timeout=0` in the dedicated profile only, because a bridge call is not a user gesture.
- New bridge version needs AMO signing before deployment.

## Acceptance criteria
- Unit tests for the queue/route gate, bridge selection/toggle logic and phone/touch buttons; full CI green.
- On a TV with signed 0.4.2: button enters and exits fullscreen on YouTube; the touch exit and volume buttons are visible in fullscreen and the volume slider works there; no automatic fullscreen when opening a video.

## Validation
`pytest -q`, `node --test tests/*.test.js`, ruff, `bash -n`; live check on the B20A and the Beelink after signing.
