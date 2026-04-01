#!/usr/bin/env python3
"""
SDR Car Radio — A simple car-radio interface for RTL-SDR dongles.

Controls:
  Left / Right arrow  — tune down / up
  Up / Down arrow     — volume up / down
  1–6                 — recall preset
  Space               — scan
  M                   — mute / unmute
  Enter               — power on / off

Right-click any preset button to save the current frequency to that preset.
"""

import json
import os
import subprocess
import threading
import tkinter as tk

# ---------------------------------------------------------------------------
# Frequency band constants
# ---------------------------------------------------------------------------
FM_MIN: float = 87.5   # MHz
FM_MAX: float = 108.0  # MHz
FM_STEP: float = 0.1   # MHz

AM_MIN: float = 0.530  # MHz  (530 kHz)
AM_MAX: float = 1.710  # MHz  (1710 kHz)
AM_STEP: float = 0.010 # MHz  (10 kHz)

DEFAULT_PRESETS: dict = {
    "FM": [87.9, 91.5, 95.5, 99.7, 103.5, 107.1],
    "AM": [0.530, 0.740, 0.880, 1.010, 1.140, 1.280],
}

PRESETS_PATH = os.path.expanduser("~/.sdr-carradio-presets.json")

# Colour palette (green phosphor LCD look)
BG_BODY   = "#2a2a2a"
BG_DARK   = "#1a1a1a"
BG_LCD    = "#001400"
FG_ON     = "#00ff41"
FG_DIM    = "#004d00"
FG_MID    = "#00bb30"
FG_GREY   = "#888888"
FG_BTN    = "#cccccc"
BG_BTN    = "#3a3a3a"
BG_BTN_HI = "#555555"
BG_PWR_OFF = "#8b0000"
FG_PWR_OFF = "#ff4444"
BG_PWR_ON  = "#006600"
FG_PWR_ON  = "#00ff41"


class RadioApp:
    """Main car-radio application window."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("SDR Car Radio")
        self.root.configure(bg=BG_DARK)
        self.root.resizable(False, False)

        # State
        self.band = "FM"
        self.frequency: float = 101.1
        self.volume: int = 70
        self.is_on: bool = False
        self.is_scanning: bool = False
        self.is_muted: bool = False
        self._rtl_proc: subprocess.Popen | None = None
        self._audio_proc: subprocess.Popen | None = None
        self._scan_after_id = None

        self.presets = self._load_presets()
        self._build_ui()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_presets(self) -> dict:
        if os.path.exists(PRESETS_PATH):
            try:
                with open(PRESETS_PATH) as fh:
                    return json.load(fh)
            except (OSError, json.JSONDecodeError):
                pass
        return {k: list(v) for k, v in DEFAULT_PRESETS.items()}

    def _save_presets(self) -> None:
        try:
            with open(PRESETS_PATH, "w") as fh:
                json.dump(self.presets, fh)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        body = tk.Frame(
            self.root, bg=BG_BODY, bd=4, relief=tk.RAISED, padx=16, pady=12
        )
        body.pack(padx=10, pady=10)

        tk.Label(
            body, text="SDR  CAR  RADIO",
            font=("Arial", 9, "bold"), fg=FG_GREY, bg=BG_BODY
        ).pack(pady=(0, 6))

        self._build_display(body)
        self._build_presets(body)
        self._build_tuning(body)
        self._build_bottom(body)
        self._bind_keys()

    def _build_display(self, parent: tk.Frame) -> None:
        """Green phosphor LCD display."""
        lcd = tk.Frame(parent, bg=BG_LCD, bd=4, relief=tk.SUNKEN, padx=12, pady=6)
        lcd.pack(fill=tk.X, pady=(0, 8))

        self._lbl_band = tk.Label(
            lcd, text="FM", font=("Courier", 18, "bold"),
            fg=FG_DIM, bg=BG_LCD, width=3, anchor="w"
        )
        self._lbl_band.grid(row=0, column=0, sticky="w")

        self._lbl_freq = tk.Label(
            lcd, text="101.1", font=("Courier", 44, "bold"),
            fg=FG_DIM, bg=BG_LCD, width=7, anchor="e"
        )
        self._lbl_freq.grid(row=0, column=1, sticky="e")

        self._lbl_unit = tk.Label(
            lcd, text="MHz", font=("Courier", 13),
            fg=FG_DIM, bg=BG_LCD
        )
        self._lbl_unit.grid(row=0, column=2, sticky="sw", padx=(5, 0))

        self._lbl_status = tk.Label(
            lcd, text="OFF", font=("Courier", 10),
            fg=FG_GREY, bg=BG_LCD
        )
        self._lbl_status.grid(row=1, column=0, columnspan=3, sticky="e")

        lcd.columnconfigure(1, weight=1)

    def _btn(self, parent: tk.Frame, text: str, cmd, width: int = 6,
             height: int = 2, font_size: int = 10) -> tk.Button:
        """Helper to create a consistently-styled button."""
        return tk.Button(
            parent, text=text,
            font=("Arial", font_size, "bold"),
            bg=BG_BTN, fg=FG_BTN,
            activebackground=BG_BTN_HI, activeforeground="#ffffff",
            relief=tk.RAISED, bd=2,
            width=width, height=height,
            command=cmd,
        )

    def _build_presets(self, parent: tk.Frame) -> None:
        frame = tk.Frame(parent, bg=BG_BODY)
        frame.pack(fill=tk.X, pady=(0, 6))

        self._preset_btns: list[tk.Button] = []
        for i in range(6):
            btn = tk.Button(
                frame, text=f"P{i + 1}",
                font=("Arial", 8, "bold"),
                bg=BG_BTN, fg=FG_BTN,
                activebackground=BG_BTN_HI, activeforeground="#ffffff",
                relief=tk.RAISED, bd=2,
                width=6, height=2,
                command=lambda idx=i: self.recall_preset(idx),
            )
            btn.grid(row=0, column=i, padx=2, pady=2)
            btn.bind("<Button-3>", lambda e, idx=i: self.save_preset(idx))
            btn.bind("<Button-2>", lambda e, idx=i: self.save_preset(idx))
            self._preset_btns.append(btn)

        self._refresh_preset_labels()

    def _build_tuning(self, parent: tk.Frame) -> None:
        frame = tk.Frame(parent, bg=BG_BODY)
        frame.pack(fill=tk.X, pady=(0, 6))

        self._btn(frame, "AM/FM", self.toggle_band).grid(
            row=0, column=0, padx=3, pady=2
        )
        self._btn(frame, "◀◀", self.tune_down, width=4, font_size=12).grid(
            row=0, column=1, padx=3, pady=2
        )
        self._scan_btn = self._btn(frame, "SCAN", self.toggle_scan)
        self._scan_btn.grid(row=0, column=2, padx=3, pady=2)
        self._btn(frame, "▶▶", self.tune_up, width=4, font_size=12).grid(
            row=0, column=3, padx=3, pady=2
        )

    def _build_bottom(self, parent: tk.Frame) -> None:
        frame = tk.Frame(parent, bg=BG_BODY)
        frame.pack(fill=tk.X, pady=(0, 2))

        # Power
        self._power_btn = tk.Button(
            frame, text="PWR",
            font=("Arial", 10, "bold"),
            bg=BG_PWR_OFF, fg=FG_PWR_OFF,
            activebackground="#cc0000", activeforeground="#ffffff",
            relief=tk.RAISED, bd=2,
            width=6, height=2,
            command=self.toggle_power,
        )
        self._power_btn.grid(row=0, column=0, padx=(0, 12), pady=2)

        tk.Label(frame, text="VOL", font=("Arial", 9),
                 fg=FG_GREY, bg=BG_BODY).grid(row=0, column=1, padx=(0, 2))

        self._btn(frame, "−", self.vol_down, width=3, height=1,
                  font_size=14).grid(row=0, column=2, padx=2)

        self._lbl_vol = tk.Label(
            frame, text="70", font=("Courier", 12, "bold"),
            fg=FG_DIM, bg=BG_LCD,
            width=3, bd=2, relief=tk.SUNKEN,
        )
        self._lbl_vol.grid(row=0, column=3, padx=2)

        self._btn(frame, "+", self.vol_up, width=3, height=1,
                  font_size=14).grid(row=0, column=4, padx=2)

        self._mute_btn = self._btn(frame, "MUTE", self.toggle_mute, width=5)
        self._mute_btn.grid(row=0, column=5, padx=(12, 0), pady=2)

    def _bind_keys(self) -> None:
        self.root.bind("<Left>",  lambda _e: self.tune_down())
        self.root.bind("<Right>", lambda _e: self.tune_up())
        self.root.bind("<Up>",    lambda _e: self.vol_up())
        self.root.bind("<Down>",  lambda _e: self.vol_down())
        self.root.bind("<space>", lambda _e: self.toggle_scan())
        self.root.bind("<Return>", lambda _e: self.toggle_power())
        self.root.bind("m",       lambda _e: self.toggle_mute())
        self.root.bind("M",       lambda _e: self.toggle_mute())
        for i in range(1, 7):
            self.root.bind(str(i), lambda _e, idx=i - 1: self.recall_preset(idx))

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    def _refresh_display(self) -> None:
        freq = self.frequency
        if self.band == "FM":
            self._lbl_freq.config(text=f"{freq:.1f}")
            self._lbl_unit.config(text="MHz")
        else:
            self._lbl_freq.config(text=f"{int(round(freq * 1000))}")
            self._lbl_unit.config(text="kHz")
        self._lbl_band.config(text=self.band)

    def _refresh_preset_labels(self) -> None:
        presets = self.presets.get(self.band, DEFAULT_PRESETS[self.band])
        for i, btn in enumerate(self._preset_btns):
            if i < len(presets):
                freq = presets[i]
                label = f"{freq:.1f}" if self.band == "FM" else f"{int(round(freq * 1000))}"
                btn.config(text=label)

    def _set_display_power(self, on: bool) -> None:
        fg = FG_ON if on else FG_DIM
        self._lbl_freq.config(fg=fg)
        self._lbl_band.config(fg=fg)
        self._lbl_vol.config(fg=fg)
        self._lbl_unit.config(fg=FG_MID if on else FG_DIM)
        self._lbl_status.config(
            text=" ON" if on else "OFF",
            fg=FG_ON if on else FG_GREY,
        )

    # ------------------------------------------------------------------
    # Frequency helpers
    # ------------------------------------------------------------------

    def _freq_step(self) -> float:
        return FM_STEP if self.band == "FM" else AM_STEP

    def _freq_min(self) -> float:
        return FM_MIN if self.band == "FM" else AM_MIN

    def _freq_max(self) -> float:
        return FM_MAX if self.band == "FM" else AM_MAX

    def _clamp_freq(self, freq: float) -> float:
        lo, hi = self._freq_min(), self._freq_max()
        if freq > hi:
            return lo
        if freq < lo:
            return hi
        return freq

    # ------------------------------------------------------------------
    # Tuning
    # ------------------------------------------------------------------

    def tune_up(self) -> None:
        self.frequency = round(
            self._clamp_freq(self.frequency + self._freq_step()), 3
        )
        self._refresh_display()
        if self.is_on:
            self._restart_radio()

    def tune_down(self) -> None:
        self.frequency = round(
            self._clamp_freq(self.frequency - self._freq_step()), 3
        )
        self._refresh_display()
        if self.is_on:
            self._restart_radio()

    def toggle_band(self) -> None:
        if self.band == "FM":
            self.band = "AM"
            self.frequency = AM_MIN
        else:
            self.band = "FM"
            self.frequency = FM_MIN
        self._refresh_display()
        self._refresh_preset_labels()
        if self.is_on:
            self._restart_radio()

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------

    def recall_preset(self, idx: int) -> None:
        presets = self.presets.get(self.band, DEFAULT_PRESETS[self.band])
        if idx < len(presets):
            self.frequency = presets[idx]
            self._refresh_display()
            if self.is_on:
                self._restart_radio()

    def save_preset(self, idx: int) -> None:
        if self.band not in self.presets:
            self.presets[self.band] = list(DEFAULT_PRESETS[self.band])
        # Extend the list if idx is beyond current length
        band_presets = self.presets[self.band]
        while len(band_presets) <= idx:
            band_presets.append(self._freq_min())
        band_presets[idx] = self.frequency
        self._save_presets()
        self._refresh_preset_labels()
        # Brief green flash to confirm save
        btn = self._preset_btns[idx]
        btn.config(bg="#006600")
        self.root.after(350, lambda: btn.config(bg=BG_BTN))

    # ------------------------------------------------------------------
    # Volume
    # ------------------------------------------------------------------

    def vol_up(self) -> None:
        self.volume = min(100, self.volume + 5)
        self._lbl_vol.config(text=str(self.volume))
        if self.is_on and not self.is_muted:
            self._apply_volume(self.volume)

    def vol_down(self) -> None:
        self.volume = max(0, self.volume - 5)
        self._lbl_vol.config(text=str(self.volume))
        if self.is_on and not self.is_muted:
            self._apply_volume(self.volume)

    def toggle_mute(self) -> None:
        self.is_muted = not self.is_muted
        if self.is_muted:
            self._mute_btn.config(bg="#8b5500", fg="#ffaa00")
            self._apply_volume(0)
        else:
            self._mute_btn.config(bg=BG_BTN, fg=FG_BTN)
            self._apply_volume(self.volume)

    @staticmethod
    def _apply_volume(pct: int) -> None:
        try:
            subprocess.run(
                ["amixer", "-q", "sset", "Master", f"{pct}%"],
                check=False, capture_output=True,
            )
        except FileNotFoundError:
            pass

    # ------------------------------------------------------------------
    # Power
    # ------------------------------------------------------------------

    def toggle_power(self) -> None:
        if self.is_on:
            self._cancel_scan()
            self._stop_radio()
            self.is_on = False
            self._power_btn.config(bg=BG_PWR_OFF, fg=FG_PWR_OFF)
            self._set_display_power(False)
        else:
            self.is_on = True
            self._power_btn.config(bg=BG_PWR_ON, fg=FG_PWR_ON)
            self._set_display_power(True)
            self._start_radio()

    # ------------------------------------------------------------------
    # SDR back-end  (rtl_fm → aplay pipeline)
    # ------------------------------------------------------------------

    def _start_radio(self) -> None:
        self._stop_radio()
        freq_hz = int(self.frequency * 1e6)

        if self.band == "FM":
            rtl_cmd = [
                "rtl_fm",
                "-f", str(freq_hz),
                "-M", "wbfm",
                "-s", "200000",
                "-r", "48000",
                "-",
            ]
        else:
            rtl_cmd = [
                "rtl_fm",
                "-f", str(freq_hz),
                "-M", "am",
                "-s", "12000",
                "-r", "48000",
                "-",
            ]

        audio_cmd = ["aplay", "-r", "48000", "-f", "S16_LE", "-t", "raw", "-"]

        try:
            self._rtl_proc = subprocess.Popen(
                rtl_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            self._audio_proc = subprocess.Popen(
                audio_cmd,
                stdin=self._rtl_proc.stdout,
                stderr=subprocess.DEVNULL,
            )
            # Allow rtl_proc to receive SIGPIPE if audio_proc dies
            self._rtl_proc.stdout.close()
            self._lbl_status.config(text="RX ", fg=FG_ON)
        except FileNotFoundError:
            # rtl_fm or aplay not found — run in demo mode (UI only)
            self._lbl_status.config(text="DEMO", fg="#ffaa00")

    def _stop_radio(self) -> None:
        for proc in (self._audio_proc, self._rtl_proc):
            if proc is not None:
                try:
                    proc.terminate()
                    proc.wait(timeout=2)
                except Exception:
                    pass
        self._rtl_proc = None
        self._audio_proc = None

    def _restart_radio(self) -> None:
        if self.is_on:
            self._start_radio()

    # ------------------------------------------------------------------
    # Scan
    # ------------------------------------------------------------------

    def toggle_scan(self) -> None:
        if not self.is_on:
            return
        if self.is_scanning:
            self._cancel_scan()
        else:
            self.is_scanning = True
            self._scan_btn.config(bg=BG_PWR_ON, fg=FG_ON)
            self._scan_step()

    def _scan_step(self) -> None:
        if not self.is_scanning:
            return
        self.tune_up()
        # Schedule the next step; user can stop by pressing SCAN again
        self._scan_after_id = self.root.after(1500, self._scan_step)

    def _cancel_scan(self) -> None:
        self.is_scanning = False
        if self._scan_after_id is not None:
            self.root.after_cancel(self._scan_after_id)
            self._scan_after_id = None
        self._scan_btn.config(bg=BG_BTN, fg=FG_BTN)

    # ------------------------------------------------------------------
    # Clean-up
    # ------------------------------------------------------------------

    def on_closing(self) -> None:
        self._cancel_scan()
        self._stop_radio()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = RadioApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
