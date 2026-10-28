# Android remote: choose a TV, then open its web remote

The Android app adds a saved media-center picker, LAN discovery and explicit switching. The controls themselves are the server's `/remote` page, so most remote UI updates do not need a new APK or Firefox-extension signature. On iPhone/iPad/iPod, use the web remote without installation; recognized iOS browsers hide the Android download invitation. This does not add an iOS app or change native Android pairing.

## Requirements

- Android 9 or newer, with an Android System WebView that supports AndroidX WebKit **MULTI_PROFILE**. The app refuses to share a global cookie profile when this feature is missing. Update WebView if prompted.
- The phone and server are on a trusted private LAN. Do not expose port 8765 to the Internet. HTTP is unencrypted: UUIDs, discovery and an identity preflight do **not** authenticate a peer or prevent LAN impersonation or cookie interception.
- The server has a persistent discovery ID. Old configurations need an explicit migration; installing an APK alone cannot add `/api/device` to an old server.

On the TV-user account, after backing up its private configuration:

```sh
~/.local/share/ad-linux-tv/venv/bin/ad-linux-tv enable-discovery \
  --config ~/.config/ad-linux-tv/config.yaml --discovery-name 'Beelink TV'
```

Restart the application's own server/session to load the new configuration. `disable-discovery` stops advertising after the next restart but preserves the ID and manual access. See [configuration](configuration.md).

## Connect and switch

1. Open the TV QR with a normal phone camera and follow the Android APK link in the browser remote. The same link remains on its main screen without PIN. Install the APK explicitly; this is developer-signed, not a Play Store release. Allow installation from the browser only if you trust this build. The native scanner still selects a center; it is not an APK downloader.
2. Choose a discovered TV, enter its private address, or scan its remote QR. QR input is presented for confirmation; it cannot supply arbitrary commands or credentials. Camera access is optional.
3. Open the selected server's web remote. Enter that TV's PIN if it requires one. PIN-free servers still create a cookie/CSRF session.
4. Use **Сменить медиацентр** to return to the picker. The old native media client/page is retired and gesture buffers are cleared. Already-dispatched operations may still finish on the old target; they are never replayed or redirected onto the new one.

On cold start, the app tries the saved last center once through the same cookie-free identity preflight and isolated-profile path. Missing/forgotten records or failed preflight open the picker, with no automatic retry or other-center fallback. An explicitly opened picker remains open across activity recreation.

Saved records contain only ID, name, address and last selection. Each **ID + origin** has a separate WebView profile. A changed IP, port or scheme does not receive the old origin's cookies. A rediscovered address for the same ID requires explicit confirmation, a fresh identity read and authorization for that origin. Duplicate discovered IDs at different origins are ambiguous. An unavailable selected TV never causes selection of another TV.

Removing a saved record removes the favorite, not the profile's server session. To revoke sessions, change that TV's PIN/authentication mode, or clear the app's data to remove all local profiles and saved centers.

The native app blocks external navigation and initial cross-origin resource requests, file/content access, third-party cookies and SSL-error bypasses. It installs no general JavaScript bridge. The server's same-origin content/security policy remains important; the selected server is trusted to serve the remote. This is not a browser for arbitrary websites.

## Playback and screen space

Use the player inside the remote page. The current server-hosted download is **0.2.5/code6**, following the previously delivered0.2.4, with a dark adaptive TV icon, compact48dp header and dark blue/cyan picker/manual entry. The picker keeps address/QR/search but hides redundant switching chrome. Native inset handling avoids counting system bars/keyboard space twice; the operator confirmed an improvement with0.2.2, not every phone/layout case. Exact installed phone version and all launcher masks remain unverified.

For optional shade controls, open the native header gear and explicitly enable **Медиакнопки в шторке**. The default is off. Android13+ asks for notification permission only after opt-in; blocked app/channel notifications are respected, not overridden. A connection starts only with the selected authorized remote loaded in foreground; it uses that origin's isolated profile and does not retry uncertain actions. The operator reported shade controls working in VK; the KION cause remains unknown. This is not universal media acceptance. The home-screen widget remains separate work.

Web remote styling is served by the TV: reload the remote to receive web changes. A server update cannot change native chrome or icons. Update the APK without clearing data; the app ID and ID+origin profile scheme are unchanged. On short screens the page may scroll; on tall screens remaining room expands the touchpad, not button rows.

## Versions in settings (S02 offline candidate)

Published **0.2.5 / build 6** adds public runtime app-version metadata for the server's shared **Settings → О программе** group. The group shows the media-center version/build separately from the phone app. Browser-only remotes hide the app row; older servers/apps may lack this support and unavailable fields show «неизвестно». Metadata is read-only display information, not authentication. It uses ordinary settings synchronization and a fixed native constant, not a new API, poll or callable bridge; opening About also checks for a late constant.

The [same-QR delivery](verification/android-apk-download-2026-10-27.md) now hosts0.2.5 and verifies the complete served file; exact phone installation remains unknown. Its APK certificate matches the provided0.2.4 certificate, but data-preserving upgrade, actual WebView callback/fragment timing and physical phone rendering still require operator acceptance. The TV glyph, compact header, insets and notification opt-in are unchanged.

## Build and check

Use JDK 17, Android SDK platform 35/build-tools 35.0.0 and the checked-in Gradle 8.11.1 wrapper. Dependency downloads are needed on a cold cache; no Google Play services are required by the app.

```sh
cd android
# Set JAVA_HOME and ANDROID_HOME to your private toolchain locations.
./gradlew --no-daemon :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

Output: `android/app/build/outputs/apk/debug/app-debug.apk` from the repository root. The wrapper distribution has a pinned SHA256. Do not publish a private signing key or `local.properties`.

Tests include endpoint/profile/selection policy and fake NSD callbacks on a virtual Android Looper: stale results, loss/re-found, resolver timeout/refresh and bounds. They do not establish actual multicast delivery, WebView profile behavior, foreground-service/notification behavior, camera, touch or phone lifecycle acceptance. Synthetic offline browser renders check web layout, not Android runtime behavior. Use the [target checklist](target-checklist.md) for physical acceptance.

## Which updates need a Firefox signature?

Discovery, APK/native UI, web controls, the TV timer/power and magnifier settings do not need a new Firefox signature. Installed signed bridge0.4.1 provides versioned managed-HTML media and declarative view capabilities; legacy0.3.2 does not. Its tile-open repair is accepted, but that does not qualify actual playback, seek, mobile layout or DRM. See the [bridge protocol](bridge-protocol.md) and [release guide](release.md).

Changes within an already supported operation can usually stay on the server/UI side. A new browser permission or operation can still require a new signed extension. There is deliberately no arbitrary-script escape hatch.

The [power/compact-remote delivery record](verification/remote-power-2026-10-26.md) distinguishes delivered0.2.4 from source-only S02 and records artifact digests and remaining phone checks.

For the dated build/source evidence, actual Beelink rollout and remaining physical checks, see the [26 October 2026 checkpoint](verification/android-remote-2026-10-26.md).
