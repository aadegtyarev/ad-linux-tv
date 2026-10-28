# Tested platforms

| Computer | Hardware | OS and display | Status |
|---|---|---|---|
| Beelink SER | AMD Ryzen AI 9 HX 470, Radeon 890M; 64 GB DDR5-5600 (2×32 GB); 2× 1 TB NVMe (Crucial E100) | Kubuntu 26.04.1, kernel 7.0, Firefox Snap 158; TV 1360×768 over HDMI | Main daily target. TV session, phone remote, bridge, HDMI audio, timer and service playback in daily use. Coexists with KDE. |
| B20A mini PC (DMI name AB2L) | Intel Celeron N3350 (2 cores, 1.1/2.4 GHz), Intel HD Graphics 500; 6 GB LPDDR4-2400; 64 GB eMMC (system) + 512 GB SATA SSD (media); Gigabit Ethernet (RTL8111), internal USB Wi-Fi RTL8723BU | Ubuntu Server 26.04.1 without desktop, kernel 7.0, Firefox Snap 159; monitor 1920×1200 over HDMI | Kiosk boots without KDE, bridge online, phone remote works, YouTube plays. Long-term playback not yet evaluated. |

## Known quirks

**B20A / RTL8723BU Wi-Fi:** the in-kernel `rtl8xxxu` driver treats this adapter as untested.

- Its Bluetooth part wedges Wi-Fi at boot. Blacklist `btusb` and power-cycle once:
  ```sh
  echo 'blacklist btusb' | sudo tee /etc/modprobe.d/blacklist-btusb.conf
  ```
- The driver sometimes hangs while loading firmware, and Wi-Fi stays down until the next reboot. Use Ethernet as the main link, mark Wi-Fi `optional: true` in netplan, and cap the boot wait with a drop-in `sys-subsystem-net-devices-<wifi>.device.d/10-timeout.conf` containing `[Unit]` / `JobRunningTimeoutSec=10s`.

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
