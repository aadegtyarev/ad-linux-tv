# Bluetooth settings and browser Home

Status: source implementation, automated checks and independent review complete. Physical Firefox and remote-button verification remains pending; no device diagnostics, installation or publication is authorized.

## Goal and scenarios

Remove physical-remote selection and key-learning/mapping UI from the shared TV/phone Bluetooth panel. Keep adapter selection and explicit power, bounded discovery, pairing/challenges, connect/disconnect and confirmed forget. Preserve existing Bluetooth configuration and bindings; hiding controls must not erase, migrate or rewrite settings. Existing explicit forget retains its documented bond-removal and associated mapping behavior. No input devices or global key remapping are introduced.

Set Firefox's existing homepage preference to the fixed local media-center URL using the existing startup preparation for the dedicated TV profile. Firefox's own browser-home action/Alt+Home may then navigate to it from sites; do not intercept or guess the physical remote key, change ordinary editing Home, override other profiles or introduce new extension permissions. A Firefox restart is required for user.js, and physical key handling, compositor interception, browser focus, restricted pages and on-device behavior remain unverified. Browser homepage navigation may operate on the current tab and is not asserted to equal the extension's managed `home` command.

## Affected surfaces

[TV launcher](../surfaces/tv-launcher.md), [phone remote](../surfaces/phone-remote.md), [Android shell](../surfaces/android-remote.md), [configuration](../surfaces/configuration.md), [Linux operation](../surfaces/linux-operation.md), and the existing [Bluetooth feature](bluetooth-remote-settings.md). Preserve local/phone security, UI focus, privacy, existing pairing and all unrelated controls.

## Acceptance and validation

Test that neither TV nor phone exposes remote selection, learning, testing, mapping or reset, while Bluetooth management flows remain intact and existing saved settings are not rewritten. Test dedicated homepage preparation on clean, existing and malformed profile blocks, idempotence, unrelated prefs and normal Home key non-interference. Test managed-tab behavior as applicable without installing or changing the signed bridge. Run Python and Node suites, lint, documentation and shell/package checks; actual Firefox shortcut handling and real remote use need separate hardware approval and must not be claimed from mocks.
