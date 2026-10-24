# Feature contract: Beelink TV session

- Status: Approved for implementation; physical display verification pending
- Date: 2026-10-24
- Approval: User designated Beelink as the target, requested TV at boot, preserved KDE access, a discreet confirmed exit, and authorized application changes.

## Goal and user-visible behavior

Beelink starts a fullscreen Firefox TV session by default when a physical display is present. The TV session uses a dedicated Linux user and Firefox profile, leaving the existing `adegtyarev` KDE session and its SDDM configuration intact. A user can switch to a text console and run `gui kde` with confirmation to enter KDE, or `gui tv` to return to TV mode. No large or accidental exit control appears on the TV page.

## Scenarios and edge cases

- With no connected display, boot remains remotely reachable and presents a text console rather than repeatedly restarting a compositor.
- Closing Firefox or a failed TV session returns control to a text console. An explicit `gui tv` retries it; a future boot attempts TV mode again.
- `gui kde` confirms before stopping TV mode and starts the existing KDE/SDDM autologin. `gui off` confirms before stopping any graphics and starting the console. Existing `gui on` remains a KDE alias.
- The dedicated user keeps server configuration and Firefox Snap profile under its own home. The server PIN never appears in arguments or logs.
- The source checkout at `/home/adegtyarev/Develop/Hobby/ad-linux-tv` is never an installation or uninstall target.
- The signed Firefox extension remains required for full remote control; unavailable signing assets are reported, not bypassed.

## Non-goals

- Changing the KDE user's profile, SDDM autologin identity, or desktop packages.
- Bypassing Firefox extension signing or DRM protections.
- Claiming visual, audio, DRM, or extension persistence success before testing with HDMI connected.

## Affected surfaces

- [Kubuntu operation](../surfaces/kubuntu-operation.md): installation, paths, graphical startup, mode switching and fallback.
- [Configuration](../surfaces/configuration.md): dedicated user owns the existing single configuration file; schema remains unchanged.
- [TV launcher](../surfaces/tv-launcher.md): fullscreen presentation; launcher behavior remains unchanged.

## Interfaces and constraints

- Preserve `./install.sh --dry-run` as a non-mutating preview and `--install` as an explicit action. A TV installation must not create KDE autostart for the TV user.
- Store the persistent Firefox Snap profile and signed XPI in the Firefox Snap user-common directory, not an inaccessible hidden host-home directory. Firefox must request explicit confirmation for signed-XPI installation.
- Boot integration must use a real logind/PAM graphical session on a VT, keep SSH available, and provide a console recovery route. Avoid an infinite restart loop without a monitor.
- The application must stop its server when the browser process exits. Do not use a private Firefox window because service logins must persist.
- Keep the existing KDE start/stop path available until the TV mode is physically validated.

## Acceptance criteria

- The installer previews all destinations, supports installing without KDE autostart, and does not touch the KDE user's files when run for the dedicated TV user.
- Removal only targets the dedicated TV user's installed application and preserves the source checkout.
- A TV session can be started and stopped independently of KDE. `gui kde` requires confirmation; `gui status` distinguishes console, TV, and KDE.
- Boot attempts TV mode with a connected display; with no display or launch failure, console and SSH remain usable.
- Firefox uses a persistent Snap-accessible profile and, when available, a verified signed XPI installed through an interactive browser confirmation.

## Validation

- Run shell/static tests, installer dry-run and existing project checks for changed behavior.
- Verify systemd unit syntax and mode-switch behavior without replacing the running KDE session.
- With HDMI later connected, verify Cage/Firefox/Snap profile, exit to console, KDE switch, reboot autostart, phone LAN control, XPI persistence, audio and DRM under the target checklist.
