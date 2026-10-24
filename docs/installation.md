# Installation / update / removal

1. Review `./install.sh --dry-run`; it previews `~/.local/share/ad-linux-tv`, `~/.config/ad-linux-tv/config.yaml`, and `~/.config/autostart/ad-linux-tv.desktop`.
2. Run `./install.sh --install` in a graphical user session. It uses a user venv and silently prompts for the PIN. Existing config is preserved. The dedicated persistent Firefox profile is `~/.local/share/ad-linux-tv/firefox-profile`; no sudo or profile-internal edits are performed.
3. Firefox Snap support and persistent profile behavior must be checked on the target Kubuntu system. The bridge extension is not signed yet: the release gate requires AMO unlisted signing and publishing the XPI plus SHA256. Once published, provide `AD_LINUX_TV_XPI_URL` and `AD_LINUX_TV_XPI_SHA256` to install; the installer verifies the digest and opens the XPI for explicit Firefox confirmation. No unattended registration.
4. Update by backing up config and rerunning install. `./uninstall.sh --dry-run` previews removal; `--remove` removes app/autostart and preserves config.

Troubleshoot: inspect terminal output, validate config with `ad-linux-tv`, confirm server and Firefox extension use localhost port 8765, and ensure phone/TV share a private LAN. Plain HTTP and non-DRM/service playback are not guaranteed.
