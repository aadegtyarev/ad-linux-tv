# Reuse the bridge without turning it into a script runner

The Firefox bridge owns browser-side operations; Python owns the catalogue, authentication, queue and system controls. A remote/UI change that uses an existing browser operation does not need a new extension signature. A new browser operation or permission still can.

Signed bridge 0.4.1 is installed on the Beelink. It retains the original tab/volume protocol and the bounded HTML-media/view capabilities introduced in 0.4.0. The 0.4.1 repair replaces a failing zoom-settings setter; an actual Browser tile click and operator confirmation passed. See the [verification record](verification/tile-open-zoom-2026-10-26.md) for evidence and limits. An unsigned source archive is not an installed or production-signed extension.

## Capability reports

The new bridge reports to `POST /extension/media`. Like poll/ACK, this requires loopback source, exact `127.0.0.1:<listener-port>` Host and `X-AD-Linux-TV-Bridge: ad-linux-tv-v1`. The header is an application discriminator, not protection against a hostile local process.

Version 1 has these fields:

| Field | Meaning |
|---|---|
| `protocol` | Integer `1` |
| `sequence` | Increasing positive safe integer; older/repeated reports rejected |
| `sent_at` | Epoch milliseconds, accepted within three seconds of server time |
| `capabilities` | At most 16 short ASCII names; unknown names never become executable operations |
| `media` | `null` or the exact bounded HTML-media snapshot below |

Recognized capabilities are `html_media_v1` and `tab_view_v1`. Capability and media state expire after three seconds using both receipt and send-time freshness. A legacy bridge never sends this report. The server must not enqueue new HTML operations without a fresh report/current media identity. Optional reporting failures must not block original polling and commands.

`/api/status` exposes supported bridge capabilities and whether configured view behavior is waiting for support. It is not a receipt proving that a page or setting has physically settled.

## Managed HTML media

An HTML snapshot contains only `media_id`, `playing`, integer-second `position`/`duration`, and `can_seek`. Duration is positive and at most 24 hours. The extension sends no page URL, title, credentials or raw DOM. Media IDs are opaque 32-hex correlation tokens tied to the element/source, not authentication.

The fixed injected function examines at most 64 accessible audio/video elements and at most 16 seekable ranges. It selects a unique playing source, or a retained/unique paused source. Multiple competing players or frames are unavailable rather than guessed. Only the active launcher-owned service tab is inspected. Changed tab/document/element/source identity invalidates old actions.

An internal queued `media` operation carries an explicit `play`, `pause` or `seek`, the expected ID, optional integer-second position and a five-second execution deadline. There is no toggle, arbitrary selector, script string or general property setter. Seek must fall in an actual finite seekable range. Restricted frames, live/infinite timelines, DRM and inaccessible media may not provide this path; there is no bypass.

The phone's authenticated `/api/media` RPC prefers adequate MPRIS timing and otherwise uses fresh HTML state. HTML actions return **202 accepted**, with the current observed snapshot. The UI waits for later observations; acceptance is not playback/seek confirmation.

The durable command claim precedes the browser effect. A timed-out dispatched operation remains uncertain, including after late completion or redelivery; it is never automatically repeated. An already-dispatched effect can still finish on its old target. Queue leases and ACK delivery are not exactly-once guarantees. The existing ledger is bounded to 256 records.

A fixed pulse is injected only into an owned visible service tab to wake Firefox's event background while that page is being watched. It does not scan or inject into unmanaged tabs.

## Declarative service view

`tab_view_v1` consumes the effective service `view` from the server catalogue, not a remote arbitrary-header command. Services inherit the common setting unless they have an explicit override:

```yaml
view:
  mode: mobile
  zoom: 200
```

Modes are `desktop` and `mobile`; zoom is integer 50–300 percent. Within an explicit view object, omitted zoom defaults to 100/200 respectively. The source backend derives desktop125 when the common setting is absent/reset; this is distinct from the installed target's explicitly saved desktop125 for all six sites. See [configuration](configuration.md#common-desktop-or-mobile-view). An absent view at the extension API boundary is a no-op, but the server supplies inherited effective settings. Mobile uses a fixed Firefox-Android HTTP User-Agent derived from the running Firefox major version, plus per-tab zoom. It is best-effort layout selection, **not** full device/touch/navigator emulation or a DRM workaround.

The mobile header listener is filtered by the browser to an owned tab ID/window. It changes only User-Agent; other header objects, including authentication values, pass through without being read or logged. Policy and zoom are installed before the first service navigation, using a reserved owned blank tab when needed. Loss of ownership retires the policy.

Bridge 0.4.1 bounds `getZoomSettings` to 1.5 seconds, rechecks ownership after the read, requires `automatic` mode and `per-tab` scope, then calls `setZoom`. It does not call `setZoomSettings`. On Firefox 158.0.1, that setter hydrated an omitted `defaultZoomFactor` to `null` and rejected otherwise compatible settings. An incompatible scope or failed getter prevents the zoom write; a dispatched write timeout remains uncertain and is not replayed.

Managed startup derives a marked `browser.zoom.siteSpecific=false` block in the **dedicated TV profile**, making zoom independent per tab within that profile. This also applies to inherited common settings; removing individual overrides does not remove the need for the block. A full Firefox restart applies this preference. Original preference lines are retained; only the managed block is replaced. No zoom setter is applied to an unmanaged tab, and the extension never falls back to per-origin zoom. Do not apply these preferences to a personal/default browser profile.

Source/API evidence: [MDN zoom scope](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/tabs/ZoomSettingsScope), [Firefox tabs implementation](https://searchfox.org/mozilla-central/source/browser/components/extensions/parent/ext-tabs.js), and [header event](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/webRequest/onBeforeSendHeaders).

The installed 0.4.1 extension uses `webRequest`/`webRequestBlocking` for this fixed, tab-filtered policy. The repair retains 0.4.0's ID and permissions; it does not accept arbitrary UA strings, headers, code or remote modules. Open the service again from its tile to apply a changed view configuration. Old signed bridges ignore these settings and retain their original controls.

## What stays outside the extension

Discovery, pairing/session rules, Android profile selection, pointer/text input, output audio, the GTK timer and initial labwc magnifier scale remain server/app/compositor responsibilities. They do not need a new Firefox signature. Keep these boundaries rather than adding an unrestricted browser escape hatch.

See [configuration](configuration.md), [Android](android.md) and [release](release.md). Automated source/fake-DOM tests do not establish real-site, multicast, phone lifecycle, signed-extension or physical playback acceptance.
