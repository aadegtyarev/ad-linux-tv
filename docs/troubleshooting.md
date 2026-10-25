# Troubleshooting

## Phone cannot connect

Check that the TV page is open, the server is running, and both devices are on the same private network. Scan the current TV QR again after a router address change. The server listens on port 8765; do not forward it to the Internet. A visible page with disabled controls may mean the WebSocket was lost; reload the phone page. For a dedicated Beelink session, run `sudo systemctl status ad-linux-tv-kiosk.service` over SSH or tty2, then use `gui status`.

## Tiles work but service controls do not

In the dedicated Firefox profile, verify `ad-linux-tv bridge` is enabled in `about:addons`. Open `http://127.0.0.1:8765/health` on the TV and check `extension_online`. After a bridge update, restart the TV session so tabs from the previous extension instance close. A pending/uncertain command on the TV or phone may need a manual retry; uncertain actions are not repeated automatically.

## No sound

Open phone **Menu → Sound** or TV **System → Sound**. Check the selected output, its mute state and level. Press **Проверить звук**. If the test sounds but a site is silent, check the Firefox-stream mute and level while media plays, then the page-player level. The output and stream are separate controls. The main phone button shows **?** if it cannot read current state; reload or check the connection. A site using WebAudio or restricted frames may not follow page-player control.

## Site will not load or navigate

Check the Firefox proxy mode in System; a custom proxy must be available. A changed proxy needs a TV-session restart. On the tested Beelink, YouTube depends on a local Xray proxy. Some sites do not support arrow or Tab navigation reliably; the pointer can click visible controls. Service playback, account login and DRM vary by site and have not all been verified.

If the phone playback panel is absent while a site plays, Firefox may not expose that media through its Linux MPRIS session. WebAudio, protected/restricted media and silent previews can lack it. The regular touchpad and site controls still work. A disabled next/previous button means the current session did not report that action.

## Recover the Beelink display

Use `gui status` over SSH or tty2. `gui tv` starts TV mode; `gui kde` switches to KDE; `gui off` returns to console. The `ad-linux-tv-kiosk.service` restarts after unexpected server/browser exit, with a start limit. Inspect `sudo journalctl -u ad-linux-tv-kiosk.service -b` for startup failures. A no-monitor boot leaves a console; attach HDMI and run `gui tv`.
