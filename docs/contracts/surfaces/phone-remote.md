# Surface contract: phone remote

## Boundary and consumers
The `/remote` web UI on a phone submits browser commands to the TV's Python HTTP service. The service queues commands for the Firefox bridge. This is trusted-LAN HTTP, not a secure Internet-facing remote.

## Inputs, outputs, and flow
- User submits PIN to `POST /api/login`; success sets an HttpOnly, SameSite=Strict, 12-hour session cookie and returns a CSRF token. Service selection comes from `/api/services`; commands post JSON to `/api/command` with CSRF header.
- Commands: `open` with configured service ID, `home`, `back`, `refresh`, `up`, `down`, `left`, `right`, `ok`. Accepted commands return 202; malformed/unknown commands 400, unauthenticated or invalid-origin requests 403, rate limited login 429, full queue 503, oversized payload 413.
- `/api/status` reports bridge online, pending count and latest failed/uncertain result. UI polls each second, presents accepted/failure/connection-loss messages and forces relogin after 401/403.

## Security and privacy
- Private/loopback source checks apply to `POST /api/login` and command POSTs, not to GET requests. Publicly reachable GET surfaces include `/`, `/remote`, `/api/services`, `/api/status`, `/health`, `/api/qr`, and static UI assets: any network source able to reach the bound listener can request them. These return UI, the configured service catalogue/advertised address, QR data, or operational status; they do not return the PIN or session/CSRF secrets.
- Phone login and command POSTs require a private/loopback client source. Phone POSTs also require HTTP Origin to equal Host, a syntactically valid Host, and (for commands) a valid session and CSRF token. This does not verify that the Host address belongs to the server. For loopback local UI POSTs, Host must parse as localhost or a loopback IP. Firefox bridge poll/ack additionally require loopback source, exact `127.0.0.1:<listener-port>` Host, and the bridge header/value.
- No TLS: use only a trusted private LAN; do not port-forward. Session cookie deliberately lacks Secure for LAN HTTP. PIN is not returned; config contains a salted PBKDF2 verifier. Client status uses fixed outcome/reason codes and excludes URLs, PINs, and exception text. HTTP access logs are suppressed.
- Local TV launcher command submission is intentionally separate from phone authentication.

## Failure, limits, and verification
The in-memory queue is FIFO and bounded to 128; status reports extension offline after 30 seconds, pending commands, and latest failure for up to 300 seconds. A later success does not clear the last failure; a newer failure replaces it. Remote UI displays pending and failure concurrently. Extension execution is at-most-once after claim and may be uncertain/lost on interruption; see [TV launcher](tv-launcher.md).

Automated tests verify authentication, CSRF/origin/security, queue and response semantics. Phone/LAN behavior on target Kubuntu remains unverified.

## Non-goals and related contracts
Arrows and OK are guaranteed only on the launcher grid; they are not service-page controls. No TLS, Internet exposure, exact-once command guarantee, or service/DRM guarantee. Related: [MVP feature](../features/media-center-mvp.md), [configuration](configuration.md), [Kubuntu operation](kubuntu-operation.md).
