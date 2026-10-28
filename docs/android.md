# Android app

The Android app is a thin shell: it finds media centers on the LAN, remembers them and opens each one's web remote (`/remote`). Remote controls come from the server, so most UI updates need no new APK. On iPhone/iPad, just use the web remote in the browser.

## Requirements

- Android 9+ with an Android System WebView that supports multi-profile (update WebView if the app asks).
- Phone and TV on the same trusted LAN. HTTP is unencrypted; discovery IDs are not authentication.
- Discovery enabled on the server (new configs have it; for old ones see [Settings](configuration.md#network-and-discovery)).

## Install and connect

1. Scan the TV QR with the phone camera; the browser remote offers the APK. Install it (developer-signed, not from Play Store).
2. In the app, pick a discovered TV, enter its address or scan its QR.
3. Enter the PIN if the TV requires one.
4. **Сменить медиацентр** returns to the list.

On start, the app reopens the last TV if it is reachable; otherwise it shows the list. It never switches to another TV on its own.

Each TV address has its own isolated session. If a TV's address changes, the app asks you to confirm. Removing a saved TV does not log it out; change the TV PIN or clear app data for that.

The app opens only the selected TV's remote, not arbitrary websites.

## Media buttons in the notification shade

Optional: open the gear in the app header and enable **Медиакнопки в шторке** (off by default). Android 13+ then asks for notification permission.

## Update

Install the new APK over the old one without clearing data. Web remote changes arrive by reloading the remote page.

## Build and check

Needs JDK 17, Android SDK platform 35 / build-tools 35.0.0. Gradle 8.11.1 comes with the wrapper.

```sh
cd android
./gradlew --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

Output: `android/app/build/outputs/apk/debug/app-debug.apk`. Set `JAVA_HOME` and `ANDROID_HOME` first. Never commit signing keys or `local.properties`.

Unit tests use fake network discovery; they do not replace testing on a real phone.
