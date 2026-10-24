# Separate target Kubuntu checks (not run in development)

- [ ] Phone on LAN can log in; outside/private-network access is denied; retry lockout works.
- [ ] Plasma graphical autostart and Firefox Snap survive logout/reboot; service logins persist.
- [ ] Test X11 and Wayland: launcher arrows/OK; third-party page controls are not promised.
- [ ] Verify Home, Back, Refresh, direct selection; test VK Видео, КиноПоиск, Яндекс Музыка, YouTube and DRM availability without bypasses.
- [ ] Test disconnect recovery and extension bridge port; confirm signed XPI persistence after Firefox updates.
- [ ] Treat HTTP as trusted-LAN only; do not expose the server externally.
- [ ] On Beelink, test TV boot with HDMI, no-HDMI console fallback, Settings QR/address, remote arrows/OK through Settings and confirmed KDE switch, Ctrl+Alt+F2, confirmed `gui kde`/`gui off`, and return with `gui tv` without changing the KDE user's profile.
