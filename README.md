# sdr-carradio

A simple **car-radio interface** for RTL-SDR dongles. No spectrum graphs, no
waterfall displays — just tune to a station and listen, exactly like the radio
in your car.

![Screenshot placeholder — run the app to see the green phosphor display]

---

## Features

- Green phosphor LCD display showing frequency and band
- **6 preset buttons** — left-click to recall, right-click (or middle-click) to save
- **Tune ◀◀ / ▶▶** — step through stations
- **SCAN** — auto-step through the band until you find something you like, press again to stop
- **AM / FM** toggle
- **Volume +/−** with on-screen readout
- **Mute** toggle
- **Power** on / off
- Keyboard shortcuts (see below)
- Presets saved to `~/.sdr-carradio-presets.json` automatically
- **Demo mode** — the UI works even without an RTL-SDR dongle attached
  (status display shows `DEMO` instead of `RX`)

---

## Requirements

### System packages

```bash
# Debian / Ubuntu / Raspberry Pi OS
sudo apt-get update
sudo apt-get install python3-tk rtl-sdr alsa-utils
```

| Package | Purpose |
|---------|---------|
| `python3-tk` | Tkinter GUI toolkit |
| `rtl-sdr` | Provides `rtl_fm` for SDR reception |
| `alsa-utils` | Provides `aplay` for audio output and `amixer` for volume control |

### Python

Python 3.10 or later is required (uses `X | Y` union type hints).
No third-party Python packages are needed.

---

## Running

```bash
python3 radio.py
```

If your RTL-SDR dongle is plugged in and the required system packages are
installed, pressing **PWR** will start receiving the displayed frequency.
If the dongle or `rtl_fm` is not found, the app runs in demo mode so you can
still explore the interface.

---

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `←` / `→` | Tune down / up |
| `↑` / `↓` | Volume up / down |
| `1` – `6` | Recall preset 1 – 6 |
| `Space` | Toggle scan |
| `M` | Toggle mute |
| `Enter` | Toggle power |

---

## Saving presets

Right-click (or middle-click) any preset button to save the currently-tuned
frequency to that slot.  The button briefly flashes green to confirm.
Presets are stored separately for FM and AM.

---

## Troubleshooting

**`rtl_fm` not found / no audio**
Ensure `rtl-sdr` and `alsa-utils` are installed (see Requirements above).

**Permission denied on the USB device**
Add your user to the `plugdev` group and reload udev rules:
```bash
sudo usermod -aG plugdev $USER
sudo udevadm control --reload-rules && sudo udevadm trigger
# then log out and back in
```

**No sound through the right output device**
Pass a device to `aplay` by editing the `audio_cmd` list in `radio.py`:
```python
audio_cmd = ["aplay", "-D", "hw:1,0", "-r", "48000", "-f", "S16_LE", "-t", "raw", "-"]
```
Run `aplay -l` to list available devices.
