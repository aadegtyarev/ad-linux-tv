# Feature contract: phone remote access and motion

- Status: WebSocket installed; user confirmed smooth real-phone cursor and scrolling. Signed bridge 0.3.1 is active in Firefox; background playback and remaining phone acceptance checks pending.
- Date: 2026-10-25
- Approval: User confirmed PIN-free operation on the reference TV, a QR on the first phone for a second phone, and cursor and scroll improvements. On 2026-10-25 the user approved Tab, Shift+Tab and Enter controls below the touchpad, tap as cursor click, site checks, and a best-effort IP-change redirect. After a real-phone packet capture, the user approved moving all live phone control to one WebSocket rather than adding a pointer-only channel. The user then requested tap-as-Enter after keyboard navigation and tap-as-click after cursor navigation, without a separate center button. The user also requested stopping background service playback on return to tiles for every service, moving Back to the far left of the row beneath the touchpad, and using the product name rather than reference TV in the app UI. The user further requested that TV System be visible on an ordinary TV for pointer clicks but excluded from arrow selection.

## Goal and user-visible behavior

The reference TV phone remote can be configured to open without entering a PIN. The first phone can display a QR code that opens the same remote on a second phone. Pointer movement and two-finger scrolling respond smoothly and in order.
The main remote exposes Tab, Shift+Tab and Enter below the touchpad. A short touchpad tap clicks at the cursor; keyboard selection uses Enter. If reference TV advertises a new LAN address while the old connection still works, the phone moves to the new remote URL.

## Scenarios and edges

- Existing configurations still require a PIN. `auth.require_pin: false` explicitly enables PIN-free access; the reference TV configuration is switched to this mode.
- A private-LAN phone opening the remote receives a session and CSRF token without a PIN. A non-private source cannot obtain either. Origin, Host, CSRF and TV-session checks remain in force for commands.
- Switching back to PIN mode invalidates sessions issued without a PIN. The TV shows that PIN is not required when the option is disabled.
- The phone menu displays a QR for the remote's current reachable LAN URL, with the URL visible as a fallback. A stale or unavailable address produces a clear retry message.
- Pointer actions remain ordered; excess movement is coalesced under latency. Two-finger scrolling does not wait behind obsolete cursor movement and does not generate erratic bursts.
- Tab/Shift+Tab move browser focus; Enter activates the focused item. After arrow or Tab navigation, a touchpad tap activates the focused item with Enter. A deliberate cursor drag or scroll returns the pad to pointer-click mode. The visible center hint identifies the current mode without adding a button.
- The row below the touchpad reads Back, Shift+Tab, Tab, Select from left to right; Back is removed from the top row.
- User-facing launcher and phone copy calls the device a media center or `ad-linux-tv`; reference TV remains only a target hardware name in deployment documentation.
- TV System is always visible on the launcher and can be clicked with the pointer. Arrow navigation and bridge OK continue to select only service tiles, even when System previously received focus.
- The phone checks the advertised address at a bounded interval and redirects only to a validated private-network `http://<ip>:8765/remote` URL when it changes. It does not redirect from a stale asynchronous response or to arbitrary hosts.
- Returning to tiles closes every launcher-managed service tab so background playback stops. Opening another service closes other launcher-managed service tabs. Firefox tabs not owned by the launcher remain untouched.
- Once paired, the phone uses one authenticated WebSocket connection for service selection, browser commands, keys, pointer, audio, timer and status. HTTP remains for loading static assets, QR, and session/login bootstrap. The phone does not maintain separate live transports for different controls.
- The server applies WebSocket actions in arrival order. Pointer movement may be coalesced before sending; click, scroll and key actions retain their order relative to preceding movement. Bounded client and server queues prevent unbounded catch-up after a stall. Connection loss is visible and reconnects through the saved session; commands are not silently replayed when completion is uncertain.

## Non-goals

- Internet-facing access, TLS, mDNS repair, sharing a PIN, or changing Firefox/DRM behavior.
- Guaranteeing smoothness on a faulty network or scrolling on third-party sites that reject wheel events.
- Guaranteed spatial arrow navigation on third-party sites, or a redirect after the old IP has already become unreachable.

## Affected surfaces

- [Phone remote](../surfaces/phone-remote.md): pairing, QR sharing, pointer and scroll.
- [Configuration](../surfaces/configuration.md): optional `auth.require_pin`.
- [TV launcher](../surfaces/tv-launcher.md): pairing text when PIN is disabled.

## Interfaces and constraints

- Preserve the fixed port, single private config file, current PIN verifier and default PIN-required mode.
- QR contains only the current remote URL, never a session token or PIN.
- Keep client source checks and same-origin CSRF protection for all phone control actions.
- Preserve existing service and kiosk restart/recovery paths.
- Preserve the existing HTTP control routes for the TV launcher and Firefox bridge while the phone switches its live control to the single WebSocket channel.

## Acceptance criteria

- A fresh phone opens the remote from the reference TV QR without PIN; another phone can scan the QR shown in the first phone menu and open it too.
- `auth.require_pin: true` and legacy configs still require a valid PIN; changing modes does not retain a PIN-free session.
- Movement requests execute in order, and scrolling remains usable during and after cursor motion.
- Tab, Shift+Tab and Enter are reachable on the main phone page; after keyboard navigation a pad tap sends Enter, while a cursor drag followed by a tap clicks at the pointer. On Kinopoisk, KION and YouTube verify the browser receives the intended keys and clicks, and document site-specific focus behavior.
- At a narrow phone viewport, Back is leftmost in the lower action row and all four controls remain visible without overflow.
- On an ordinary TV without touchscreen, System is visible and clickable; arrow keys stay within the service grid and cannot select System.
- If the advertised address changes while the old server connection survives, the phone navigates to the new address. Invalid, unchanged or stale addresses do not redirect.
- Existing authenticated input, audio, timer and browser commands still work.
- For each configured service, switching to another service or Home leaves no launcher-managed background tab playing. Unmanaged Firefox tabs remain open.
- The paired phone can perform every live action and receive status over one WebSocket; reconnect preserves the session and does not duplicate a click or key after an uncertain disconnect. A delayed network packet does not cause seconds of stale cursor movement after finger release.

## Validation

- Run focused Python and Node tests, full project tests and lint, dry-run deployment, then deploy to reference TV.
- Verify live HTTP session flow and QR URL on the reference TV. Real phone feel and scan remain a user acceptance check.
- Verify button behavior, redirect policy and timer cleanup in Node tests. Recheck live endpoints on the reference TV; real phone navigation and DHCP failover remain user acceptance checks.
- All six launcher services were opened on the reference TV for keyboard checks. Focus and arrow behavior vary by site; see the target checklist for observed results.
- Reproduce a stalled connection and recovery in tests. Verify authentication, Origin, CSRF, frame bounds, command order, single-channel behavior and reconnect against the live reference TV listener. Compare phone packet traces before and after migration.
