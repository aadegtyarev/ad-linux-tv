# Controls for the current video

Status: requested by the owner after the 0.2.1 deployment. The previous placement and restrictions did not meet their expectations.

## Goal and behavior

Remove format and mirror controls from the general settings/menu. Provide a screen-settings button on the phone's playback panel, as explicitly clarified by the owner after testing VK Video. Its choices affect the specific current video only, never the entire application or a later video. A paused, identified video is a valid target; opening the control never starts playback. Do not store, arm or carry a choice to another video. Do not start playback, switch tabs or change pairing.

Try the operation on an accessible uniquely selected HTML video, including an accessible embedded frame; do not reject frames solely because they are frames. Keep the existing ownership, identity, source-change and at-most-once boundaries. Where a parent frame, browser or site prevents verifying the final presentation, report that limitation honestly rather than claiming a guaranteed screen result. No DRM bypass, frame extraction, arbitrary script/CSS or universal-site promise. Unsupported, absent or ambiguous video is reported clearly.

The separate requested feature to assign three physical-remote buttons (video menu, magnifier, fullscreen) remains pending; this correction must not silently remap any button.

## Affected surfaces

- [Phone remote](../surfaces/phone-remote.md)
- [TV launcher](../surfaces/tv-launcher.md)
- [Configuration](../surfaces/configuration.md)
- [Linux operation](../surfaces/linux-operation.md)
- [Bridge protocol](../../bridge-protocol.md)

## Validation

Cover menu placement on the visible playback panel, a paused identified video, safe selection and source/tab changes, accessible frame vs unavailable frame, honest frame feedback, no persistence or delayed application to another video, existing key controls and authentication. Run focused and full suites, independent review and real Firefox synthetic tests. Target deployment is authorized by the owner; actual site/physical-screen acceptance remains a separate user check.
