# Feature contract: media-center MVP

- Status: Approved
- Date: 2026-10-24

## Goal

Provide `ad-linux-tv`, a Kubuntu media center launched in Firefox, with an adaptive service grid and phone-based LAN control. Services are defined in an understandable `config.yaml`: initial services are VK Видео, КиноПоиск, Яндекс Музыка, and YouTube. Each service opens in its own browser tab; Home closes that service tab and returns to the tiles. A persistent Firefox profile preserves service logins. A Firefox WebExtension connects commands to the browser. Start automatically after Kubuntu graphical login.

The local PWA management page is reachable from a phone on the LAN, with TV-displayed address and QR code. Its controls are arrows, OK, Back, Home, refresh, and direct service selection. System volume control is conditional on safe availability and is not a required acceptance item. Protect remote control with a PIN/token.

## Scenarios and edge cases

- Four service tiles fit without scrolling on an ordinary TV; layout adapts to screen sizes. New configured services appear automatically; above a configurable limit, paginate (proposed default: 12).
- Invalid YAML produces an understandable error and does not disclose secrets.
- A phone outside the LAN or presenting an invalid PIN cannot control the browser.
- Server or extension disconnection has understandable recovery behavior.
- DRM/Widevine and individual services are best-effort and manually verified; DRM circumvention is prohibited.
- Do not promise systemd autostart outside an active graphical user session.

## Non-goals

Local mpv/files, physical remote control, circumventing DRM/ads/subscriptions/geo-restrictions, and deployment or installation on the working system during this task. Future extensibility for a physical remote is a constraint, not an implementation commitment.

## Affected surfaces

No existing surfaces. Expected new durable contracts after implementation:
- `docs/contracts/surfaces/tv-launcher.md`
- `docs/contracts/surfaces/phone-remote.md`
- `docs/contracts/surfaces/configuration.md`
- `docs/contracts/surfaces/kubuntu-operation.md`

## Interfaces and constraints

- Keep setup simple and flexible through one `config.yaml`; minimize dependencies.
- LAN bind address is configurable. Do not place secrets in client configuration or logs.
- Account for Firefox Snap constraints; do not assume LAN HTTP is a secure context.
- Keep future physical-remote extensibility possible without implementing it now.

## Acceptance criteria

- The service grid, browser navigation, and remote-control flows follow the goal and scenarios above.
- Remote access is protected by LAN restriction and PIN/token authentication; invalid configuration fails safely.
- Autostart is scoped to an active Kubuntu graphical user session.

## Validation

- Unit/integration tests cover configuration, adaptive layout logic, authentication, and commands; run lint/static checks.
- Validate Firefox extension manifest if tooling is available; perform browser UI smoke testing where possible.
- Keep a manual Kubuntu TV/phone/DRM/autostart checklist separate when unavailable in a headless environment.
- Pi package inventory could not be checked because parent tooling was incompatible with `/usr/bin/node` 20; this is unverified. Do not install or update Pi packages. No legacy extension conflicts were found during reconnaissance.
