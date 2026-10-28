# Feature contract: generic Linux kiosk

Status: approved 2026-10-28, in progress.

## Goal and user-visible behavior
The dedicated TV session installs on any apt/snap Linux computer, not only the original Beelink with KDE.

1. **Generic target.** Kiosk integration lives in `ops/kiosk/` and is documented in `docs/kiosk.md`. Scripts, guides and contracts do not name a hardware vendor or a personal account. The administrator is the user who runs `sudo` (`$SUDO_USER`); the source checkout is wherever the scripts are run from. Setup installs the runtime it needs: labwc session packages, PipeWire, fonts, `python3-venv` and Firefox Snap.
2. **KDE is optional.** When no `sddm.service` exists, the TV System control does not offer the KDE switch and `gui kde` reports that it is unavailable. Existing KDE computers keep the switch.
3. **Browser chrome independent of proxy.** Setup always hides Firefox tabs/toolbars in the dedicated profile. The proxy comes only from the existing `proxy` setting; setup no longer probes `127.0.0.1:1081`.
4. **Firefox language.** Optional `browser.locale` (`ru` or `en`, default `ru`) is chosen in TV System and phone Menu → Settings as «Язык браузера». Saving writes a managed locale block in the dedicated profile and asks for the existing TV-session restart. Setup downloads the language pack matching the installed Firefox version from `releases.mozilla.org`, verifies it against the release `SHA256SUMS`, and installs it in the dedicated profile.
5. **Signed bridge enabled by setup.** When a signed XPI is present, setup installs it in the dedicated profile's `extensions/` directory and sets `extensions.autoDisableScopes=0` there, so Firefox enables it without an on-screen confirmation. Firefox still enforces the AMO signature.

## Scenarios and edge cases
- Fresh Ubuntu Server with no desktop: setup + deploy + activate produce a working kiosk at boot with a connected display.
- Existing Beelink deployment: config, PIN, sessions, profile, bridge and local Xray are preserved; KDE switch still available.
- Language pack download fails or version has no pack: setup warns and continues; settings show that the selected language pack is not installed and Firefox stays in its default language.
- Configs without `browser` are valid and mean `ru`.

## Non-goals
Translating the launcher or phone remote UI; installing Xray or any proxy credentials; disabling Firefox signature checks; changing the generic per-user `install.sh` flow beyond shared code; rewriting dated verification records.

## Affected surfaces
[Kubuntu operation](../surfaces/linux-operation.md) (renamed to `linux-operation.md`), [configuration](../surfaces/configuration.md), [TV launcher](../surfaces/tv-launcher.md), [phone remote](../surfaces/phone-remote.md).

## Interfaces and constraints
- Settings action `{"setting": "browser_locale", "value": "ru"|"en"}`; snapshot adds `browser_locale`, `browser_locales_installed` and contributes to `restart_required`. Strict validation; unknown values fail before mutation.
- Managed `// BEGIN AD-LINUX-TV LOCALE` block in the dedicated `user.js` only; startup re-derives it from config.
- `/api/system/kde` refuses when KDE is unavailable; launcher hides the button.
- Scripts keep `--dry-run` as the non-mutating default.

## Acceptance criteria
- No `beelink`/`/home/adegtyarev` in code, scripts, guides or contracts outside `docs/verification/` and the dated target checklist.
- Python, Node, Ruff and shell checks pass in CI.
- On ad-server (Ubuntu Server, no KDE) a reboot with HDMI starts the kiosk, bridge reports online, Firefox UI is Russian and tabs are hidden.
- On the Beelink the update preserves config/PIN/proxy and the bridge reports online after the kiosk restart.

## Validation
`pytest -q`, `node --test tests/*.test.js`, `ruff check . && ruff format --check .`, `bash -n` on scripts; live checks on both targets.
