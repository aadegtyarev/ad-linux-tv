# Use the TV and phone

The launcher and remote interface are in Russian.

## TV

Pick a service tile with the arrows and Enter, or click it from the phone. **Плитки** (Home) returns to the tiles. **System** opens TV settings. Standard volume +/− keys on a physical remote or keyboard adjust the selected software output in 5% steps, up to 100%. A small volume bar briefly appears at the top of the TV picture when the level changes.

## Connect a phone

Scan the TV QR code with a phone on the same home network. No PIN is needed by default; if you enable one, the four-digit code is shown only on the TV. **Menu → QR** shows a code for a second phone. If the TV's address changes, the phone tries to follow it; otherwise rescan the QR. Android users can install the [Android app](android.md).

## Remote

- **Touchpad:** drag to move the pointer, tap to click, two fingers to scroll. Edge arrows send arrow keys; after arrow/Tab navigation a tap sends Enter.
- **Keys:** Shift+Tab, Tab, Enter and Back below the pad.
- **Text:** opens a field and the phone keyboard for the focused Firefox field.
- **Volume:** slider and mute for the selected output. **Menu → Sound** has output choice, a test chime and separate levels for output, Firefox stream and page player.
- **Magnifier:** button next to the volume.
- **⛶ Экран:** puts the video on the current page into fullscreen; press again to return. Only on press, never automatically.
- **Media panel:** appears when the site exposes playback (title, play/pause, position, previous/next where supported).
- **Screen settings on the playback panel:** choose **Исходный**, **4:3** or **16:9**, optionally enable horizontal mirror, then press **Применить**. The change affects only the current eligible video; 4:3 and 16:9 stretch or squeeze it. Accessible embedded players are attempted, but some sites and protected video may not support the operation. Assigning a physical remote button is not yet available.

## Touch panel

On a touchscreen, a small panel offers Home, Back/Forward, keyboard, timer, volume and **⛶** for video fullscreen. Over fullscreen video only the handle, **⛶** (to return) and the volume button stay; drag the handle to move this small panel, it keeps its own place.

## Timer

Choose Off, 15, 30, 60, 90 or 120 minutes. The TV shows a small clock in the upper-left corner and warns two minutes before the end. At expiry, playback pauses and the display turns off. A touch or phone command turns it back on; if the TV stays dark, use its own remote.

## Power (⏻ next to Timer)

- **Tap:** display sleep or wake. Sleep pauses playback first and keeps the display on if it cannot confirm silence.
- **Hold 1.2 s:** confirmation to shut down the whole computer. It can only be turned on again with its power button.

## Settings

TV **System** and phone **Menu → Settings** contain PIN, proxy, browser language, Browser-tile search, cursor acceleration, magnifier scale, site view and sound. In **Поиск в браузере**, save Яндекс, Google or DuckDuckGo for the next Browser-tile open. **Текущий адрес из конфигурации** restores the existing configured address; saving a provider does not overwrite it. **О программе** shows versions. Details: [Settings](configuration.md).

### Bluetooth adapter

Open **Bluetooth** in TV or phone settings. Choose a detected adapter by its BlueZ name and address suffix; names may be missing or identical, and list numbers can change. To identify a USB stick when names are ambiguous, compare the list before and after plugging it in. If the chosen adapter is off, use **Включить выбранный адаптер** and wait for its observed state. The system may deny the request.

A chosen adapter is remembered. If it disappears, the panel reports it missing rather than silently using another; it becomes available again when that adapter returns. **Автоматически** restores the former automatic behavior. Finish or cancel discovery or pairing before switching. The device list shows the Bluetooth name and, when different, its alias; either may appear later during discovery. An alias can look like an address and does not establish device identity. Selection does not disable another adapter, disconnect devices, remove or transfer Bluetooth pairings, or change other applications' controller choice. Devices paired through another adapter may require separate pairing; do not forget an existing bond just to switch adapters.

The Bluetooth panel does not configure or intercept physical remote buttons. Existing saved mappings are not automatically deleted; explicitly forgetting their associated device can remove its saved mappings. Adapter switching and pairing with actual hardware still need verification; a displayed name does not prove whether an adapter is USB or built in. If a verified UR02's OK button does not activate a tile, see [UR02 troubleshooting](troubleshooting.md#ur02-ok-does-not-activate-a-tile).

The dedicated TV Firefox profile prepares the media-center launcher as its browser homepage at startup. Firefox's own Home action (including Alt+Home) can then open it from a site; this may navigate the current tab and does not invoke the bridge's separate Home command. Ordinary text-editing Home is not intercepted. Whether the physical remote button reaches Firefox's browser-home action depends on the system and focus and remains untested.

Site playback, login and DRM depend on Firefox and the site.
