# Troubleshooting

## Phone cannot connect

- Both devices must be on the same private network.
- Rescan the TV QR after the router changes the address.
- Controls greyed out: reload the phone page.
- Check the server is running (dedicated TV: `gui status`).

## Tiles open but service controls do not work

- In the TV Firefox, `about:addons` must show `ad-linux-tv bridge` enabled.
- `http://127.0.0.1:8765/health` must show `extension_online: true`.
- After a bridge update, restart the TV session.
- A command shown as uncertain is never repeated automatically; retry it yourself.

## No sound

1. Open **Menu → Sound** (phone) or **System → Sound** (TV).
2. Check the selected output, its mute and level, then press **Проверить звук**.
3. If the test plays but the site is silent, check the Firefox-stream and page-player levels while the video plays.

**?** on the volume button means its state could not be read; reload the page.

## Site does not load

- Check the [proxy setting](configuration.md#proxy); a custom proxy must be running. Changes need a TV-session restart.
- Some sites ignore arrow/Tab navigation; use the pointer.
- Login, playback and DRM depend on the site.

## No media panel on the phone

The site does not expose its playback to Firefox (common with WebAudio, protected or muted previews). Use the touchpad and the site's own controls.

## Firefox is in English

Set **Язык браузера** and restart the TV session. If settings report the language pack missing, re-run `sudo ./ops/kiosk/configure-firefox.sh --configure`.

## TV screen is dark or wrong (dedicated TV)

Connect over SSH or switch to tty2, then:

```sh
gui status
gui tv
sudo systemctl status ad-linux-tv-kiosk.service
sudo journalctl -u ad-linux-tv-kiosk.service -b
```

The service restarts itself after a crash, up to a limit. Without a monitor at boot, the computer stays on the console; connect one and run `gui tv`. If the computer shows a picture but the TV does not, wake the TV with its own remote.
