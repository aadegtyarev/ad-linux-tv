# Settings and network access

The server uses one configuration file: `~/.config/ad-linux-tv/config.yaml`. Installation creates it only when absent and keeps it private (`0600`). The TV **System** screen and phone **Menu → Settings** cover the common choices; manual editing is mainly for administrators.

- **Phone access:** a new installation has `auth.require_pin: false`. Anyone who can reach the server on the trusted private network can open a remote session. Turn PIN on in settings and enter a four-digit code if needed. Only a salted verifier is stored in config; changing access mode or PIN ends existing phone sessions. Older configs retain their previous PIN setting.
- **Services:** `services` holds unique IDs, display names, HTTPS URLs and optional tile colors and view settings. Initial tiles are VK Видео, КиноПоиск, Яндекс Музыка, YouTube, KION and Browser. The Browser tile starts at `https://ya.ru/`.
- **Sound:** saved Firefox-stream level/mute and page-player target apply when new media starts. The selected output, its current level and mute are reported separately by the TV audio system. The phone and TV both show these layers in Sound.
- **Cursor:** acceleration ranges from 0 to 100. The magnifier is off by default and can be toggled from the TV or directly below the phone touchpad. Its initial scale defaults to 2.5×; the shared slider saves 1.25–5× in 0.25 steps. A scale change needs an explicit TV-session restart, not an automatic interruption of playback.
- **Firefox proxy:** system, none, or custom HTTP/SOCKS5 host and port. It affects only the dedicated TV Firefox profile; a change needs a TV-session restart.
- **Listener:** `bind` is the local address and port is fixed at 8765 because the Firefox bridge uses it. The QR advertises the OS-preferred private LAN address and changes after address renewal.

The phone receives a 14-day HttpOnly, SameSite=Strict session cookie and sends commands through one authenticated WebSocket. Origin and CSRF checks remain active with PIN off. HTTP on the home LAN does not encrypt typed text or session traffic; use a trusted private network and do not port-forward the listener. The PIN is displayed only on the local TV and is never returned to a phone.

## Discovery and stable identity

New configurations contain `discovery: {enabled: true, id: <UUID>, name: <friendly name>}`. Old configurations do not acquire an ID or start broadcasting merely by loading. Back up the private config, then use `ad-linux-tv enable-discovery --config <path> --discovery-name 'Beelink TV'` and restart the own server/session. `disable-discovery` preserves the ID. An already configured disabled center remains available by manual address/QR.

`_ad-linux-tv._tcp.local.` advertises a private address, actual port and nonsecret ID/name/protocol/path. Private-source, direct-Host `GET /api/device` exposes identity without cookies or authentication material; an unconfigured legacy server returns 503. IDs are correlation, not certificates or pairing authority. Do not copy the same ID to another TV; duplicate discovered IDs are ambiguous. See [Android](android.md).

## Initial magnifier scale

```yaml
magnifier:
  scale: 2.5
```

Omission keeps 2.5×. Only finite quarter steps from 1.25 through 5 are accepted. The kiosk launcher derives a private runtime labwc `rc.xml` from the YAML before starting the compositor. Settings distinguish saved scale from the boot-applied scale; a server-only restart does not pretend to have changed the compositor. Saving the slider never emits zoom keys or restarts the TV. The shared restart action explicitly warns that viewing will be interrupted.

## Common desktop or mobile view

Open «Вид сайтов» in phone or TV settings. Choose «Все сайты» for the common view or one configured site for an individual override. Choose «Мобильный / Обычный» and zoom, then save. A site without an override inherits the common setting; «Как для всех сайтов» removes only that site's exception. Common «По умолчанию» restores desktop125.

Saving does not navigate, reload video or restart the TV. Settings distinguish saved values from prepared profile state and show whether a restart is required. If required, restart explicitly when ready: viewing will be interrupted. Then reopen the service from its tile. Otherwise follow the next-open hint. The connected extension must also support the view policy.

The [2026-10-27 installation](verification/settings-versions-2026-10-27.md) includes this shared editor and desktop125 common omission/reset behavior. Read-only checks found all six services inheriting the explicitly saved common desktop125, with no individual overrides and no pending restart. Loading an omitted common value derives the default without rewriting private YAML.

YAML remains an alternative for an explicit service policy:

```yaml
services:
  - id: browser
    name: Browser
    url: https://ya.ru/
    view:
      mode: mobile
      zoom: 200
```

Use `desktop` or `mobile`, with integer zoom 50–300 percent. For a legacy explicitly specified mode with omitted zoom, desktop defaults to100 and mobile to200; this is distinct from the desktop125 common omission/reset default. A service without its own `view` inherits the common setting. Saving a common view preserves individual exceptions; clearing an exception changes only that service.

This needs a fresh `tab_view_v1` capability report. Installed signed 0.4.1 provided it during [tile-open acceptance](verification/tile-open-zoom-2026-10-26.md); legacy signed 0.3.2 keeps its original controls and ignores the new view fields. Missing/stale capability is reported as pending, not success. Mobile mode combines a fixed mobile HTTP User-Agent with per-tab zoom. It is not full touch/device/navigator emulation. A site may ignore it or require desktop mode for playback/DRM; there is no bypass or automatic fallback.

`run.sh` derives a marked `browser.zoom.siteSpecific=false` block in the dedicated TV profile so Firefox permits independent per-tab zoom, including inherited common settings. Original preferences remain; resetting common view settings still needs this block. Bridge 0.4.1 reads actual zoom settings, validates automatic/per-tab scope and rechecks ownership before `setZoom`; it no longer calls `setZoomSettings`. Getter failure or incompatible scope prevents the write, and a dispatched write timeout is uncertain and never automatically replayed. No zoom setter targets unmanaged tabs; the profile's zoom-persistence behavior changes while this policy is enabled. Personal/default profiles are not modified. See the [bridge protocol](bridge-protocol.md).
