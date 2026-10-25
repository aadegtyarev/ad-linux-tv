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

## Daily operation

The TV shows service tiles, a QR for the phone and a small **System** button. `ad-tv` uses a large white pointer and a dedicated Firefox profile. The on-screen keyboard has a one-tap EN/RU switch. A movable touch overlay offers Home, Back/Forward, keyboard, output volume and timer. The timer badge can stay above fullscreen video. The phone remote uses the same server, with cursor, text, audio and timer controls; its media panel appears when Firefox publishes a controllable media session.

The tested Beelink uses a local Xray proxy at `127.0.0.1:1081` for external Firefox sites and excludes private LAN addresses. TV/phone settings can change only that profile's proxy; the KDE user's Firefox remains separate. YouTube on this machine depends on Xray. The current saved config is PIN-free; a new PIN can be set on TV or phone. The phone QR follows the active network address.

## Switch and recover

`gui status` shows TV/KDE/console. `gui tv` starts TV mode; `gui kde` switches to the existing KDE desktop; `gui off` returns to console. SSH and tty2 remain recovery paths. For startup faults inspect:

```sh
sudo systemctl status ad-linux-tv-kiosk.service
sudo journalctl -u ad-linux-tv-kiosk.service -b
```

The TV service restarts after an unexpected server or browser exit, with a bounded retry limit. A browser bridge update should be followed by `sudo systemctl restart ad-linux-tv-kiosk.service` so old tabs cannot keep audio playing. See [troubleshooting](troubleshooting.md) for sound and connection checks.

TV boot with HDMI, audio test chime, signed Firefox bridge persistence, phone pointer, scrolling, keyboard EN/RU, QR address failover and KDE switching have been observed on this target. Playback and site-specific behavior still need checks across all services; see the [target checklist](target-checklist.md).
