# Surface contract: TV launcher

## Boundary and consumers
The browser-rendered home page and Firefox bridge provide TV service selection and browser-tab control. The Python HTTP server owns service catalogue, command queue, and status; launcher clients are unauthenticated on the TV-side local page.

## Inputs, outputs, and flows
- `/` renders configured services, an adaptive grid, page indicator, phone QR/address and bridge/command status. A small System button sits in the upper right outside the service grid and offers a confirmed switch to KDE in the dedicated kiosk session. The service set may include a Browser tile opening Yandex search as an ordinary managed Firefox tab.
- `GET /api/services` supplies services, page size and advertised remote address; `/api/status` supplies bridge online, pending count and latest command failure. Polling refreshes every five seconds.
- Arrow keys move focus in the grid (wraps horizontally and vertically); from the top row or last service, an arrow reaches System. Next/previous controls paginate. OK from bridge selects the focused service or opens System. In System, arrows move between controls and OK activates the focused control; leaving for KDE requires a second confirmation. Clicking a service tile queues `open`.
- Firefox bridge polls localhost port 8765 and executes open/home/back/refresh plus launcher navigation; service selection opens a managed service tab. Home returns to launcher and closes the managed service tab.
- A compact Waybar overlay remains visible on third-party pages. Its «Плитки» touch target sends Home through the loopback command route, and «Клав.» toggles Squeekboard through its session D-Bus API. It requires no extension permission change.

## Guarantees, failures, and security
- Pagination and focus are adaptive to configured page size and responsive CSS grid. The launcher refreshes the advertised LAN address and QR when the route address changes. Opening a service shows a spinner while the bridge accepts the command, then a retry hint if the launcher remains visible; a third-party page may instead show Firefox's own loading or error page. Status displays bridge offline, pending commands, and last failed/uncertain outcome alongside pending state.
- Queue is bounded (128); browser lease/poll and acknowledgements expose failures. Extension command execution is at-most-once after persisted execution claim; interruption in claim/effect/ack window can lose an action and report uncertain. Completed effect is not repeated on lost acknowledgement. Deduplication ledger is bounded (256); tab ownership survives event-page unload, not browser restart or extension reload/update/disable.
- Launcher is served over local HTTP; remote control constraints are in [phone remote](phone-remote.md). Firefox bridge uses the localhost host permission and bridge header, not a general remote browser API. Authenticated phone text entry uses the compositor's virtual keyboard protocol; it does not change extension permissions.
- `POST /api/system/kde` is available only to the kiosk launcher over loopback with exact `127.0.0.1:<port>` Host and matching Origin. It starts a narrowly authorized systemd switch unit. LAN clients cannot call it directly.

## Non-goals and verification
No guarantee of arrows/OK on third-party pages, service playback/DRM, or exactly-once browser actions. Automated source/tests cover layout, focus selection, commands and status. On Beelink, HDMI rendering, Browser/YouTube opening, bridge persistence across Firefox restarts, and the System-to-KDE switch have been checked. Touch keyboard auto-show, DHCP failover, reboot and playback/DRM remain target checks.

Related: [media-center MVP](../features/media-center-mvp.md), [configuration](configuration.md), [phone remote](phone-remote.md), [Kubuntu operation](kubuntu-operation.md).
