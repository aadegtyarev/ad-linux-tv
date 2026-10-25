# Feature contract: phone remote access and motion

- Status: Implemented on Beelink; real-phone navigation and DHCP failover acceptance pending
- Date: 2026-10-25
- Approval: User confirmed PIN-free operation on Beelink, a QR on the first phone for a second phone, and cursor and scroll improvements. On 2026-10-25 the user approved Tab, Shift+Tab and Enter controls below the touchpad, tap as cursor click, site checks, and a best-effort IP-change redirect.

## Goal and user-visible behavior

The Beelink phone remote can be configured to open without entering a PIN. The first phone can display a QR code that opens the same remote on a second phone. Pointer movement and two-finger scrolling respond smoothly and in order.
The main remote exposes Tab, Shift+Tab and Enter below the touchpad. A short touchpad tap clicks at the cursor; keyboard selection uses Enter. If Beelink advertises a new LAN address while the old connection still works, the phone moves to the new remote URL.

## Scenarios and edges

- Existing configurations still require a PIN. `auth.require_pin: false` explicitly enables PIN-free access; the Beelink configuration is switched to this mode.
- A private-LAN phone opening the remote receives a session and CSRF token without a PIN. A non-private source cannot obtain either. Origin, Host, CSRF and TV-session checks remain in force for commands.
- Switching back to PIN mode invalidates sessions issued without a PIN. The TV shows that PIN is not required when the option is disabled.
- The phone menu displays a QR for the remote's current reachable LAN URL, with the URL visible as a fallback. A stale or unavailable address produces a clear retry message.
- Pointer actions remain ordered; excess movement is coalesced under latency. Two-finger scrolling does not wait behind obsolete cursor movement and does not generate erratic bursts.
- Tab/Shift+Tab move browser focus; Enter activates the focused item. The touchpad tap always sends a pointer click, independent of earlier arrow or Tab input.
- The phone checks the advertised address at a bounded interval and redirects only to a validated private-network `http://<ip>:8765/remote` URL when it changes. It does not redirect from a stale asynchronous response or to arbitrary hosts.

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

## Acceptance criteria

- A fresh phone opens the remote from the Beelink QR without PIN; another phone can scan the QR shown in the first phone menu and open it too.
- `auth.require_pin: true` and legacy configs still require a valid PIN; changing modes does not retain a PIN-free session.
- Movement requests execute in order, and scrolling remains usable during and after cursor motion.
- Tab, Shift+Tab and Enter are reachable on the main phone page; tap clicks at the cursor even after keyboard navigation. On Kinopoisk, KION and YouTube verify the browser receives the intended keys and clicks, and document site-specific focus behavior.
- If the advertised address changes while the old server connection survives, the phone navigates to the new address. Invalid, unchanged or stale addresses do not redirect.
- Existing authenticated input, audio, timer and browser commands still work.

## Validation

- Run focused Python and Node tests, full project tests and lint, dry-run deployment, then deploy to Beelink.
- Verify live HTTP session flow and QR URL on Beelink. Real phone feel and scan remain a user acceptance check.
- Verify button behavior, redirect policy and timer cleanup in Node tests. Recheck live endpoints on Beelink; real phone navigation and DHCP failover remain user acceptance checks.
- All six launcher services were opened on Beelink for keyboard checks. Focus and arrow behavior vary by site; see the target checklist for observed results.
