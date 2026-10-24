# Beelink TV session: staged setup

Beelink is the target. Source lives at `/home/adegtyarev/Develop/Hobby/ad-linux-tv` and must not be used as an installation or removal directory. The installed application and private config belong to the dedicated `ad-tv` user under `/home/ad-tv`. Existing KDE belongs to `adegtyarev` and is started through its current SDDM configuration.

The source checkout, system integration, TV-user deployment, and boot activation are separate steps. None of these steps edits the KDE profile. A physical HDMI screen and a signed Firefox XPI are still required for full validation.

## Preview and stage

From the source checkout:

```sh
./ops/beelink/setup.sh --dry-run
./ops/beelink/deploy.sh --dry-run
```

After reviewing the previews, `sudo ./ops/beelink/setup.sh --install` creates `ad-tv`, installs Cage, copies the TV systemd/PAM helpers, enables a tty2 console, and backs up/replaces the `gui` helper. It does not activate TV at boot. `sudo ./ops/beelink/deploy.sh --install` stages source through a private temporary directory, runs the user-scoped installer for `ad-tv` with `--no-autostart`, and prompts for the remote PIN without echo. The source checkout is preserved. Do not run the deployment command from a noninteractive terminal: PIN entry needs a TTY.

The installed app uses `/home/ad-tv/.local/share/ad-linux-tv`; config is `/home/ad-tv/.config/ad-linux-tv/config.yaml`. Firefox Snap profile and signed XPI are under `/home/ad-tv/snap/firefox/common/`. The installer still needs target testing to confirm Snap access and extension persistence. Current public artifacts do not include the signed XPI, so the TV boot gate remains closed.

## Mode switching and recovery

After integration is staged, `gui status` reports the current mode. `gui tv` starts the TV session when a display is connected; `gui kde` starts the existing KDE autologin; `gui off` returns to the tty1 console. Switching away from an active graphical session requires confirmation. `gui on` remains an alias for KDE. On the TV launcher, open the Settings tile with arrows and OK on the phone remote or with a keyboard/mouse. Settings shows the phone QR/address and a confirmed "Выйти из ТВ-режима → KDE" action. In TV mode, Ctrl+Alt+F2 opens the tty2 recovery console, where `gui kde` or `gui off` can also be run. SSH remains available.

Cage runs Firefox fullscreen and stops when the browser exits. The script then stops the local server. The kiosk unit switches to tty2 on exit or failure, leaving a login console. With no monitor at boot, tty1 remains a login console. If a monitor is connected after boot, use `gui tv` to start TV mode manually.

Only after signed-XPI installation has been confirmed in Firefox and the HDMI session has been manually tested, run `sudo ./ops/beelink/setup.sh --activate`. This enables an attempt to start TV mode at the next boot whenever a monitor is connected. It does not reboot or switch the current session. The boot helper checks for the installed app, config, signed XPI, and a connected physical display before starting the kiosk.

## Pending physical checks

Confirm Firefox Snap can use the dedicated profile, the signed extension remains installed after restart/refresh, the phone reaches the chosen private LAN address, keyboard/phone navigation works, audio and service logins persist, and DRM playback works where supported. Test `gui tv`, Ctrl+Alt+F2, `gui kde`, `gui off`, and a reboot with and without HDMI. See [target checklist](target-checklist.md).
