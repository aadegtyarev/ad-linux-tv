# Beelink TV session

Beelink is the target. Source lives at `/home/adegtyarev/Develop/Hobby/ad-linux-tv` and is never an installation or removal directory. The installed application and private config belong to `ad-tv` under `/home/ad-tv`; the existing KDE session belongs to `adegtyarev`.

## Install and update

From the source checkout, preview first:

```sh
./ops/beelink/setup.sh --dry-run
./ops/beelink/deploy.sh --dry-run
```

`sudo ./ops/beelink/setup.sh --install` creates `ad-tv`, installs labwc, Squeekboard, wtype and GTK layer-shell bindings, copies the systemd/PAM helpers and enables the tty2 console. It preserves the KDE user's profile and SDDM configuration. When local Xray listens on `127.0.0.1:1081`, it configures only the TV Firefox profile to use that proxy for external websites while excluding localhost and private LAN addresses. `sudo ./ops/beelink/configure-firefox.sh --configure` can reapply that profile setting later. English/Russian on-screen keyboard labels are installed from pinned, checksum-verified Squeekboard source; if download fails, the packaged keyboard remains usable. TV session startup selects the saved TV-user audio output if connected, otherwise prefers HDMI; analog remains available. The phone remote and the tile screen's System menu can choose an output, set its volume (0–100%) and mute. Pair a Bluetooth speaker in the operating system first; it appears in the list when PipeWire reports it.

`sudo ./ops/beelink/deploy.sh --install` copies source through a private temporary directory and runs the user-scoped installer for `ad-tv` with `--no-autostart`. The source checkout is preserved. The first installation needs an interactive TTY to enter the phone PIN; updates preserve the existing verifier. Installed app: `/home/ad-tv/.local/share/ad-linux-tv`; config: `/home/ad-tv/.config/ad-linux-tv/config.yaml` (existing configs are preserved; KION was added explicitly on this Beelink); Firefox Snap profile and signed XPI: `/home/ad-tv/snap/firefox/common/`.

The signed XPI must be installed with Firefox's confirmation prompt. The application installer cannot register an unsigned add-on. After installation, `about:addons` should show `ad-linux-tv bridge` active and `/health` should report `extension_online: true` after Firefox starts.

## Daily use

With HDMI attached, TV mode uses labwc and Firefox in a maximized window. The dedicated Firefox profile hides the browser toolbar until the address field receives focus, while keeping the touch keyboard usable. The home screen shows service tiles with colors set by optional `services[].color` in the private config, a Browser tile that opens Yandex search, a KION tile added to the private Beelink config, a small System button in the upper right, and the phone QR/address. The local TV screen shows the pairing PIN below the QR; LAN clients cannot request it. Three compact touch controls in the upper right offer Home, keyboard and temporary output and Firefox-volume sliders; they disappear while a window is fullscreen and when no touchscreen is connected. The on-screen keyboard has a large `EN → RU` / `RU → EN` key for one-tap language cycling. The advertised address and QR refresh when the OS changes the preferred LAN address; the listener remains on `0.0.0.0:8765`.

Scan the QR on a phone in the same trusted LAN and enter the TV PIN. The phone remote keeps `К плиткам`, Back and Refresh at the top, plus service selection and text input using the phone's native keyboard. Use `Следующее поле` to focus a website field, then `Ввести` and `Enter`; the `Открыть адрес сайта` form first opens the managed Browser tab and enters the address. Text is sent only to the focused Firefox window; it is not stored or returned by the server. On a touch display, Squeekboard provides local on-screen typing. Firefox's dedicated non-private profile keeps website cookies across TV session restarts, subject to each website's expiry rules.

System opens the confirmed KDE switch. `gui status` reports TV/KDE/console; `gui tv` starts TV mode; `gui kde` starts the existing KDE autologin after confirmation if TV is active; `gui off` returns to console after confirmation. `gui on` remains a KDE alias. The text console on tty2 and SSH remain recovery routes. On a television with no keyboard or touch, use the phone remote during normal operation; if the local server itself is unavailable, reconnect by SSH and inspect `systemctl status ad-linux-tv-kiosk.service`, then use `gui tv` after fixing the reported error.

If Firefox or the server exits unexpectedly, the whole TV session restarts automatically after five seconds. systemd stops repeated failures after six attempts in two minutes; SSH and tty2 remain available. The on-screen opening indicator and phone remote show connection errors or a retry action, while a failed third-party site may still show Firefox's own error page. YouTube requires the local Xray proxy on this target; check `systemctl status xray` and `127.0.0.1:1081` if it times out.

## Start at boot

`sudo ./ops/beelink/setup.sh --activate` enables an attempt to start TV mode on the next boot if a monitor is connected. On this Beelink the unit is enabled and a real HDMI reboot started TV mode successfully. With no display, the boot helper leaves a console. If a monitor is connected later, use `gui tv`. Activation does not reboot or switch the current session.

Ethernet-to-Wi-Fi address failover, the keyboard controls supplied by Yandex and YouTube, opening Squeekboard with the overlay touch button, automatic overlay hiding on a fullscreen Firefox window, PIN display below QR, an audible HDMI test sound, and TV boot after a real HDMI reboot were observed on this target. The remaining checks include physical Home/keyboard dismissal, no-HDMI fallback, real-phone pairing and reconnection, a fresh DHCP lease, password-field typing, website playback, service login persistence, and DRM playback without bypasses. See [target checklist](target-checklist.md).
