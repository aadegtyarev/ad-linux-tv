# Surface contract: Kubuntu operation

## Boundary and consumers
`install.sh`, `uninstall.sh`, CLI and graphical autostart install/run/remove the application within the invoking user's Kubuntu graphical session. Operators use the documented dry-run, install, update and removal flows.

## Paths and flows
- App, venv, run script, dedicated Firefox profile: `~/.local/share/ad-linux-tv` (profile subdirectory `firefox-profile`). Configuration: `~/.config/ad-linux-tv/config.yaml`. Plasma autostart: `~/.config/autostart/ad-linux-tv.desktop`.
- `./install.sh --dry-run` is the non-mutating default preview; actual installation requires explicit `./install.sh --install`. It prompts for PIN, preserves existing config, uses user venv, does not use sudo by default, and does not edit Firefox profile internals or register extensions unattended.
- `./uninstall.sh --dry-run` previews; `--remove` removes app/autostart and preserves config. Update is backup config then rerun install.
- Release extension flow requires signed XPI and SHA256 supplied via `AD_LINUX_TV_XPI_URL` and `AD_LINUX_TV_XPI_SHA256`; installer verifies digest and opens XPI for explicit interactive Firefox confirmation. Current AMO signing/assets are not provided. Optional enterprise policy is a separate explicitly privileged target gate, not default installation.

## Safety, failures, and recovery
Never put PIN/secrets in command arguments or logs; review dry-run before mutation. No silent sudo. Installed CLI validates config; troubleshoot server output, matching bridge localhost port 8765, and shared private LAN. Uninstall retains user configuration.

## Verification boundary and target checklist
Automated source/docs checks do not establish successful installation on Kubuntu. Firefox Snap installation, policy and persistent profile/extension behavior are explicitly unverified and require target testing. Before release, operator must check phone LAN login/retry lockout/outside access; Plasma autostart across logout/reboot; Firefox Snap extension persistence; X11 and Wayland focus/navigation; browser commands and extension disconnect recovery; service playback/DRM only without bypasses; signed XPI and digest flow. See [target checklist](../../target-checklist.md).

## Non-goals and related contracts
No deployment to development host, default system-wide changes, unattended Firefox registration, disabling signature checks, or DRM circumvention. Autostart applies only in active graphical user session. Related: [MVP feature](../features/media-center-mvp.md), [configuration](configuration.md), [TV launcher](tv-launcher.md), [phone remote](phone-remote.md).
