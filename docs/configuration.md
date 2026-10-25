# Settings and network access

The server uses one configuration file: `~/.config/ad-linux-tv/config.yaml`. Installation creates it only when absent and keeps it private (`0600`). The TV **System** screen and phone **Menu → Settings** cover the common choices; manual editing is mainly for administrators.

- **Phone access:** a new installation has `auth.require_pin: false`. Anyone who can reach the server on the trusted private network can open a remote session. Turn PIN on in settings and enter a four-digit code if needed. Only a salted verifier is stored in config; changing access mode or PIN ends existing phone sessions. Older configs retain their previous PIN setting.
- **Services:** `services` holds unique IDs, display names, HTTPS URLs and optional tile colors. Initial tiles are VK Видео, КиноПоиск, Яндекс Музыка, YouTube, KION and Browser. The Browser tile starts at `https://ya.ru/`.
- **Sound:** saved Firefox-stream level/mute and page-player target apply when new media starts. The selected output, its current level and mute are reported separately by the TV audio system. The phone and TV both show these layers in Sound.
- **Cursor:** acceleration ranges from 0 to 100. The magnifier is off by default and can be toggled from the TV or directly below the phone touchpad.
- **Firefox proxy:** system, none, or custom HTTP/SOCKS5 host and port. It affects only the dedicated TV Firefox profile; a change needs a TV-session restart.
- **Listener:** `bind` is the local address and port is fixed at 8765 because the Firefox bridge uses it. The QR advertises the OS-preferred private LAN address and changes after address renewal.

The phone receives a 14-day HttpOnly, SameSite=Strict session cookie and sends commands through one authenticated WebSocket. Origin and CSRF checks remain active with PIN off. HTTP on the home LAN does not encrypt typed text or session traffic; use a trusted private network and do not port-forward the listener. The PIN is displayed only on the local TV and is never returned to a phone.
