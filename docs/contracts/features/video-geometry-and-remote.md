# Temporary video geometry and physical remote menu

Status: approved by owner; implementation in progress. The phone-to-bridge prototype is wired and tested with synthetic video, but has not been released or physically verified. Physical-button delivery remains gated on a demonstrably safe mechanism and must be reported unavailable otherwise.

## Goal and behavior

From the authenticated phone remote, explicitly select **Исходный**, **4:3** or **16:9** for the current eligible HTML5 video and independently toggle horizontal mirror. The 4:3 and 16:9 choices deliberately stretch/squeeze the image to that display aspect; they do not promise source-preserving crop. Исходный restores the site's original appearance, and the mirror affects the video image only, not text, controls or subtitles. State is temporary for the current video and must not silently carry to a new source, unrelated tab or next playback. Initial behavior is unchanged. Existing Home, playback, fullscreen, profile, system TV and output settings are unchanged.

Support fullscreen when the browser, frame and actual player allow a safe operation; otherwise give a short understandable failure notification. If no uniquely suitable owned video, no accessible frame, an incompatible bridge or an unconfirmed/uncertain dispatch, report the relevant bounded outcome without claiming the effect succeeded. No arbitrary selectors/scripts/URLs/CSS from clients, no video frame capture, media extraction or DRM circumvention. Site/browser/DRM behavior and actual TV/phone acceptance remain unproven until explicitly tested.

## Physical video-menu key and user assignment

A user can explicitly choose a safe button for opening the video menu only if a narrowly scoped, independently reviewed mechanism proves the selected physical remote identity, protects unrelated input and suppresses the old action without duplicate execution. Only the explicitly assigned button may replace its former behavior. Navigation, OK, text, modifiers, power, volume and other reserved, hazardous or ambiguous buttons are not assigned. No automatic remapping, pairing changes or silent promotion of another device.

Until such a mechanism is demonstrated and approved for the operating boundary, show the feature as unavailable and do not persist an assignment or claim it works. Investigate alternatives without unrestricted keyboard access, global input capture, unauthenticated privileged helpers, unrestricted EVIOCGRAB, logging input history, or recursive synthetic events. Learning is explicit, bounded, cancellable, authenticated, scoped to the verified device and records at most the permitted chosen identifier. Device disconnect/hotplug, identity ambiguity and session end fail closed. Privileged policy/helper or suppression design is a separate review/deployment gate; no installation or system change is implied by this contract.

## Affected surfaces

- [TV launcher](../surfaces/tv-launcher.md)
- [Phone remote](../surfaces/phone-remote.md)
- [Configuration](../surfaces/configuration.md)
- [Linux operation](../surfaces/linux-operation.md)
- Existing [bridge protocol](../../bridge-protocol.md)

## Interfaces and constraints

Retain private-source/Origin/session/CSRF and ordered transport checks, loopback bridge boundary, fixed allowlisted command and bounded queue/at-most-once semantics. Gate new behavior on an explicit fresh bridge capability; legacy extensions fail safely. Scope to the current owned HTTP(S) service tab/frame and current video identity, rechecking after asynchronous operations; do not mutate unmanaged tabs or unrelated video. Protect current site styling and restore only changes owned by this feature without overwriting newer site changes. Treat a changed `currentSrc`, including reuse of the same video element, and tab/clip switches as a new target; do not leak geometry into it. Prevent stale operations or delayed errors from altering a later target. A request or successful dispatch is not success: report applied only after the current target's actual presentation has been verified; if verification is impossible or uncertain, report that honestly. Keep controls/subtitles unmirrored, preserve playback and do not trigger playback, navigation or fullscreen changes. Do not add application settings writes merely to operate temporary geometry.

## Open blockers

The initial inline-style prototype was discarded. The current prototype uses a removable, narrowly scoped stylesheet and never writes the player's inline styles. It verifies computed geometry, not decoded pixels or physical display output. Direct fullscreen of a video element, inaccessible roots, protected media, visible native controls and ambiguous or clipped targets are reported unavailable. The owner subsequently requested accessible embedded frames; bridge 0.4.5 attempts them and asks the user to check the picture because outer-frame geometry is not verified. Failed bridge receipts also trigger a fixed five-second notice in the existing timer overlay; this is unit-tested but not physically verified on the TV. Revalidation after site changes, cancellation, error feedback and the fixed bridge boundary still require end-to-end review. A mechanism for selected-device-only key suppression without duplicate/native effects remains unproven; physical assignment must remain unavailable.

## Isolated CSS-layer investigation

A local disposable headless Firefox 158 test used synthetic two-colour non-DRM video; no TV/device or user video was touched. An author-origin temporary style layer produced a 16:9 mirrored video in a screenshot without modifying the video's inline style. A newer player inline `!important` transform overrode that layer and remained after it was removed, including when the newer inline value matched the layer. An open shadow root and same-origin iframe needed their own local style layer. A cross-origin frame could not be inspected by its parent; a WebDriver frame-context experiment worked but does not prove Firefox extension injection permissions. Reusing the same element with a changed source triggered removal in the synthetic test.

In a disposable Firefox extension and synthetic non-DRM video test, the fixed bridge script preserved its per-frame controller across injections, applied 16:9 plus horizontal mirror, restored the original, and applied 4:3 plus mirror inside a fullscreen player container. A second disposable Firefox test exercised the actual owned-tab command controller through open, media snapshot, fullscreen apply and reset, both in the main document and in an open shadow root. Fullscreen of the video element itself produced computed `transform: none` in a separate experiment and remains unsupported. The later current-video correction attempts accessible iframe and shadow-root videos and gives feedback that asks the user to verify the picture. These tests do not establish compatibility with real sites, protected media or the TV.

## Acceptance and validation

Unit/integration tests must cover default and all fixed modes, restoration, horizontal mirror independently of aspect, source replacement, the same HTML video element changing `currentSrc`, tab/clip switching, site-style conflicts and non-destructive restoration, no/ambiguous media, missing/restricted frames, fullscreen and resize boundaries, actual-application confirmation, unsupported/old bridge, stale/duplicate/uncertain commands, authorization and untrusted input, error feedback, text-entry isolation and unchanged Home/controls. Physical assignment remains unavailable unless its device identity, permissions, cancellation, repeat, OS-action suppression, unplug/reconnect and independent review gates are passed. Run project Python/Node suites, Ruff, manifest/shell and documentation checks; independent review. The owner authorized repository delivery and installation; real-site and physical-TV acceptance are still separate checks. After the current deployment, the requested follow-up covers three user-assignable buttons: video menu, magnifier and fullscreen.
