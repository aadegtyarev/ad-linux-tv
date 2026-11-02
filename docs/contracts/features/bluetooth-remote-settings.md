# Bluetooth devices and remote key settings

Status: scope approved by the operator on 2026-11-02; runtime baseline qualified, implementation pending.

## Goal and visible behavior

Manage Bluetooth and a selected physical remote from the media center instead of coordinating pairing through chat. The TV and existing authenticated phone settings share device selection and status. Key bindings use a fixed media-center action catalogue, not arbitrary commands.

## Scenarios

- Start and stop a time-bounded discovery session; show a capped deduplicated list and honest adapter/off/unavailable/searching status. Discovery is not a permanent background scan.
- Select a device and explicitly request pairing or connection. Show any required PIN/passkey/confirmation in an operation-bound UI, without persisting or logging it. Distinguish requested, paired, connected, failed and uncertain states; stale operations cannot act on a replacement device.
- Disconnect a selected device or forget its bond with explicit confirmation. Do not trust or pair arbitrary discovered devices automatically. BlueZ retains bond keys; application configuration does not.
- Select the remote, choose an action and press a button in a bounded learning session; display the observed key identifier, test the assignment, unmap or reset. Learning can be canceled and expires. Capture is scoped to the selected physical remote, not the ordinary keyboard or all input devices.
- Bind only navigation, OK, Back, Home, play/pause, seek, output volume and mute. No arbitrary shell/argv/URL/scripts, poweroff, session restart, KDE switching, microphone recording or global keyboard history.
- Bindings survive application restart and device reconnect using validated device identity. Device replacement, loss and hotplug retire stale learning/action ownership. Repeat and duplicate events must not execute actions twice; long-press macros are not included.
- Reuse existing context-aware browser/managed-media actions and timer/asleep fences. The qualified deployed baseline has no owned native player; this feature does not introduce local playback or a native prerequisite. Native-owner/occupancy guarantees apply only if a separately approved integration baseline supplies that owner. Never automatically resume playback or promise universal third-party-site navigation.

## Affected surfaces

- ../surfaces/tv-launcher.md
- ../surfaces/phone-remote.md
- ../surfaces/configuration.md
- ../surfaces/linux-operation.md
- ../surfaces/android-remote.md only if its existing server-hosted settings interface changes; no new native Android UI is currently approved.

## Security and interfaces

Existing local-TV/private-source/Host/Origin rules and authenticated phone session plus CSRF/ordered socket rules remain authoritative for inventory and management. Device lists, pairing challenges and mapping state are not public discovery/status data. Management operations have bounded ownership, timeouts and cancellation; conflicting clients do not implicitly steal active pairing/learning. Device names are untrusted text, never markup or commands.

Bluetooth administration and selected-device input access require a narrowly delegated system boundary, not a root media-center process, unrestricted sudo, membership granting all keyboard capture, or an unauthenticated LAN helper. Root may provision only the reviewed fixed helper/policy and selected-device access needed for this feature. No unrestricted EVIOCGRAB/global remapping or recursive synthetic-event handling. Exact helper protocol and access mechanism must be reviewed before installation; stop for approval if scope cannot be met without broader authority.

Store validated mappings/settings by targeted atomic update in the existing private config.yaml. Preserve unrelated secrets, PIN/auth sessions, discovery identity, browser profiles, local media roots and concurrent settings updates. Absence of new fields remains backward compatible. Pairing secrets and raw input histories never enter YAML or logs.

UI instructions are concise polite Russian: «вы», «нажмите», «выберите». TV focus and ordinary keyboard operation remain available even before a remote is paired; phone disconnection must not strand a privileged operation or permanent discovery.

## Source and deployment constraints

Canonical checkout main 63c2b31 has pre-existing dirty center-availability/local-player changes. They are preserved separately and are not approved for publication or deployment merely by this feature. No reset/stash or silent inclusion. Parent observed installed version0.2.0 and actual runtime hashes; scout mechanically verified exact 49/49 name-and-byte equality to clean Git commit 63c2b31a48c447ae8e00b72fea0d5b7304796ad1, with no extra Git runtime files. Reproduced public build fingerprint: 2f9d15daf0bfc108. Evidence projection SHA256: 1432b61fd95afab5b79d268a49e0c1fd333055aa6007f8fb5921b68d992e9665. This clean commit is the target application base; historical native55/ac123 belongs to another installation and is excluded along with all dirty availability/Android work. Isolate feature ownership and record pins; qualify external ops/deployment separately. Fresh tests are required; historical native test receipts do not validate this base.

The operator approved implementation, validation on ad-linux-tv and repository delivery. Live deployment must use a fresh reviewed transaction with backups and current lifecycle/timer/native-player checks, preserving existing functions. Do not replay consumed historical installers. Announce any required TV/audio/service interruption first. No unrelated network/SSH/display/power/kernel/boot policy changes, personal-media scan, or driver replacement.

Current target facts are diagnostic context, not durable guarantees: ad-linux-tv.local, ad-tv Wayland/labwc/Firefox; BlueZ 5.85 and evtest installed; RTL8723BU btusb manual enable_autosuspend=0 trial works over Wi-Fi but permanent blacklist retained; HDA sound is currently a one-shot GRUB test. Permanent Bluetooth driver provisioning and permanent audio changes need explicit separately reviewed scope, not an implicit UI side effect.

## Acceptance criteria

1. TV and authenticated phone can run bounded discovery, select a device, complete supported pairing challenges, connect/disconnect and confirmed forget; absent/off adapter and failures are actionable and do not hang the settings UI.
2. Unauthorized/public/cross-origin/stale requests cannot expose inventory or invoke management/input actions; helper accepts only validated typed operations and bounded data.
3. Pairing, discovery and learning expire/cancel cleanly on timeout, client/session retirement, device replacement and shutdown without automatic replay or trust-all behavior.
4. Learning and runtime actions are limited to the selected remote; ordinary keyboard input and reserved kiosk/accessibility controls remain functional. No text/password/history capture. Explicit mappings do not also pass through as a duplicate action.
5. Fixed actions work through existing context-aware owners; browser/managed-media/timer/asleep and stale media-ID fences remain intact. Native-specific acceptance is not applicable to the qualified main49 baseline and must not be claimed. Unsupported actions are reported honestly.
6. Mapping load/save/reset is schema-validated, bounded and atomic, preserving unrelated configuration and concurrent edits; reconnect uses correct physical identity.
7. Unit/integration tests cover fake BlueZ agent/clock, operation ownership, authentication/CSRF/socket allowlists, redaction, device identity/hotplug, repeats/double delivery, settings persistence and shared UI focus/error states.
8. Independent review precedes controlled device validation. On the actual selected UR-02, verify pairing, button assignments and reconnect with Wi-Fi still available. Physical reboot/persistence validation only under its explicitly approved scope.
9. No claim of feature completion until tested source, review, target result and repository handoff are recorded. Keep this temporary contract while any required gate is blocked.

## Validation

Run project Python/Node tests, Ruff check/format, extension manifest JSON validation and shell syntax checks from AGENTS.md. Add targeted backend/UI/helper tests and dependency/package checks appropriate to the selected mechanism. Run documentation checks for changed durable docs. Record physical validation separately from simulated tests; no real personal media or raw keyboard logging in test fixtures.
