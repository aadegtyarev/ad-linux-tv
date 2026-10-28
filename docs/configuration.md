# Settings

Most settings are in TV **System** and phone **Menu → Settings**. They are stored in `~/.config/ad-linux-tv/config.yaml` (mode `0600`); edit it by hand only if needed. Some changes apply after a TV-session restart; the settings screen offers it and warns that viewing will be interrupted.

| Setting | Config | Notes |
|---|---|---|
| Phone PIN | `auth.require_pin` | Off by default. Changing it ends phone sessions. |
| Proxy | `proxy` | Applies after restart. |
| Язык браузера | `browser: {locale: ru}` | `ru` (default) or `en`. Applies after restart. |
| Cursor acceleration | `pointer` | 0–100. |
| Magnifier scale | `magnifier: {scale: 2.5}` | 1.25–5 in 0.25 steps. Applies after restart. |
| Site view | `view`, `services[].view` | See below. |
| Sound | `audio` | Output, Firefox stream and page-player levels. |

## Proxy

Affects only the TV Firefox profile. Modes: `system` (default), `none` or `custom`:

```yaml
proxy:
  mode: custom
  protocol: http      # or socks5
  host: 127.0.0.1
  port: 1081
```

This example points to a local proxy such as Xray; installing the proxy itself is up to you.

## Browser language

Firefox needs the language pack for `ru`; the [kiosk setup](kiosk.md) installs it. If it is missing, settings say so and Firefox stays English.

## Services and site view

`services` lists tiles: `id`, `name`, HTTPS `url`, optional color and `view`. Defaults: VK Видео, КиноПоиск, Яндекс Музыка, YouTube, KION and Browser (`https://ya.ru/`).

In **Вид сайтов** choose **Все сайты** or one site, then mode (**Мобильный / Обычный**) and zoom. A site without its own setting follows the common one; the default is desktop at 125%.

```yaml
view: {mode: mobile, zoom: 200}   # desktop|mobile, zoom 50–300
```

Mobile mode only changes the User-Agent and zoom; a site may ignore it. Needs the signed bridge; reopen the tile to apply.

## Network and discovery

Port 8765 is fixed. Phones get a 14-day session cookie. Traffic is unencrypted HTTP: use a trusted LAN and never port-forward.

New configs include `discovery: {enabled: true, id, name}` for the [Android app](android.md). For an old config:

```sh
~/.local/share/ad-linux-tv/venv/bin/ad-linux-tv enable-discovery \
  --config ~/.config/ad-linux-tv/config.yaml --discovery-name 'Living room TV'
```

Then restart the TV session. `disable-discovery` keeps the ID. Do not copy one ID to another TV.
