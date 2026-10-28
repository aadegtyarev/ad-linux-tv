# Feature contract: phone cursor acceleration

- Status: Installed on the reference TV; Python/Node checks passed and the user confirmed real-phone acceleration. TV pointer-slider arrow check remains, 2026-10-25.
- Approval: User approved speed-based acceleration and settings on TV and phone.

## Goal and scenarios
- Slow finger movement retains the current precise cursor motion; faster movement crosses more of the TV screen without lifting the finger. A paused finger or new gesture starts from low speed again, so it does not jump.
- TV System and phone Settings offer an «Ускорение курсора» 0–100 control. The value persists in the existing private configuration and is shared across phones. The default is moderate; zero restores the current constant 3× mapping.
- Two-finger scrolling, arrow navigation, taps and click ordering remain as they are. Cursor displacement remains bounded by the existing transport limits.

## Non-goals
- Changing physical mouse/libinput settings, cursor prediction, scroll acceleration or the transport.

## Affected surfaces
- [Configuration](../surfaces/configuration.md)
- [TV launcher](../surfaces/tv-launcher.md)
- [Phone remote](../surfaces/phone-remote.md)

## Interfaces and constraints
- Reuse `/api/settings` over the authenticated phone WebSocket and local TV route. Do not expose secrets or store pointer traces. Use the existing `SettingsManager` and `config.yaml`.
- Apply the speed curve on the phone before coalescing relative moves; do not change the `wlrctl` pointer protocol. Base mapping remains 3× and high-speed gain is bounded.

## Acceptance and validation
- Validate the setting and persistence, default and zero behavior, slow/fast gesture motion, pause and direction-change reset, TV/phone settings rendering, and no change to two-finger scroll/click/navigation. Run Python/Node tests and verify on a real phone with the TV cursor.
