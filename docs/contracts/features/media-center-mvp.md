# Feature contract: media-center MVP

- Status: Approved
- Date: 2026-10-24

## Goal

Provide `ad-linux-tv`, a Kubuntu media center launched in Firefox, with an adaptive service grid and phone-based LAN control. Services are defined in an understandable `config.yaml`: initial services are VK Видео, КиноПоиск, Яндекс Музыка, and YouTube. Each service opens in its own browser tab; Home closes that service tab and returns to the tiles. A persistent Firefox profile preserves service logins. A Firefox WebExtension connects commands to the browser. Start automatically after Kubuntu graphical login.

The local PWA management page is reachable from a phone on the LAN, with TV-displayed address and QR code. On the launcher grid, phone arrows and OK are guaranteed; on third-party services those controls are not guaranteed. Home, Back, Refresh, and direct service selection are guaranteed through browser/tab control. System volume control is conditional on safe availability and is not a required acceptance item. Protect remote control with a PIN/token.

Deliver a public GitHub repository at `aadegtyarev/ad-linux-tv` with understandable installation, configuration, update, and troubleshooting documentation; `install.sh` and `uninstall.sh`; dependency setup; generated user configuration; graphical Plasma autostart; and Firefox components. Development and automated checks run in the current development/test environment. Actual deployment and hardware smoke tests happen later on a separate target Kubuntu PC.

## Scenarios and edge cases

- Four service tiles fit without scrolling on an ordinary TV; layout adapts to screen sizes. New configured services appear automatically; above a configurable limit, paginate (proposed default: 12).
- Invalid YAML produces an understandable error and does not disclose secrets.
- A phone outside the LAN or presenting an invalid PIN cannot control the browser.
- On the launcher grid, arrows and OK move/select as promised. On third-party services, only Home, Back, Refresh, and direct service selection through browser/tab control are guaranteed; arrows/OK behavior is explicitly best-effort.
- Server or extension disconnection has understandable recovery behavior.
- Installer/uninstaller must preview and document filesystem locations, be safe/idempotent as far as practical, preserve user configuration on uninstall, avoid secrets in arguments/logs, and not weaken Firefox security. Target installation may use sudo and additional packages; keep Firefox Snap.
- Persistent Firefox extension installation may require a signed XPI or supported Firefox policy. Never disable signature/security checks. If automation requires unavailable signing credentials or policy setup, record a release blocker/manual gate rather than using an insecure workaround.
- DRM/Widevine and individual services are best-effort and manually verified; DRM circumvention is prohibited.
- Do not promise systemd autostart outside an active graphical user session.

## Non-goals

Local mpv/files, physical remote control, and circumventing DRM/ads/subscriptions/geo-restrictions. Deployment/install execution on the current development host is out of scope; target execution is a later operator action on another Kubuntu PC. Future extensibility for a physical remote is a constraint, not an implementation commitment.

## Affected surfaces

No existing surfaces. Expected new durable contracts after implementation:
- `docs/contracts/surfaces/tv-launcher.md`
- `docs/contracts/surfaces/phone-remote.md`
- `docs/contracts/surfaces/configuration.md`
- `docs/contracts/surfaces/kubuntu-operation.md`

## Interfaces and constraints

- Keep setup simple and flexible through one `config.yaml`; minimize dependencies.
- LAN bind address is configurable. Do not place secrets in client configuration or logs, installer arguments, or logs.
- Account for Firefox Snap constraints; do not assume LAN HTTP is a secure context. Preserve Snap and Firefox security settings.
- Installer/uninstaller must make filesystem locations understandable, and uninstall must preserve user configuration.
- Keep future physical-remote extensibility possible without implementing it now.
- Publish via the public GitHub repository `aadegtyarev/ad-linux-tv` and follow project GitHub publication/PR/merge workflow; this amendment task does not authorize remote creation or push.

## Acceptance criteria

- The service grid, browser navigation, and remote-control flows follow the goal and scenarios above, including the distinction between launcher-grid arrows/OK guarantees and third-party service controls.
- Remote access is protected by LAN restriction and PIN/token authentication; invalid configuration fails safely.
- Packaging provides the documented install/update/troubleshooting flow, safe/idempotent install/uninstall as far as practical, dependency setup, generated user configuration, graphical Plasma autostart, and Firefox components; uninstall preserves user configuration.
- Firefox extension installation never weakens security. Any signing/policy prerequisite that cannot be automated without credentials is an explicit release blocker/manual gate.
- Autostart is scoped to an active Kubuntu graphical user session. Current development host is not deployed to; target deployment requires later operator execution.
- Public GitHub publication and project PR/merge workflow are completed before release.

## Validation

- Run automated unit/integration tests for configuration, adaptive layout logic, authentication, and commands, plus available lint/static checks in the development environment.
- Validate installer/uninstaller safety and documented filesystem previews without deploying onto the current development host. Validate the Firefox extension manifest and installation/security approach; never disable signature/security checks.
- Maintain a separate target Kubuntu checklist for LAN phone control, Snap extension operation, X11/Wayland behavior as applicable, DRM/service playback, and graphical autostart. Run these checks on the separate target PC after an operator deploys; do not claim them verified from development checks.
- Pi package inventory could not be checked because parent tooling was incompatible with `/usr/bin/node` 20; this is unverified. Do not install or update Pi packages. No legacy extension conflicts were found during reconnaissance.
