# Tested platforms

| Computer | Hardware | OS and display | Status |
|---|---|---|---|
| Beelink SER | AMD Ryzen AI 9 HX 470, Radeon 890M; 64 GB DDR5-5600 (2×32 GB); 2× 1 TB NVMe (Crucial E100) | Kubuntu 26.04.1, kernel 7.0, Firefox Snap 158; TV 1360×768 over HDMI | Main daily target. TV session, phone remote, bridge, HDMI audio, timer and service playback in daily use. Coexists with KDE. |
| B20A mini PC (DMI name AB2L) | Intel Celeron N3350 (2 cores, 1.1/2.4 GHz), Intel HD Graphics 500; 6 GB LPDDR4-2400; 64 GB eMMC (system) + 512 GB SATA SSD (media); Gigabit Ethernet (RTL8111), internal USB Wi-Fi RTL8723BU (out-of-tree driver) | Ubuntu Server 26.04.1 without desktop, kernel 7.0, Firefox Snap 159; monitor 1920×1200 over HDMI | Kiosk boots without KDE, bridge online, phone remote works, YouTube plays. Long-term playback not yet evaluated. |

## Known quirks

**B20A / RTL8723BU Wi-Fi:** the in-kernel `rtl8xxxu` driver treats this adapter as untested and often fails to restart its firmware after a warm reboot. The tested setup instead uses the out-of-tree [`dini/rtl8723bu`](https://github.com/dini/rtl8723bu) driver through DKMS, with concurrent mode off and a small patch for the kernel 6.17+ `cfg80211` signatures (`radio_idx`). `rtl8xxxu` and `btusb` are blacklisted. If DKMS cannot build the driver for a new kernel, the kernel upgrade still completes and a boot service falls back to `rtl8xxxu` with a warning in the journal. Three warm reboots in a row brought Wi-Fi up each time.

## Minimum requirements

These are recommendations, not hard limits:

- x86_64 CPU with 2 cores or more;
- 4 GB RAM (6 GB tested);
- about 16 GB free disk for the OS and Firefox Snap;
- GPU with Mesa/Wayland support and HDMI or DisplayPort output;
- Ethernet or Wi-Fi on the same LAN as the phone;
- apt + snap based distribution where labwc is packaged (Ubuntu 24.04+).

Low-end CPUs such as the Celeron N3350 are for 1080p at most; 4K playback is not expected.

Dated test records: [docs/verification](verification/).
