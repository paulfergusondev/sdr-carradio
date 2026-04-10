# PyRadio SDR — Software Defined Radio with Car-Radio UI

A Python reimplementation of [Guglielmo](https://github.com/marcogrecopriolo/guglielmo) (C++/Qt FM & DAB tuner) featuring a stunning **luxury car-radio** inspired UI built entirely in Python with PySide6.

![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue)
![License: GPL-2.0](https://img.shields.io/badge/license-GPL--2.0-green)

---

## Features

| Feature | Status |
|---------|--------|
| **FM Reception** (87.5–108.0 MHz) | ✅ Full DSP pipeline |
| **FM Demodulation** (wideband FM discriminator) | ✅ Working |
| **Stereo indicator** | ✅ Visual |
| **RDS display** (simulated / real when hardware connected) | ✅ Working |
| **Spectrum analyzer** (real-time FFT + waterfall) | ✅ Animated |
| **DAB mode** (channel/service browser) | 🔲 UI complete, backend stub |
| **8 Station Presets** (save/recall/delete) | ✅ Persistent JSON |
| **Volume & Squelch knobs** (custom-painted rotary) | ✅ Interactive |
| **Signal & SNR LED meters** | ✅ Animated bar graphs |
| **Recording** | 🔲 UI wired, file output TBD |
| **Settings dialog** (Device, FM, Audio, UI tabs) | ✅ Complete |
| **RTL-SDR hardware support** | ✅ via pyrtlsdr |
| **Simulated SDR mode** (no hardware needed) | ✅ Built-in demo |
| **Multi-device support** (Airspy, SDRplay, etc.) | 🔲 Planned via SoapySDR |

---

## Requirements

- **Python 3.8+** (tested on 3.10, 3.11, 3.12)
- **Operating System:** Windows 10+, macOS 11+, Linux (X11 or Wayland)
- **Hardware (optional):** RTL-SDR dongle (V3 or V4 recommended)

---

## Installation

### 1. Clone or download

```bash
# Place the files in a directory of your choice
mkdir pyradio-sdr && cd pyradio-sdr
# Copy sdr_radio.py, requirements.txt, and this README here
```

### 2. Create a virtual environment (recommended)

```bash
python3 -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

#### Dependency notes

| Package | Purpose | Notes |
|---------|---------|-------|
| `PySide6` | Qt6 GUI framework | The entire UI |
| `numpy` | Array math / DSP | Core signal processing |
| `scipy` | FIR filters, resampling | FM demod pipeline |
| `pyrtlsdr` | RTL-SDR device driver | Optional — only needed for real hardware |
| `sounddevice` | Real-time audio playback | Uses PortAudio under the hood |

**If you don't have an RTL-SDR dongle**, the app runs perfectly in **Simulated** mode (the default). The simulated backend generates a synthetic FM signal so you can explore the UI, see the spectrum, and hear a test tone.

### 4. RTL-SDR driver setup (only if you have hardware)

#### Linux
```bash
sudo apt install librtlsdr-dev rtl-sdr
# Blacklist the default kernel driver:
echo 'blacklist dvb_usb_rtl28xxu' | sudo tee /etc/modprobe.d/rtlsdr.conf
sudo modprobe -r dvb_usb_rtl28xxu
```

#### macOS
```bash
brew install librtlsdr
```

#### Windows
Install [Zadig](https://zadig.akeo.ie/) and replace the RTL-SDR driver with WinUSB.

---

## Running

```bash
python launcher.py
```

The application starts in **Simulated SDR** mode by default. Press **▶ Play** to start receiving, and you'll see the spectrum analyzer come alive with the signal visualization.

### Quick start guide

1. **Play** — Press the ▶ button to start the simulated receiver
2. **Tune** — Use the TUNING knob or ±0.1 buttons to change frequency
3. **Presets** — Click numbered buttons (1–8) to recall saved stations
4. **Save preset** — Tune to a frequency, then click **M+**
5. **Volume** — Drag the VOLUME knob up/down
6. **Mode** — Switch between FM and DAB with the mode buttons
7. **Settings** — Click ⚙ to configure device, FM params, audio output

### Using real RTL-SDR hardware

1. Open **Settings** (⚙ button)
2. In the **Device** tab, select your RTL-SDR device
3. Adjust gain as needed (Auto is usually fine to start)
4. Close settings and press **▶ Play**

---

## Windows packaging

This repository now includes a portable folder build and an installer build.

### Build the portable release

```powershell
.\build_portable.ps1
```

Output:

- `dist\PyRadioSDR\` (folder containing `PyRadioSDR.exe`)

The portable build uses **PyInstaller** and bundles the Qt runtime, PortAudio, RTL-SDR native library files, and the application icon into a self-contained directory.
Packaged builds now start through a lightweight launcher that shows a small splash window while the heavy SDR/DSP modules import.

### Build the installer

```powershell
.\build_installer.ps1
```

Primary output:

- `dist\installer\PyRadioSDRSetup.exe`

Installer behavior:

- Installs the application into **Program Files\PyRadio SDR**
- Creates **Desktop** and **Start Menu** shortcuts
- Uses **Inno Setup** if it is installed
- Falls back to the built-in Windows **IExpress** packager if Inno Setup is not available

### Build-time files

- `requirements-build.txt` — build-only Python dependency list
- `pyradio_sdr.spec` — PyInstaller spec for the portable build
- `build_portable.ps1` — portable build script
- `build_installer.ps1` — installer build script
- `installer\PyRadioSDR.iss` — Inno Setup script
- `installer\install_pyradio_sdr.ps1` — install action used by the IExpress fallback

---

## Architecture

```
sdr_radio.py
│
├── UI Layer (PySide6 custom widgets)
│   ├── VFDDisplay        — Vacuum-fluorescent frequency readout
│   ├── RotaryKnob        — Metallic rotary controls
│   ├── SignalMeter        — LED bar graph meters
│   ├── GlowIndicator     — Status LEDs with glow
│   ├── SpectrumWidget     — FFT spectrum + waterfall
│   ├── PresetButton       — Illuminated preset buttons
│   └── StyledButton       — Transport & mode buttons
│
├── SDR Backend
│   ├── SDRBackend         — RTL-SDR device handler
│   ├── SimulatedSDR       — Synthetic FM signal generator
│   └── FMDemodulator      — IQ → audio DSP pipeline
│
└── Application
    ├── MainWindow         — Main car-radio interface
    └── SettingsDialog     — Multi-tab configuration
```

### DSP Pipeline (FM)

```
RTL-SDR IQ samples (2.4 MS/s complex)
  │
  ├─→ Low-pass filter (FIR, cutoff at IF/2)
  ├─→ Decimate to 240 kHz IF rate
  ├─→ FM discriminator (polar: angle of conjugate product)
  ├─→ Audio low-pass filter (15 kHz cutoff)
  ├─→ De-emphasis filter (50µs / 75µs)
  ├─→ Decimate to 48 kHz audio rate
  └─→ sounddevice output stream
```

---

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Space` | Play / Pause |
| `↑` / `↓` | Volume up / down |
| `←` / `→` | Tune down / up (0.1 MHz) |
| `1`–`8` | Recall preset |
| `F` | Switch to FM mode |
| `D` | Switch to DAB mode |
| `Esc` | Quit |

---

## Credits & License

Inspired by [Guglielmo](https://github.com/marcogrecopriolo/guglielmo) by Marco Greco, which is itself based on Qt-DAB and sdr-j-fm by Jan van Katwijk.

This project is an independent Python reimplementation of the UI and core SDR concepts. No code was directly ported from the C++ original.

Licensed under **GPL-2.0** — see [LICENSE](LICENSE) for details.
