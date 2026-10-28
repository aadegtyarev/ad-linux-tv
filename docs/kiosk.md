# Dedicated TV computer (kiosk)

This setup turns a computer into a TV appliance. A separate `ad-tv` account runs labwc, Firefox Snap, an on-screen keyboard and the TV overlays. An existing desktop (for example KDE) can stay installed but is not required. Tested hardware is on [Tested platforms](platforms.md).

## Install

From a source checkout, as the administrator account:

```sh
sudo ./ops/kiosk/setup.sh --install
```

This creates the `ad-tv` user and installs labwc, squeekboard, PipeWire, fonts, `python3-venv`, `curl` and Firefox Snap if missing. It also installs the systemd units, PAM and sudoers files, the `gui` helper into the administrator's `~/.local/bin`, and configures the TV Firefox profile. Set `AD_LINUX_TV_ADMIN` to choose another administrator.

Put the AMO-signed bridge at `/home/ad-tv/snap/firefox/common/ad-linux-tv-signed.xpi`, or set `AD_LINUX_TV_XPI_URL` and `AD_LINUX_TV_XPI_SHA256`. Then:

```sh
sudo ./ops/kiosk/deploy.sh --install
sudo ./ops/kiosk/setup.sh --activate
```

`deploy.sh` installs the app for `ad-tv` and re-runs `ops/kiosk/configure-firefox.sh --configure`. `--activate` starts the TV at boot when a display is connected (from the next boot).

Every script defaults to `--dry-run`, so run it without arguments first to see what it will do.

## Firefox profile

`configure-firefox.sh --configure` changes only the dedicated TV profile:

- hides tabs and toolbars;
- installs the signed bridge so Firefox enables it without an on-screen prompt (signatures are still checked);
- downloads the Firefox language pack matching the installed version and verifies its checksum.

The proxy is not set here; use the `proxy` [setting](configuration.md).

## Update

Run `sudo ./ops/kiosk/deploy.sh --install` from the new checkout. Config, Firefox profile and the signed XPI are kept.

## Paths

App `/home/ad-tv/.local/share/ad-linux-tv`, config `/home/ad-tv/.config/ad-linux-tv/config.yaml`, profile `/home/ad-tv/snap/firefox/common/ad-linux-tv-profile`.

## Switch and recover

- `gui status` shows the current mode.
- `gui tv` starts the TV; `gui off` returns to the console.
- `gui kde` switches to KDE, if installed (SDDM present).

Without a monitor at boot, the computer stays on the console; connect a display and run `gui tv`. SSH and the tty2 console always work. See [Troubleshooting](troubleshooting.md).
