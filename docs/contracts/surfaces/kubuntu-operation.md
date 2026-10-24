# Surface contract: Kubuntu operation

## Boundary and consumers
`install.sh`, `uninstall.sh`, CLI and graphical startup install/run/remove the application within the invoking user's session. Operators use the documented dry-run, install, update and removal flows. Beelink-specific TV integration is staged separately from the existing KDE login.

## Paths and flows
- App, venv and run script: `~/.local/share/ad-linux-tv`. Persistent Firefox Snap profile and signed XPI: `~/snap/firefox/common/`. Configuration: `~/.config/ad-linux-tv/config.yaml`. Optional Plasma autostart: `~/.config/autostart/ad-linux-tv.desktop`.
- `./install.sh --dry-run` is the non-mutating default preview; actual installation requires explicit `./install.sh --install`. `--no-autostart` omits/removes the invoking user's Plasma autostart entry for a separately managed TV session. Installation prompts for PIN, preserves existing config, uses a user venv, does not use sudo by default, and does not edit Firefox profile internals or register extensions unattended.
- `./uninstall.sh --dry-run` previews; `--remove` removes app/autostart and preserves config plus Firefox Snap profile/XPI. Update is backup config then rerun install.
- Release extension flow requires signed XPI and SHA256 supplied via `AD_LINUX_TV_XPI_URL` and `AD_LINUX_TV_XPI_SHA256`; installer verifies digest and opens XPI for explicit interactive Firefox confirmation. Current AMO signing/assets are not provided. Optional enterprise policy is a separate explicitly privileged target gate, not default installation.
- In the Beelink kiosk, the launcher Settings tile contains the phone QR/address and a confirmed KDE switch. A separate root-owned systemd unit performs the switch; `ad-tv` may only request that exact unit through sudo. Console and SSH `gui` recovery remain available.

## Safety, failures, and recovery
Never put PIN/secrets in command arguments or logs; review dry-run before mutation. No silent sudo. Installed CLI validates config; troubleshoot server output, matching bridge localhost port 8765, and shared private LAN. Uninstall retains user configuration.

## Verification boundary and target checklist
Automated source/docs checks do not establish successful installation on Beelink. Firefox Snap installation, policy and persistent profile/extension behavior are explicitly unverified and require target testing. Before release, operator must check phone LAN login/retry lockout/outside access; Beelink TV boot and KDE/console switching; Firefox Snap extension persistence; X11 and Wayland focus/navigation as applicable; browser commands and extension disconnect recovery; service playback/DRM only without bypasses; signed XPI and digest flow. See [target checklist](../../target-checklist.md).

## Non-goals and related contracts
No unattended Firefox registration, disabling signature checks, or DRM circumvention. Graphical startup applies only in an active graphical user session. Beelink system integration is separately previewed and activated under the [TV session feature](../features/beelink-tv-session.md), leaving KDE configuration intact. Related: [MVP feature](../features/media-center-mvp.md), [configuration](configuration.md), [TV launcher](tv-launcher.md), [phone remote](phone-remote.md).
