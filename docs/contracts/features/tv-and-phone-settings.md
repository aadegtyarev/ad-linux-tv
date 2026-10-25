# Feature contract: TV and phone settings

- Status: Installed on Beelink; automated checks and TV visual check passed. Real-phone settings and actual PIN/proxy changes remain acceptance checks, 2026-10-25.
- Approval: User approved the exact scope through the in-session contract question. Telegram was removed from scope; local-file playback is a later task.

## Goal and user-visible behavior
TV System exposes PIN, magnifier and TV-browser proxy settings. The phone Menu has PIN and proxy settings, with the magnifier shortcut beside the volume slider on the main phone remote. The TV System page fits the normal TV screen without a scrollbar. New installations have PIN access disabled by default.

## Scenarios and edges
- New configs use `auth.require_pin: false`; existing configs keep their saved mode. TV and authenticated phone can enable PIN with a confirmed four-digit code, replace it, and disable it. PIN material never appears in phone settings reads or logs. On mode/code change, old phone sessions become invalid and the phone follows the new login flow.
- The labwc built-in cursor magnifier is off at TV-session start, shows a 2.5x window around the cursor when switched on, and is controlled from TV System or a button beside phone volume under the touchpad. State is shared and visible on both surfaces. It does not magnify the phone UI.
- Firefox in the dedicated TV profile offers system proxy, no proxy and manually specified HTTP or SOCKS5 host/port. The existing `127.0.0.1:1081` setting is retained until changed. Localhost/private LAN bypass remains in manual mode. Invalid proxy input changes nothing. Changes take effect after restarting the TV browser/session with user-visible feedback.
- The compact TV System keeps audio, timer and the confirmed KDE switch accessible without vertical scrolling at the target 1360x768 display. Arrow/OK navigation remains usable. The phone Menu opens a Settings page for PIN and proxy.
- Telegram is not added. Local-file playback is outside this feature.

## Non-goals
- Changing global OS/KDE proxy settings, exposing credentials in proxy URLs, automatic proxy health checks, changing website navigation/DRM, or implementing a file player.

## Affected surfaces
- [Configuration](../surfaces/configuration.md)
- [TV launcher](../surfaces/tv-launcher.md)
- [Phone remote](../surfaces/phone-remote.md)
- [Kubuntu operation](../surfaces/kubuntu-operation.md)

## Interfaces and constraints
- Keep one private `config.yaml` as the durable source; save atomically with mode 0600. No new standalone live phone transport: authenticated settings actions use the existing WebSocket with Origin, session and CSRF checks. Local TV settings calls require exact loopback Host/Origin and kiosk mode.
- Never return PIN verifier/salt or raw PIN to a phone settings read. Keep existing local-TV pairing display boundary. Old sessions are invalidated on PIN changes; prevent a remote lockout by requiring the new PIN before enabling.
- Firefox proxy applies only to the dedicated TV profile. Existing unrelated preferences and the KDE profile remain untouched.
- If applying a setting fails, report it and preserve the previous working setting wherever possible.

## Acceptance and validation
- Config validation and CLI defaults; PIN enable/change/disable flows from both clients, session invalidation and forbidden LAN direct writes; proxy mode/input validation and profile output; magnifier toggle and state; TV/phone controls and focus; compact TV viewport screenshot/layout.
- Run focused and full Python/Node tests, lint, shell checks and deployment dry-run; deploy to Beelink, verify no Firefox audio stream regresses, test signed bridge still active. Real phone and TV visual acceptance may remain user checks.
