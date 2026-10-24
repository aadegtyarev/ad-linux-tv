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
- Default installation is fully user-scoped: application files under `~/.local/share/ad-linux-tv`, configuration at `~/.config/ad-linux-tv/config.yaml`, and graphical autostart under `~/.config/autostart/`. Document any additional supporting paths consistently. Uninstall preserves configuration.
- Installer/uninstaller must preview and document filesystem locations, be safe/idempotent as far as practical, and avoid secrets in arguments/logs. Installation must not require sudo by default. Sudo is allowed only for an unavoidable optional system integration or dependency: never perform it silently; preview the exact privileged changes and ask for permission separately. Keep Firefox Snap.
- Stable Firefox requires a signed XPI. The recommended release path is AMO unlisted signing in CI, with signing credentials stored only in GitHub secrets and the signed XPI plus SHA256 published as release assets. The default user install downloads and verifies the XPI, then requires explicit interactive confirmation in Firefox. `install.sh` must not claim unattended extension registration or mutate Firefox profile internals.
- An optional Firefox enterprise policy is a separate, explicit sudo/target gate, not the default install path. Never disable signature checks. Firefox Snap policy, installation, and extension persistence require target testing.
- Use Firefox MV3 `background.scripts`, not `background.service_worker`, with minimal localhost host permissions.
- Until AMO signing credentials and target testing exist, signed-XPI release and Snap validation are explicit release gates; source and development checks may proceed.
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
- Default installation is user-scoped at `~/.local/share/ad-linux-tv`; configuration is `~/.config/ad-linux-tv/config.yaml`; graphical autostart is under `~/.config/autostart/`. Document additional supporting paths consistently. Uninstall preserves user configuration.
- No sudo is used by default. If an unavoidable optional system integration/dependency requires privilege, preview the exact changes and request permission separately; never apply privileged changes silently.
- Do not automate Firefox extension registration or mutate profile internals. The default flow verifies a signed XPI and requires explicit interactive Firefox confirmation. Release signing uses recommended AMO unlisted signing in CI; credentials are GitHub secrets only, and signed XPI plus SHA256 are release assets. Optional enterprise policy is a separate sudo/target gate, never the default. Firefox MV3 uses `background.scripts` and minimal localhost host permissions. Firefox Snap policy, installation, and extension persistence require target testing.
- Keep future physical-remote extensibility possible without implementing it now.
- Publish via the public GitHub repository `aadegtyarev/ad-linux-tv` and follow project GitHub publication/PR/merge workflow; this amendment task does not authorize remote creation or push.

## Acceptance criteria

- The service grid, browser navigation, and remote-control flows follow the goal and scenarios above, including the distinction between launcher-grid arrows/OK guarantees and third-party service controls.
- Remote access is protected by LAN restriction and PIN/token authentication; invalid configuration fails safely.
- Packaging provides the documented install/update/troubleshooting flow, safe/idempotent user-scoped install/uninstall as far as practical, dependency setup, generated user configuration, graphical Plasma autostart, and Firefox components; uninstall preserves user configuration. Default paths are `~/.local/share/ad-linux-tv`, `~/.config/ad-linux-tv/config.yaml`, and `~/.config/autostart/`.
- Default installation requires no sudo. Any unavoidable optional privileged integration/dependency is separately previewed with exact changes and requires separate user consent; no silent sudo.
- Firefox extension installation never weakens security: default installation verifies a signed XPI and requires explicit interactive Firefox confirmation without unattended profile registration or internal profile mutation. AMO unlisted signing credentials are held only in GitHub secrets; signed XPI and SHA256 are release assets. Unavailable signing credentials and untested Firefox Snap behavior remain explicit release gates, not reasons to use an insecure workaround. Enterprise policy is optional and separately gated.
- Autostart is scoped to an active Kubuntu graphical user session. Current development host is not deployed to; target deployment requires later operator execution.
- Public GitHub publication and project PR/merge workflow are completed before release.

## Validation

- Run automated unit/integration tests for configuration, adaptive layout logic, authentication, and commands, plus available lint/static checks in the development environment.
- Validate installer/uninstaller safety and documented filesystem previews without deploying onto the current development host. Validate the Firefox extension manifest and installation/security approach; verify signed XPI downloads against SHA256 and require interactive Firefox confirmation; never claim unattended registration or mutate profile internals or disable signature/security checks.
- Maintain a separate target Kubuntu checklist for LAN phone control, Firefox Snap policy/install/extension persistence, X11/Wayland behavior as applicable, DRM/service playback, and graphical autostart. Run these checks on the separate target PC after an operator deploys; do not claim them verified from development checks. Until AMO signing credentials and target testing exist, release is gated; source/dev checks may continue.
- Pi package inventory could not be checked because parent tooling was incompatible with `/usr/bin/node` 20; this is unverified. Do not install or update Pi packages. No legacy extension conflicts were found during reconnaissance.
