# Timer window: native icon-loader crash repair

Status: bounded repair deployed2026-10-28; [actual native-output verification](../../verification/timer-window-icon-2026-10-28.md) confirms compact countdown, automatic expanded warning and normal same-generation expiry/asleep/noerror. Source scope was recorded before implementation under the original repair/self-deploy/self-inspection requests. The operator subsequently explicitly authorized «Буди, ставь» and benign live checks; one post-fix wake(falseCEC)/15-minute cycle completed. No further wake/reset is implied. Retain this contract for the listed fullscreen/action/hardware acceptance limits.

## Goal and evidence

Restore the existing focusless native countdown panel without changing deadline, sleep, media or control semantics. Source/installed inspection alone initially found no deterministic failure. Parent then set the supported15-minute preset under explicit authorization (10 was rejected before mutation). HTTP confirmed countdown; a private narrow real-TV crop during the active countdown showed no panel at its expected upper-left location. No private screenshot or raw console is shipped or sent.

Filtered evidence from the dedicated own-kiosk VT identifies repeated `gtkiconhelper.c:495` assertion failures with `gdk-pixbuf-error-quark`, failed image loading, `image-missing`, `glycin`, `bwrap` and the timer script; no touch-overlay attribution. This is consistent with the sole themed `Gtk.Image.new_from_icon_name("alarm-symbolic", ...)` in the timer panel aborting at first render. Current installed scripts match source. Keep the image-loader/sandbox security policy unchanged; avoid that theme/pixbuf dependency inside this panel instead.

The authorized timer expired normally and the server reports asleep/no error. Do not wake, reset/cancel a timer, restart the whole kiosk or run another physical timer to manufacture acceptance without fresh explicit authorization.

## Allowed implementation and surfaces

- Replace only the timer header's themed alarm image with a compact readable text/vector representation that needs no image/theme/pixbuf loader and no new dependency. Preserve the count label, compact proportions, accessibility and upper-left placement.
- Add focused source/mock regression checks that execute actual constructor/render methods without real GTK/Wayland/network/actuators. No broad renderer/model refactor or new icon framework.
- Affected surfaces: [TV launcher](../surfaces/tv-launcher.md) and [Kubuntu operation](../surfaces/kubuntu-operation.md). Shared [phone](../surfaces/phone-remote.md) and [configuration](../surfaces/configuration.md) boundaries remain unchanged.

Do not change timer_notice, timer requests/DTO/auth, server/sleep_timer deadlines/generations, presets, warning timing/dismissal, Change/Cancel actions, focus policy, fullscreen behavior, global scale, media pause/silence/wake/CEC or other overlays. No packages, new services/privileges, system icon/theme caches, browser/native/signing changes, GTK security flags, glycin/bwrap bypass or unrelated files.

## Validation and parent deployment

One isolated source writer, then a fresh independent review; no overlapping agents. Require the approved two-minute warning, generation-scoped dismissal/rearm, presets/actions and in-place rendering to remain intact. Test the actual source methods and prove that header construction/rendering never requests themed/pixbuf images; distinguish mock/source evidence from native rendering.

Build no new app/APK: this is one external root-owned libexec script, outside package build8a. Parent alone may atomically replace only `/usr/local/libexec/ad-linux-tv/timer-overlay.py` after verifying current known5264156c235597c2aafc62c3ff4c072e0763b0a123ae1d5a28572ad93ddeb2e0 bytes/type/root ownership/nonwrite ancestry and the copied reviewed replacement, preserving0755/root:root and keeping a bounded private rollback copy. Do not run setup or alter unit/session/wrapper/module files. Do not replay successful app transaction markers.

If needed to load reviewed bytes, parent may restart only the freshly identified own timer-overlay child through its existing supervisor, with current UID/script/executable/own-main ancestry and a PID-reuse-safe identity fence. Never signal a historical PID or another component. Confirm unchanged server/timer state; no whole-kiosk restart, screen-on/wake command or timer mutation. A failed/ambiguous writer means stop/report partial state, no blind retry or rollback.

Positive real-TV rendering remains a separate final checkpoint requiring an awake active countdown and explicit authorization if a new wake/timer action is necessary. Do not call the visible symptom fixed merely from mocks or process liveness.
