# Dedicated Beelink TV session

This is the **tested appliance recipe** for a Beelink with Kubuntu. It creates a separate `ad-tv` account running labwc, Firefox Snap, Squeekboard and the TV overlays. The normal KDE account remains available. The checked-in helper scripts contain target-specific user paths and system integration; review them before applying to another computer.

## Install or update

From a checkout on the Beelink:

```sh
./ops/beelink/setup.sh --dry-run
./ops/beelink/deploy.sh --dry-run
sudo ./ops/beelink/setup.sh --install
sudo ./ops/beelink/deploy.sh --install
```

`setup.sh` stages the TV account, labwc configuration, keyboard and systemd helpers. `deploy.sh` copies source into the TV user's app and runs the installer without Plasma autostart. Installed app: `/home/ad-tv/.local/share/ad-linux-tv`; config: `/home/ad-tv/.config/ad-linux-tv/config.yaml`; Firefox profile: `/home/ad-tv/snap/firefox/common/ad-linux-tv-profile`. Updates preserve config and profile. Install or confirm the AMO-signed bridge interactively in the TV Firefox profile; `about:addons` should show it enabled. The deployment helper does not silently approve Firefox extensions.

TV mode starts at boot on this tested machine if HDMI is present. To enable that behavior on a prepared machine, run `sudo ./ops/beelink/setup.sh --activate`; it affects the next boot and does not switch the current desktop. With no monitor, the helper leaves a console. Use `gui tv` after attaching a display.

For an already prepared appliance, review the targeted update instead of blindly reinstalling all integration packages. Back up its private app/config, own unit and changed helpers; stop only `ad-linux-tv-kiosk.service`, install the verified app/helpers/unit, reload that unit definition and restart it. Preserve the signed XPI and personal browser state. Keep a rollback copy and verify own service identity/health before declaring deployment complete. Do not run a live seek or timer-expiry test merely to prove an update.

The current kiosk launcher uses `start-compositor.sh` to render a private runtime labwc config from the `/etc` template and YAML magnifier scale before starting labwc. The boot-exported scale distinguishes pending settings from applied settings. The saved scale slider never restarts viewing automatically. `run.sh` prepares only marked view preferences in the dedicated profile, including inherited common settings; see [configuration](configuration.md).

## Daily operation

The TV shows service tiles, a QR for the phone and a small **System** button. `ad-tv` uses a large white pointer and a dedicated Firefox profile. The on-screen keyboard has a one-tap EN/RU switch. A movable touch overlay offers Home, Back/Forward, keyboard, output volume and timer. The timer uses one semi-transparent upper-left panel above fullscreen video, away from the upper-right touch toolbar. Clock/time stay compact; hover/click enlarges it and reveals Change/Cancel. The same panel expands for the two-minute warning and presets without taking keyboard focus. The phone remote uses the same server with the restored compact layout, large pad and inline media panel. Menu contains settings/QR, not service/URL/browser-command banks. The media panel prefers MPRIS and can use a fresh capability-gated HTML fallback from installed signed bridge0.4.1; service playback/seek acceptance remains separate. The [Android shell](android.md) adds discovery and separate center/origin profiles; the last delivered native0.2.4 has compact chrome, a dark picker and TV icon, with optional shade controls explicitly enabled from its gear (default off). Exact installed phone version is not verified; S02 native0.2.5/code6 remains source-only.

The tested Beelink uses a local Xray proxy at `127.0.0.1:1081` for external Firefox sites and excludes private LAN addresses. TV/phone settings can change only that profile's proxy; the KDE user's Firefox remains separate. YouTube on this machine depends on Xray. The current saved config is PIN-free; a new PIN can be set on TV or phone. The phone QR follows the active network address.

## Display sleep and host shutdown

The phone ⏻ beside Timer requests display sleep/wake; hold1.2s opens a separate whole-host confirmation. Sleep uses managed pause and verified silence; wake does not resume playback or guarantee the physical TV woke. Use the TV remote if the picture stays dark. Optional CEC uses existing hardware/tools only, with no provisioning.

The power delivery installed a fixed root-owned poweroff unit plus one exact sudoers permission. It did not start or enable that unit for verification. Confirming shutdown later stops every host task, and the phone cannot restart the stopped computer: use the physical power button. The [delivery record](verification/remote-power-2026-10-26.md) names the wheel digest and root-private rollback directory. Restoration requires a separately approved owned-service maintenance window; do not run old deployment helpers or a shutdown test just to verify documentation.

## Switch and recover

`gui status` shows TV/KDE/console. `gui tv` starts TV mode; `gui kde` switches to the existing KDE desktop; `gui off` returns to console. SSH and tty2 remain recovery paths. For startup faults inspect:

```sh
sudo systemctl status ad-linux-tv-kiosk.service
sudo journalctl -u ad-linux-tv-kiosk.service -b
```

The TV service restarts after an unexpected server or browser exit, with a bounded retry limit. A browser bridge update should be followed by `sudo systemctl restart ad-linux-tv-kiosk.service` so old tabs cannot keep audio playing. See [troubleshooting](troubleshooting.md) for sound and connection checks.

TV boot with HDMI, audio test chime, signed Firefox bridge persistence, phone pointer, scrolling, keyboard EN/RU, QR address failover and KDE switching have been observed on this target. The later signed0.4.1 zoom repair passed an actual served Browser-tile click and operator confirmation; see the [verification record](verification/tile-open-zoom-2026-10-26.md). Its fresh media/view capabilities are not physical media acceptance. The target had an explicitly saved common desktop125 for all six sites before the overnight freeze, with no individual Kinopoisk override. Earlier observations and this bounded repair do not qualify Android lifecycle, compact timer layout, HTML playback/seek, mobile-site behavior or DRM. New automatic source/fake-platform checks and builds remain distinct from physical phone, GTK/fullscreen, multicast and site acceptance. Playback and site-specific behavior still need checks across all services; see the [target checklist](target-checklist.md).
