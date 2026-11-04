# Bluetooth adapter selection

Status: source implementation, automated tests and focused independent review complete; installation and physical testing require separate approval. The contract remains open for those hardware gates.

## Goal and scenarios

The shared TV and authenticated phone Bluetooth settings list currently observed BlueZ adapters and let the user explicitly choose one. Persist a validated adapter address, never an unstable hci number or object path. Existing configurations without a preference retain the previous automatic selection, including the saved remote's adapter. An explicit missing choice remains selected and unavailable without falling back; it becomes usable again when the same unambiguous identity returns. Detect unplug/replacement and reject stale or duplicate identities. Show unavailable, off, powered and discovering truthfully.

An explicit action can request power on for the selected present adapter; success is based on subsequent observation, not dispatch. Never power off other adapters. While an operation, pairing or discovery is outstanding reject a selection/power change as busy; apply existing lease, epoch, deadline, cleanup, no-replay and private authorization rules. Preserve saved remote identity/bindings, existing BlueZ bonds and established connections; no migration, automatic unpair, disconnect or device trust. A remote saved for another adapter remains saved but cannot be represented as usable on the selected adapter. BlueZ and other applications retain their own independent controller policies.

## Affected surfaces

- [TV launcher](../surfaces/tv-launcher.md)
- [Phone remote](../surfaces/phone-remote.md) and [Android shell](../surfaces/android-remote.md) for its existing server-hosted UI only
- [Configuration](../surfaces/configuration.md)
- [Linux operation](../surfaces/linux-operation.md)
- Existing [Bluetooth management feature](bluetooth-remote-settings.md) remains incomplete; physical remote-button control is not implemented by this feature.

## Constraints and acceptance

Use existing private config.yaml targeted atomic writer and strict backward-compatible schema. Device inventory and operations remain behind existing local/phone authentication, CSRF, session and lease boundaries. Never persist pairing secrets, D-Bus paths or arbitrary commands; do not add global privileges, services, driver installation, network changes, session restarts or automatic fallback. Preserve operation identity and stale generation fences, reject ambiguous adapters, and handle denied or uncertain power writes without blind replay or claiming success.

Automated tests cover legacy compatibility, distinct/duplicate adapters, explicit selection and restart, absent/off/reappearing/replaced adapters, switching during activity, concurrent clients, stale events/IDs, power denial/uncertainty, no bond destruction or global power effects, authenticated API, and shared TV/phone UI. Document observable behavior and limitations. Run relevant Python/Node tests, lint, documentation and package checks. Hardware behavior, actual physical pairing and remote-button input remain unverified until separately approved device tests.
