# Firefox bridge protocol

The Firefox bridge (`extension/`) does browser work: owned service tabs, page-player volume, HTML media and per-tab view. Python owns the catalogue, authentication, command queue and system controls. A UI change that uses an existing bridge operation needs no new AMO signature; a new operation or permission does. There is no arbitrary-script operation, by design.

## Commands

The bridge polls the local server for queued commands, executes each at most once and acknowledges the result. A command that timed out after dispatch is marked uncertain and never repeated automatically. Bridge endpoints accept only loopback requests with Host `127.0.0.1:8765` and header `X-AD-Linux-TV-Bridge: ad-linux-tv-v1` (an identifier, not security).

## Capability reports

The bridge sends `POST /extension/media`:

| Field | Meaning |
|---|---|
| `protocol` | `1` |
| `sequence` | Increasing integer; older reports rejected |
| `sent_at` | Epoch ms, within 3 s of server time |
| `capabilities` | Up to 16 names: `html_media_v1`, `tab_view_v1`, `video_fullscreen_v1` |
| `media` | `null` or the HTML media snapshot |

Reports expire after 3 s. Without a fresh report the server queues no HTML-media operations. `/api/status` shows supported capabilities.

## HTML media (`html_media_v1`)

The snapshot has only `media_id` (opaque 32-hex), `playing`, `position`, `duration` and `can_seek`; no URL, title or DOM. Only the active owned tab is inspected; several competing players means "unavailable". Operations: `play`, `pause`, `seek` with the expected media ID and a 5 s deadline. The phone prefers MPRIS and falls back to HTML. HTML actions return 202 (accepted, not confirmed).

## Site view (`tab_view_v1`)

The bridge applies the effective `view` (`desktop`/`mobile`, zoom 50–300) from the server catalogue to owned tabs only. Mobile mode sets a Firefox-Android User-Agent for that tab and changes nothing else. Zoom uses `tabs.setZoom` after checking for automatic/per-tab zoom scope; `setZoomSettings` is not used. The launcher adds `browser.zoom.siteSpecific=false` to the dedicated profile only.

## Video fullscreen (`video_fullscreen_v1`, bridge 0.4.2+)

Queue command `fullscreen` toggles: if any frame of the active owned tab is fullscreen, the bridge leaves fullscreen; otherwise it fullscreens the largest visible video (a playing one wins), using the site's player box of the same size so its controls stay. No video means `no_media`. `POST /api/command` answers 409 while the bridge does not report the capability. The dedicated profile sets `full-screen-api.allow-trusted-requests-only=false` because a bridge call is not a user gesture.

## Outside the bridge

Discovery, pairing, Android, pointer/text input, output audio, the timer and the magnifier are handled by the server, app or compositor and never need a bridge signature.

See [Release](release.md) for signing.
