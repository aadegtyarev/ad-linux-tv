# Installation / update / removal

1. Review `./install.sh --dry-run`; it previews `~/.local/share/ad-linux-tv`, `~/.config/ad-linux-tv/config.yaml`, and `~/.config/autostart/ad-linux-tv.desktop`.
2. Run `./install.sh --install` in a graphical user session. It uses a user venv and silently prompts for the PIN. Existing config is preserved. The dedicated persistent Firefox profile is `~/.local/share/ad-linux-tv/firefox-profile`; no sudo or profile-internal edits are performed.
3. Firefox Snap support and persistent profile behavior must be checked on the target Kubuntu system. The bridge extension is not signed yet: the release gate requires AMO unlisted signing and publishing the XPI plus SHA256. Once published, provide `AD_LINUX_TV_XPI_URL` and `AD_LINUX_TV_XPI_SHA256` to install; the installer verifies the digest and opens the XPI for explicit Firefox confirmation. No unattended registration.
4. Update by backing up config and rerunning install. `./uninstall.sh --dry-run` previews removal; `--remove` removes app/autostart and preserves config.

Manual installed start: `~/.local/share/ad-linux-tv/run.sh ~/.config/ad-linux-tv/config.yaml`; direct server CLI: `~/.local/share/ad-linux-tv/venv/bin/ad-linux-tv --config ~/.config/ad-linux-tv/config.yaml`. Development uses `.venv/bin/ad-linux-tv` after `pip install -e '.[dev]'`.

Troubleshoot: inspect terminal output, validate config with the installed venv CLI above, confirm server and Firefox extension use localhost port 8765, and ensure phone/TV share a private LAN. Plain HTTP and non-DRM/service playback are not guaranteed.

## Firefox command recovery semantics

Managed tab ownership lives in Firefox `storage.session`: it survives background event-page unload/reload, but is cleared by browser restart or extension reload/update/disable. After that boundary, pre-existing service tabs are intentionally treated as unmanaged; Home/Back/Refresh/Open will not claim them by URL or reused tab ID. The bounded 256-entry command deduplication ledger is mirrored to `storage.local` so an unacknowledged command cannot repeat across a browser restart; it contains command IDs, states, and fixed reason codes only.

Commands are at-most-once after the extension records an execution claim. If Firefox loses the event page or browser in the claim/effect/ack window, recovery avoids replaying a potentially non-idempotent action; that action may be lost and is surfaced as an uncertain command result. Acknowledgement loss after the effect does not repeat completed effects. Preparation-only failures retry at most three total attempts; a terminal browser operation failure is reported and acknowledged so FIFO delivery can continue. The server retains only the most recent failed/uncertain result for up to five minutes; a later success does not clear it, while a newer failure replaces it. Launcher and phone remote display failure alongside pending state. The status response contains only a fixed reason code and outcome, never URLs, PINs, or exception text.
