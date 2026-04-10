#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║  PyRadio SDR — Software Defined Radio with Car-Radio UI     ║
║  A Python rewrite inspired by Guglielmo (C++ Qt SDR)        ║
║  Features: FM reception, RDS/RBDS, presets, waveform      ║
╚══════════════════════════════════════════════════════════════╝
"""

import sys
import os
import json
import math
import struct
import threading
import time
from collections import deque
from typing import Callable, Optional, List, Dict, Tuple

import numpy as np
from scipy.signal import firwin, lfilter, lfilter_zi, decimate, resample_poly, upfirdn

# ─── Ensure librtlsdr native DLL is discoverable on Windows ─────────
if sys.platform == 'win32':
    # Python 3.8+ restricts DLL search to explicit directories only.
    import importlib.util as _ilu
    _dll_dirs = []
    for _module_name in ('rtlsdr', 'pyrtlsdrlib', '_sounddevice_data'):
        _spec = _ilu.find_spec(_module_name)
        if not _spec or not _spec.submodule_search_locations:
            continue
        for _pkg_dir in _spec.submodule_search_locations:
            _dll_dirs.append(_pkg_dir)
            _dll_dirs.append(os.path.join(_pkg_dir, 'lib'))
            _dll_dirs.append(os.path.join(_pkg_dir, 'portaudio-binaries'))

    _seen_dirs = set()
    for _p in _dll_dirs:
        if _p in _seen_dirs or not os.path.isdir(_p):
            continue
        _seen_dirs.add(_p)
        os.add_dll_directory(_p)

    del _dll_dirs, _ilu, _module_name, _p, _pkg_dir, _seen_dirs, _spec

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QSlider, QComboBox, QStackedWidget,
    QListWidget, QListWidgetItem, QDialog, QTabWidget, QSpinBox,
    QCheckBox, QGroupBox, QScrollArea, QFrame, QSizePolicy,
    QGraphicsDropShadowEffect, QAbstractItemView, QDoubleSpinBox, QLineEdit,
    QGraphicsView, QGraphicsScene, QGraphicsProxyWidget
)
from PySide6.QtCore import (
    Qt, QTimer, Signal, QPropertyAnimation, QEasingCurve,
    Property, QRect, QRectF, QPointF, QSize, QObject, Slot, QEvent
)
from PySide6.QtGui import (
    QPainter, QColor, QLinearGradient, QRadialGradient, QConicalGradient,
    QPen, QBrush, QFont, QFontDatabase, QPainterPath, QPixmap,
    QMouseEvent, QWheelEvent, QPaintEvent, QResizeEvent, QIcon,
    QDoubleValidator
)

from app_metadata import APP_ICON_PATH, APP_NAME, APP_VERSION, WINDOWS_APP_ID

# ─── Color Palette ───────────────────────────────────────────
class Palette:
    """Midnight luxe car-radio palette."""
    BG_DARK       = QColor(12, 12, 16)
    BG_MID        = QColor(22, 22, 30)
    BG_PANEL      = QColor(28, 28, 38)
    BG_SURFACE    = QColor(36, 36, 48)
    BG_RAISED     = QColor(44, 42, 56)

    AMBER         = QColor(255, 170, 40)
    AMBER_DIM     = QColor(180, 110, 20)
    AMBER_GLOW    = QColor(255, 180, 60, 80)

    CYAN          = QColor(0, 220, 230)
    CYAN_DIM      = QColor(0, 140, 150)
    CYAN_GLOW     = QColor(0, 220, 230, 60)

    RED           = QColor(255, 60, 60)
    RED_DIM       = QColor(140, 30, 30)
    GREEN         = QColor(40, 220, 80)
    GREEN_DIM     = QColor(20, 100, 40)

    TEXT_PRIMARY   = QColor(230, 225, 215)
    TEXT_SECONDARY = QColor(140, 135, 125)
    TEXT_DIM       = QColor(80, 75, 70)

    KNOB_BODY     = QColor(55, 52, 65)
    KNOB_RING     = QColor(75, 72, 88)
    KNOB_SHINE    = QColor(110, 105, 130)
    KNOB_INDICATOR = QColor(255, 170, 40)

    GLASS_TOP     = QColor(255, 255, 255, 8)
    GLASS_BOT     = QColor(0, 0, 0, 30)


PALETTE_COLOR_FIELDS = (
    "BG_DARK",
    "BG_MID",
    "BG_PANEL",
    "BG_SURFACE",
    "BG_RAISED",
    "AMBER",
    "AMBER_DIM",
    "AMBER_GLOW",
    "CYAN",
    "CYAN_DIM",
    "CYAN_GLOW",
    "RED",
    "RED_DIM",
    "GREEN",
    "GREEN_DIM",
    "TEXT_PRIMARY",
    "TEXT_SECONDARY",
    "TEXT_DIM",
    "KNOB_BODY",
    "KNOB_RING",
    "KNOB_SHINE",
    "KNOB_INDICATOR",
    "GLASS_TOP",
    "GLASS_BOT",
)

PALETTE_DEFAULTS = {
    name: QColor(getattr(Palette, name))
    for name in PALETTE_COLOR_FIELDS
}

DEFAULT_SKIN_NAME = "Midnight Amber"
APP_SETTINGS_PATH = os.path.expanduser("~/.pyradio_sdr_settings.json")

DEFAULT_SKIN_STYLE = {
    "ui_font_family": "Segoe UI",
    "mono_font_family": "Consolas",
    "widget_text": "#e6e1d7",
    "app_bg_top": "#10101a",
    "app_bg_mid": "#0c0c10",
    "app_bg_bottom": "#080810",
    "ui_bg_top": "#10101a",
    "ui_bg_mid": "#0c0c10",
    "ui_bg_bottom": "#080810",
    "view_bg": "#0c0c10",
    "presets_top": "#1e1c28",
    "presets_bottom": "#161420",
    "presets_border": "#2a2836",
    "scrollbar_bg": "#1a1822",
    "scrollbar_handle": "#3c3a4a",
    "scrollbar_handle_hover": "#5a566e",
    "status_bg": "#0a0a10",
    "status_border": "#1a1822",
    "status_idle": "#8c877d",
    "status_freq": "#00dce6",
    "status_warning": "#ffaa28",
    "status_ok": "#28dc50",
    "status_error": "#ff3c3c",
    "status_sep": "#2a2836",
    "button_bg_top": "#2a2834",
    "button_bg_bottom": "#1e1c26",
    "button_border": "#3c3948",
    "button_hover_bg": "#32303e",
    "button_hover_border": "#555164",
    "preset_active_top": "#3c2d0f",
    "preset_active_bottom": "#281e0a",
    "preset_hover_top": "#32303e",
    "preset_hover_bottom": "#262430",
    "preset_hover_border": "#504c5f",
    "preset_bg_top": "#2a2834",
    "preset_bg_bottom": "#1e1c26",
    "preset_border": "#3c3948",
    "preset_number_inactive": "#cdc7bc",
    "preset_text_inactive": "#b8b2a5",
    "vfd_bezel_top": "#2d2a38",
    "vfd_bezel_mid": "#1e1c28",
    "vfd_bezel_bottom": "#14121c",
    "vfd_screen_top": "#051216",
    "vfd_screen_mid": "#020a0e",
    "vfd_screen_bottom": "#040e12",
    "vfd_text": "#00ebd2",
    "vfd_glow": (0, 235, 210, 40),
    "vfd_dim": "#00b4a5",
    "vfd_editor_bg": "rgba(2, 18, 24, 235)",
    "vfd_editor_border": "#00dce6",
    "vfd_editor_text": "#00ebd2",
    "vfd_editor_selection_bg": "#00b4a8",
    "vfd_editor_selection_fg": "#021214",
    "wave_bg_top": "#060a0e",
    "wave_bg_bottom": "#04070a",
    "wave_grid": (30, 50, 55, 80),
    "wave_center": (50, 80, 85, 120),
    "wave_fill_top": (0, 200, 180, 45),
    "wave_fill_mid": (0, 220, 200, 18),
    "wave_fill_bottom": (0, 200, 180, 45),
    "wave_glow": (0, 220, 200, 55),
    "wave_line": (0, 235, 215, 230),
    "wave_border": (40, 60, 65, 140),
}

SKIN_DEFINITIONS = {
    "Midnight Amber": {
        "palette": {},
        "style": {},
    },
    "Ocean Cyan": {
        "palette": {
            "AMBER": "#36d9ff",
            "AMBER_DIM": "#1a6e88",
            "AMBER_GLOW": (54, 217, 255, 80),
            "CYAN": "#50f4ff",
            "CYAN_DIM": "#1d8290",
            "CYAN_GLOW": (80, 244, 255, 70),
            "KNOB_INDICATOR": "#36d9ff",
        },
        "style": {
            "status_warning": "#36d9ff",
            "vfd_text": "#50f4ff",
            "vfd_glow": (80, 244, 255, 48),
            "vfd_dim": "#29c7d6",
            "vfd_editor_border": "#36d9ff",
            "vfd_editor_text": "#50f4ff",
            "vfd_editor_selection_bg": "#1ca6b5",
            "wave_fill_top": (43, 223, 255, 50),
            "wave_fill_mid": (70, 242, 255, 22),
            "wave_fill_bottom": (43, 223, 255, 50),
            "wave_glow": (80, 244, 255, 65),
            "wave_line": (102, 247, 255, 235),
            "wave_grid": (36, 80, 90, 90),
            "wave_center": (66, 120, 130, 130),
        },
    },
    "Deep Red": {
        "palette": {
            "AMBER": "#ff7a55",
            "AMBER_DIM": "#8e3f28",
            "AMBER_GLOW": (255, 122, 85, 80),
            "CYAN": "#ff6f78",
            "CYAN_DIM": "#96424d",
            "CYAN_GLOW": (255, 111, 120, 60),
            "GREEN": "#ffb36b",
            "GREEN_DIM": "#8e6636",
            "KNOB_INDICATOR": "#ff7a55",
        },
        "style": {
            "status_warning": "#ff7a55",
            "status_freq": "#ff6f78",
            "status_ok": "#ffb36b",
            "vfd_text": "#ff8d72",
            "vfd_glow": (255, 141, 114, 48),
            "vfd_dim": "#df5d56",
            "vfd_editor_border": "#ff7a55",
            "vfd_editor_text": "#ff8d72",
            "vfd_editor_selection_bg": "#c15247",
            "wave_fill_top": (255, 116, 96, 52),
            "wave_fill_mid": (255, 141, 114, 22),
            "wave_fill_bottom": (255, 116, 96, 52),
            "wave_glow": (255, 141, 114, 70),
            "wave_line": (255, 175, 138, 240),
            "wave_grid": (82, 46, 46, 90),
            "wave_center": (122, 64, 64, 130),
        },
    },
    "Classic Green": {
        "palette": {
            "AMBER": "#9ddf5e",
            "AMBER_DIM": "#507a30",
            "AMBER_GLOW": (157, 223, 94, 80),
            "CYAN": "#6ce7a8",
            "CYAN_DIM": "#2f835d",
            "CYAN_GLOW": (108, 231, 168, 60),
            "GREEN": "#b5ff85",
            "GREEN_DIM": "#5d8c43",
            "KNOB_INDICATOR": "#9ddf5e",
        },
        "style": {
            "status_warning": "#9ddf5e",
            "status_freq": "#6ce7a8",
            "status_ok": "#b5ff85",
            "vfd_text": "#aaff89",
            "vfd_glow": (170, 255, 137, 42),
            "vfd_dim": "#72cf6d",
            "vfd_editor_border": "#9ddf5e",
            "vfd_editor_text": "#aaff89",
            "vfd_editor_selection_bg": "#5aa760",
            "wave_fill_top": (134, 235, 113, 46),
            "wave_fill_mid": (170, 255, 137, 18),
            "wave_fill_bottom": (134, 235, 113, 46),
            "wave_glow": (170, 255, 137, 62),
            "wave_line": (195, 255, 160, 235),
            "wave_grid": (46, 82, 50, 88),
            "wave_center": (74, 121, 80, 128),
        },
    },
    "Winamp Classic": {
        "palette": {
            "BG_DARK": "#11275b",
            "BG_MID": "#2d5fb6",
            "BG_PANEL": "#4f7fd0",
            "BG_SURFACE": "#84afe8",
            "BG_RAISED": "#c0d8fb",
            "AMBER": "#cdbb76",
            "AMBER_DIM": "#746841",
            "AMBER_GLOW": (205, 187, 118, 66),
            "CYAN": "#bdd4ff",
            "CYAN_DIM": "#6a90d4",
            "CYAN_GLOW": (189, 212, 255, 58),
            "RED": "#d9887f",
            "RED_DIM": "#814e49",
            "GREEN": "#96f052",
            "GREEN_DIM": "#5b8b34",
            "TEXT_PRIMARY": "#e8eff9",
            "TEXT_SECONDARY": "#cad7ea",
            "TEXT_DIM": "#8d9fbb",
            "KNOB_BODY": "#c7dcff",
            "KNOB_RING": "#4670b7",
            "KNOB_SHINE": "#f2f7ff",
            "KNOB_INDICATOR": "#d2c27d",
            "GLASS_TOP": (255, 255, 255, 38),
            "GLASS_BOT": (10, 10, 18, 30),
        },
        "style": {
            "ui_font_family": "Tahoma",
            "mono_font_family": "Lucida Console",
            "widget_text": "#dde7f5",
            "app_bg_top": "#4375c8",
            "app_bg_mid": "#224a97",
            "app_bg_bottom": "#112b64",
            "ui_bg_top": "#5d8edb",
            "ui_bg_mid": "#3267bb",
            "ui_bg_bottom": "#19468e",
            "view_bg": "#0f1c45",
            "presets_top": "#4179de",
            "presets_bottom": "#1e458f",
            "presets_border": "#6e98e2",
            "scrollbar_bg": "#14274f",
            "scrollbar_handle": "#c2d7fb",
            "scrollbar_handle_hover": "#ebf3ff",
            "status_bg": "#0d1d46",
            "status_border": "#5a84d0",
            "status_idle": "#d3d8e0",
            "status_freq": "#96f052",
            "status_warning": "#d2c27d",
            "status_ok": "#96f052",
            "status_error": "#ff9f91",
            "status_sep": "#678bd0",
            "button_bg_top": "#ddeaff",
            "button_bg_bottom": "#83ace6",
            "button_border": "#2e5cab",
            "button_hover_bg": "#eef4ff",
            "button_hover_border": "#6f9ee2",
            "preset_active_top": "#2d69df",
            "preset_active_bottom": "#153a81",
            "preset_hover_top": "#e4eeff",
            "preset_hover_bottom": "#a7c4ec",
            "preset_hover_border": "#7199d8",
            "preset_bg_top": "#d0e2ff",
            "preset_bg_bottom": "#7fa7e0",
            "preset_border": "#4d79bf",
            "preset_number_inactive": "#f2f7ff",
            "preset_text_inactive": "#e4edf9",
            "vfd_bezel_top": "#d9e7ff",
            "vfd_bezel_mid": "#a8c4f2",
            "vfd_bezel_bottom": "#6b91cc",
            "vfd_screen_top": "#06080d",
            "vfd_screen_mid": "#010204",
            "vfd_screen_bottom": "#040507",
            "vfd_text": "#8dff45",
            "vfd_glow": (141, 255, 69, 36),
            "vfd_dim": "#5ea533",
            "vfd_editor_bg": "rgba(5, 7, 10, 245)",
            "vfd_editor_border": "#6d755f",
            "vfd_editor_text": "#8dff45",
            "vfd_editor_selection_bg": "#2954b8",
            "vfd_editor_selection_fg": "#eef4e8",
            "wave_bg_top": "#040507",
            "wave_bg_bottom": "#000000",
            "wave_grid": (84, 112, 72, 84),
            "wave_center": (124, 168, 104, 120),
            "wave_fill_top": (98, 182, 55, 46),
            "wave_fill_mid": (76, 138, 42, 18),
            "wave_fill_bottom": (98, 182, 55, 46),
            "wave_glow": (141, 255, 69, 70),
            "wave_line": (167, 255, 112, 238),
            "wave_border": (110, 120, 96, 130),
        },
    },
}

SKIN_NAMES = list(SKIN_DEFINITIONS.keys())
ACTIVE_SKIN_NAME = DEFAULT_SKIN_NAME
ALLOWED_AUDIO_RATES = (48000, 44100, 22050)
ALLOWED_AUDIO_BLOCK_SIZES = tuple(range(256, 8193, 256))
DEFAULT_RUNTIME_SETTINGS = {
    "device_selection": "auto",
    "gain_mode": "auto",
    "gain_db": 20.0,
    "deemphasis_us": 75,
    "stereo_enabled": True,
    "rds_enabled": True,
    "bandwidth_mode": "wide",
    "audio_output_device": None,
    "audio_output_rate": 48000,
    "audio_blocksize": 1024,
    "show_spectrum": False,
}

HARDWARE_AUDIO_BLOCKSIZE = DEFAULT_RUNTIME_SETTINGS["audio_blocksize"]
AUDIO_RING_BUFFER_SECONDS = 1.35
AUDIO_TARGET_FILL_SECONDS = 0.38
AUDIO_PRIME_FILL_SECONDS = 0.28
AUDIO_RESUME_FILL_SECONDS = 0.12
AUDIO_LOW_WATER_SECONDS = 0.08
AUDIO_REFILL_EMPTY_CALLBACKS = 2
SDR_SAMPLE_RATE_ESTIMATE_ALPHA = 0.18
AUDIO_OUTPUT_RATE_ESTIMATE_WINDOW = 0.60
AUDIO_OUTPUT_RATE_ESTIMATE_ALPHA = 0.10
AUDIO_OUTPUT_RATE_ESTIMATE_MAX_DEVIATION = 0.02
AUDIO_INPUT_RATE_ESTIMATE_WINDOW = 0.45
AUDIO_INPUT_RATE_ESTIMATE_ALPHA = 0.10
AUDIO_INPUT_RATE_ESTIMATE_MAX_DEVIATION = 0.015
AUDIO_CLOCK_CORRECTION_GAIN = 0.003
AUDIO_CLOCK_CORRECTION_INTEGRAL_GAIN = 0.002
AUDIO_CLOCK_CORRECTION_MAX_FRAMES = 6
AUDIO_CLOCK_CORRECTION_DEADBAND_SECONDS = 0.03
AUDIO_SIGNAL_METRICS_INTERVAL_SCAN = 0.05
AUDIO_SIGNAL_METRICS_INTERVAL = 0.12
AUDIO_SIGNAL_METRICS_INTERVAL_LOW = 0.24
AUDIO_QUEUE_PRESSURE_THRESHOLD = 32
SDR_SYNC_DEVICE_READ_SAMPLES = 32768
SCAN_STEP_MHZ = 0.1
SCAN_SETTLE_SECONDS = 0.42
SCAN_CONFIRM_STEPS = 2
SCAN_CONFIRM_MARGIN = 0.02
SCAN_REQUIRED_BASE = 0.22
SCAN_REQUIRED_MAX = 0.48
SCAN_REQUIRED_SQUELCH_SCALE = 420.0
SCAN_RELEASE_MARGIN = 0.10
SCAN_RELEASE_FLOOR = 0.18
STATION_INDICATOR_THRESHOLD = 0.18
STATION_INDICATOR_RELEASE = 0.12
STEREO_INDICATOR_THRESHOLD = 0.08
STEREO_INDICATOR_RELEASE = 0.05
STEREO_PILOT_ANALYSIS_SAMPLES = 4096
STEREO_PILOT_RATIO_FLOOR = 0.018
STEREO_PILOT_RATIO_SPAN = 0.050


def _color_from_value(value) -> QColor:
    if isinstance(value, QColor):
        return QColor(value)
    if isinstance(value, str):
        return QColor(value)
    if isinstance(value, tuple):
        return QColor(*value)
    raise TypeError(f"Unsupported color value: {value!r}")


def normalize_skin_name(skin_name: str) -> str:
    return skin_name if skin_name in SKIN_DEFINITIONS else DEFAULT_SKIN_NAME


def skin_definition(skin_name: Optional[str] = None) -> Dict[str, Dict[str, object]]:
    return SKIN_DEFINITIONS[normalize_skin_name(skin_name or ACTIVE_SKIN_NAME)]


def skin_value(key: str, skin_name: Optional[str] = None):
    definition = skin_definition(skin_name)
    return definition["style"].get(key, DEFAULT_SKIN_STYLE[key])


def skin_color(key: str, skin_name: Optional[str] = None) -> QColor:
    return _color_from_value(skin_value(key, skin_name))


def is_winamp_classic_skin(skin_name: Optional[str] = None) -> bool:
    return normalize_skin_name(skin_name or ACTIVE_SKIN_NAME) == "Winamp Classic"


def draw_bevel_frame(painter: QPainter, rect: QRectF, light, dark, inset: float = 0.0):
    frame = rect.adjusted(inset, inset, -inset, -inset)
    light_color = _color_from_value(light)
    dark_color = _color_from_value(dark)
    painter.setPen(QPen(light_color, 1))
    painter.drawLine(frame.topLeft(), frame.topRight())
    painter.drawLine(frame.topLeft(), frame.bottomLeft())
    painter.setPen(QPen(dark_color, 1))
    painter.drawLine(frame.bottomLeft(), frame.bottomRight())
    painter.drawLine(frame.topRight(), frame.bottomRight())


def apply_palette_for_skin(skin_name: str):
    definition = skin_definition(skin_name)
    overrides = definition["palette"]
    for field in PALETTE_COLOR_FIELDS:
        source = _color_from_value(overrides.get(field, PALETTE_DEFAULTS[field]))
        target = getattr(Palette, field)
        target.setRed(source.red())
        target.setGreen(source.green())
        target.setBlue(source.blue())
        target.setAlpha(source.alpha())


def set_active_skin(skin_name: str) -> str:
    global ACTIVE_SKIN_NAME
    ACTIVE_SKIN_NAME = normalize_skin_name(skin_name)
    apply_palette_for_skin(ACTIVE_SKIN_NAME)
    return ACTIVE_SKIN_NAME


def load_app_settings() -> Dict[str, object]:
    if not os.path.exists(APP_SETTINGS_PATH):
        return {}
    try:
        with open(APP_SETTINGS_PATH, 'r', encoding='utf-8') as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_app_settings(settings: Dict[str, object]):
    try:
        with open(APP_SETTINGS_PATH, 'w', encoding='utf-8') as handle:
            json.dump(settings, handle, indent=2, sort_keys=True)
    except Exception:
        pass


def normalize_audio_rate(value) -> int:
    try:
        rate = int(value)
    except (TypeError, ValueError):
        return DEFAULT_RUNTIME_SETTINGS["audio_output_rate"]
    return rate if rate in ALLOWED_AUDIO_RATES else DEFAULT_RUNTIME_SETTINGS["audio_output_rate"]


def normalize_audio_blocksize(value) -> int:
    try:
        blocksize = int(value)
    except (TypeError, ValueError):
        return DEFAULT_RUNTIME_SETTINGS["audio_blocksize"]
    if blocksize < ALLOWED_AUDIO_BLOCK_SIZES[0]:
        return ALLOWED_AUDIO_BLOCK_SIZES[0]
    if blocksize > ALLOWED_AUDIO_BLOCK_SIZES[-1]:
        return ALLOWED_AUDIO_BLOCK_SIZES[-1]
    return int(round(blocksize / 256.0)) * 256


def normalize_device_selection(value):
    if value == "simulated":
        return "simulated"
    if value == "auto":
        return "auto"
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return "auto"


def normalize_output_device(value):
    if value in (None, "", "default"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def normalize_gain_mode(value) -> str:
    lowered = str(value or "").strip().lower()
    return "manual" if lowered in {"manual", "off", "software", "combined"} else "auto"


def normalize_bandwidth_mode(value) -> str:
    return "narrow" if str(value or "").strip().lower() == "narrow" else "wide"


def normalize_deemphasis_us(value) -> int:
    try:
        deemphasis = int(value)
    except (TypeError, ValueError):
        return DEFAULT_RUNTIME_SETTINGS["deemphasis_us"]
    return 50 if deemphasis == 50 else 75


def normalize_runtime_settings(settings: Optional[Dict[str, object]]) -> Dict[str, object]:
    merged = DEFAULT_RUNTIME_SETTINGS.copy()
    if isinstance(settings, dict):
        merged.update(settings)

    try:
        gain_db = float(merged.get("gain_db", DEFAULT_RUNTIME_SETTINGS["gain_db"]))
    except (TypeError, ValueError):
        gain_db = float(DEFAULT_RUNTIME_SETTINGS["gain_db"])

    return {
        "device_selection": normalize_device_selection(merged.get("device_selection")),
        "gain_mode": normalize_gain_mode(merged.get("gain_mode")),
        "gain_db": max(0.0, min(50.0, gain_db)),
        "deemphasis_us": normalize_deemphasis_us(merged.get("deemphasis_us")),
        "stereo_enabled": normalize_bool(merged.get("stereo_enabled"), DEFAULT_RUNTIME_SETTINGS["stereo_enabled"]),
        "rds_enabled": normalize_bool(merged.get("rds_enabled"), DEFAULT_RUNTIME_SETTINGS["rds_enabled"]),
        "bandwidth_mode": normalize_bandwidth_mode(merged.get("bandwidth_mode")),
        "audio_output_device": normalize_output_device(merged.get("audio_output_device")),
        "audio_output_rate": normalize_audio_rate(merged.get("audio_output_rate")),
        "audio_blocksize": normalize_audio_blocksize(merged.get("audio_blocksize")),
        "show_spectrum": normalize_bool(merged.get("show_spectrum"), DEFAULT_RUNTIME_SETTINGS["show_spectrum"]),
    }


def list_audio_output_choices() -> List[Tuple[str, Optional[int]]]:
    choices: List[Tuple[str, Optional[int]]] = [("Default output", None)]
    try:
        import sounddevice as sd

        hostapis = sd.query_hostapis()
        for index, device in enumerate(sd.query_devices()):
            if int(device.get("max_output_channels", 0)) <= 0:
                continue
            host_name = ""
            host_index = int(device.get("hostapi", -1))
            if 0 <= host_index < len(hostapis):
                host_name = str(hostapis[host_index].get("name", "")).strip()
            label = str(device.get("name", f"Output {index}")).strip() or f"Output {index}"
            if host_name:
                label = f"{label} [{host_name}]"
            choices.append((label, index))
    except Exception:
        pass
    return choices


def list_rtl_sdr_device_indices() -> List[int]:
    try:
        from rtlsdr import RtlSdr

        get_count = getattr(RtlSdr, "get_device_count", None)
        if callable(get_count):
            count = int(get_count() or 0)
            if count > 0:
                return list(range(count))

        get_serials = getattr(RtlSdr, "get_device_serial_addresses", None)
        if callable(get_serials):
            serials = list(get_serials() or [])
            if serials:
                return list(range(len(serials)))
    except Exception:
        pass

    return [0, 1]


def list_rtl_sdr_device_choices() -> List[Tuple[str, object]]:
    choices: List[Tuple[str, object]] = [("RTL-SDR (auto)", "auto")]
    try:
        from rtlsdr import RtlSdr

        serials = []
        get_serials = getattr(RtlSdr, "get_device_serial_addresses", None)
        if callable(get_serials):
            serials = list(get_serials() or [])

        if serials:
            for index, serial in enumerate(serials):
                suffix = f" ({serial})" if serial else ""
                choices.append((f"RTL-SDR #{index}{suffix}", index))
        else:
            for index in list_rtl_sdr_device_indices():
                choices.append((f"RTL-SDR #{index}", index))
    except Exception:
        for index in list_rtl_sdr_device_indices():
            choices.append((f"RTL-SDR #{index}", index))

    choices.append(("Simulated", "simulated"))
    return choices


RTL_SDR_TUNER_LABELS = {
    1: "E4000",
    2: "FC0012",
    3: "FC0013",
    4: "FC2580",
    5: "R820T",
    6: "R828D",
}


def describe_rtl_sdr_device(device_index: int, device=None) -> str:
    label = f"RTL-SDR #{int(device_index)}"

    try:
        import ctypes
        from rtlsdr import librtlsdr

        get_name = getattr(librtlsdr, "rtlsdr_get_device_name", None)
        if get_name is not None:
            get_name.restype = ctypes.c_char_p
            raw_name = get_name(int(device_index))
            if raw_name:
                decoded_name = raw_name.decode(errors='ignore').strip()
                if decoded_name.lower().startswith("generic "):
                    decoded_name = decoded_name[8:]
                if decoded_name:
                    label = decoded_name
    except Exception:
        pass

    if device is not None:
        try:
            get_tuner_type = getattr(device, "get_tuner_type", None)
            tuner_type = int(get_tuner_type()) if callable(get_tuner_type) else -1
            tuner_label = RTL_SDR_TUNER_LABELS.get(tuner_type, "")
            if tuner_label and tuner_label.lower() not in label.lower():
                label = f"{label} / {tuner_label}"
        except Exception:
            pass

    return label


set_active_skin(DEFAULT_SKIN_NAME)


# ─── Helpers ─────────────────────────────────────────────────
def glow_shadow(color: QColor, radius: int = 20, offset: int = 0):
    eff = QGraphicsDropShadowEffect()
    eff.setColor(color)
    eff.setBlurRadius(radius)
    eff.setOffset(offset, offset)
    return eff


def resource_path(*parts: str) -> str:
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, *parts)


def app_icon_file() -> str:
    return resource_path(*APP_ICON_PATH)


def clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, value))


def load_app_icon() -> QIcon:
    icon_file = app_icon_file()
    if not os.path.exists(icon_file):
        return QIcon()
    icon = QIcon(icon_file)
    return icon if not icon.isNull() else QIcon()


def apply_windows_taskbar_icon(hwnd: int, icon_file: str) -> List[int]:
    if sys.platform != 'win32' or not hwnd or not os.path.exists(icon_file):
        return []

    try:
        import ctypes

        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x0010
        LR_DEFAULTSIZE = 0x0040
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1
        GCLP_HICON = -14
        GCLP_HICONSM = -34

        user32 = ctypes.windll.user32

        load_image = user32.LoadImageW
        load_image.restype = ctypes.c_void_p
        load_image.argtypes = [
            ctypes.c_void_p,
            ctypes.c_wchar_p,
            ctypes.c_uint,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]

        send_message = user32.SendMessageW
        send_message.restype = ctypes.c_void_p
        send_message.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_size_t,
            ctypes.c_size_t,
        ]

        set_class_icon = getattr(user32, "SetClassLongPtrW", None)
        if set_class_icon is None:
            set_class_icon = user32.SetClassLongW
        set_class_icon.restype = ctypes.c_size_t
        set_class_icon.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_size_t,
        ]

        handles: List[int] = []
        for icon_kind, size, class_index in (
            (ICON_BIG, 256, GCLP_HICON),
            (ICON_SMALL, 32, GCLP_HICONSM),
        ):
            handle = load_image(None, icon_file, IMAGE_ICON, size, size, LR_LOADFROMFILE | LR_DEFAULTSIZE)
            if not handle:
                continue
            icon_handle = int(handle)
            handles.append(icon_handle)
            send_message(hwnd, WM_SETICON, icon_kind, icon_handle)
            set_class_icon(hwnd, class_index, icon_handle)
        return handles
    except Exception:
        return []


def destroy_windows_icon_handles(handles: List[int]):
    try:
        import ctypes

        destroy_icon = ctypes.windll.user32.DestroyIcon
        destroy_icon.argtypes = [ctypes.c_void_p]
        destroy_icon.restype = ctypes.c_bool
    except Exception:
        return

    for handle in handles or []:
        try:
            destroy_icon(handle)
        except Exception:
            pass


def open_rtl_sdr_device(device_index: int, sample_rate: float, center_freq: float, gain):
    sdr = None
    try:
        from rtlsdr import RtlSdr

        sdr = RtlSdr(device_index=device_index)
        sdr.sample_rate = sample_rate
        sdr.center_freq = center_freq
        sdr.gain = "auto" if gain in (None, "auto") else gain
        return sdr, ""
    except ImportError as error:
        return None, str(error)
    except Exception as error:
        if sdr is not None:
            try:
                sdr.close()
            except Exception:
                pass
        return None, str(error)


def clamp_frequency(freq_mhz: float) -> float:
    return round(max(87.5, min(108.0, freq_mhz)), 1)


def format_station_label(freq_mhz: float) -> str:
    return f"{clamp_frequency(freq_mhz):.1f} MHz"


def format_display_radiotext(text: str) -> str:
    text = " ".join(text.split()) if text else ""
    if not text:
        return ""

    letters = sum(char.isalpha() for char in text)
    invalid = sum(
        not (char.isprintable() and (char.isalnum() or char in " .,:;!?-'&/()+"))
        for char in text
    )

    words = []
    current = []
    for char in text:
        if char.isalpha():
            current.append(char)
        elif current:
            words.append("".join(current))
            current = []
    if current:
        words.append("".join(current))

    strong_letters = sum(
        sum(letter.isalpha() for letter in word)
        for word in words
        if len(word) >= 3
    )

    if invalid != 0 or letters < max(5, len(text) // 3):
        return ""
    if strong_letters < max(5, math.ceil(letters * 0.5)):
        return ""
    return text


def readability_scale(view_scale: float) -> float:
    return max(0.92, min(1.16, 1.0 + (1.0 - view_scale) * 0.24))


def set_windows_app_id(app_id: str = WINDOWS_APP_ID):
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
#  CUSTOM WIDGETS — Stunning car-radio components
# ═══════════════════════════════════════════════════════════════

class VFDDisplay(QWidget):
    """Vacuum-fluorescent-display style frequency readout."""

    frequencySubmitted = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frequency = 87.5  # MHz
        self._rds_text = "PyRadio SDR"
        self._stereo = False
        self._mode = "FM"
        self._ui_scale = 1.0
        self._scroll_buffer = ""
        self._scroll_offset = 0
        self._scroll_hold = 0
        self.setMinimumSize(440, 140)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._marquee_timer = QTimer(self)
        self._marquee_timer.timeout.connect(self._advance_marquee)
        self._marquee_timer.start(160)

        self._freq_editor = QLineEdit(self)
        self._freq_editor.hide()
        self._freq_editor.setAlignment(Qt.AlignCenter)
        validator = QDoubleValidator(87.5, 108.0, 1, self._freq_editor)
        validator.setNotation(QDoubleValidator.StandardNotation)
        self._freq_editor.setValidator(validator)
        self._freq_editor.returnPressed.connect(self._commit_frequency_edit)
        self._freq_editor.editingFinished.connect(self._commit_frequency_edit)
        self._freq_editor.installEventFilter(self)
        self._apply_editor_style()
        self.set_rds_text(self._rds_text)

    def _font_scale(self) -> float:
        width_scale = self.width() / 440.0 if self.width() else 1.0
        height_scale = self.height() / 140.0 if self.height() else 1.0
        return max(0.82, min(1.35, min(width_scale, height_scale) * readability_scale(self._ui_scale)))

    def eventFilter(self, obj, event):
        if obj is self._freq_editor and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self._cancel_frequency_edit()
                return True
        return super().eventFilter(obj, event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and self._frequency_rect().contains(event.position().toPoint()):
            self._begin_frequency_edit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def set_frequency(self, freq_mhz: float):
        freq_mhz = clamp_frequency(float(freq_mhz))
        if abs(freq_mhz - self._frequency) < 1e-6:
            return
        self._frequency = freq_mhz
        if self._freq_editor.isVisible():
            self._freq_editor.setText(f"{self._frequency:.1f}")
        self.update()

    def set_rds_text(self, text: str):
        text = " ".join(text.split()) if text else ""
        if text == self._rds_text:
            return
        self._rds_text = text
        self._scroll_buffer = f"{text}   |   " if text else ""
        self._scroll_offset = 0
        self._scroll_hold = 6
        self.update()

    def set_stereo(self, stereo: bool):
        if stereo == self._stereo:
            return
        self._stereo = stereo
        self.update()

    def set_mode(self, mode: str):
        if mode == self._mode:
            return
        self._mode = mode
        self.update()

    def set_ui_scale(self, scale: float):
        self._ui_scale = max(0.65, min(1.8, scale))
        self._apply_editor_style()
        self._layout_frequency_editor()
        self.update()

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self._layout_frequency_editor()

    def _frequency_rect(self) -> QRect:
        w, h = self.width(), self.height()
        return QRect(int(w * 0.17), 18, int(w * 0.58), 70)

    def _layout_frequency_editor(self):
        rect = self._frequency_rect().adjusted(0, 4, 0, -4)
        self._freq_editor.setGeometry(rect)

    def _apply_editor_style(self):
        font_px = max(28, min(54, int(round(44 * self._font_scale()))))
        radius = 2 if is_winamp_classic_skin() else 8
        self._freq_editor.setFont(QFont(str(skin_value("mono_font_family")), font_px, QFont.Bold))
        self._freq_editor.setStyleSheet(
            "QLineEdit {"
            f"background: {skin_value('vfd_editor_bg')};"
            f"border: 1px solid {skin_value('vfd_editor_border')};"
            f"border-radius: {radius}px;"
            f"color: {skin_value('vfd_editor_text')};"
            "padding: 2px 8px;"
            f"selection-background-color: {skin_value('vfd_editor_selection_bg')};"
            f"selection-color: {skin_value('vfd_editor_selection_fg')};"
            "}"
        )

    def _begin_frequency_edit(self):
        self._freq_editor.setText(f"{self._frequency:.1f}")
        self._layout_frequency_editor()
        self._freq_editor.show()
        self._freq_editor.raise_()
        self._freq_editor.setFocus(Qt.MouseFocusReason)
        self._freq_editor.selectAll()
        self.update()

    def _cancel_frequency_edit(self):
        if not self._freq_editor.isVisible():
            return
        self._freq_editor.hide()
        self._freq_editor.clearFocus()
        self.update()

    def _commit_frequency_edit(self):
        if not self._freq_editor.isVisible():
            return
        raw_text = self._freq_editor.text().strip()
        self._freq_editor.hide()
        self._freq_editor.clearFocus()
        if not raw_text:
            self.update()
            return
        try:
            freq = clamp_frequency(float(raw_text))
        except ValueError:
            self.update()
            return
        self.frequencySubmitted.emit(freq)
        self.update()

    def _advance_marquee(self):
        if not self._rds_text:
            return
        metrics = self.fontMetrics()
        available_width = max(1, self.width() - 40)
        if metrics.horizontalAdvance(self._rds_text) <= available_width:
            if self._scroll_offset != 0:
                self._scroll_offset = 0
                self.update()
            return
        if self._scroll_hold > 0:
            self._scroll_hold -= 1
        else:
            loop_len = max(1, len(self._scroll_buffer))
            self._scroll_offset = (self._scroll_offset + 1) % loop_len
            if self._scroll_offset == 0:
                self._scroll_hold = 5
        self.update()

    def _display_rds_text(self, metrics, max_width: int) -> str:
        if not self._rds_text:
            return ""
        if metrics.horizontalAdvance(self._rds_text) <= max_width:
            return self._rds_text
        char_width = max(1, metrics.horizontalAdvance("M"))
        visible_chars = max(6, int(max_width / char_width))
        loop_text = self._scroll_buffer or f"{self._rds_text}   |   "
        end = self._scroll_offset + visible_chars
        if end <= len(loop_text):
            return loop_text[self._scroll_offset:end]
        return loop_text[self._scroll_offset:] + loop_text[:end - len(loop_text)]

    def paintEvent(self, event: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        font_scale = self._font_scale()
        classic = is_winamp_classic_skin()

        # ── Outer bezel ──
        bezel = QPainterPath()
        if classic:
            bezel.addRoundedRect(QRectF(0, 0, w, h), 3, 3)
        else:
            bezel.addRoundedRect(QRectF(0, 0, w, h), 14, 14)
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, skin_color("vfd_bezel_top"))
        grad.setColorAt(0.5, skin_color("vfd_bezel_mid"))
        grad.setColorAt(1.0, skin_color("vfd_bezel_bottom"))
        p.fillPath(bezel, QBrush(grad))
        if classic:
            draw_bevel_frame(
                p,
                QRectF(0.5, 0.5, w - 1, h - 1),
                QColor(skin_color("vfd_bezel_top")).lighter(124),
                QColor(skin_color("vfd_bezel_bottom")).darker(165),
            )
            draw_bevel_frame(
                p,
                QRectF(0.5, 0.5, w - 1, h - 1),
                QColor(skin_color("vfd_bezel_mid")).lighter(112),
                QColor(skin_color("vfd_bezel_mid")).darker(128),
                1.0,
            )

        # ── Inner screen area ──
        inset = 6
        screen = QPainterPath()
        if classic:
            screen.addRoundedRect(QRectF(inset, inset, w - 2*inset, h - 2*inset), 2, 2)
        else:
            screen.addRoundedRect(QRectF(inset, inset, w - 2*inset, h - 2*inset), 10, 10)
        sg = QLinearGradient(0, inset, 0, h - inset)
        sg.setColorAt(0.0, skin_color("vfd_screen_top"))
        sg.setColorAt(0.3, skin_color("vfd_screen_mid"))
        sg.setColorAt(1.0, skin_color("vfd_screen_bottom"))
        p.fillPath(screen, QBrush(sg))
        if classic:
            draw_bevel_frame(p, QRectF(inset, inset, w - 2 * inset, h - 2 * inset), "#707470", "#0a0b0d")

        # ── Scan-line effect ──
        p.setPen(Qt.NoPen)
        for y in range(inset, h - inset, 3):
            p.setBrush(QColor(0, 0, 0, 18))
            p.drawRect(inset, y, w - 2*inset, 1)

        # ── Stereo indicator ──
        if self._stereo:
            st_x = inset + 12
            badge_y = inset + 10
            p.setPen(QPen(Palette.GREEN, 1.5))
            p.setBrush(QColor(40, 220, 80, 25))
            if classic:
                p.drawRect(QRectF(st_x, badge_y, 58, 20))
            else:
                p.drawRoundedRect(QRectF(st_x, badge_y, 58, 20), 4, 4)
            p.setFont(QFont(str(skin_value("mono_font_family")), max(8, int(round(9 * font_scale))), QFont.Bold))
            p.setPen(Palette.GREEN)
            p.drawText(QRectF(st_x, badge_y, 58, 20), Qt.AlignCenter, "STEREO")

        # ── Frequency display ──
        freq_str = f"{self._frequency:6.1f}" if self._mode == "FM" else f"{self._frequency:3.0f}"
        unit = "MHz" if self._mode == "FM" else "CH"

        vfd_color = skin_color("vfd_text")
        vfd_glow = skin_color("vfd_glow")

        # Glow layer
        freq_font_size = max(36, min(58, int(round(48 * font_scale))))
        p.setFont(QFont(str(skin_value("mono_font_family")), freq_font_size, QFont.Bold))
        p.setPen(QPen(vfd_glow, 3))
        freq_rect = QRectF(self._frequency_rect())
        p.drawText(freq_rect, Qt.AlignCenter, freq_str)

        # Sharp layer
        p.setPen(vfd_color)
        p.drawText(freq_rect, Qt.AlignCenter, freq_str)

        # Unit
        p.setFont(QFont(str(skin_value("mono_font_family")), max(12, int(round(16 * font_scale))), QFont.Bold))
        p.setPen(skin_color("vfd_dim"))
        unit_rect = QRectF(w * 0.78, inset + 40, w * 0.18, 30)
        p.drawText(unit_rect, Qt.AlignLeft | Qt.AlignVCenter, unit)

        # ── RDS / station text ──
        p.setFont(QFont(str(skin_value("mono_font_family")), max(10, int(round(12 * font_scale)))))
        dim_color = skin_color("vfd_dim")
        dim_color.setAlpha(180)
        p.setPen(dim_color)
        rds_rect = QRectF(inset + 12, h - 36, w - 2*inset - 24, 24)
        display_text = self._display_rds_text(p.fontMetrics(), int(rds_rect.width()))
        p.drawText(rds_rect, Qt.AlignCenter | Qt.AlignVCenter, display_text)

        # ── Glass highlight ──
        if classic:
            p.fillRect(QRectF(inset + 2, inset + 2, w - 2 * inset - 4, max(10.0, (h - 2 * inset) * 0.12)), QColor(255, 255, 255, 10))
        else:
            glass = QPainterPath()
            glass.addRoundedRect(QRectF(inset+2, inset+2, w-2*inset-4, (h-2*inset)*0.35), 8, 8)
            gg = QLinearGradient(0, inset, 0, inset + (h-2*inset)*0.35)
            gg.setColorAt(0.0, QColor(255, 255, 255, 12))
            gg.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.fillPath(glass, QBrush(gg))

        p.end()


class RotaryKnob(QWidget):
    """Luxury metallic rotary knob with smooth interaction."""
    valueChanged = Signal(float)

    def __init__(self, label: str = "", min_val: float = 0, max_val: float = 100,
                 default: float = 50, accent: QColor = None, step: float = 0, parent=None):
        super().__init__(parent)
        self._label = label
        self._min = min_val
        self._max = max_val
        self._value = default
        self._step = step  # 0 = continuous
        self._angle = self._value_to_angle(default)
        self._accent = accent or Palette.AMBER
        self._dragging = False
        self._last_y = 0
        self._ui_scale = 1.0
        self.setFixedSize(90, 110)
        self.setCursor(Qt.PointingHandCursor)

    def set_ui_scale(self, scale: float):
        self._ui_scale = max(0.65, min(1.8, scale))
        self.update()

    def _value_to_angle(self, val: float) -> float:
        frac = (val - self._min) / max(self._max - self._min, 1e-9)
        return -135 + frac * 270

    def _angle_to_value(self, angle: float) -> float:
        frac = (angle + 135) / 270
        return self._min + frac * (self._max - self._min)

    @property
    def value(self):
        return self._value

    def set_value(self, val: float):
        val = max(self._min, min(self._max, val))
        if self._step > 0:
            val = round(val / self._step) * self._step
            val = round(val, 10)  # avoid floating-point residue
        if abs(val - self._value) < 1e-9:
            return
        self._value = val
        self._angle = self._value_to_angle(val)
        self.valueChanged.emit(val)
        self.update()

    def paintEvent(self, event: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = 45, 45
        r = 34

        # ── Shadow ──
        p.setPen(Qt.NoPen)
        shadow_grad = QRadialGradient(cx, cy + 4, r + 12)
        shadow_grad.setColorAt(0.0, QColor(0, 0, 0, 80))
        shadow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(shadow_grad))
        p.drawEllipse(QPointF(cx, cy + 4), r + 10, r + 10)

        # ── Arc track ──
        pen = QPen(QColor(50, 48, 60), 4, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(QRect(cx - r, cy - r, 2*r, 2*r), int((-135 - 90) * -16), int(270 * -16))

        # ── Active arc ──
        frac = (self._value - self._min) / max(self._max - self._min, 1e-9)
        sweep = frac * 270
        pen2 = QPen(self._accent, 4, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen2)
        p.drawArc(QRect(cx - r, cy - r, 2*r, 2*r), int((-135 - 90) * -16), int(sweep * -16))

        # ── Knob body ──
        kr = 24
        body_grad = QRadialGradient(cx - 5, cy - 5, kr * 1.4)
        body_grad.setColorAt(0.0, QColor(90, 85, 110))
        body_grad.setColorAt(0.4, QColor(60, 57, 75))
        body_grad.setColorAt(1.0, QColor(35, 33, 45))
        p.setPen(QPen(QColor(70, 67, 85), 1.5))
        p.setBrush(QBrush(body_grad))
        p.drawEllipse(QPointF(cx, cy), kr, kr)

        # ── Knob texture rings ──
        for i in range(3):
            ring_r = kr - 5 - i * 5
            if ring_r > 3:
                p.setPen(QPen(QColor(80, 76, 100, 40), 0.5))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(cx, cy), ring_r, ring_r)

        # ── Indicator line ──
        angle_rad = math.radians(self._angle - 90)
        ix = cx + math.cos(angle_rad) * (kr - 4)
        iy = cy + math.sin(angle_rad) * (kr - 4)
        ox = cx + math.cos(angle_rad) * (kr - 14)
        oy = cy + math.sin(angle_rad) * (kr - 14)
        p.setPen(QPen(self._accent, 3, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(ox, oy), QPointF(ix, iy))

        # ── Highlight dome ──
        hl = QRadialGradient(cx - 6, cy - 8, kr * 0.6)
        hl.setColorAt(0.0, QColor(255, 255, 255, 30))
        hl.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(hl))
        p.drawEllipse(QPointF(cx, cy), kr - 2, kr - 2)

        # ── Label ──
        p.setFont(QFont(str(skin_value("ui_font_family")), max(8, int(round(9 * readability_scale(self._ui_scale))))))
        p.setPen(Palette.TEXT_SECONDARY)
        p.drawText(QRectF(0, 90, 90, 20), Qt.AlignCenter, self._label)

        p.end()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._last_y = event.position().y()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging:
            dy = self._last_y - event.position().y()
            self._last_y = event.position().y()
            if self._step > 0:
                step = self._step
            else:
                step = (self._max - self._min) / 200
            self.set_value(self._value + dy * step)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._dragging = False

    def wheelEvent(self, event: QWheelEvent):
        if self._step > 0:
            step = self._step
        else:
            step = (self._max - self._min) / 100
        delta = event.angleDelta().y() / 120
        self.set_value(self._value + delta * step)


class SignalMeter(QWidget):
    """LED bar graph signal-strength meter."""

    def __init__(self, label: str = "SIG", parent=None):
        super().__init__(parent)
        self._level = 0.0  # 0.0 to 1.0
        self._label = label
        self._ui_scale = 1.0
        self.setFixedSize(160, 36)

    def set_ui_scale(self, scale: float):
        self._ui_scale = max(0.65, min(1.8, scale))
        self.update()

    def set_level(self, level: float):
        clamped = max(0.0, min(1.0, level))
        if abs(clamped - self._level) < 0.01:
            return
        self._level = clamped
        self.update()

    def paintEvent(self, event: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Label
        p.setFont(QFont(str(skin_value("mono_font_family")), max(7, int(round(8 * readability_scale(self._ui_scale)))), QFont.Bold))
        p.setPen(Palette.TEXT_SECONDARY)
        p.drawText(QRectF(0, 0, 36, h), Qt.AlignVCenter | Qt.AlignLeft, self._label)

        # LED bars
        bar_x = 40
        bar_w = w - bar_x
        n_bars = 16
        bar_width = (bar_w - (n_bars - 1) * 2) / n_bars
        active = int(self._level * n_bars)

        for i in range(n_bars):
            x = bar_x + i * (bar_width + 2)
            rect = QRectF(x, 8, bar_width, h - 16)

            if i < active:
                if i < n_bars * 0.6:
                    color = Palette.GREEN
                elif i < n_bars * 0.85:
                    color = Palette.AMBER
                else:
                    color = Palette.RED
                p.setPen(Qt.NoPen)
                p.setBrush(color)
                p.drawRoundedRect(rect, 1.5, 1.5)

                # Glow
                glow = QColor(color.red(), color.green(), color.blue(), 50)
                p.setBrush(glow)
                p.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), 2, 2)
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(40, 38, 50))
                p.drawRoundedRect(rect, 1.5, 1.5)

        p.end()


class StatusBarMeter(QWidget):
    """Compact LED bar graph for status-strip buffer monitoring."""

    def __init__(self, label: str = "BUF", parent=None):
        super().__init__(parent)
        self._label = label
        self._level = 0.0
        self._ui_scale = 1.0
        self.setFixedSize(132, 24)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def set_ui_scale(self, scale: float):
        self._ui_scale = max(0.65, min(1.8, scale))
        width = max(112, int(round(132 * readability_scale(self._ui_scale))))
        height = max(20, int(round(24 * readability_scale(self._ui_scale))))
        self.setFixedSize(width, height)
        self.update()

    def set_level(self, level: float):
        clamped = max(0.0, min(1.0, float(level)))
        if abs(clamped - self._level) < 0.01:
            return
        self._level = clamped
        self.update()

    def paintEvent(self, event: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        p.setFont(QFont(str(skin_value("mono_font_family")), max(7, int(round(8 * readability_scale(self._ui_scale)))), QFont.Bold))
        p.setPen(Palette.TEXT_SECONDARY)
        p.drawText(QRectF(0, 0, 30, h), Qt.AlignVCenter | Qt.AlignLeft, self._label)

        bar_x = 34
        bar_w = max(12, w - bar_x)
        n_bars = 12
        gap = 2
        bar_width = (bar_w - (n_bars - 1) * gap) / n_bars
        active = int(round(self._level * n_bars))

        for index in range(n_bars):
            x = bar_x + index * (bar_width + gap)
            rect = QRectF(x, 5, bar_width, h - 10)

            if index < active:
                if self._level >= 0.70:
                    color = Palette.GREEN
                elif self._level >= 0.35:
                    color = Palette.AMBER
                else:
                    color = Palette.RED
                p.setPen(Qt.NoPen)
                p.setBrush(color)
                p.drawRoundedRect(rect, 1.4, 1.4)
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(40, 38, 50))
                p.drawRoundedRect(rect, 1.4, 1.4)

        p.end()


class GlowIndicator(QWidget):
    """Small circular status LED with glow."""

    def __init__(self, label: str = "", color_on: QColor = Palette.GREEN,
                 color_off: QColor = None, parent=None):
        super().__init__(parent)
        self._on = False
        self._label = label
        self._color_on = color_on
        self._color_off = color_off or QColor(color_on.red()//4, color_on.green()//4, color_on.blue()//4)
        self._ui_scale = 1.0
        self.setFixedSize(60, 28)

    def set_on(self, state: bool):
        if self._on == state:
            return
        self._on = state
        self.update()

    def set_ui_scale(self, scale: float):
        self._ui_scale = max(0.65, min(1.8, scale))
        self.update()

    def paintEvent(self, event: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        color = self._color_on if self._on else self._color_off
        cx, cy, r = 8, 14, 5

        if self._on:
            glow = QRadialGradient(cx, cy, r * 3)
            glow.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), 80))
            glow.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(glow))
            p.drawEllipse(QPointF(cx, cy), r * 3, r * 3)

        p.setPen(QPen(QColor(80, 77, 90), 1))
        p.setBrush(color)
        p.drawEllipse(QPointF(cx, cy), r, r)

        if self._on:
            hl = QRadialGradient(cx - 1, cy - 2, r * 0.5)
            hl.setColorAt(0, QColor(255, 255, 255, 90))
            hl.setColorAt(1, QColor(255, 255, 255, 0))
            p.setBrush(QBrush(hl))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(cx - 1, cy - 2), r * 0.5, r * 0.5)

        p.setFont(QFont(str(skin_value("ui_font_family")), max(7, int(round(8 * readability_scale(self._ui_scale))))))
        p.setPen(Palette.TEXT_SECONDARY if self._on else Palette.TEXT_DIM)
        p.drawText(QRectF(20, 0, 40, 28), Qt.AlignVCenter | Qt.AlignLeft, self._label)
        p.end()


class AudioWaveformWidget(QWidget):
    """Real-time audio waveform oscilloscope display."""

    # Shared ring buffer written from audio callback, read from paint thread
    _RING = 2048

    def __init__(self, parent=None):
        super().__init__(parent)
        self._samples = np.zeros(self._RING, dtype=np.float32)
        self._write_pos = 0
        self._lock = threading.Lock()
        # Smoothed envelope for the filled area
        self._env = np.zeros(512, dtype=np.float32)
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def push_samples(self, chunk: np.ndarray):
        """Called from audio thread — write newest samples into ring buffer."""
        with self._lock:
            n = len(chunk)
            if n >= self._RING:
                self._samples[:] = chunk[-self._RING:]
                self._write_pos = 0
            else:
                end = self._write_pos + n
                if end <= self._RING:
                    self._samples[self._write_pos:end] = chunk
                else:
                    split = self._RING - self._write_pos
                    self._samples[self._write_pos:] = chunk[:split]
                    self._samples[:n - split] = chunk[split:]
                self._write_pos = end % self._RING

    def clear(self):
        with self._lock:
            self._samples.fill(0.0)
            self._write_pos = 0
        self.update()

    def _get_display_window(self) -> np.ndarray:
        """Return a contiguous view of the most recent 1024 samples."""
        with self._lock:
            n = 1024
            pos = self._write_pos
            if pos >= n:
                return self._samples[pos - n:pos].copy()
            else:
                return np.concatenate([self._samples[-(n - pos):], self._samples[:pos]])

    def paintEvent(self, event: QPaintEvent):
        p = QPainter(self)
        w, h = self.width(), self.height()
        mid = h / 2

        # ── Background ──
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0, skin_color("wave_bg_top"))
        bg.setColorAt(1, skin_color("wave_bg_bottom"))
        p.fillRect(0, 0, w, h, QBrush(bg))

        # ── Grid ──
        p.setPen(QPen(skin_color("wave_grid"), 0.5, Qt.DashLine))
        for i in range(1, 4):
            y = h * i / 4
            p.drawLine(QPointF(0, y), QPointF(w, y))
        for i in range(1, 9):
            x = w * i / 8
            p.drawLine(QPointF(x, 0), QPointF(x, h))

        # ── Centre line ──
        p.setPen(QPen(skin_color("wave_center"), 1))
        p.drawLine(QPointF(0, mid), QPointF(w, mid))

        samples = self._get_display_window()
        n = len(samples)

        if n > 1:
            # Keep waveform rendering lightweight enough for steady hardware playback.
            render_n = min(n, max(96, min(240, int(w * 0.35))))
            step = n / render_n
            xs = np.arange(render_n) * (w / (render_n - 1))
            idxs = (np.arange(render_n) * step).astype(int).clip(0, n - 1)
            ys = mid - samples[idxs] * (mid * 0.88)

            # ── Waveform line ──
            wave_path = QPainterPath()
            wave_path.moveTo(xs[0], ys[0])
            for i in range(1, render_n):
                wave_path.lineTo(xs[i], ys[i])

            # Sharp pass
            sharp_pen = QPen(skin_color("wave_line"), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            p.setPen(sharp_pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(wave_path)

        # ── Border ──
        p.setPen(QPen(skin_color("wave_border"), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(0, 0, w - 1, h - 1), 6, 6)

        p.end()


class PresetButton(QPushButton):
    """Sleek illuminated preset button."""

    def __init__(self, number: int, text: str = "", parent=None):
        super().__init__(parent)
        self._number = number
        self._text = text
        self._active = False
        self._ui_scale = 1.0
        self.setFixedSize(80, 50)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("background: transparent; border: none;")

    def set_active(self, active: bool):
        self._active = active
        self.update()

    def set_text(self, text: str):
        self._text = text
        self.update()

    def set_ui_scale(self, scale: float):
        self._ui_scale = max(0.65, min(1.8, scale))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        classic = is_winamp_classic_skin()
        radius = 2 if classic else 8

        # Background
        bg = QPainterPath()
        bg.addRoundedRect(QRectF(2, 2, w-4, h-4), radius, radius)

        if self._active:
            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0, skin_color("preset_active_top"))
            grad.setColorAt(1, skin_color("preset_active_bottom"))
            p.fillPath(bg, QBrush(grad))
            p.setPen(QPen(Palette.AMBER, 1.5))
        elif self.underMouse():
            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0, skin_color("preset_hover_top"))
            grad.setColorAt(1, skin_color("preset_hover_bottom"))
            p.fillPath(bg, QBrush(grad))
            p.setPen(QPen(skin_color("preset_hover_border"), 1))
        else:
            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0, skin_color("preset_bg_top"))
            grad.setColorAt(1, skin_color("preset_bg_bottom"))
            p.fillPath(bg, QBrush(grad))
            p.setPen(QPen(skin_color("preset_border"), 1))

        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(2, 2, w-4, h-4), radius, radius)
        if classic:
            if self._active:
                bevel_light = QColor(skin_color("preset_active_top")).lighter(145)
                bevel_dark = QColor(skin_color("preset_active_bottom")).darker(145)
            else:
                bevel_light = QColor(skin_color("preset_bg_top")).lighter(125)
                bevel_dark = QColor(skin_color("preset_border")).darker(145)
            draw_bevel_frame(p, QRectF(2.5, 2.5, w - 5, h - 5), bevel_light, bevel_dark)

        # Number
        font_scale = readability_scale(self._ui_scale)
        p.setFont(QFont(str(skin_value("mono_font_family")), max(9, int(round(10 * font_scale))), QFont.Bold))
        color = Palette.AMBER if self._active else skin_color("preset_number_inactive")
        p.setPen(color)
        p.drawText(QRectF(0, 4, w, 20), Qt.AlignCenter, str(self._number))

        # Label
        if self._text:
            p.setFont(QFont(str(skin_value("ui_font_family")), max(6, int(round(7 * font_scale)))))
            p.setPen(Palette.AMBER if self._active else skin_color("preset_text_inactive"))
            label = p.fontMetrics().elidedText(self._text, Qt.ElideRight, w - 10)
            p.drawText(QRectF(0, 24, w, 18), Qt.AlignCenter, label)

        p.end()

    def enterEvent(self, event):
        self.update()

    def leaveEvent(self, event):
        self.update()


class StyledButton(QPushButton):
    """Smooth styled button with hover effects."""

    def __init__(self, text: str = "", icon_text: str = "", accent: QColor = None,
                 size: QSize = QSize(48, 40), parent=None):
        super().__init__(parent)
        self._text = text
        self._icon_text = icon_text
        self._accent = accent or Palette.AMBER
        self._pressed = False
        self._ui_scale = 1.0
        self.setFixedSize(size)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("background: transparent; border: none;")

    def set_active(self, active: bool):
        self._pressed = active
        self.update()

    def set_icon_text(self, icon_text: str):
        self._icon_text = icon_text
        self._text = ""
        self.update()

    def set_text(self, text: str):
        self._text = text
        self._icon_text = ""
        self.update()

    def set_ui_scale(self, scale: float):
        self._ui_scale = max(0.65, min(1.8, scale))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        classic = is_winamp_classic_skin()
        radius = 2 if classic else 8

        bg = QPainterPath()
        bg.addRoundedRect(QRectF(1, 1, w-2, h-2), radius, radius)

        if classic:
            pressed = self._pressed or self.isDown()
            grad = QLinearGradient(0, 0, 0, h)
            button_top = QColor(skin_color("button_bg_top"))
            button_bottom = QColor(skin_color("button_bg_bottom"))
            hover_fill = QColor(skin_color("button_hover_bg"))
            if pressed:
                grad.setColorAt(0, button_bottom.darker(118))
                grad.setColorAt(1, button_top.lighter(110))
            elif self.underMouse():
                grad.setColorAt(0, hover_fill.lighter(104))
                grad.setColorAt(1, button_top.lighter(112))
            else:
                grad.setColorAt(0, button_top.lighter(108))
                grad.setColorAt(1, button_bottom)
            p.fillPath(bg, QBrush(grad))
            p.setPen(QPen(skin_color("button_border"), 1))
        elif self._pressed or self.isDown():
            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0, QColor(self._accent.red()//3, self._accent.green()//3, self._accent.blue()//3))
            grad.setColorAt(1, QColor(self._accent.red()//5, self._accent.green()//5, self._accent.blue()//5))
            p.fillPath(bg, QBrush(grad))
            p.setPen(QPen(self._accent, 1.5))
        elif self.underMouse():
            p.fillPath(bg, QBrush(skin_color("button_hover_bg")))
            p.setPen(QPen(skin_color("button_hover_border"), 1))
        else:
            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0, skin_color("button_bg_top"))
            grad.setColorAt(1, skin_color("button_bg_bottom"))
            p.fillPath(bg, QBrush(grad))
            p.setPen(QPen(skin_color("button_border"), 1))

        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(1, 1, w-2, h-2), radius, radius)
        if classic:
            pressed = self._pressed or self.isDown()
            if not pressed:
                bevel_light = QColor(skin_color("button_bg_top")).lighter(132)
                bevel_dark = QColor(skin_color("button_border")).darker(150)
            else:
                bevel_light = QColor(skin_color("button_border")).darker(118)
                bevel_dark = QColor(skin_color("button_bg_top")).lighter(120)
            draw_bevel_frame(p, QRectF(1.5, 1.5, w - 3, h - 3), bevel_light, bevel_dark)
            if self._pressed:
                accent_band = QColor(self._accent)
                accent_band.setAlpha(180)
                p.fillRect(QRectF(3, h - 5, w - 6, 2), accent_band)

        if classic:
            txt_color = QColor("#1d2027") if not self.underMouse() else QColor("#0f1217")
        else:
            txt_color = self._accent if self._pressed else (Palette.TEXT_PRIMARY if self.underMouse() else Palette.TEXT_SECONDARY)
        font_scale = readability_scale(self._ui_scale)
        text_rect = QRectF(0, 0, w, h)
        if classic and (self._pressed or self.isDown()):
            text_rect.translate(1, 1)

        if self._icon_text:
            icon_size = max(11, int(round((14 if classic else 16) * font_scale)))
            p.setFont(QFont(str(skin_value("ui_font_family")), icon_size, QFont.Bold if classic else QFont.Normal))
            p.setPen(txt_color)
            p.drawText(text_rect, Qt.AlignCenter, self._icon_text)
        elif self._text:
            p.setFont(QFont(str(skin_value("ui_font_family")), max(8, int(round(10 * font_scale))), QFont.Bold))
            p.setPen(txt_color)
            p.drawText(text_rect, Qt.AlignCenter, self._text)

        p.end()

    def enterEvent(self, event):
        self.update()

    def leaveEvent(self, event):
        self.update()


class LoadingSpinner(QWidget):
    """Simple animated loader used by the startup overlay."""

    def __init__(self, accent: QColor = None, parent=None):
        super().__init__(parent)
        self._accent = accent or Palette.AMBER
        self._angle = 0
        self.setFixedSize(68, 68)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._timer.setInterval(80)

    def start(self):
        if not self._timer.isActive():
            self._timer.start()
        self.show()

    def stop(self):
        self._timer.stop()
        self.update()

    def _advance(self):
        self._angle = (self._angle + 30) % 360
        self.update()

    def paintEvent(self, event: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(self.width() / 2, self.height() / 2)

        for index in range(12):
            p.save()
            p.rotate(self._angle - index * 30)
            alpha = 220 - index * 16
            color = QColor(self._accent)
            color.setAlpha(max(24, alpha))
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(16, -3, 16, 6), 3, 3)
            p.restore()

        p.end()


class LoadingOverlay(QFrame):
    """Blocks interaction while the backend is being prepared."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("loadingOverlay")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("""
            #loadingOverlay {
                background: rgba(6, 6, 10, 196);
            }
            #loadingPanel {
                background: qlineargradient(y1:0, y2:1,
                    stop:0 rgba(26, 24, 34, 245), stop:1 rgba(16, 16, 24, 245));
                border: 1px solid rgba(255, 170, 40, 90);
                border-radius: 18px;
            }
            QLabel#loadingTitle {
                color: #ffaa28;
                font-family: 'Segoe UI', 'Helvetica Neue', sans-serif;
                font-size: 18px;
                font-weight: bold;
            }
            QLabel#loadingDetail {
                color: #d7d1c5;
                font-family: 'Segoe UI', 'Helvetica Neue', sans-serif;
                font-size: 12px;
                line-height: 1.4em;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.addStretch()

        panel = QFrame()
        panel.setObjectName("loadingPanel")
        panel.setFixedWidth(380)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(28, 24, 28, 24)
        panel_layout.setSpacing(14)

        self.spinner = LoadingSpinner(Palette.AMBER)
        panel_layout.addWidget(self.spinner, 0, Qt.AlignHCenter)

        self.title_label = QLabel("Booting radio")
        self.title_label.setObjectName("loadingTitle")
        self.title_label.setAlignment(Qt.AlignCenter)
        panel_layout.addWidget(self.title_label)

        self.detail_label = QLabel("Checking for RTL-SDR hardware...")
        self.detail_label.setObjectName("loadingDetail")
        self.detail_label.setAlignment(Qt.AlignCenter)
        self.detail_label.setWordWrap(True)
        panel_layout.addWidget(self.detail_label)

        root.addWidget(panel, 0, Qt.AlignHCenter)
        root.addStretch()
        self.hide()

    def show_message(self, title: str, detail: str = ""):
        self.title_label.setText(title)
        self.detail_label.setText(detail)
        self.detail_label.setVisible(bool(detail))
        self.spinner.start()
        self.show()
        self.raise_()

    def hide_message(self):
        self.spinner.stop()
        self.hide()


# ═══════════════════════════════════════════════════════════════
#  SDR BACKEND — RTL-SDR device handler + DSP pipeline
# ═══════════════════════════════════════════════════════════════

class SDRBackend(QObject):
    """Manages RTL-SDR device and IQ sample reading."""
    samples_ready = Signal(np.ndarray)
    device_error = Signal(str)
    device_connected = Signal(bool)

    def __init__(self):
        super().__init__()
        self._sdr = None
        self.on_samples = None
        self._running = False
        self._stream_requested = False
        self._thread = None
        self._control_lock = threading.RLock()
        self._sample_rate = 240000
        self._center_freq = 100e6
        self._gain = 'auto'
        self._device_index = 0
        self._device_label = ""
        self._read_size = 4096
        self._flush_reads_remaining = 0
        self._measured_sample_rate = float(self._sample_rate)
        self._last_read_completed_at = 0.0
        self._stream_token = 0
        self._last_stream_start_at = 0.0
        self._last_sample_at = 0.0

    def set_read_size(self, read_size: int):
        normalized = max(4096, int(read_size))
        normalized = ((normalized + 4095) // 4096) * 4096
        with self._control_lock:
            self._read_size = normalized

    def _schedule_stream_flush_locked(self):
        device_read_size = self._effective_device_read_size_locked()
        flush_samples = max(device_read_size * 2, int(self._sample_rate * 0.12))
        flush_reads = max(2, int(math.ceil(flush_samples / max(device_read_size, 1))))
        self._flush_reads_remaining = flush_reads

    @property
    def connected(self):
        return self._is_device_open()

    def estimated_sample_rate(self) -> float:
        with self._control_lock:
            return float(self._measured_sample_rate)

    def diagnostics(self) -> Dict[str, object]:
        now = time.monotonic()
        with self._control_lock:
            thread = self._thread
            last_sample_at = float(self._last_sample_at)
            last_read_completed_at = float(self._last_read_completed_at)
            return {
                "running": bool(self._running),
                "stream_requested": bool(self._stream_requested),
                "thread_alive": bool(thread is not None and thread.is_alive()),
                "sample_rate": int(self._sample_rate),
                "center_freq_hz": float(self._center_freq),
                "read_size": int(self._read_size),
                "device_read_size": int(self._effective_device_read_size_locked()),
                "flush_reads_remaining": int(self._flush_reads_remaining),
                "measured_sample_rate": float(self._measured_sample_rate),
                "device_index": int(self._device_index),
                "device_label": str(self._device_label),
                "device_open": bool(self._is_device_open()),
                "last_sample_age": (now - last_sample_at) if last_sample_at > 0.0 else None,
                "last_read_age": (now - last_read_completed_at) if last_read_completed_at > 0.0 else None,
            }

    def sample_stalled(self, timeout: float = 1.5, now: Optional[float] = None) -> bool:
        check_at = time.monotonic() if now is None else float(now)
        with self._control_lock:
            if not self._stream_requested or self._stream_token == 0:
                return False
            last_activity = self._last_sample_at or self._last_stream_start_at
            thread = self._thread
            running = self._running
        if thread is not None and not thread.is_alive():
            return True
        if not running:
            return True
        return bool(last_activity) and (check_at - last_activity) > timeout

    def _is_device_open(self) -> bool:
        return self._sdr is not None and bool(getattr(self._sdr, "device_opened", True))

    def adopt_device(self, device, index: Optional[int] = None):
        with self._control_lock:
            stale = self._sdr
            self._sdr = device
            if index is not None:
                self._device_index = index
            self._device_label = describe_rtl_sdr_device(self._device_index, device) if device is not None else ""
            if stale is not None and stale is not device:
                try:
                    stale.close()
                except Exception:
                    pass

    def _open_device_locked(self) -> bool:
        device, error = open_rtl_sdr_device(
            self._device_index,
            self._sample_rate,
            self._center_freq,
            self._gain,
        )
        if device is None:
            self.device_error.emit(error)
            self.adopt_device(None, self._device_index)
            self.device_connected.emit(False)
            return False

        self.adopt_device(device, self._device_index)
        self.device_connected.emit(True)
        return True

    def _ensure_device_open_locked(self) -> bool:
        if self._is_device_open():
            return True
        return self._open_device_locked()

    def connect_device(self, index: int = 0):
        """Try to open an RTL-SDR device."""
        with self._control_lock:
            self._device_index = index
            return self._open_device_locked()

    def disconnect_device(self):
        self.stop_streaming(wait=True)
        self.adopt_device(None)
        self.device_connected.emit(False)

    def set_frequency(self, freq_hz: float):
        with self._control_lock:
            self._center_freq = freq_hz
            if self._sdr is None:
                return
            if not self._ensure_device_open_locked():
                return
            try:
                self._sdr.center_freq = freq_hz
            except Exception as e:
                self.device_error.emit(str(e))

    def retune(self, freq_hz: float, flush_stream: bool = False):
        with self._control_lock:
            self._center_freq = freq_hz
            if self._sdr is None:
                return
            if not self._ensure_device_open_locked():
                return
            try:
                self._sdr.center_freq = freq_hz
                if flush_stream and self._stream_requested and self._running:
                    self._schedule_stream_flush_locked()
            except Exception as e:
                self.device_error.emit(str(e))

    def set_gain(self, gain):
        with self._control_lock:
            self._gain = gain
            if self._sdr:
                try:
                    self._sdr.gain = gain
                except Exception:
                    pass

    def start_streaming(self):
        with self._control_lock:
            self._stream_requested = True
            if not self._ensure_device_open_locked():
                self._stream_requested = False
                return
            if self._running:
                return
            self._flush_reads_remaining = 0
            self._measured_sample_rate = float(self._sample_rate)
            self._last_read_completed_at = 0.0
            self._stream_token += 1
            token = self._stream_token
            started_at = time.monotonic()
            self._last_stream_start_at = started_at
            self._last_sample_at = started_at
            self._thread = threading.Thread(target=self._read_loop, args=(token,), daemon=True)
            self._thread.start()

    def stop_streaming(self, wait: bool = False, timeout: float = 1.0):
        with self._control_lock:
            self._stream_requested = False
            self._running = False
            self._flush_reads_remaining = 0
            self._last_read_completed_at = 0.0
            self._stream_token += 1
            thread = self._thread
        if wait and thread and thread.is_alive() and threading.current_thread() is not thread:
            thread.join(timeout=timeout)
        if thread and not thread.is_alive() and self._thread is thread:
            self._thread = None

    def restart_stream(self, reopen_device: bool = True, wait: bool = False) -> bool:
        self.stop_streaming(wait=wait, timeout=0.35 if not wait else 1.0)

        stale = None
        if reopen_device:
            with self._control_lock:
                stale = self._sdr
                self._sdr = None
                self._running = False
            if stale is not None:
                try:
                    stale.close()
                except Exception:
                    pass

        self.start_streaming()
        with self._control_lock:
            return self._stream_requested and self._thread is not None

    def _effective_device_read_size_locked(self, emit_chunk_size: Optional[int] = None) -> int:
        chunk_size = self._read_size if emit_chunk_size is None else max(4096, int(emit_chunk_size))
        device_read_size = max(chunk_size, SDR_SYNC_DEVICE_READ_SAMPLES)
        return ((device_read_size + chunk_size - 1) // chunk_size) * chunk_size

    def _read_samples_sync(self, sdr, num_samples: int) -> np.ndarray:
        raw = sdr.read_bytes(int(num_samples) * 2)
        data = np.ctypeslib.as_array(raw)
        floats = data.astype(np.float32)
        floats -= np.float32(127.5)
        floats *= np.float32(1.0 / 127.5)
        return floats.view(np.complex64)

    def _read_loop(self, stream_token: int):
        """Continuously read IQ samples using blocking librtlsdr sync reads."""
        self._running = True
        try:
            while True:
                with self._control_lock:
                    if stream_token != self._stream_token or not self._stream_requested:
                        break
                    sdr = self._sdr
                    read_size = self._read_size
                    device_read_size = self._effective_device_read_size_locked(read_size)
                    if not sdr or not self._is_device_open():
                        break

                try:
                    samples = self._read_samples_sync(sdr, device_read_size)
                except Exception as error:
                    with self._control_lock:
                        still_active = stream_token == self._stream_token and self._stream_requested
                    if still_active:
                        self.device_connected.emit(False)
                        self.device_error.emit(str(error))
                    break

                sample_now = time.monotonic()
                with self._control_lock:
                    if stream_token != self._stream_token or not self._stream_requested:
                        break
                    last_read_completed_at = self._last_read_completed_at
                    if last_read_completed_at > 0.0 and len(samples) > 0:
                        elapsed = sample_now - last_read_completed_at
                        if 0.001 <= elapsed <= 0.5:
                            instant_rate = len(samples) / elapsed
                            alpha = SDR_SAMPLE_RATE_ESTIMATE_ALPHA
                            self._measured_sample_rate = (
                                self._measured_sample_rate * (1.0 - alpha)
                                + instant_rate * alpha
                            )
                    self._last_read_completed_at = sample_now
                    self._last_sample_at = sample_now
                    flush_reads_remaining = self._flush_reads_remaining
                    if flush_reads_remaining > 0:
                        self._flush_reads_remaining = flush_reads_remaining - 1

                if not self._stream_requested:
                    break

                if flush_reads_remaining > 0:
                    continue

                if len(samples) <= read_size:
                    self._handle_async_samples(samples, stream_token)
                    continue

                for start in range(0, len(samples), read_size):
                    self._handle_async_samples(samples[start:start + read_size], stream_token)
        finally:
            with self._control_lock:
                if stream_token == self._stream_token:
                    self._running = False
                    if self._thread is threading.current_thread():
                        self._thread = None

    def _handle_async_samples(self, samples, context=None):
        with self._control_lock:
            active = self._running and (context is None or context == self._stream_token)
        if active and len(samples) > 0:
            sample_block = np.array(samples, dtype=np.complex64, copy=True)
            callback = self.on_samples
            if callable(callback):
                try:
                    callback(sample_block)
                    return
                except Exception as error:
                    self.device_error.emit(str(error))
            self.samples_ready.emit(sample_block)


class StreamingPolyphaseResampler:
    """Chunk-safe rational resampler that preserves phase and filter state."""

    def __init__(self, input_rate: int, output_rate: int):
        input_rate = max(int(input_rate), 1)
        output_rate = max(int(output_rate), 1)
        rate_gcd = math.gcd(input_rate, output_rate)
        self._up = output_rate // rate_gcd
        self._down = input_rate // rate_gcd
        max_rate = max(self._up, self._down)
        num_taps = 10 * max_rate + 1
        self._taps = firwin(num_taps, 1.0 / max_rate, window=("kaiser", 5.0)).astype(np.float64) * self._up
        self._history_size = int(math.ceil((len(self._taps) - 1) / self._up))
        self._history = np.zeros(self._history_size, dtype=np.float64)
        self.reset()

    def reset(self):
        self._history_count = 0
        self._total_input = 0
        self._total_output = 0

    def process(self, samples: np.ndarray) -> np.ndarray:
        data = np.asarray(samples, dtype=np.float64)
        if data.size == 0:
            return np.array([], dtype=np.float64)

        if self._history_count:
            history = self._history[-self._history_count:]
            working = np.concatenate((history, data))
        else:
            working = data

        local_input_start = self._total_input - self._history_count
        phase = (-local_input_start * self._up) % self._down
        upsampled = upfirdn(self._taps, working, up=self._up, down=1)
        decimated = upsampled[phase::self._down]

        local_output_start = math.ceil((local_input_start * self._up) / self._down)
        new_total_input = self._total_input + data.size
        new_total_output = math.ceil((new_total_input * self._up) / self._down)
        emit_start = self._total_output - local_output_start
        emit_stop = new_total_output - local_output_start
        output = decimated[emit_start:emit_stop]

        keep = min(self._history_size, working.size)
        if keep > 0:
            self._history[:keep] = working[-keep:]
        self._history_count = keep
        self._total_input = new_total_input
        self._total_output = new_total_output
        return output


class FMDemodulator:
    """FM demodulation pipeline: IQ → audio."""

    def __init__(self, sample_rate: float = 2.4e6, audio_rate: float = 48000,
                 deemph_tau: float = 75e-6, audio_cutoff: float = 15000.0):
        self._sample_rate = sample_rate
        self._audio_rate = int(audio_rate)
        self._if_rate = 240000  # Intermediate rate after first decimation
        self._dec1 = int(sample_rate / self._if_rate)
        self._deemph_tau = deemph_tau
        self._audio_cutoff = min(float(audio_cutoff), self._if_rate * 0.48)

        # FM demod state
        self._prev_sample = 0 + 0j

        # Filters — use lfilter_zi for proper steady-state initialization
        self._lpf1 = firwin(96, self._if_rate * 0.45, fs=sample_rate, window=("kaiser", 7.5))
        self._lpf2 = firwin(96, self._audio_cutoff, fs=self._if_rate, window=("kaiser", 8.0))
        self._lpf1_zi_template = lfilter_zi(self._lpf1, 1.0).astype(np.complex128)
        self._lpf2_zi_template = lfilter_zi(self._lpf2, 1.0)
        self._lpf1_zi = self._lpf1_zi_template.copy()
        self._lpf2_zi = self._lpf2_zi_template.copy()

        # De-emphasis IIR
        dt = 1.0 / float(self._audio_rate)
        alpha = dt / (self._deemph_tau + dt)
        self._deemph_b = np.array([alpha])
        self._deemph_a = np.array([1.0, -(1.0 - alpha)])
        self._deemph_zi = np.zeros(max(len(self._deemph_b), len(self._deemph_a)) - 1)
        self._dc_block_b = np.array([1.0, -1.0])
        self._dc_block_a = np.array([1.0, -0.995])
        self._dc_block_zi = np.zeros(1, dtype=np.float64)
        self._audio_resampler = StreamingPolyphaseResampler(int(self._if_rate), self._audio_rate)

    def reset(self):
        self._prev_sample = 0 + 0j
        self._lpf1_zi = self._lpf1_zi_template.copy()
        self._lpf2_zi = self._lpf2_zi_template.copy()
        self._deemph_zi = np.zeros_like(self._deemph_zi)
        self._dc_block_zi = np.zeros_like(self._dc_block_zi)
        self._audio_resampler.reset()

    def demodulate(self, iq_samples: np.ndarray) -> Tuple[np.ndarray, np.ndarray, float]:
        """Demodulate IQ samples to audio. Returns (audio, mpx_at_if_rate, rms_level)."""
        if len(iq_samples) < self._dec1 * 2:
            return np.array([], dtype=np.float32), np.array([]), 0.0

        # Decimate to IF rate
        filtered, self._lpf1_zi = lfilter(self._lpf1, 1.0, iq_samples, zi=self._lpf1_zi)
        decimated = filtered[::self._dec1]

        # FM discriminator (polar discriminator)
        product = np.empty_like(decimated)
        product[0] = decimated[0] * np.conj(self._prev_sample)
        product[1:] = decimated[1:] * np.conj(decimated[:-1])
        self._prev_sample = decimated[-1]
        fm_demod = np.angle(product)

        # Keep the full-bandwidth MPX signal for RDS extraction
        mpx_signal = fm_demod

        # Low pass filter for audio
        try:
            audio_filtered, self._lpf2_zi = lfilter(self._lpf2, 1.0, fm_demod, zi=self._lpf2_zi)
        except Exception:
            self._lpf2_zi = lfilter_zi(self._lpf2, 1.0)
            audio_filtered, self._lpf2_zi = lfilter(self._lpf2, 1.0, fm_demod, zi=self._lpf2_zi)

        # Preserve resampler state across chunk boundaries to avoid audible clicks.
        audio = self._audio_resampler.process(audio_filtered)

        # De-emphasis filter
        audio, self._deemph_zi = lfilter(
            self._deemph_b, self._deemph_a, audio, zi=self._deemph_zi
        )

        # Remove low-frequency bias before the final output stage.
        audio, self._dc_block_zi = lfilter(
            self._dc_block_b, self._dc_block_a, audio, zi=self._dc_block_zi
        )

        # Keep some extra headroom before the final safety limiter so hot stations
        # do not spend large stretches pinned against the clip ceiling.
        audio *= 0.70
        limiter_threshold = 0.88
        abs_audio = np.abs(audio)
        over_mask = abs_audio > limiter_threshold
        if np.any(over_mask):
            overshoot = abs_audio[over_mask] - limiter_threshold
            limited = limiter_threshold + np.tanh(overshoot / max(1.0 - limiter_threshold, 1e-6)) * (1.0 - limiter_threshold)
            audio = audio.copy()
            audio[over_mask] = np.sign(audio[over_mask]) * limited

        audio = np.clip(audio, -0.98, 0.98)

        rms = float(np.sqrt(np.mean(audio ** 2))) if len(audio) > 0 else 0.0
        return audio.astype(np.float32), mpx_signal.astype(np.float32), rms


class RDSDecoder:
    """Asynchronous RDS/RBDS decoder fed by MPX snapshots.

    The real-time audio path only appends MPX samples to a ring buffer. A background
    decoder thread periodically processes a recent snapshot using a more robust RDS
    chain based on the PySDR/gr-rds reference flow: shift -> filter -> decimate ->
    resample -> Mueller and Muller clock recovery -> Costas loop -> CRC block sync.
    """

    _SYNDROMES = (383, 14, 303, 663, 748)
    _OFFSET_POSITIONS = (0, 1, 2, 3, 2)
    _OFFSET_WORDS = (252, 408, 360, 436, 848)

    def __init__(self, if_rate: float = 240000):
        self._if_rate = int(if_rate)
        self._decode_interval = 0.90
        self._snapshot_seconds = 1.75
        self._buffer_seconds = 3.5
        self._snapshot_samples = int(self._if_rate * self._snapshot_seconds)
        self._ring_size = int(self._if_rate * self._buffer_seconds)
        self._ring = np.zeros(self._ring_size, dtype=np.float32)
        self._write_pos = 0
        self._sample_count = 0
        self._lock = threading.Lock()
        self._wake_event = threading.Event()
        self._stop_event = threading.Event()
        self._lpf = firwin(numtaps=161, cutoff=3000, fs=self._if_rate)
        self._last_decode_at = 0.0
        self._station_vote_threshold = 2
        self._radio_vote_threshold = 2
        self._generation = 0

        self.pi_code = ""
        self.station_name = ""
        self.radio_text = ""
        self._station_buf = list("        ")
        self._radio_text_buf = [' '] * 64
        self._last_pi_code = ""
        self._radio_text_ab_flag: Optional[int] = None
        self._station_votes = [dict() for _ in range(8)]
        self._radio_text_votes = [dict() for _ in range(64)]

        self._thread = threading.Thread(target=self._decode_loop, daemon=True)
        self._thread.start()

    def reset(self):
        with self._lock:
            self._generation += 1
            self._ring.fill(0.0)
            self._write_pos = 0
            self._sample_count = 0
            self.pi_code = ""
            self.station_name = ""
            self.radio_text = ""
            self._station_buf = list("        ")
            self._radio_text_buf = [' '] * 64
            self._last_pi_code = ""
            self._radio_text_ab_flag = None
            self._station_votes = [dict() for _ in range(8)]
            self._radio_text_votes = [dict() for _ in range(64)]
            self._last_decode_at = 0.0
        self._wake_event.set()

    def stop(self):
        self._stop_event.set()
        self._wake_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def get_state(self) -> Tuple[str, str, str]:
        with self._lock:
            return self.pi_code, self.station_name, self.radio_text

    def process_mpx(self, mpx_signal: np.ndarray):
        if len(mpx_signal) == 0:
            return

        data = np.asarray(mpx_signal, dtype=np.float32)
        n = len(data)

        with self._lock:
            if n >= self._ring_size:
                self._ring[:] = data[-self._ring_size:]
                self._write_pos = 0
                self._sample_count = self._ring_size
            else:
                end = self._write_pos + n
                if end <= self._ring_size:
                    self._ring[self._write_pos:end] = data
                else:
                    split = self._ring_size - self._write_pos
                    self._ring[self._write_pos:] = data[:split]
                    self._ring[:n - split] = data[split:]
                self._write_pos = end % self._ring_size
                self._sample_count = min(self._ring_size, self._sample_count + n)

        self._wake_event.set()

    def _decode_loop(self):
        while not self._stop_event.is_set():
            self._wake_event.wait(timeout=self._decode_interval)
            self._wake_event.clear()

            now = time.monotonic()
            if now - self._last_decode_at < self._decode_interval:
                continue

            snapshot_info = self._get_snapshot()
            if snapshot_info is None:
                continue
            snapshot, generation = snapshot_info

            result = self._decode_snapshot(snapshot)
            self._last_decode_at = now
            if result is None:
                continue

            with self._lock:
                if generation != self._generation:
                    continue
                if result["pi_code"]:
                    if self._last_pi_code and result["pi_code"] != self._last_pi_code:
                        self._station_buf = list("        ")
                        self._radio_text_buf = [' '] * 64
                        self._station_votes = [dict() for _ in range(8)]
                        self._radio_text_votes = [dict() for _ in range(64)]
                        self._radio_text_ab_flag = None
                        self.station_name = ""
                        self.radio_text = ""
                    self.pi_code = result["pi_code"]
                    self._last_pi_code = result["pi_code"]

                radio_ab_flag = result.get("radio_ab_flag")
                if radio_ab_flag is not None:
                    if self._radio_text_ab_flag is not None and radio_ab_flag != self._radio_text_ab_flag:
                        self._radio_text_buf = [' '] * 64
                        self._radio_text_votes = [dict() for _ in range(64)]
                    self._radio_text_ab_flag = radio_ab_flag

                raw_station = self._clean_station_text(result["station_name"])
                raw_radiotext = self._clean_radio_text(result["radio_text"])

                if self._plausible_live_station(raw_station):
                    self.station_name = raw_station

                if self._plausible_live_radio_text(raw_radiotext):
                    if len(raw_radiotext) >= len(self.radio_text) or not self.radio_text:
                        self.radio_text = raw_radiotext

                for index, char in enumerate(result["station_name"]):
                    if char != ' ':
                        votes = self._station_votes[index]
                        votes[char] = votes.get(char, 0) + 1

                for index, char in enumerate(result["radio_text"][:len(self._radio_text_buf)]):
                    if char != ' ':
                        votes = self._radio_text_votes[index]
                        votes[char] = votes.get(char, 0) + 1

                voted_station = self._build_station_name()
                voted_radio = self._build_radio_text()
                if voted_station:
                    self.station_name = voted_station
                if voted_radio and (len(voted_radio) >= len(self.radio_text) or not self.radio_text):
                    self.radio_text = voted_radio

    @staticmethod
    def _collapse_spaces(text: str) -> str:
        return " ".join(text.split())

    @classmethod
    def _clean_station_text(cls, text: str) -> str:
        return cls._collapse_spaces(text.strip()) if text else ""

    @classmethod
    def _clean_radio_text(cls, text: str) -> str:
        if not text:
            return ""
        cleaned = []
        for char in text:
            if char in "\r\n\t":
                cleaned.append(' ')
            elif 32 <= ord(char) <= 126:
                cleaned.append(char)
        return cls._collapse_spaces("".join(cleaned).strip())

    @staticmethod
    def _plausible_station(text: str) -> bool:
        if len(text) < 4 or text != text.upper():
            return False
        allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 &/+-.'")
        invalid = sum(char not in allowed for char in text)
        alnum = sum(char.isalnum() for char in text)
        return invalid <= max(1, len(text) // 5) and alnum >= max(2, len(text) // 3)

    @staticmethod
    def _plausible_radio_text(text: str) -> bool:
        if len(text) < 8:
            return False
        allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 &/+-.,:;!?()'\"")
        invalid = sum(char not in allowed and char != ' ' for char in text)
        alnum = sum(char.isalnum() for char in text)
        return invalid <= max(2, len(text) // 6) and alnum >= max(4, len(text) // 3)

    @staticmethod
    def _plausible_live_radio_text(text: str) -> bool:
        if len(text) < 6:
            return False
        allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 &/+-.,:;!?()'\"")
        invalid = sum(char not in allowed and char != ' ' for char in text)
        letters = sum(char.isalpha() for char in text)
        return invalid <= max(2, len(text) // 5) and letters >= max(4, len(text) // 4)

    @staticmethod
    def _plausible_live_station(text: str) -> bool:
        if len(text) < 4 or text != text.upper():
            return False
        allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 &/+-.'")
        invalid = sum(char not in allowed and char != ' ' for char in text)
        alnum = sum(char.isalnum() for char in text)
        return invalid == 0 and alnum >= 4

    def _build_station_name(self) -> str:
        chars: List[str] = []
        stable_chars = 0
        for votes in self._station_votes:
            if not votes:
                chars.append(' ')
                continue
            char, count = max(votes.items(), key=lambda item: item[1])
            if count >= self._station_vote_threshold:
                chars.append(char)
                stable_chars += 1
            else:
                chars.append(' ')

        station = self._clean_station_text("".join(chars))
        if stable_chars < 3 or not self._plausible_station(station):
            return ""
        return station

    def _build_radio_text(self) -> str:
        chars: List[str] = []
        stable_chars = 0
        for votes in self._radio_text_votes:
            if not votes:
                chars.append(' ')
                continue
            char, count = max(votes.items(), key=lambda item: item[1])
            if count >= self._radio_vote_threshold:
                chars.append(char)
                stable_chars += 1
            else:
                chars.append(' ')

        text = self._clean_radio_text("".join(chars))
        if stable_chars < 8 or not self._plausible_radio_text(text):
            return ""
        return text

    def _get_snapshot(self) -> Optional[Tuple[np.ndarray, int]]:
        with self._lock:
            n = min(self._sample_count, self._snapshot_samples)
            if n < self._if_rate:
                return None

            pos = self._write_pos
            if pos >= n:
                return self._ring[pos - n:pos].copy(), self._generation

            return np.concatenate((self._ring[-(n - pos):], self._ring[:pos])), self._generation

    @staticmethod
    def _calc_syndrome(value: int, message_len: int) -> int:
        reg = 0
        poly = 0x5B9
        plen = 10

        for i in range(message_len, 0, -1):
            reg = (reg << 1) | ((value >> (i - 1)) & 0x01)
            if reg & (1 << plen):
                reg ^= poly

        for _ in range(plen, 0, -1):
            reg <<= 1
            if reg & (1 << plen):
                reg ^= poly

        return reg & ((1 << plen) - 1)

    @staticmethod
    def _mueller_muller(samples: np.ndarray) -> np.ndarray:
        interpolated = resample_poly(samples, 32, 1).astype(np.complex64, copy=False)
        sps = 16
        mu = 0.01
        out = np.zeros(len(samples) + 10, dtype=np.complex64)
        out_rail = np.zeros(len(samples) + 10, dtype=np.complex64)
        i_in = 0
        i_out = 2

        while i_out < len(samples) and (i_in + 32) < len(samples):
            out[i_out] = interpolated[i_in * 32 + int(mu * 32)]
            out_rail[i_out] = (
                int(np.real(out[i_out]) > 0) +
                1j * int(np.imag(out[i_out]) > 0)
            )
            x_term = (out_rail[i_out] - out_rail[i_out - 2]) * np.conj(out[i_out - 1])
            y_term = (out[i_out] - out[i_out - 2]) * np.conj(out_rail[i_out - 1])
            mm_val = np.real(y_term - x_term)
            mu += sps + 0.01 * mm_val
            i_in += int(np.floor(mu))
            mu -= np.floor(mu)
            i_out += 1

        return out[2:i_out]

    @staticmethod
    def _costas_loop(samples: np.ndarray) -> np.ndarray:
        phase = 0.0
        freq = 0.0
        alpha = 100.0
        beta = 0.5
        out = np.zeros(len(samples), dtype=np.complex64)

        for i, sample in enumerate(samples):
            out[i] = sample * np.exp(-1j * phase)
            error = float(np.real(out[i]) * np.imag(out[i]))
            freq += beta * error
            phase += freq + (alpha * error)
            while phase >= 2 * np.pi:
                phase -= 2 * np.pi
            while phase < 0:
                phase += 2 * np.pi

        return out

    def _decode_snapshot(self, mpx_signal: np.ndarray) -> Optional[Dict[str, object]]:
        x = np.asarray(mpx_signal, dtype=np.float32)
        if len(x) < self._if_rate:
            return None

        n = np.arange(len(x), dtype=np.float64)
        x = x.astype(np.complex64) * np.exp(-2j * np.pi * 57000.0 * n / self._if_rate)
        x = np.convolve(x, self._lpf, mode='valid')
        x = x[::10]
        x = resample_poly(x, 19, 24).astype(np.complex64, copy=False)

        x = self._mueller_muller(x)
        if len(x) < 128:
            return None

        x = self._costas_loop(x)
        bits = (np.real(x) > 0).astype(np.uint8)
        if len(bits) < 128:
            return None
        bits = ((bits[1:] - bits[:-1]) % 2).astype(np.uint8)

        groups = self._extract_groups(bits)
        if not groups:
            return None

        return self._parse_groups(groups)

    def _extract_groups(self, bits: np.ndarray) -> List[bytes]:
        synced = False
        presync = False
        wrong_blocks_counter = 0
        blocks_counter = 0
        group_good_blocks_counter = 0
        reg = np.uint32(0)
        lastseen_offset_counter = 0
        lastseen_offset = 0
        block_bit_counter = 0
        block_number = 0
        group_assembly_started = False
        groups: List[bytes] = []
        group = bytearray(8)

        for i, bit in enumerate(bits):
            reg = np.bitwise_or(np.left_shift(reg, 1), np.uint32(bit))

            if not synced:
                reg_syndrome = self._calc_syndrome(int(reg), 26)
                for j, syndrome in enumerate(self._SYNDROMES):
                    if reg_syndrome != syndrome:
                        continue

                    if not presync:
                        lastseen_offset = j
                        lastseen_offset_counter = i
                        presync = True
                    else:
                        if self._OFFSET_POSITIONS[lastseen_offset] >= self._OFFSET_POSITIONS[j]:
                            block_distance = self._OFFSET_POSITIONS[j] + 4 - self._OFFSET_POSITIONS[lastseen_offset]
                        else:
                            block_distance = self._OFFSET_POSITIONS[j] - self._OFFSET_POSITIONS[lastseen_offset]

                        if (block_distance * 26) != (i - lastseen_offset_counter):
                            presync = False
                        else:
                            wrong_blocks_counter = 0
                            blocks_counter = 0
                            block_bit_counter = 0
                            block_number = (j + 1) % 4
                            group_assembly_started = False
                            synced = True
                    break
                continue

            if block_bit_counter < 25:
                block_bit_counter += 1
                continue

            good_block = False
            dataword = (int(reg) >> 10) & 0xFFFF
            block_calculated_crc = self._calc_syndrome(dataword, 16)
            checkword = int(reg) & 0x3FF

            if block_number == 2:
                block_received_crc = checkword ^ self._OFFSET_WORDS[block_number]
                if block_received_crc == block_calculated_crc:
                    good_block = True
                else:
                    block_received_crc = checkword ^ self._OFFSET_WORDS[4]
                    if block_received_crc == block_calculated_crc:
                        good_block = True
                    else:
                        wrong_blocks_counter += 1
            else:
                block_received_crc = checkword ^ self._OFFSET_WORDS[block_number]
                if block_received_crc == block_calculated_crc:
                    good_block = True
                else:
                    wrong_blocks_counter += 1

            if block_number == 0 and good_block:
                group_assembly_started = True
                group_good_blocks_counter = 1
                group = bytearray(8)

            if group_assembly_started:
                if not good_block:
                    group_assembly_started = False
                else:
                    group[block_number * 2] = (dataword >> 8) & 0xFF
                    group[block_number * 2 + 1] = dataword & 0xFF
                    group_good_blocks_counter += 1
                    if group_good_blocks_counter == 5:
                        groups.append(bytes(group))

            block_bit_counter = 0
            block_number = (block_number + 1) % 4
            blocks_counter += 1

            if blocks_counter == 50:
                if wrong_blocks_counter > 35:
                    synced = False
                    presync = False
                blocks_counter = 0
                wrong_blocks_counter = 0

        return groups

    @staticmethod
    def _parse_groups(groups: List[bytes]) -> Dict[str, object]:
        pi_code = ""
        station = list("        ")
        radiotext = [' '] * 64
        radiotext_ab_flag: Optional[int] = None
        radiotext_end: Optional[int] = None

        for group in groups:
            group_0 = group[1] | (group[0] << 8)
            group_1 = group[3] | (group[2] << 8)
            group_2 = group[5] | (group[4] << 8)
            group_3 = group[7] | (group[6] << 8)

            pi_code = f"{group_0:04X}"
            group_type = (group_1 >> 12) & 0xF
            version_b = (group_1 >> 11) & 0x1

            if group_type == 0:
                segment = group_1 & 0x3
                chars = [(group_3 >> 8) & 0xFF, group_3 & 0xFF]
                base = segment * 2
                for offset, char_code in enumerate(chars):
                    if 32 <= char_code <= 126 and base + offset < len(station):
                        station[base + offset] = chr(char_code)

            elif group_type == 2:
                ab_flag = (group_1 >> 4) & 0x1
                if radiotext_ab_flag is None or radiotext_ab_flag != ab_flag:
                    radiotext = [' '] * 64
                    radiotext_end = None
                radiotext_ab_flag = ab_flag

                segment = group_1 & 0xF
                if version_b:
                    chars = [(group_3 >> 8) & 0xFF, group_3 & 0xFF]
                    base = segment * 2
                else:
                    chars = [
                        (group_2 >> 8) & 0xFF,
                        group_2 & 0xFF,
                        (group_3 >> 8) & 0xFF,
                        group_3 & 0xFF,
                    ]
                    base = segment * 4

                for offset, char_code in enumerate(chars):
                    pos = base + offset
                    if pos >= len(radiotext):
                        break
                    if char_code == 0x0D:
                        radiotext_end = pos
                        break
                    if 32 <= char_code <= 126:
                        radiotext[pos] = chr(char_code)

        station_name = "".join(station)
        if radiotext_end is not None:
            raw_radio_text = "".join(radiotext[:radiotext_end])
        else:
            raw_radio_text = "".join(radiotext)

        return {
            "pi_code": pi_code,
            "station_name": station_name,
            "radio_text": raw_radio_text,
            "radio_ab_flag": radiotext_ab_flag,
        }


class SimulatedSDR(QObject):
    """Generates simulated FM radio signal for demo/testing when no hardware."""
    samples_ready = Signal(np.ndarray)

    def __init__(self, sample_rate: float = 240000):
        super().__init__()
        self.on_samples = None
        self._sample_rate = sample_rate
        self._running = False
        self._thread = None
        self._frequency = 100.0e6
        self._phase = 0.0
        self._fm_phase = 0.0  # Cumulative FM carrier phase for continuity
        self._station_profiles = {
            87.5: {"pi": "8750", "station": "CITY FM", "text": "Morning traffic and city updates", "tones": (294, 588, 882), "noise": 0.03},
            92.3: {"pi": "9230", "station": "RETRO", "text": "Classic hits all day long", "tones": (330, 660, 990), "noise": 0.025},
            97.9: {"pi": "9790", "station": "JAZZ", "text": "Late night sessions and live sets", "tones": (220, 440, 659), "noise": 0.02},
            101.7: {"pi": "A117", "station": "NEWS", "text": "Headlines, weather, and local talk", "tones": (180, 360, 540), "noise": 0.015},
            105.5: {"pi": "B155", "station": "ELECTRO", "text": "Weekend mix with tight bass lines", "tones": (392, 784, 1176), "noise": 0.02},
        }

    def set_frequency(self, freq_hz: float):
        self._frequency = freq_hz

    def get_rds_state(self) -> Tuple[str, str, str]:
        profile = self._current_profile()
        if profile is None:
            return "", "", ""
        return profile["pi"], profile["station"], profile["text"]

    def _current_profile(self) -> Optional[Dict[str, object]]:
        freq_mhz = clamp_frequency(self._frequency / 1e6)
        return self._station_profiles.get(freq_mhz)

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            self.stop()
        self._running = True
        self._thread = threading.Thread(target=self._generate_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _generate_loop(self):
        """Generate a simulated FM signal with some audio content."""
        chunk_size = max(4096, int(self._sample_rate * 0.025))
        t_step = 1.0 / self._sample_rate
        fm_deviation = 75000  # FM broadcast deviation
        chunk_duration = chunk_size / self._sample_rate
        next_time = time.monotonic()

        while self._running:
            t = np.arange(chunk_size) * t_step + self._phase
            profile = self._current_profile()
            if profile is None:
                iq = 0.08 * (
                    np.random.randn(chunk_size) + 1j * np.random.randn(chunk_size)
                ).astype(np.complex64)
            else:
                tone_1, tone_2, tone_3 = profile["tones"]
                noise_level = float(profile["noise"])

                # Modulating audio: mix of tones + some noise
                mod_signal = (
                    0.4 * np.sin(2 * np.pi * tone_1 * t) +
                    0.2 * np.sin(2 * np.pi * tone_2 * t) +
                    0.1 * np.sin(2 * np.pi * tone_3 * t) +
                    0.05 * np.random.randn(chunk_size)
                )

                # FM modulation — continuous phase across chunks to avoid clicks
                phase_inc = 2 * np.pi * fm_deviation * mod_signal * t_step
                cum_phase = self._fm_phase + np.cumsum(phase_inc)
                self._fm_phase = cum_phase[-1] % (2 * np.pi)
                iq = np.exp(1j * cum_phase).astype(np.complex64)

                # Add noise
                iq += noise_level * (np.random.randn(chunk_size) + 1j * np.random.randn(chunk_size))

            self._phase = (self._phase + chunk_size * t_step) % 1.0
            callback = self.on_samples
            if callable(callback):
                try:
                    callback(iq)
                except Exception:
                    pass
            else:
                self.samples_ready.emit(iq)

            # Drift-correcting sleep: compensate for jitter across iterations
            next_time += chunk_duration
            sleep_for = next_time - time.monotonic()
            if sleep_for > 0:
                time.sleep(sleep_for)
            elif sleep_for < -0.1:
                # Fell too far behind — reset to avoid burst catch-up
                next_time = time.monotonic()


# ═══════════════════════════════════════════════════════════════
#  SETTINGS DIALOG
# ═══════════════════════════════════════════════════════════════

class SettingsDialog(QDialog):
    """Settings with multiple tabs, matching the car-radio aesthetic."""

    def __init__(self, settings: Optional[Dict[str, object]] = None,
                 skin_name: str = DEFAULT_SKIN_NAME, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setFixedSize(520, 440)
        if parent is not None and not parent.windowIcon().isNull():
            self.setWindowIcon(parent.windowIcon())
        self.setStyleSheet(self._build_stylesheet())
        self._build_ui()
        self._populate_dynamic_choices()
        self._load_runtime_settings(settings or DEFAULT_RUNTIME_SETTINGS, skin_name)

    def _build_stylesheet(self):
        return """
            QDialog {
                background: #1c1c26;
                color: #e6e1d7;
            }
            QTabWidget::pane {
                border: 1px solid #3c3a4a;
                border-radius: 6px;
                background: #24222e;
                top: -1px;
            }
            QTabBar::tab {
                background: #2a2836;
                color: #8c877d;
                padding: 8px 18px;
                margin-right: 2px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-family: 'Segoe UI', 'Helvetica Neue', sans-serif;
                font-size: 11px;
            }
            QTabBar::tab:selected {
                background: #24222e;
                color: #ffaa28;
                border-bottom: 2px solid #ffaa28;
            }
            QTabBar::tab:hover {
                background: #302e3c;
                color: #e6e1d7;
            }
            QLabel {
                color: #b0ab9f;
                font-family: 'Segoe UI', 'Helvetica Neue', sans-serif;
                font-size: 12px;
            }
            QComboBox {
                background: #2a2836;
                color: #e6e1d7;
                border: 1px solid #3c3a4a;
                border-radius: 6px;
                padding: 6px 12px;
                font-family: 'Segoe UI', 'Helvetica Neue', sans-serif;
                font-size: 11px;
            }
            QComboBox:hover { border-color: #5a566e; }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox QAbstractItemView {
                background: #2a2836;
                color: #e6e1d7;
                selection-background-color: #3c3a4a;
                border: 1px solid #4a4660;
            }
            QSpinBox, QDoubleSpinBox {
                background: #2a2836;
                color: #e6e1d7;
                border: 1px solid #3c3a4a;
                border-radius: 6px;
                padding: 4px 8px;
                font-family: 'Consolas', 'SF Mono', monospace;
            }
            QCheckBox {
                color: #b0ab9f;
                spacing: 8px;
                font-family: 'Segoe UI', 'Helvetica Neue', sans-serif;
                font-size: 11px;
            }
            QCheckBox::indicator {
                width: 18px; height: 18px;
                border-radius: 4px;
                border: 1px solid #4a4660;
                background: #2a2836;
            }
            QCheckBox::indicator:checked {
                background: #ffaa28;
                border-color: #ffaa28;
            }
            QGroupBox {
                font-family: 'Segoe UI', 'Helvetica Neue', sans-serif;
                font-size: 11px;
                font-weight: bold;
                color: #8c877d;
                border: 1px solid #3c3a4a;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 18px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 16px;
                padding: 0 6px;
            }
            QPushButton {
                background: #2a2836;
                color: #e6e1d7;
                border: 1px solid #3c3a4a;
                border-radius: 6px;
                padding: 8px 20px;
                font-family: 'Segoe UI', 'Helvetica Neue', sans-serif;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #3c3a4a;
                border-color: #5a566e;
            }
            QPushButton:pressed {
                background: #4a4660;
            }
        """

    @staticmethod
    def _set_combo_data(combo: QComboBox, value):
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return
        if combo.count():
            combo.setCurrentIndex(0)

    def _populate_dynamic_choices(self):
        self.device_combo.clear()
        for label, value in list_rtl_sdr_device_choices():
            self.device_combo.addItem(label, value)

        self.audio_combo.clear()
        for label, value in list_audio_output_choices():
            self.audio_combo.addItem(label, value)

    def _update_gain_enabled(self):
        self.gain_spin.setEnabled(self.agc_combo.currentData() == "manual")

    def _load_runtime_settings(self, settings: Dict[str, object], skin_name: str):
        runtime_settings = normalize_runtime_settings(settings)
        self._set_combo_data(self.device_combo, runtime_settings["device_selection"])
        self._set_combo_data(self.agc_combo, runtime_settings["gain_mode"])
        self.gain_spin.setValue(float(runtime_settings["gain_db"]))
        self._set_combo_data(self.deemph_combo, runtime_settings["deemphasis_us"])
        self.stereo_check.setChecked(bool(runtime_settings["stereo_enabled"]))
        self.rds_check.setChecked(bool(runtime_settings["rds_enabled"]))
        self._set_combo_data(self.bw_combo, runtime_settings["bandwidth_mode"])
        self._set_combo_data(self.audio_combo, runtime_settings["audio_output_device"])
        self._set_combo_data(self.sr_combo, runtime_settings["audio_output_rate"])
        self.buf_spin.setValue(int(runtime_settings["audio_blocksize"]))
        self.theme_combo.setCurrentText(normalize_skin_name(skin_name))
        self.spectrum_check.setChecked(bool(runtime_settings["show_spectrum"]))
        self._update_gain_enabled()

    def runtime_settings(self) -> Dict[str, object]:
        return normalize_runtime_settings({
            "device_selection": self.device_combo.currentData(),
            "gain_mode": self.agc_combo.currentData(),
            "gain_db": self.gain_spin.value(),
            "deemphasis_us": self.deemph_combo.currentData(),
            "stereo_enabled": self.stereo_check.isChecked(),
            "rds_enabled": self.rds_check.isChecked(),
            "bandwidth_mode": self.bw_combo.currentData(),
            "audio_output_device": self.audio_combo.currentData(),
            "audio_output_rate": self.sr_combo.currentData(),
            "audio_blocksize": self.buf_spin.value(),
            "show_spectrum": self.spectrum_check.isChecked(),
        })

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        self.tabs = QTabWidget()

        # ── Device tab ──
        dev_tab = QWidget()
        dl = QVBoxLayout(dev_tab)
        dg = QGroupBox("SDR Device")
        dgl = QGridLayout(dg)
        dgl.addWidget(QLabel("Device:"), 0, 0)
        self.device_combo = QComboBox()
        dgl.addWidget(self.device_combo, 0, 1)
        dgl.addWidget(QLabel("AGC Mode:"), 1, 0)
        self.agc_combo = QComboBox()
        self.agc_combo.addItem("Auto", "auto")
        self.agc_combo.addItem("Manual", "manual")
        self.agc_combo.currentIndexChanged.connect(self._update_gain_enabled)
        dgl.addWidget(self.agc_combo, 1, 1)
        dgl.addWidget(QLabel("Gain (dB):"), 2, 0)
        self.gain_spin = QDoubleSpinBox()
        self.gain_spin.setRange(0, 50)
        self.gain_spin.setValue(20)
        self.gain_spin.setSingleStep(0.5)
        dgl.addWidget(self.gain_spin, 2, 1)
        dl.addWidget(dg)
        dl.addStretch()
        self.tabs.addTab(dev_tab, "Device")

        # ── FM tab ──
        fm_tab = QWidget()
        fl = QVBoxLayout(fm_tab)
        fg = QGroupBox("FM Settings")
        fgl = QGridLayout(fg)
        fgl.addWidget(QLabel("De-emphasis:"), 0, 0)
        self.deemph_combo = QComboBox()
        self.deemph_combo.addItem("50 µs (Europe/World)", 50)
        self.deemph_combo.addItem("75 µs (USA)", 75)
        fgl.addWidget(self.deemph_combo, 0, 1)
        fgl.addWidget(QLabel("Stereo:"), 1, 0)
        self.stereo_check = QCheckBox("Enable stereo decoding")
        self.stereo_check.setChecked(True)
        fgl.addWidget(self.stereo_check, 1, 1)
        fgl.addWidget(QLabel("RDS:"), 2, 0)
        self.rds_check = QCheckBox("Enable RDS decoding")
        self.rds_check.setChecked(True)
        fgl.addWidget(self.rds_check, 2, 1)
        fgl.addWidget(QLabel("FM Bandwidth:"), 3, 0)
        self.bw_combo = QComboBox()
        self.bw_combo.addItem("Wide (200 kHz)", "wide")
        self.bw_combo.addItem("Narrow (100 kHz)", "narrow")
        fgl.addWidget(self.bw_combo, 3, 1)
        fl.addWidget(fg)
        fl.addStretch()
        self.tabs.addTab(fm_tab, "FM")

        # ── Audio tab ──
        audio_tab = QWidget()
        al = QVBoxLayout(audio_tab)
        ag = QGroupBox("Audio Output")
        agl = QGridLayout(ag)
        agl.addWidget(QLabel("Output:"), 0, 0)
        self.audio_combo = QComboBox()
        agl.addWidget(self.audio_combo, 0, 1)
        agl.addWidget(QLabel("Sample Rate:"), 1, 0)
        self.sr_combo = QComboBox()
        for rate in ALLOWED_AUDIO_RATES:
            self.sr_combo.addItem(f"{rate} Hz", rate)
        agl.addWidget(self.sr_combo, 1, 1)
        agl.addWidget(QLabel("Buffer Size:"), 2, 0)
        self.buf_spin = QSpinBox()
        self.buf_spin.setRange(ALLOWED_AUDIO_BLOCK_SIZES[0], ALLOWED_AUDIO_BLOCK_SIZES[-1])
        self.buf_spin.setValue(DEFAULT_RUNTIME_SETTINGS["audio_blocksize"])
        self.buf_spin.setSingleStep(256)
        agl.addWidget(self.buf_spin, 2, 1)
        al.addWidget(ag)
        al.addStretch()
        self.tabs.addTab(audio_tab, "Audio")

        # ── UI tab ──
        ui_tab = QWidget()
        ul = QVBoxLayout(ui_tab)
        ug = QGroupBox("Appearance")
        ugl = QGridLayout(ug)
        ugl.addWidget(QLabel("Theme:"), 0, 0)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(SKIN_NAMES)
        ugl.addWidget(self.theme_combo, 0, 1)
        ugl.addWidget(QLabel("Spectrum:"), 1, 0)
        self.spectrum_check = QCheckBox("Show spectrum analyzer")
        self.spectrum_check.setChecked(bool(DEFAULT_RUNTIME_SETTINGS["show_spectrum"]))
        ugl.addWidget(self.spectrum_check, 1, 1)
        ul.addWidget(ug)
        ul.addStretch()
        self.tabs.addTab(ui_tab, "UI")

        # ── About tab ──
        about_tab = QWidget()
        about_layout = QVBoxLayout(about_tab)
        about_group = QGroupBox("About PyRadio SDR")
        about_group_layout = QVBoxLayout(about_group)
        about_group_layout.setSpacing(10)

        about_headline = QLabel('"Vibe-coded" by Paul Ferguson')
        about_headline.setStyleSheet("color: #ffaa28; font-size: 18px; font-weight: bold;")
        about_headline.setWordWrap(True)
        about_group_layout.addWidget(about_headline)

        about_body = QLabel(
            "A focused FM/RDS desktop receiver with a car-radio UI, tuned for quick station surfing and live listening."
        )
        about_body.setStyleSheet("color: #e6e1d7;")
        about_body.setWordWrap(True)
        about_group_layout.addWidget(about_body)

        inspired_by = QLabel(
            'Inspired by <a href="https://github.com/marcogrecopriolo/guglielmo" style="color:#00dce6; text-decoration:none;">Guglielmo</a>.'
        )
        inspired_by.setOpenExternalLinks(True)
        inspired_by.setWordWrap(True)
        about_group_layout.addWidget(inspired_by)

        about_layout.addWidget(about_group)
        about_layout.addStretch()
        self.tabs.addTab(about_tab, "About")

        layout.addWidget(self.tabs)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)


# ═══════════════════════════════════════════════════════════════
#  MAIN WINDOW — The car-radio masterpiece
# ═══════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    """Main application window — the luxe car radio."""

    _REF_WIDTH = 860
    _REF_HEIGHT_FULL = 720
    _REF_HEIGHT_COMPACT_MIN = 540

    def __init__(self, startup_pulse: Optional[Callable[[], None]] = None):
        super().__init__()
        self._startup_pulse = startup_pulse
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(430, 320)
        self._ref_width = self._REF_WIDTH
        self._ref_height = self._REF_HEIGHT_FULL
        self._aspect_ratio = self._ref_width / self._ref_height
        self.resize(self._ref_width, self._ref_height)
        self._aspect_lock = False
        self._ui_scale = 1.0
        self._status_style = "font-family: 'Consolas', 'SF Mono', monospace; font-size: 13px; font-weight: 600;"

        # ── State ──
        self._frequency = 87.5  # MHz
        self._volume = 50
        self._muted = False
        self._squelch = 0
        self._playing = False
        self._recording = False
        self._presets: List[Dict] = self._load_presets()
        self._active_preset = -1
        self._signal_level = 0.0
        self._quality_level = 0.0
        self._signal_level_raw = 0.0
        self._quality_level_raw = 0.0
        self._scan_detect_level = 0.0
        self._station_detect_level = 0.0
        self._stereo_detect_level = 0.0
        self._scanning = False
        self._scan_direction = 1  # +1 up, -1 down
        self._scan_next_action_at = 0.0
        self._scan_steps = 0
        self._scan_candidate_freq: Optional[float] = None
        self._scan_candidate_quality = 0.0
        self._scan_confirm_remaining = 0
        self._scan_last_freq: Optional[float] = None
        self._scan_last_quality = 0.0
        self._scan_wait_for_release = False
        self._scan_mute_enabled = True
        self._last_tune_at = 0.0
        self._rds_resume_at = 0.0
        self._last_audio_push_at = 0.0
        self._hardware_watchdog_grace_until = 0.0
        self._last_hardware_recovery_at = 0.0
        self._startup_started = False
        self._closing = False
        self._native_icon_handles: List[int] = []
        self._app_settings = load_app_settings()
        self._app_settings.pop("show_waterfall", None)
        if not self._app_settings.get("_spectrum_hidden_default_v1"):
            self._app_settings["show_spectrum"] = False
            self._app_settings["_spectrum_hidden_default_v1"] = True
        self._app_settings["skin"] = normalize_skin_name(str(self._app_settings.get("skin", DEFAULT_SKIN_NAME)))
        self._runtime_settings = normalize_runtime_settings(self._app_settings)
        self._app_settings.update(self._runtime_settings)
        self._skin_name = set_active_skin(self._app_settings["skin"])
        self._pulse_startup()

        # ── SDR + DSP ──
        self._sdr = SDRBackend()
        self._sim = SimulatedSDR(sample_rate=240000)
        self._preferred_device_selection = self._runtime_settings["device_selection"]
        self._stereo_enabled = bool(self._runtime_settings["stereo_enabled"])
        self._rds_enabled = bool(self._runtime_settings["rds_enabled"])
        self._show_spectrum = bool(self._runtime_settings["show_spectrum"])
        self._audio_output_device = self._runtime_settings["audio_output_device"]
        self._audio_output_rate = self._runtime_settings["audio_output_rate"]
        self._audio_blocksize = self._runtime_settings["audio_blocksize"]
        self._audio_stream_blocksize = self._audio_blocksize
        self._sdr._device_index = self._device_probe_index(self._preferred_device_selection)
        self._sdr.set_gain(self._current_gain_value())
        self._demod_hw = self._make_demodulator(self._sdr._sample_rate)
        self._demod_sim = self._make_demodulator(240000)
        self._rds_hw  = RDSDecoder(if_rate=240000)
        self._rds_sim = RDSDecoder(if_rate=240000)
        self._use_sim = True
        self._device_status = "Disconnected"
        self._device_error_msg = ""
        self._pipeline_lock = threading.RLock()
        self._pipeline_generation = 0
        self._sample_queue_lock = threading.Lock()
        self._sample_queue_event = threading.Event()
        self._sample_queue = deque(maxlen=64)
        self._sample_processor_stop = threading.Event()
        self._sample_queue_high_water = 0
        self._sample_queue_drop_count = 0
        self._sample_process_ms_ema = 0.0
        self._sample_process_peak_ms = 0.0
        self._visual_lock = threading.Lock()
        self._visual_audio_queue = deque(maxlen=24)
        # ── Audio ring buffer (like reference AudioOutput) ──
        self._audio_lock = threading.Lock()
        self._audio_error_msg = ""
        self._audio_callback_status = ""
        self._audio_primed = False
        self._audio_resume_fill = 0
        self._audio_low_water = 0
        self._audio_empty_callbacks = 0
        self._audio_underrun_count = 0
        self._audio_min_fill = 0
        self._audio_max_fill = 0
        self._audio_clock_correction_accum = 0.0
        self._audio_clock_correction_bias = 0.0
        self._audio_output_rate_estimate = float(self._audio_output_rate)
        self._audio_output_rate_window_started_at = 0.0
        self._audio_output_rate_window_frames = 0
        self._audio_input_rate_estimate = float(self._audio_output_rate)
        self._audio_input_rate_window_started_at = 0.0
        self._audio_input_rate_window_samples = 0
        self._last_signal_metrics_at = 0.0
        self._audio_play_started_at = 0.0
        self._audio_total_pushed_samples = 0
        self._audio_lt_rate_started_at = 0.0
        self._audio_lt_samples_snapshot = 0
        self._audio_total_consumed_samples = 0
        self._audio_total_callback_frames = 0
        self._last_audio_push_samples = 0
        self._last_audio_push_at = 0.0
        self._last_audio_push_fill = 0
        self._last_audio_callback_frames = 0
        self._last_audio_callback_source_len = 0
        self._last_audio_callback_available = 0
        self._last_audio_callback_fill_after = 0
        self._last_audio_callback_target_fill = 0
        self._last_audio_callback_fill_delta = 0
        self._last_audio_callback_correction_frames = 0
        self._last_audio_callback_estimated_input_rate = float(self._audio_output_rate)
        self._configure_audio_buffer(self._audio_output_rate)

        # ── Audio output ──
        self._audio_stream = None

        self._app_icon = load_app_icon()
        self._set_window_icon()

        self._sim.on_samples = self._enqueue_sim_samples
        self._sdr.on_samples = self._enqueue_sdr_samples
        self._sample_processor_thread = threading.Thread(target=self._sample_processor_loop, daemon=True)
        self._sample_processor_thread.start()
        self._pulse_startup()

        # ── Build UI ──
        self._build_ui()
        self._pulse_startup()

        # ── Timers ──
        self._ui_timer = QTimer()
        self._ui_timer.timeout.connect(self._update_ui)

        self._spectrum_timer = QTimer()
        self._spectrum_timer.timeout.connect(self._update_waveform_display)

        self._apply_visualizer_settings(resize_window=True)
        self._apply_skin(self._skin_name, persist=False)
        self._set_loading_overlay(True, "Booting radio", "Checking for RTL-SDR hardware...")
        self._ui_timer.start(50)  # ~20fps
        self._pulse_startup()

        self._sdr.device_connected.connect(self._on_device_connected)
        self._sdr.device_error.connect(self._on_device_error)

        # Keep both sources aligned with the UI frequency before any device starts.
        self._sync_tuned_frequency()
        self._pulse_startup()

        # ── Probe hardware after the first paint so the UI appears immediately ──
        self._device_status = "Checking"
        self._device_error_msg = ""

        # ── RDS display state ──
        self._rds_station = ""
        self._rds_text = ""
        self._rds_pi = ""
        self._rds_blocked_pi = ""
        self._rds_ignore_until = 0.0
        self._rds_update_timer = QTimer()
        self._rds_update_timer.timeout.connect(self._update_rds_display)
        self._rds_update_timer.start(150)
        self._clear_rds_display(tuning=False)
        self._pulse_startup()

    def _pulse_startup(self):
        if self._startup_pulse is None:
            return
        try:
            self._startup_pulse()
        except Exception:
            pass

    # ─── UI Construction ────────────────────────────────────
    def _build_ui(self):
        # Build UI at reference resolution inside a fixed-size container
        self._ui_container = QWidget()
        self._ui_container.setFixedSize(self._ref_width, self._ref_height)
        self._ui_container.setStyleSheet("""
            background: qlineargradient(y1:0, y2:1,
                stop:0 #10101a, stop:0.5 #0c0c10, stop:1 #080810);
        """)
        root = QVBoxLayout(self._ui_container)
        self._ui_root_layout = root
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        # ═══ TOP: Display + Indicators ═══
        top_row = QHBoxLayout()
        top_row.setSpacing(14)

        # VFD display
        self.vfd = VFDDisplay()
        self.vfd.frequencySubmitted.connect(self._set_frequency_from_input)
        top_row.addWidget(self.vfd, stretch=1)

        # Right indicators column
        ind_col = QVBoxLayout()
        ind_col.setSpacing(4)

        self.ind_stereo = GlowIndicator("STEREO", Palette.GREEN)
        self.ind_signal = GlowIndicator("SIGNAL", Palette.CYAN)
        self.ind_rds = GlowIndicator("RDS", Palette.AMBER)

        ind_col.addWidget(self.ind_stereo)
        ind_col.addWidget(self.ind_signal)
        ind_col.addWidget(self.ind_rds)
        ind_col.addStretch()

        top_row.addLayout(ind_col)
        root.addLayout(top_row)

        # ═══ SIGNAL METERS ═══
        meters_row = QHBoxLayout()
        meters_row.setSpacing(20)
        meters_row.addStretch()
        self.sig_meter = SignalMeter("SIG")
        self.qual_meter = SignalMeter("SNR")
        meters_row.addWidget(self.sig_meter)
        meters_row.addWidget(self.qual_meter)
        meters_row.addStretch()
        root.addLayout(meters_row)

        # ═══ MIDDLE: FM content ═══
        fm_panel = self._build_fm_panel()
        self._fm_panel = fm_panel
        root.addWidget(fm_panel, stretch=1)

        # ═══ PRESETS BAR ═══
        presets_frame = QFrame()
        presets_frame.setObjectName("presetsFrame")
        presets_layout = QHBoxLayout(presets_frame)
        presets_layout.setContentsMargins(8, 4, 8, 4)
        presets_layout.setSpacing(6)

        self.preset_buttons: List[PresetButton] = []
        for i in range(8):
            pb = PresetButton(i + 1)
            if i < len(self._presets):
                pb.set_text(self._presets[i].get("name", ""))
            pb.clicked.connect(lambda checked, idx=i: self._recall_preset(idx))
            self.preset_buttons.append(pb)
            presets_layout.addWidget(pb)

        # Preset M+ / M- buttons
        mem_plus = StyledButton(text="M+", accent=Palette.AMBER, size=QSize(44, 50))
        mem_plus.clicked.connect(self._save_preset)
        mem_minus = StyledButton(text="M−", accent=Palette.RED, size=QSize(44, 50))
        mem_minus.clicked.connect(self._delete_preset)
        self._memory_buttons = [mem_plus, mem_minus]
        presets_layout.addWidget(mem_plus)
        presets_layout.addWidget(mem_minus)

        root.addWidget(presets_frame)

        # ═══ BOTTOM: Controls bar ═══
        controls = QHBoxLayout()
        controls.setSpacing(12)

        # Volume knob
        self.vol_knob = RotaryKnob("VOLUME", 0, 100, 50, Palette.AMBER)
        self.vol_knob.valueChanged.connect(self._on_volume_changed)
        controls.addWidget(self.vol_knob)

        self.btn_mute = StyledButton(icon_text="🔊", accent=Palette.RED, size=QSize(54, 38))
        self.btn_mute.clicked.connect(self._toggle_mute)
        controls.addWidget(self.btn_mute)

        # Squelch knob
        self.squelch_knob = RotaryKnob("SQUELCH", 0, 100, 0, Palette.CYAN)
        self.squelch_knob.valueChanged.connect(self._on_squelch_changed)
        controls.addWidget(self.squelch_knob)

        controls.addSpacing(12)

        # ── Transport buttons ──
        btn_col = QVBoxLayout()
        btn_row1 = QHBoxLayout()
        btn_row1.setSpacing(8)

        # Power toggle
        self.btn_play = StyledButton(icon_text="⏻", accent=Palette.GREEN, size=QSize(56, 38))
        self.btn_play.clicked.connect(self._toggle_play)
        btn_row1.addWidget(self.btn_play)

        btn_row1.addSpacing(12)

        # Settings button
        self.btn_settings = StyledButton(icon_text="⚙", accent=Palette.TEXT_SECONDARY, size=QSize(48, 38))
        self.btn_settings.clicked.connect(self._open_settings)
        btn_row1.addWidget(self.btn_settings)

        btn_row1.addStretch()
        btn_col.addLayout(btn_row1)
        controls.addLayout(btn_col, stretch=1)

        root.addLayout(controls)

        # ═══ STATUS BAR ═══
        status_frame = QFrame()
        self._status_frame = status_frame
        status_frame.setObjectName("statusBar")
        status_frame.setFixedHeight(38)
        status_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(10, 0, 10, 0)
        status_layout.setSpacing(6)

        status_style = self._status_style

        self.status_sdr = QLabel("\u25cf SDR: Simulated")
        self.status_sdr.setAlignment(Qt.AlignCenter)
        self.status_sdr.setStyleSheet(f"color: #ffaa28; {status_style}")
        self.status_sdr.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        status_layout.addWidget(self.status_sdr, 2)

        sep1 = QLabel("\u2502")
        sep1.setAlignment(Qt.AlignCenter)
        sep1.setStyleSheet(f"color: #2a2836; {status_style}")
        status_layout.addWidget(sep1)

        self.status_freq = QLabel("87.5 MHz")
        self.status_freq.setAlignment(Qt.AlignCenter)
        self.status_freq.setStyleSheet(f"color: #00dce6; {status_style}")
        self.status_freq.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        status_layout.addWidget(self.status_freq, 1)

        sep2 = QLabel("\u2502")
        sep2.setAlignment(Qt.AlignCenter)
        sep2.setStyleSheet(f"color: #2a2836; {status_style}")
        status_layout.addWidget(sep2)

        self.status_audio = QLabel("\u25cf Audio: Stopped")
        self.status_audio.setAlignment(Qt.AlignCenter)
        self.status_audio.setStyleSheet(f"color: #8c877d; {status_style}")
        self.status_audio.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        status_layout.addWidget(self.status_audio, 2)

        sep3 = QLabel("\u2502")
        sep3.setAlignment(Qt.AlignCenter)
        sep3.setStyleSheet(f"color: #2a2836; {status_style}")
        status_layout.addWidget(sep3)

        self.status_buffer = StatusBarMeter("BUF")
        status_layout.addWidget(self.status_buffer, 1, Qt.AlignCenter)

        sep4 = QLabel("\u2502")
        sep4.setAlignment(Qt.AlignCenter)
        sep4.setStyleSheet(f"color: #2a2836; {status_style}")
        status_layout.addWidget(sep4)

        self.status_sr = QLabel("SR: 48 kHz / 240 kHz")
        self.status_sr.setAlignment(Qt.AlignCenter)
        self.status_sr.setStyleSheet(f"color: #8c877d; {status_style}")
        self.status_sr.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        status_layout.addWidget(self.status_sr, 2)

        self._status_labels = [
            self.status_sdr,
            self.status_freq,
            self.status_audio,
            self.status_sr,
            sep1,
            sep2,
            sep3,
            sep4,
        ]

        root.addWidget(status_frame)

        # ── Wrap the UI container in a QGraphicsView for smooth scaling ──
        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(0, 0, self._ref_width, self._ref_height)
        self._proxy = self._scene.addWidget(self._ui_container)
        self._view = QGraphicsView(self._scene, self)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._view.setFrameShape(QFrame.NoFrame)
        self._view.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self._view.setOptimizationFlag(QGraphicsView.DontSavePainterState, True)
        self._view.setOptimizationFlag(QGraphicsView.DontAdjustForAntialiasing, True)
        self._view.setStyleSheet("background: #0c0c10; border: none;")
        self._view.setAlignment(Qt.AlignCenter)
        self.setCentralWidget(self._view)

        self._loading_overlay = LoadingOverlay(self._view.viewport())
        self._loading_overlay.setGeometry(self._view.viewport().rect())

    def _build_fm_panel(self) -> QWidget:
        """Build the FM-specific panel with waveform and tuning."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self._fm_panel_layout = layout
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Audio waveform
        self.waveform = AudioWaveformWidget()
        self._waveform_expanded_min_height = self.waveform.minimumHeight()
        layout.addWidget(self.waveform, stretch=1)

        # ── Tuning row ──
        tune_row = QHBoxLayout()
        tune_row.setSpacing(6)

        # Auto-scan buttons
        self.btn_scan_down = StyledButton(icon_text="⏪", accent=Palette.AMBER, size=QSize(44, 36))
        self.btn_scan_down.clicked.connect(self._auto_scan_down)
        tune_row.addWidget(self.btn_scan_down)

        self.btn_scan_mute = StyledButton(icon_text="🔇", accent=Palette.RED, size=QSize(34, 36))
        self.btn_scan_mute.clicked.connect(self._toggle_scan_mute)
        tune_row.addWidget(self.btn_scan_mute)

        self.btn_scan_up = StyledButton(icon_text="⏩", accent=Palette.AMBER, size=QSize(44, 36))
        self.btn_scan_up.clicked.connect(self._auto_scan_up)
        tune_row.addWidget(self.btn_scan_up)

        self.btn_scan_stop = StyledButton(text="STOP", accent=Palette.RED, size=QSize(52, 36))
        self.btn_scan_stop.clicked.connect(self._scan_stop)
        tune_row.addWidget(self.btn_scan_stop)

        tune_row.addSpacing(8)

        # Frequency tuning knob (0.1 MHz steps via wheel/drag)
        self.tune_knob = RotaryKnob("TUNING", 87.5, 108.0, 87.5, Palette.CYAN, step=0.1)
        self.tune_knob.valueChanged.connect(self._on_frequency_changed)
        tune_row.addWidget(self.tune_knob)

        tune_row.addSpacing(8)

        # Fine step buttons: −1  −0.1  +0.1  +1
        self._tune_step_buttons = []
        for label, delta in [("−1", -1.0), ("−0.1", -0.1), ("+0.1", 0.1), ("+1", 1.0)]:
            is_coarse = abs(delta) >= 1.0
            accent = Palette.AMBER if is_coarse else Palette.TEXT_SECONDARY
            btn = StyledButton(text=label, accent=accent, size=QSize(46, 36))
            btn.clicked.connect(lambda _=False, d=delta: self._nudge_freq(d))
            self._tune_step_buttons.append(btn)
            tune_row.addWidget(btn)

        layout.addLayout(tune_row)

        self._refresh_audio_control_buttons()

        return panel

    def _apply_stylesheet(self):
        font_family = str(skin_value("ui_font_family", self._skin_name))
        widget_text = skin_value("widget_text", self._skin_name)
        classic = is_winamp_classic_skin(self._skin_name)
        frame_radius = 2 if classic else 10
        status_radius = 2 if classic else 6
        self.setStyleSheet(f"""
            QMainWindow {{
                background: qlineargradient(y1:0, y2:1,
                    stop:0 {skin_value('app_bg_top', self._skin_name)}, stop:0.5 {skin_value('app_bg_mid', self._skin_name)}, stop:1 {skin_value('app_bg_bottom', self._skin_name)});
            }}
            QWidget {{
                background: transparent;
                color: {widget_text};
                font-family: '{font_family}', 'Segoe UI', 'Helvetica Neue', sans-serif;
            }}
            #presetsFrame {{
                background: qlineargradient(y1:0, y2:1,
                    stop:0 {skin_value('presets_top', self._skin_name)}, stop:1 {skin_value('presets_bottom', self._skin_name)});
                border: 1px solid {skin_value('presets_border', self._skin_name)};
                border-radius: {frame_radius}px;
            }}
            QScrollBar:vertical {{
                background: {skin_value('scrollbar_bg', self._skin_name)};
                width: 8px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {skin_value('scrollbar_handle', self._skin_name)};
                border-radius: 4px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {skin_value('scrollbar_handle_hover', self._skin_name)};
            }}
            QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
            #statusBar {{
                background: {skin_value('status_bg', self._skin_name)};
                border: 1px solid {skin_value('status_border', self._skin_name)};
                border-radius: {status_radius}px;
            }}
            #statusBar QLabel {{
                background: transparent;
            }}
        """)

        if hasattr(self, '_ui_container'):
            self._ui_container.setStyleSheet(
                "background: qlineargradient(y1:0, y2:1, "
                f"stop:0 {skin_value('ui_bg_top', self._skin_name)}, "
                f"stop:0.5 {skin_value('ui_bg_mid', self._skin_name)}, "
                f"stop:1 {skin_value('ui_bg_bottom', self._skin_name)});"
            )
        if hasattr(self, '_view'):
            self._view.setStyleSheet(f"background: {skin_value('view_bg', self._skin_name)}; border: none;")

    def _refresh_indicator_palette(self):
        for indicator, color in (
            (getattr(self, 'ind_stereo', None), Palette.GREEN),
            (getattr(self, 'ind_signal', None), Palette.CYAN),
            (getattr(self, 'ind_rds', None), Palette.AMBER),
        ):
            if indicator is None:
                continue
            indicator._color_on = QColor(color)
            indicator._color_off = QColor(color.red() // 4, color.green() // 4, color.blue() // 4)
            indicator.update()

    def _apply_skin(self, skin_name: str, persist: bool = True):
        self._skin_name = set_active_skin(skin_name)
        self._apply_stylesheet()
        self._refresh_indicator_palette()
        self._apply_ui_scale(getattr(self, '_ui_scale', 1.0) or 1.0)

        for widget in (
            getattr(self, 'vfd', None),
            getattr(self, 'waveform', None),
            getattr(self, '_ui_container', None),
            getattr(self, '_view', None),
            getattr(self, '_loading_overlay', None),
            self,
        ):
            if widget is not None:
                widget.update()

        if persist:
            self._app_settings["skin"] = self._skin_name
            save_app_settings(self._app_settings)

    def _target_reference_height(self) -> int:
        if self._show_spectrum or not hasattr(self, '_ui_root_layout'):
            return self._REF_HEIGHT_FULL

        waveform_hint = max(120, int(getattr(self, '_waveform_expanded_min_height', 120)))
        target_height = self._REF_HEIGHT_FULL - max(128, waveform_hint + 8)
        target_height = max(self._REF_HEIGHT_COMPACT_MIN, min(self._REF_HEIGHT_FULL, target_height))
        return target_height

    def _apply_reference_geometry(self, resize_window: bool = False):
        if not hasattr(self, '_ui_container'):
            return

        target_height = self._target_reference_height()
        if target_height != self._ref_height:
            self._ref_height = target_height
            self._aspect_ratio = self._ref_width / self._ref_height
            self._ui_container.setFixedSize(self._ref_width, self._ref_height)
            if hasattr(self, '_scene'):
                self._scene.setSceneRect(0, 0, self._ref_width, self._ref_height)

        if resize_window:
            current_width = max(self.minimumWidth(), self.width())
            target_window_height = max(self.minimumHeight(), round(current_width / self._aspect_ratio))
            self._aspect_lock = True
            self.resize(current_width, target_window_height)
            self._aspect_lock = False

        if hasattr(self, '_view'):
            self._rescale_view()

    # ─── Aspect-ratio lock & scaling ────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        self._set_window_icon()
        self._update_loading_overlay_geometry()
        QTimer.singleShot(0, self._rescale_view)
        if not self._startup_started:
            self._startup_started = True
            QTimer.singleShot(0, self._begin_startup_probe)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        if not hasattr(self, '_view'):
            return
        if self._aspect_lock:
            return
        self._aspect_lock = True
        w = event.size().width()
        h = event.size().height()
        desired_h = round(w / self._aspect_ratio)
        if abs(desired_h - h) > 2:
            self.resize(w, desired_h)
        self._rescale_view()
        self._update_loading_overlay_geometry()
        self._aspect_lock = False

    def _rescale_view(self):
        vp = self._view.viewport().size()
        sx = vp.width() / self._ref_width
        sy = vp.height() / self._ref_height
        scale = min(sx, sy)
        self._ui_scale = scale
        self._view.resetTransform()
        self._view.scale(scale, scale)
        self._view.centerOn(self._proxy)

        self._apply_ui_scale(scale)
        self._update_loading_overlay_geometry()

    def _apply_ui_scale(self, scale: float):
        status_font_px = max(10, min(17, int(round(13 * readability_scale(scale)))))
        self._status_style = (
            f"font-family: '{skin_value('mono_font_family', self._skin_name)}', 'Consolas', monospace; "
            f"font-size: {status_font_px}px; font-weight: 600;"
        )
        if hasattr(self, '_status_frame'):
            self._status_frame.setFixedHeight(max(36, min(48, int(round(38 * readability_scale(scale))))))

        widgets = [
            getattr(self, 'vfd', None),
            getattr(self, 'sig_meter', None),
            getattr(self, 'qual_meter', None),
            getattr(self, 'status_buffer', None),
            getattr(self, 'ind_stereo', None),
            getattr(self, 'ind_signal', None),
            getattr(self, 'ind_rds', None),
            getattr(self, 'vol_knob', None),
            getattr(self, 'squelch_knob', None),
            getattr(self, 'tune_knob', None),
            getattr(self, 'btn_play', None),
            getattr(self, 'btn_mute', None),
            getattr(self, 'btn_settings', None),
            getattr(self, 'btn_scan_up', None),
            getattr(self, 'btn_scan_down', None),
            getattr(self, 'btn_scan_mute', None),
            getattr(self, 'btn_scan_stop', None),
        ]
        widgets.extend(getattr(self, 'preset_buttons', []))
        widgets.extend(getattr(self, '_memory_buttons', []))
        widgets.extend(getattr(self, '_tune_step_buttons', []))

        for widget in widgets:
            if widget is not None and hasattr(widget, 'set_ui_scale'):
                widget.set_ui_scale(scale)

        for label in getattr(self, '_status_labels', []):
            color = skin_value('status_idle', self._skin_name)
            if label is getattr(self, 'status_freq', None):
                color = skin_value('status_freq', self._skin_name)
            elif label.text() == "│":
                color = skin_value('status_sep', self._skin_name)
            label.setStyleSheet(f"color: {color}; {self._status_style}")
            label.setProperty("_cached_style", "")
        if hasattr(self, '_update_ui'):
            self._update_ui()

    def _set_window_icon(self):
        icon = self._app_icon if hasattr(self, '_app_icon') else load_app_icon()
        if icon.isNull():
            return

        self.setWindowIcon(icon)
        app = QApplication.instance()
        if app is not None:
            app.setWindowIcon(icon)
        if hasattr(self, '_view'):
            self._view.setWindowIcon(icon)
        handle = self.windowHandle()
        if handle is not None:
            handle.setIcon(icon)
        if sys.platform == 'win32':
            icon_file = app_icon_file()
            hwnd = int(self.winId()) if self.winId() else 0
            if hwnd:
                destroy_windows_icon_handles(self._native_icon_handles)
                self._native_icon_handles = apply_windows_taskbar_icon(hwnd, icon_file)

    def _update_loading_overlay_geometry(self):
        if not hasattr(self, '_loading_overlay') or not hasattr(self, '_view'):
            return
        viewport = self._view.viewport()
        self._loading_overlay.setGeometry(viewport.rect())
        self._loading_overlay.raise_()

    def _set_loading_overlay(self, visible: bool, title: str = "", detail: str = ""):
        if not hasattr(self, '_loading_overlay'):
            return
        if visible:
            self._update_loading_overlay_geometry()
            self._loading_overlay.show_message(title, detail)
            return
        self._loading_overlay.hide_message()

    def _begin_startup_probe(self):
        if self._closing:
            return

        if self._preferred_device_selection == "simulated":
            self._use_sim = True
            self._device_status = "Simulated"
            self._device_error_msg = ""
            self._sync_tuned_frequency()
            self._set_loading_overlay(False)
            return

        self._device_status = "Checking"
        self._device_error_msg = ""
        self._set_loading_overlay(True, "Booting radio", "Checking for RTL-SDR hardware...")
        QApplication.processEvents()
        self._try_connect_hardware(self._preferred_device_selection)
        if not self._closing:
            self._set_loading_overlay(False)

    def _apply_hardware_probe_result(self, device, device_index: int):
        self._sdr.adopt_device(device, device_index)
        if device is None:
            self._use_sim = True
            self._device_status = "Simulated"
        else:
            self._use_sim = False
            self._device_status = "Connected"
        self._device_error_msg = ""
        self._sync_tuned_frequency()

    def _device_probe_index(self, selection=None) -> int:
        normalized = self._preferred_device_selection if selection is None else normalize_device_selection(selection)
        return 0 if normalized in {"auto", "simulated"} else int(normalized)

    def _current_gain_value(self, settings: Optional[Dict[str, object]] = None):
        runtime_settings = self._runtime_settings if settings is None else normalize_runtime_settings(settings)
        if runtime_settings["gain_mode"] == "auto":
            return 'auto'
        return float(runtime_settings["gain_db"])

    def _current_deemphasis_tau(self) -> float:
        return 50e-6 if self._runtime_settings["deemphasis_us"] == 50 else 75e-6

    def _current_audio_cutoff(self) -> float:
        return 15000.0 if self._runtime_settings["bandwidth_mode"] == "wide" else 11000.0

    def _make_demodulator(self, sample_rate: float) -> FMDemodulator:
        return FMDemodulator(
            sample_rate=sample_rate,
            audio_rate=self._audio_output_rate,
            deemph_tau=self._current_deemphasis_tau(),
            audio_cutoff=self._current_audio_cutoff(),
        )

    def _recommended_sdr_read_size(self) -> int:
        audio_rate = max(int(self._audio_output_rate), 1)
        audio_blocksize = max(int(getattr(self, '_audio_stream_blocksize', self._audio_blocksize)), 1)
        sdr_rate = max(int(getattr(self._sdr, '_sample_rate', 240000)), 1)
        callback_equivalent = int(math.ceil((audio_blocksize * sdr_rate) / audio_rate))
        target_samples = max(4096, callback_equivalent // 2)
        return max(4096, ((target_samples + 4095) // 4096) * 4096)

    def _effective_audio_blocksize(self, blocksize: int) -> int:
        normalized = normalize_audio_blocksize(blocksize)
        if self._preferred_device_selection != "simulated":
            return min(normalized, HARDWARE_AUDIO_BLOCKSIZE)
        return normalized

    def _configure_audio_buffer(self, audio_rate: int):
        rate = normalize_audio_rate(audio_rate)
        configured_blocksize = normalize_audio_blocksize(self._audio_blocksize)
        effective_blocksize = self._effective_audio_blocksize(configured_blocksize)
        self._audio_output_rate = rate
        self._audio_blocksize = configured_blocksize
        self._audio_stream_blocksize = effective_blocksize
        self._audio_buf_size = max(effective_blocksize * 24, int(rate * AUDIO_RING_BUFFER_SECONDS))
        self._audio_target_fill = max(effective_blocksize * 7, int(rate * AUDIO_TARGET_FILL_SECONDS))
        self._audio_prime_fill = max(effective_blocksize * 6, int(rate * AUDIO_PRIME_FILL_SECONDS))
        self._audio_resume_fill = max(effective_blocksize * 3, int(rate * AUDIO_RESUME_FILL_SECONDS))
        self._audio_low_water = max(effective_blocksize * 2, int(rate * AUDIO_LOW_WATER_SECONDS))
        self._audio_trim_threshold = int(self._audio_buf_size * 0.96)
        self._audio_trim_target = max(self._audio_target_fill, int(self._audio_buf_size * 0.90))
        self._audio_ring = np.zeros(self._audio_buf_size, dtype=np.float32)
        self._audio_write_pos = 0
        self._audio_read_pos = 0
        self._audio_count = 0
        self._audio_primed = False
        self._audio_empty_callbacks = 0
        self._audio_underrun_count = 0
        self._audio_min_fill = self._audio_buf_size
        self._audio_max_fill = 0
        self._audio_clock_correction_accum = 0.0
        self._audio_clock_correction_bias = 0.0
        self._audio_output_rate_estimate = float(rate)
        self._audio_output_rate_window_started_at = 0.0
        self._audio_output_rate_window_frames = 0
        self._audio_input_rate_estimate = float(rate)
        self._audio_input_rate_window_started_at = 0.0
        self._audio_input_rate_window_samples = 0
        self._last_signal_metrics_at = 0.0
        self._audio_play_started_at = 0.0
        self._audio_total_pushed_samples = 0
        self._audio_lt_rate_started_at = 0.0
        self._audio_lt_samples_snapshot = 0
        self._audio_total_consumed_samples = 0
        self._audio_total_callback_frames = 0
        self._last_audio_push_samples = 0
        self._last_audio_push_fill = 0
        self._last_audio_callback_frames = 0
        self._last_audio_callback_source_len = 0
        self._last_audio_callback_available = 0
        self._last_audio_callback_fill_after = 0
        self._last_audio_callback_target_fill = 0
        self._last_audio_callback_fill_delta = 0
        self._last_audio_callback_correction_frames = 0
        self._last_audio_callback_estimated_input_rate = float(rate)
        if hasattr(self, '_sdr') and self._sdr is not None:
            self._sdr.set_read_size(self._recommended_sdr_read_size())

    def _maybe_recover_hardware_stream(self, now: float):
        if self._closing or not self._playing or self._use_sim:
            return
        if now < self._hardware_watchdog_grace_until:
            return
        if now - self._last_hardware_recovery_at < 2.5:
            return

        stalled_audio = self._audio_stream is not None and (now - self._last_audio_push_at) > 1.35
        stalled_samples = self._sdr.sample_stalled(1.35, now=now)
        if not stalled_audio and not stalled_samples:
            return

        self._last_hardware_recovery_at = now
        self._hardware_watchdog_grace_until = now + 1.8
        self._device_status = "Recovering"
        self._audio_error_msg = ""
        self._audio_callback_status = "Reopening SDR"
        self._reset_active_pipeline()
        self._sdr.restart_stream(reopen_device=True, wait=False)

    def _apply_visualizer_settings(self, resize_window: bool = False):
        if hasattr(self, 'waveform'):
            if self._show_spectrum:
                self.waveform.setMinimumHeight(int(getattr(self, '_waveform_expanded_min_height', 120)))
                self.waveform.setMaximumHeight(16777215)
                self.waveform.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            else:
                self.waveform.setMinimumHeight(0)
                self.waveform.setMaximumHeight(0)
                self.waveform.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.waveform.setVisible(self._show_spectrum)
            if not self._show_spectrum:
                self.waveform.clear()
        if hasattr(self, '_spectrum_timer'):
            if self._show_spectrum:
                if not self._spectrum_timer.isActive():
                    self._spectrum_timer.start(60)
            else:
                self._spectrum_timer.stop()
                self._clear_visual_audio_queue()
        self._apply_reference_geometry(resize_window=resize_window)

    def _refresh_audio_control_buttons(self):
        if hasattr(self, 'btn_mute'):
            self.btn_mute.set_active(self._muted)
            self.btn_mute.set_icon_text("🔇" if self._muted else "🔊")
        if hasattr(self, 'btn_scan_mute'):
            self.btn_scan_mute.set_active(self._scan_mute_enabled)
            self.btn_scan_mute.set_icon_text("🔇" if self._scan_mute_enabled else "🔊")

    def _effective_audio_muted(self) -> bool:
        return self._muted or (self._scan_mute_enabled and self._scanning)

    def _toggle_mute(self):
        self._muted = not self._muted
        self._refresh_audio_control_buttons()

    def _toggle_scan_mute(self):
        self._scan_mute_enabled = not self._scan_mute_enabled
        self._refresh_audio_control_buttons()

    def _queue_visual_audio(self, chunk: np.ndarray):
        if not self._show_spectrum:
            return
        data = np.asarray(chunk, dtype=np.float32)
        if data.size == 0:
            return
        with self._visual_lock:
            self._visual_audio_queue.append(data)

    def _clear_visual_audio_queue(self):
        with self._visual_lock:
            self._visual_audio_queue.clear()

    def _drain_visual_audio_queue(self):
        chunks: List[np.ndarray] = []
        with self._visual_lock:
            while self._visual_audio_queue:
                chunks.append(self._visual_audio_queue.popleft())

        if not chunks:
            return False

        waveform_visible = hasattr(self, 'waveform') and self.waveform.isVisible()
        if not waveform_visible:
            return False

        for chunk in chunks:
            self.waveform.push_samples(chunk)
        return True

    def _set_status_label(self, label: QLabel, text: str, color: str):
        if label.text() != text:
            label.setText(text)
        style = f"color: {color}; {self._status_style}"
        if label.property("_cached_style") != style:
            label.setStyleSheet(style)
            label.setProperty("_cached_style", style)

    def _clear_sample_queue(self):
        with self._sample_queue_lock:
            self._sample_queue.clear()
            self._sample_queue_high_water = 0
            self._sample_queue_drop_count = 0
            self._sample_process_ms_ema = 0.0
            self._sample_process_peak_ms = 0.0
        self._sample_queue_event.clear()

    def _enqueue_sample_batch(self, source: str, iq_samples: np.ndarray):
        if self._closing:
            return

        data = np.asarray(iq_samples, dtype=np.complex64)
        if data.size == 0:
            return

        with self._pipeline_lock:
            generation = self._pipeline_generation

        with self._sample_queue_lock:
            if len(self._sample_queue) == self._sample_queue.maxlen:
                self._sample_queue.popleft()
                self._sample_queue_drop_count += 1
            self._sample_queue.append((source, generation, data))
            self._sample_queue_high_water = max(self._sample_queue_high_water, len(self._sample_queue))
            self._sample_queue_event.set()

    def _enqueue_sim_samples(self, iq_samples: np.ndarray):
        self._enqueue_sample_batch("sim", iq_samples)

    def _enqueue_sdr_samples(self, iq_samples: np.ndarray):
        self._enqueue_sample_batch("sdr", iq_samples)

    def _sample_processor_loop(self):
        while not self._sample_processor_stop.is_set():
            self._sample_queue_event.wait(timeout=0.1)
            if self._sample_processor_stop.is_set():
                break

            while True:
                with self._sample_queue_lock:
                    if not self._sample_queue:
                        self._sample_queue_event.clear()
                        break
                    source, generation, iq_samples = self._sample_queue.popleft()
                    queue_depth = len(self._sample_queue)

                if not self._playing:
                    continue

                batch_started = time.perf_counter()

                with self._pipeline_lock:
                    if generation != self._pipeline_generation:
                        continue

                    if source == "sim":
                        if not self._use_sim:
                            continue
                        audio, mpx, rms = self._demod_sim.demodulate(iq_samples)
                        rds_decoder = self._rds_sim
                    else:
                        if self._use_sim:
                            continue
                        audio, mpx, rms = self._demod_hw.demodulate(iq_samples)
                        rds_decoder = self._rds_hw

                    should_process_rds = (
                        self._rds_enabled
                        and len(mpx) > 0
                        and time.monotonic() >= self._rds_resume_at
                        and queue_depth < AUDIO_QUEUE_PRESSURE_THRESHOLD
                    )
                    if should_process_rds:
                        rds_decoder.process_mpx(mpx)

                if generation != self._pipeline_generation or not self._playing:
                    continue

                if len(audio) > 0:
                    self._push_audio(iq_samples, audio, mpx, rms)

                process_ms = (time.perf_counter() - batch_started) * 1000.0
                if self._sample_process_ms_ema <= 0.0:
                    self._sample_process_ms_ema = process_ms
                else:
                    self._sample_process_ms_ema = (self._sample_process_ms_ema * 0.82) + (process_ms * 0.18)
                self._sample_process_peak_ms = max(self._sample_process_peak_ms, process_ms)

    # ─── Actions ────────────────────────────────────────────

    def _set_mode(self, mode: str):
        pass  # FM only — nothing to switch

    def _sync_tuned_frequency(self, flush_stream: bool = False):
        freq_hz = self._frequency * 1e6
        self._sim.set_frequency(freq_hz)
        if self._playing and not self._use_sim:
            self._sdr.retune(freq_hz, flush_stream=flush_stream)
            return
        self._sdr.set_frequency(freq_hz)

    def _current_rds_state(self) -> Tuple[str, str, str]:
        if self._use_sim:
            return self._sim.get_rds_state()
        return self._rds_hw.get_state()

    def _clear_rds_display(self, tuning: bool = False):
        self._rds_station = ""
        self._rds_text = ""
        self._rds_pi = ""
        base = format_station_label(self._frequency)
        if not self._rds_enabled:
            self.vfd.set_rds_text(f"{base} | RDS Off" if self._playing else base)
            self.ind_rds.set_on(False)
            return
        if self._playing and tuning:
            self.vfd.set_rds_text(f"{base} | Tuning...")
        elif self._playing:
            self.vfd.set_rds_text(f"{base} | No RDS")
        else:
            self.vfd.set_rds_text(base)
        self.ind_rds.set_on(False)

    def _reset_active_pipeline(self):
        with self._pipeline_lock:
            self._pipeline_generation += 1
            if self._use_sim:
                self._demod_sim.reset()
                self._rds_sim.reset()
            else:
                self._demod_hw.reset()
                self._rds_hw.reset()

        self._signal_level = 0.0
        self._quality_level = 0.0
        self._signal_level_raw = 0.0
        self._quality_level_raw = 0.0
        self._scan_detect_level = 0.0
        self._station_detect_level = 0.0
        self._stereo_detect_level = 0.0
        self._audio_callback_status = ""
        self._rds_resume_at = time.monotonic() + 0.9
        self._clear_sample_queue()
        self._clear_audio_buffer()
        self._clear_visual_audio_queue()
        self.waveform.clear()
        self._clear_rds_display(tuning=self._playing)

    def _on_frequency_changed(self, freq: float):
        freq = clamp_frequency(freq)
        changed = abs(freq - self._frequency) >= 0.05
        self._frequency = freq
        self.vfd.set_frequency(self._frequency)
        self.status_freq.setText(f"{self._frequency:.1f} MHz")
        if changed:
            blocked_pi, _, _ = self._current_rds_state()
            self._rds_blocked_pi = blocked_pi
            self._rds_ignore_until = time.monotonic() + 12.0
            self._last_tune_at = time.monotonic()
            self._hardware_watchdog_grace_until = self._last_tune_at + 1.8
            if self._scanning:
                self._scan_next_action_at = self._last_tune_at + SCAN_SETTLE_SECONDS
            self._reset_active_pipeline()
            if self._playing:
                with self._audio_lock:
                    self._audio_play_started_at = self._last_tune_at
        self._sync_tuned_frequency(flush_stream=changed)
        if not self._playing:
            self._clear_rds_display(tuning=False)

    def _set_frequency_from_input(self, freq: float):
        self._active_preset = -1
        if abs(freq - self._frequency) < 0.05:
            self._on_frequency_changed(freq)
        else:
            self.tune_knob.set_value(freq)
        self._update_preset_buttons()

    def _nudge_freq(self, delta: float):
        new_freq = clamp_frequency(self._frequency + delta)
        if abs(new_freq - self._frequency) < 0.05:
            return
        self._active_preset = -1
        self.tune_knob.set_value(new_freq)
        self._update_preset_buttons()

    def _reset_scan_search_state(self):
        self._scan_candidate_freq = None
        self._scan_candidate_quality = 0.0
        self._scan_confirm_remaining = 0
        self._scan_last_freq = None
        self._scan_last_quality = 0.0

    def _scan_required_quality(self) -> float:
        return min(SCAN_REQUIRED_MAX, SCAN_REQUIRED_BASE + self._squelch / SCAN_REQUIRED_SQUELCH_SCALE)

    def _scan_release_quality(self) -> float:
        return max(SCAN_RELEASE_FLOOR, self._scan_required_quality() - SCAN_RELEASE_MARGIN)

    def _advance_scan_frequency(self):
        next_freq = self._frequency + self._scan_direction * SCAN_STEP_MHZ
        if next_freq > 108.0:
            next_freq = 87.5
        elif next_freq < 87.5:
            next_freq = 108.0
        self._scan_steps += 1
        self._active_preset = -1
        self._update_preset_buttons()
        self.tune_knob.set_value(round(next_freq, 1))
        self._scan_next_action_at = time.monotonic() + SCAN_SETTLE_SECONDS

    def _scan_stop(self):
        self._scanning = False
        self._scan_next_action_at = 0.0
        self._scan_steps = 0
        self._scan_wait_for_release = False
        self._reset_scan_search_state()
        self.btn_scan_up.set_active(False)
        self.btn_scan_down.set_active(False)

    def _update_scan(self, now: float):
        if not self._scanning or not self._playing:
            return
        if now < self._scan_next_action_at:
            return

        current_freq = self._frequency
        current_quality = self._scan_detect_level
        required_quality = self._scan_required_quality()

        if self._scan_wait_for_release:
            if current_quality > self._scan_release_quality():
                self._scan_last_freq = current_freq
                self._scan_last_quality = current_quality
                self._advance_scan_frequency()
                return
            self._scan_wait_for_release = False
            self._reset_scan_search_state()

        if self._scan_confirm_remaining > 0:
            if current_quality > self._scan_candidate_quality:
                self._scan_candidate_freq = current_freq
                self._scan_candidate_quality = current_quality
            self._scan_last_freq = current_freq
            self._scan_last_quality = current_quality
            self._scan_confirm_remaining -= 1

            if self._scan_confirm_remaining == 0:
                best_freq = self._scan_candidate_freq or current_freq
                best_quality = max(self._scan_candidate_quality, current_quality)
                self._reset_scan_search_state()
                if best_quality >= required_quality + SCAN_CONFIRM_MARGIN:
                    self._scan_stop()
                    if abs(best_freq - self._frequency) >= 0.05:
                        self.tune_knob.set_value(best_freq)
                    return

            self._advance_scan_frequency()
            return

        candidate_freq = current_freq
        candidate_quality = current_quality
        if self._scan_last_freq is not None and self._scan_last_quality > candidate_quality:
            candidate_freq = self._scan_last_freq
            candidate_quality = self._scan_last_quality

        self._scan_last_freq = current_freq
        self._scan_last_quality = current_quality

        if self._scan_steps > 0 and candidate_quality >= required_quality:
            self._scan_candidate_freq = candidate_freq
            self._scan_candidate_quality = candidate_quality
            self._scan_confirm_remaining = SCAN_CONFIRM_STEPS

        self._advance_scan_frequency()

    def _on_volume_changed(self, val: float):
        self._volume = int(val)

    def _on_squelch_changed(self, val: float):
        self._squelch = int(val)

    def _stop_playback(self):
        self._scan_stop()
        self._playing = False
        self._last_audio_push_at = 0.0
        self._hardware_watchdog_grace_until = 0.0
        self.btn_play.set_active(False)
        if self._use_sim:
            self._sim.stop()
        else:
            self._sdr.stop_streaming(wait=True)
        self._clear_sample_queue()
        self._stop_audio()
        self._signal_level = 0.0
        self._quality_level = 0.0
        self._signal_level_raw = 0.0
        self._quality_level_raw = 0.0
        self._scan_detect_level = 0.0
        self._station_detect_level = 0.0
        self._stereo_detect_level = 0.0
        self._clear_visual_audio_queue()
        self.waveform.clear()
        self._clear_rds_display(tuning=False)

    def _start_audio(self):
        """Start audio output stream."""
        if self._audio_stream is not None:
            return
        self._configure_audio_buffer(self._audio_output_rate)
        try:
            import sounddevice as sd
            self._audio_error_msg = ""
            self._audio_callback_status = ""
            self._audio_primed = False
            stream_blocksize = self._audio_stream_blocksize
            stream_latency = "high" if not self._use_sim else max(
                0.10,
                min(0.24, (self._audio_stream_blocksize / max(self._audio_output_rate, 1)) * 5.0),
            )
            stream_kwargs = dict(
                samplerate=self._audio_output_rate,
                channels=1,
                dtype='float32',
                blocksize=stream_blocksize,
                latency=stream_latency,
                callback=self._audio_callback
            )
            if self._audio_output_device is not None:
                stream_kwargs["device"] = self._audio_output_device
            self._audio_stream = sd.OutputStream(**stream_kwargs)
            self._audio_stream.start()
        except Exception as e:
            self._audio_stream = None
            self._audio_error_msg = str(e)

    def _reset_dsp_state(self):
        with self._pipeline_lock:
            self._pipeline_generation += 1
            old_rds_hw = getattr(self, '_rds_hw', None)
            old_rds_sim = getattr(self, '_rds_sim', None)
            self._demod_hw = self._make_demodulator(self._sdr._sample_rate)
            self._demod_sim = self._make_demodulator(240000)
            self._rds_hw = RDSDecoder(if_rate=240000)
            self._rds_sim = RDSDecoder(if_rate=240000)

        if old_rds_hw is not None:
            old_rds_hw.stop()
        if old_rds_sim is not None:
            old_rds_sim.stop()

        self._signal_level = 0.0
        self._quality_level = 0.0
        self._signal_level_raw = 0.0
        self._quality_level_raw = 0.0
        self._scan_detect_level = 0.0
        self._station_detect_level = 0.0
        self._stereo_detect_level = 0.0
        self._rds_resume_at = time.monotonic() + 0.9
        self._clear_sample_queue()
        self._clear_audio_buffer()
        self._clear_visual_audio_queue()
        self.waveform.clear()
        self._clear_rds_display(tuning=self._playing)

    def _stop_audio(self):
        if self._audio_stream:
            try:
                self._audio_stream.stop()
                self._audio_stream.close()
            except:
                pass
            self._audio_stream = None
        self._clear_audio_buffer()
        self._audio_callback_status = ""
        self._audio_primed = False

    def _clear_audio_buffer(self):
        """Reset the audio ring buffer."""
        with self._audio_lock:
            self._audio_write_pos = 0
            self._audio_read_pos = 0
            self._audio_count = 0
            self._audio_primed = False
            self._audio_empty_callbacks = 0
            self._audio_underrun_count = 0
            self._audio_min_fill = self._audio_buf_size
            self._audio_max_fill = 0
            self._audio_clock_correction_accum = 0.0
            self._audio_clock_correction_bias = 0.0
            self._audio_output_rate_estimate = float(self._audio_output_rate)
            self._audio_output_rate_window_started_at = 0.0
            self._audio_output_rate_window_frames = 0
            self._audio_input_rate_estimate = float(self._audio_output_rate)
            self._audio_input_rate_window_started_at = 0.0
            self._audio_input_rate_window_samples = 0
            self._last_signal_metrics_at = 0.0
            self._audio_play_started_at = 0.0
            self._audio_total_pushed_samples = 0
            self._audio_lt_rate_started_at = 0.0
            self._audio_lt_samples_snapshot = 0
            self._audio_total_consumed_samples = 0
            self._audio_total_callback_frames = 0
            self._last_audio_push_samples = 0
            self._last_audio_push_fill = 0
            self._last_audio_callback_frames = 0
            self._last_audio_callback_source_len = 0
            self._last_audio_callback_available = 0
            self._last_audio_callback_fill_after = 0
            self._last_audio_callback_target_fill = 0
            self._last_audio_callback_fill_delta = 0
            self._last_audio_callback_correction_frames = 0
            self._last_audio_callback_estimated_input_rate = float(self._audio_output_rate)

    def get_audio_diagnostics(self) -> Dict[str, object]:
        with self._audio_lock:
            now = time.monotonic()
            playback_elapsed = (now - self._audio_play_started_at) if self._audio_play_started_at > 0.0 else 0.0
            audio_diag = {
                "playing": bool(self._playing),
                "using_sim": bool(self._use_sim),
                "frequency_mhz": float(self._frequency),
                "buffer_count": int(self._audio_count),
                "buffer_capacity": int(self._audio_buf_size),
                "buffer_seconds": float(self._audio_count / max(self._audio_output_rate, 1)),
                "buffer_min_fill": int(self._audio_min_fill),
                "buffer_max_fill": int(self._audio_max_fill),
                "primed": bool(self._audio_primed),
                "empty_callbacks": int(self._audio_empty_callbacks),
                "underruns": int(self._audio_underrun_count),
                "input_rate_estimate": float(self._audio_input_rate_estimate),
                "output_rate": int(self._audio_output_rate),
                "target_fill": int(self._audio_target_fill),
                "prime_fill": int(self._audio_prime_fill),
                "resume_fill": int(self._audio_resume_fill),
                "low_water": int(self._audio_low_water),
                "trim_target": int(self._audio_trim_target),
                "clock_correction_accum": float(self._audio_clock_correction_accum),
                "clock_correction_bias": float(self._audio_clock_correction_bias),
                "output_rate_estimate": float(self._audio_output_rate_estimate),
                "playback_elapsed": float(playback_elapsed),
                "total_pushed_samples": int(self._audio_total_pushed_samples),
                "total_consumed_samples": int(self._audio_total_consumed_samples),
                "total_callback_frames": int(self._audio_total_callback_frames),
                "avg_push_rate": (float(self._audio_total_pushed_samples) / playback_elapsed) if playback_elapsed > 0.0 else 0.0,
                "avg_consume_rate": (float(self._audio_total_consumed_samples) / playback_elapsed) if playback_elapsed > 0.0 else 0.0,
                "avg_callback_rate": (float(self._audio_total_callback_frames) / playback_elapsed) if playback_elapsed > 0.0 else 0.0,
                "callback_frames": int(self._last_audio_callback_frames),
                "callback_source_len": int(self._last_audio_callback_source_len),
                "callback_available": int(self._last_audio_callback_available),
                "callback_fill_after": int(self._last_audio_callback_fill_after),
                "callback_target_fill": int(self._last_audio_callback_target_fill),
                "callback_fill_delta": int(self._last_audio_callback_fill_delta),
                "callback_correction_frames": int(self._last_audio_callback_correction_frames),
                "callback_estimated_input_rate": float(self._last_audio_callback_estimated_input_rate),
                "callback_status": str(self._audio_callback_status),
                "last_push_samples": int(self._last_audio_push_samples),
                "last_push_fill": int(self._last_audio_push_fill),
                "last_audio_push_age": (time.monotonic() - self._last_audio_push_at) if self._last_audio_push_at > 0.0 else None,
            }

        with self._sample_queue_lock:
            queue_diag = {
                "sample_queue_depth": int(len(self._sample_queue)),
                "sample_queue_high_water": int(self._sample_queue_high_water),
                "sample_queue_drops": int(self._sample_queue_drop_count),
                "sample_process_ms_ema": float(self._sample_process_ms_ema),
                "sample_process_peak_ms": float(self._sample_process_peak_ms),
            }

        audio_diag.update(queue_diag)
        audio_diag["sdr"] = self._sdr.diagnostics()
        return audio_diag

    def _update_audio_input_rate_estimate(self, sample_count: int, now: float):
        if self._use_sim:
            self._audio_input_rate_estimate = float(self._audio_output_rate)
            self._audio_input_rate_window_started_at = now
            self._audio_input_rate_window_samples = 0
            return
        if sample_count <= 0:
            return

        if self._audio_input_rate_window_started_at <= 0.0:
            self._audio_input_rate_window_started_at = now
            self._audio_input_rate_window_samples = 0

        self._audio_input_rate_window_samples += int(sample_count)
        elapsed = now - self._audio_input_rate_window_started_at
        if elapsed < AUDIO_INPUT_RATE_ESTIMATE_WINDOW:
            return

        nominal_rate = float(self._audio_output_rate)
        measured_rate = self._audio_input_rate_window_samples / max(elapsed, 1e-6)
        max_deviation = nominal_rate * AUDIO_INPUT_RATE_ESTIMATE_MAX_DEVIATION
        measured_rate = max(nominal_rate - max_deviation, min(nominal_rate + max_deviation, measured_rate))
        alpha = AUDIO_INPUT_RATE_ESTIMATE_ALPHA
        self._audio_input_rate_estimate = (
            self._audio_input_rate_estimate * (1.0 - alpha)
            + measured_rate * alpha
        )
        self._audio_input_rate_window_started_at = now
        self._audio_input_rate_window_samples = 0

    def _update_audio_output_rate_estimate(self, frame_count: int, now: float):
        if self._use_sim:
            self._audio_output_rate_estimate = float(self._audio_output_rate)
            self._audio_output_rate_window_started_at = now
            self._audio_output_rate_window_frames = 0
            return
        if frame_count <= 0:
            return

        if self._audio_output_rate_window_started_at <= 0.0:
            self._audio_output_rate_window_started_at = now
            self._audio_output_rate_window_frames = 0

        self._audio_output_rate_window_frames += int(frame_count)
        elapsed = now - self._audio_output_rate_window_started_at
        if elapsed < AUDIO_OUTPUT_RATE_ESTIMATE_WINDOW:
            return

        nominal_rate = float(self._audio_output_rate)
        measured_rate = self._audio_output_rate_window_frames / max(elapsed, 1e-6)
        max_deviation = nominal_rate * AUDIO_OUTPUT_RATE_ESTIMATE_MAX_DEVIATION
        measured_rate = max(nominal_rate - max_deviation, min(nominal_rate + max_deviation, measured_rate))
        alpha = AUDIO_OUTPUT_RATE_ESTIMATE_ALPHA
        self._audio_output_rate_estimate = (
            self._audio_output_rate_estimate * (1.0 - alpha)
            + measured_rate * alpha
        )
        self._audio_output_rate_window_started_at = now
        self._audio_output_rate_window_frames = 0

    def _copy_audio_ring_locked(self, start: int, count: int, cap: int) -> np.ndarray:
        if count <= 0:
            return np.array([], dtype=np.float32)

        end = start + count
        if end <= cap:
            return self._audio_ring[start:end].copy()

        first = cap - start
        chunk = np.empty(count, dtype=np.float32)
        chunk[:first] = self._audio_ring[start:cap]
        chunk[first:] = self._audio_ring[:count - first]
        return chunk

    def _audio_callback(self, outdata, frames, time_info, status):
        """sounddevice callback — read directly from ring buffer."""
        if status:
            self._audio_callback_status = str(status)
        vol = 0.0 if self._effective_audio_muted() else (self._volume / 100.0)
        outdata[:] = 0

        partial_underrun = False
        hard_underrun = False
        recovered = False
        primed_after = False
        buffered_after = 0
        callback_now = time.monotonic()

        with self._audio_lock:
            cap = self._audio_buf_size
            self._update_audio_output_rate_estimate(frames, callback_now)
            self._audio_total_callback_frames += int(frames)
            self._last_audio_callback_frames = int(frames)
            self._last_audio_callback_source_len = 0
            self._last_audio_callback_available = int(self._audio_count)
            self._last_audio_callback_fill_after = int(self._audio_count)
            self._last_audio_callback_target_fill = 0
            self._last_audio_callback_fill_delta = 0
            self._last_audio_callback_correction_frames = 0
            self._last_audio_callback_estimated_input_rate = float(self._audio_input_rate_estimate)

            if not self._audio_primed:
                resume_fill = self._audio_resume_fill if self._audio_empty_callbacks else self._audio_prime_fill
                if self._audio_count >= resume_fill:
                    self._audio_primed = True
                    self._audio_empty_callbacks = 0
                    recovered = True

            if self._audio_primed:
                available = self._audio_count
                if available <= 0:
                    hard_underrun = True
                    self._audio_empty_callbacks += 1
                    self._audio_underrun_count += 1
                    if self._audio_empty_callbacks >= AUDIO_REFILL_EMPTY_CALLBACKS:
                        self._audio_primed = False
                else:
                    source_len = min(frames, available)
                    correction_frames = 0
                    target_fill = 0
                    fill_delta = 0
                    if not self._use_sim:
                        target_fill = max(self._audio_target_fill, frames * 6)
                        estimated_input_rate = max(float(self._audio_input_rate_estimate), 1.0)
                        
                        if self._audio_lt_rate_started_at == 0.0:
                            self._audio_lt_rate_started_at = callback_now
                            self._audio_lt_samples_snapshot = self._audio_total_pushed_samples
                            
                        if self._audio_lt_rate_started_at > 0.0:
                            elapsed_lt = callback_now - self._audio_lt_rate_started_at
                            pushed_in_lt = self._audio_total_pushed_samples - self._audio_lt_samples_snapshot
                            if elapsed_lt > 12.0 and pushed_in_lt > 0:
                                nominal_rate = float(self._audio_output_rate)
                                lt_push_rate = pushed_in_lt / elapsed_lt
                                lt_push_rate = max(nominal_rate * 0.97, min(nominal_rate * 1.03, lt_push_rate))
                                estimated_input_rate = lt_push_rate
                                
                        estimated_output_rate = max(float(self._audio_output_rate_estimate), 1.0)
                        rate_matched_source = frames * (estimated_input_rate / estimated_output_rate)
                        fill_delta = available - target_fill
                        fill_deadband = max(frames, int(self._audio_output_rate * AUDIO_CLOCK_CORRECTION_DEADBAND_SECONDS))
                        fill_error = 0.0
                        if abs(fill_delta) > fill_deadband:
                            effective_fill_delta = fill_delta - math.copysign(fill_deadband, fill_delta)
                            fill_error = effective_fill_delta / max(target_fill, 1)
                        max_correction = float(AUDIO_CLOCK_CORRECTION_MAX_FRAMES)
                        self._audio_clock_correction_bias += fill_error * AUDIO_CLOCK_CORRECTION_INTEGRAL_GAIN
                        self._audio_clock_correction_bias = max(
                            -max_correction,
                            min(max_correction, self._audio_clock_correction_bias),
                        )
                        desired_source_len = rate_matched_source + (fill_error * frames * AUDIO_CLOCK_CORRECTION_GAIN) + self._audio_clock_correction_bias
                        desired_correction = max(-max_correction, min(max_correction, desired_source_len - frames))
                        self._audio_clock_correction_accum += desired_correction
                        self._audio_clock_correction_accum = max(-max_correction, min(max_correction, self._audio_clock_correction_accum))
                        correction_frames = int(math.trunc(self._audio_clock_correction_accum))
                        if correction_frames != 0:
                            self._audio_clock_correction_accum -= correction_frames
                        source_len = max(1, min(available, frames + correction_frames))

                    self._last_audio_callback_source_len = int(source_len)
                    self._last_audio_callback_available = int(available)
                    self._last_audio_callback_target_fill = int(target_fill)
                    self._last_audio_callback_fill_delta = int(fill_delta)
                    self._last_audio_callback_correction_frames = int(correction_frames)
                    self._last_audio_callback_estimated_input_rate = float(self._audio_input_rate_estimate)

                    read_pos = self._audio_read_pos
                    if vol > 0.0:
                        if source_len == frames:
                            end = read_pos + source_len
                            if end <= cap:
                                outdata[:frames, 0] = self._audio_ring[read_pos:end] * vol
                            else:
                                first = cap - read_pos
                                outdata[:first, 0] = self._audio_ring[read_pos:cap] * vol
                                outdata[first:frames, 0] = self._audio_ring[:frames - first] * vol
                        else:
                            source = self._copy_audio_ring_locked(read_pos, source_len, cap)
                            if source_len == 1:
                                outdata[:frames, 0] = source[0] * vol
                            else:
                                source_positions = np.arange(source_len, dtype=np.float64)
                                target_positions = np.linspace(0.0, source_len - 1, num=frames, dtype=np.float64)
                                outdata[:frames, 0] = np.interp(target_positions, source_positions, source).astype(np.float32) * vol
                    self._audio_read_pos = (self._audio_read_pos + source_len) % cap
                    self._audio_count -= source_len
                    if self._audio_count <= 0:
                        self._audio_count = 0
                    self._audio_total_consumed_samples += int(source_len)
                    self._last_audio_callback_fill_after = int(self._audio_count)
                    if available < max(frames - AUDIO_CLOCK_CORRECTION_MAX_FRAMES, 1):
                        partial_underrun = True
                        self._audio_underrun_count += 1
                    else:
                        self._audio_empty_callbacks = 0

            primed_after = self._audio_primed
            buffered_after = self._audio_count
            if primed_after:
                self._audio_min_fill = min(self._audio_min_fill, buffered_after)

        if not status:
            if hard_underrun:
                self._audio_callback_status = "Buffer refill" if not primed_after else "Recovering"
            elif partial_underrun:
                self._audio_callback_status = "Low buffer"
            else:
                self._audio_callback_status = ""

    def _estimate_stereo_level(self, mpx_signal: np.ndarray) -> float:
        if len(mpx_signal) < 256:
            return 0.0

        window = np.asarray(mpx_signal[-min(len(mpx_signal), STEREO_PILOT_ANALYSIS_SAMPLES):], dtype=np.float32)
        sample_rms = float(np.sqrt(np.mean(window ** 2))) if len(window) > 0 else 0.0
        if sample_rms <= 1e-6:
            return 0.0

        phase_scale = (2.0 * math.pi) / 240000.0
        phases = phase_scale * np.arange(len(window), dtype=np.float64)

        def tone_strength(freq_hz: float) -> float:
            oscillator = np.exp(-1j * phases * freq_hz)
            return float(abs(np.dot(window, oscillator)) * (2.0 / max(len(window), 1)))

        pilot_strength = tone_strength(19000.0)
        neighbor_strength = 0.5 * (tone_strength(18000.0) + tone_strength(20000.0))
        pilot_ratio = max(0.0, pilot_strength - neighbor_strength * 1.15) / sample_rms
        return clamp_unit((pilot_ratio - STEREO_PILOT_RATIO_FLOOR) / STEREO_PILOT_RATIO_SPAN)

    def _update_signal_metrics(self, iq_samples: np.ndarray, audio: np.ndarray, mpx_signal: np.ndarray, rms: float):
        if len(iq_samples) == 0 or len(audio) == 0:
            self._signal_level = 0.0
            self._quality_level = 0.0
            self._signal_level_raw = 0.0
            self._quality_level_raw = 0.0
            self._scan_detect_level = 0.0
            self._station_detect_level = 0.0
            self._stereo_detect_level = 0.0
            return

        rf_power = float(np.mean(np.abs(iq_samples) ** 2))
        rf_score = clamp_unit((10.0 * math.log10(max(rf_power, 1e-12)) + 18.0) / 18.0)

        if len(audio) > 1:
            noise_rms = float(np.sqrt(np.mean(np.diff(audio) ** 2)))
        else:
            noise_rms = 1.0
        quiet_score = clamp_unit(1.0 - noise_rms * 16.0)
        audio_level = clamp_unit(rms * 3.6)

        signal_level = clamp_unit(max(audio_level, rf_score))
        quality_level = clamp_unit(quiet_score * 0.88 + rf_score * 0.12)
        scan_detect_level = clamp_unit(max(quality_level, rf_score * 0.68 + quality_level * 0.32))
        if self._use_sim:
            stereo_detect_level = scan_detect_level if scan_detect_level >= STATION_INDICATOR_RELEASE else 0.0
        elif scan_detect_level >= STATION_INDICATOR_RELEASE and len(mpx_signal) > 0:
            stereo_detect_level = self._estimate_stereo_level(mpx_signal)
        else:
            stereo_detect_level = 0.0

        self._signal_level_raw = signal_level
        self._quality_level_raw = quality_level
        self._scan_detect_level = scan_detect_level
        self._station_detect_level = self._station_detect_level * 0.68 + scan_detect_level * 0.32

        self._signal_level = self._signal_level * 0.55 + signal_level * 0.45
        self._quality_level = self._quality_level * 0.55 + quality_level * 0.45
        self._stereo_detect_level = self._stereo_detect_level * 0.70 + stereo_detect_level * 0.30

    def _push_audio(self, iq_samples: np.ndarray, audio: np.ndarray, mpx: np.ndarray, rms: float):
        """Write demodulated audio directly into the ring buffer."""
        if not self._playing or len(audio) == 0:
            return

        data = audio.astype(np.float32, copy=False)
        n = len(data)
        buffered_after_write = 0
        now = time.monotonic()

        self._last_audio_push_at = now

        with self._audio_lock:
            cap = self._audio_buf_size
            if n >= cap:
                data = data[-cap:]
                n = len(data)
                self._audio_write_pos = 0
                self._audio_read_pos = 0
                self._audio_count = 0

            if self._audio_play_started_at > 0.0 and (now - self._audio_play_started_at) > 2.0:
                self._update_audio_input_rate_estimate(n, now)

            # Drop oldest if we'd overflow
            space = cap - self._audio_count
            if n > space:
                drop = n - space
                self._audio_read_pos = (self._audio_read_pos + drop) % cap
                self._audio_count -= drop

            # Write in up to two segments (wrap around ring)
            end = self._audio_write_pos + n
            if end <= cap:
                self._audio_ring[self._audio_write_pos:end] = data
            else:
                first = cap - self._audio_write_pos
                self._audio_ring[self._audio_write_pos:cap] = data[:first]
                self._audio_ring[:n - first] = data[first:]
            self._audio_write_pos = (self._audio_write_pos + n) % cap
            self._audio_count += n
            self._audio_max_fill = max(self._audio_max_fill, self._audio_count)
            self._audio_total_pushed_samples += int(n)

            if self._audio_count > self._audio_trim_threshold:
                trim = self._audio_count - self._audio_trim_target
                self._audio_read_pos = (self._audio_read_pos + trim) % cap
                self._audio_count -= trim
            buffered_after_write = self._audio_count
            self._last_audio_push_samples = int(n)
            self._last_audio_push_fill = int(buffered_after_write)

        if buffered_after_write >= self._audio_low_water:
            self._queue_visual_audio(data)

        now = time.monotonic()
        if self._scanning:
            metrics_interval = AUDIO_SIGNAL_METRICS_INTERVAL_SCAN
        else:
            metrics_interval = (
                AUDIO_SIGNAL_METRICS_INTERVAL
                if buffered_after_write >= self._audio_target_fill else
                AUDIO_SIGNAL_METRICS_INTERVAL_LOW
            )
        if now - self._last_signal_metrics_at >= metrics_interval:
            self._last_signal_metrics_at = now
            self._update_signal_metrics(iq_samples, data, mpx, rms)

    @Slot(bool)
    def _on_device_connected(self, connected: bool):
        if connected:
            self._use_sim = False
            self._device_status = "Connected"
            self._device_error_msg = ""
            self._sync_tuned_frequency()
        else:
            self._device_status = "Disconnected"

    @Slot(str)
    def _on_device_error(self, msg: str):
        self._device_error_msg = msg
        self._device_status = "Error"

    def _try_connect_hardware(self, selection=None):
        """Attempt RTL-SDR connection; fall back silently to simulated mode."""
        self._sync_tuned_frequency()
        normalized = self._preferred_device_selection if selection is None else normalize_device_selection(selection)

        if normalized == "simulated":
            self._apply_hardware_probe_result(None, self._sdr._device_index)
            return

        candidates: List[int]
        if normalized == "auto":
            candidates = list_rtl_sdr_device_indices()
            if self._sdr._device_index in candidates:
                candidates = [self._sdr._device_index] + [index for index in candidates if index != self._sdr._device_index]
        else:
            candidates = [int(normalized)]

        last_error = ""
        for candidate_index in candidates:
            device, error = open_rtl_sdr_device(
                candidate_index,
                self._sdr._sample_rate,
                self._frequency * 1e6,
                self._sdr._gain,
            )
            if device is not None:
                self._apply_hardware_probe_result(device, candidate_index)
                return
            last_error = error

        self._apply_hardware_probe_result(None, candidates[0] if candidates else 0)
        if last_error:
            self._device_error_msg = last_error

    def _open_settings(self):
        was_playing = self._playing
        previous_settings = dict(self._runtime_settings)
        dlg = SettingsDialog(settings=self._runtime_settings, skin_name=self._skin_name, parent=self)
        dlg.setWindowModality(Qt.ApplicationModal)
        if dlg.exec() != QDialog.Accepted:
            return

        new_settings = dlg.runtime_settings()
        selected_theme = normalize_skin_name(dlg.theme_combo.currentText())
        target_selection = new_settings["device_selection"]
        target_index = self._device_probe_index(target_selection)
        target_simulated = target_selection == "simulated"

        needs_device_transition = False
        if target_simulated:
            needs_device_transition = not self._use_sim or self._sdr._sdr is not None
        else:
            needs_device_transition = self._use_sim or target_index != self._sdr._device_index or not self._sdr.connected

        audio_rate_changed = new_settings["audio_output_rate"] != previous_settings["audio_output_rate"]
        audio_blocksize_changed = new_settings["audio_blocksize"] != previous_settings["audio_blocksize"]
        audio_device_changed = new_settings["audio_output_device"] != previous_settings["audio_output_device"]
        needs_audio_restart = audio_rate_changed or audio_blocksize_changed or audio_device_changed
        needs_dsp_reset = (
            audio_rate_changed
            or new_settings["deemphasis_us"] != previous_settings["deemphasis_us"]
            or new_settings["bandwidth_mode"] != previous_settings["bandwidth_mode"]
        )
        rds_changed = new_settings["rds_enabled"] != previous_settings["rds_enabled"]

        if needs_device_transition and was_playing:
            self._stop_playback()
        elif needs_audio_restart and was_playing:
            self._stop_audio()

        self._runtime_settings = new_settings
        self._app_settings.update(new_settings)
        self._preferred_device_selection = new_settings["device_selection"]
        self._stereo_enabled = bool(new_settings["stereo_enabled"])
        self._rds_enabled = bool(new_settings["rds_enabled"])
        self._show_spectrum = bool(new_settings["show_spectrum"])
        self._audio_output_device = new_settings["audio_output_device"]
        self._audio_blocksize = new_settings["audio_blocksize"]
        if needs_audio_restart:
            self._configure_audio_buffer(new_settings["audio_output_rate"])
        else:
            self._audio_output_rate = new_settings["audio_output_rate"]
            self._audio_blocksize = normalize_audio_blocksize(self._audio_blocksize)

        self._sdr._device_index = self._device_probe_index(self._preferred_device_selection)
        self._sdr.set_gain(self._current_gain_value())
        self._apply_visualizer_settings(resize_window=True)

        if needs_dsp_reset or rds_changed:
            self._reset_dsp_state()
        elif not self._rds_enabled:
            self._clear_rds_display(tuning=self._playing)

        if selected_theme != self._skin_name:
            self._apply_skin(selected_theme, persist=False)

        self._app_settings["skin"] = self._skin_name
        self._app_settings.pop("show_waterfall", None)
        self._app_settings["_spectrum_hidden_default_v1"] = True
        save_app_settings(self._app_settings)

        if target_simulated:
            if not self._use_sim or self._sdr._sdr is not None:
                self._sdr.disconnect_device()
            self._device_status = "Simulated"
            self._device_error_msg = ""
            self._use_sim = True
            self._sync_tuned_frequency()
        else:
            if needs_device_transition:
                self._device_status = "Connecting…"
                self._device_error_msg = ""
                self._sdr.disconnect_device()
                self._try_connect_hardware(target_selection)
            else:
                self._use_sim = False
                self._device_status = "Connected"
                self._device_error_msg = ""
                self._sync_tuned_frequency()

        if was_playing and needs_device_transition:
            self._toggle_play()
        elif was_playing and needs_audio_restart:
            self._start_audio()

    # ─── Presets ────────────────────────────────────────────

    def _load_presets(self) -> List[Dict]:
        path = os.path.expanduser("~/.pyradio_sdr_presets.json")
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            except:
                pass
        return []

    def _save_presets(self):
        path = os.path.expanduser("~/.pyradio_sdr_presets.json")
        try:
            with open(path, 'w') as f:
                json.dump(self._presets, f)
        except:
            pass

    def _recall_preset(self, idx: int):
        if idx < len(self._presets):
            p = self._presets[idx]
            self._active_preset = idx
            freq = clamp_frequency(p.get("freq", 87.5))
            if abs(freq - self._frequency) < 0.05:
                self._on_frequency_changed(freq)
            else:
                self.tune_knob.set_value(freq)
            for i, btn in enumerate(self.preset_buttons):
                btn.set_active(i == idx)

    def _save_preset(self):
        """Save current station to next available preset."""
        name = format_station_label(self._frequency)
        preset = {
            "name": name,
            "freq": self._frequency
        }
        if len(self._presets) < 8:
            self._presets.append(preset)
        else:
            self._presets[7] = preset  # Overwrite last

        self._update_preset_buttons()
        self._save_presets()

    def _delete_preset(self):
        if 0 <= self._active_preset < len(self._presets):
            self._presets.pop(self._active_preset)
            self._active_preset = -1
            self._update_preset_buttons()
            self._save_presets()

    def _update_preset_buttons(self):
        for i, btn in enumerate(self.preset_buttons):
            if i < len(self._presets):
                btn.set_text(self._presets[i].get("name", ""))
            else:
                btn.set_text("")
            btn.set_active(i == self._active_preset)

    # ─── Periodic UI updates ────────────────────────────────

    def _update_ui(self):
        """Update indicators and meters at ~20fps."""
        now = time.monotonic()
        if self._playing:
            self._maybe_recover_hardware_stream(now)
        self._update_scan(now)

        if self._playing:
            target_sig = self._signal_level
            target_qual = self._quality_level
        else:
            target_sig = 0.0
            target_qual = 0.0

        current_sig = self.sig_meter._level
        current_qual = self.qual_meter._level
        self.sig_meter.set_level(current_sig + (target_sig - current_sig) * 0.15)
        self.qual_meter.set_level(current_qual + (target_qual - current_qual) * 0.15)

        station_threshold = STATION_INDICATOR_RELEASE if self.ind_signal._on else STATION_INDICATOR_THRESHOLD
        station_active = self._playing and self._station_detect_level > station_threshold
        self.ind_signal.set_on(station_active)
        stereo_threshold = STEREO_INDICATOR_RELEASE if self.ind_stereo._on else STEREO_INDICATOR_THRESHOLD
        stereo_active = station_active and self._stereo_enabled and self._stereo_detect_level > stereo_threshold
        self.ind_stereo.set_on(stereo_active)
        _, station_name, radio_text = self._current_rds_state()
        has_rds = self._rds_enabled and bool(station_name.strip() or radio_text.strip())
        self.ind_rds.set_on(self._playing and has_rds)
        self.vfd.set_stereo(stereo_active)

        # ── Status bar ──
        sdr_display = self._device_status
        hardware_active = self._playing and not self._use_sim and self._device_status == "Connected"
        if self._device_error_msg:
            sdr_display = f"Err: {self._device_error_msg[:30]}"
        elif self._device_status == "Connected":
            sdr_display = getattr(self._sdr, '_device_label', '') or "Connected"

        if hardware_active and not self._device_error_msg:
            sdr_color = skin_value('status_ok', self._skin_name)
        elif self._device_status == "Error" or self._device_error_msg:
            sdr_color = skin_value('status_error', self._skin_name)
        else:
            sdr_color = skin_value('status_warning', self._skin_name)
        self._set_status_label(self.status_sdr, f"\u25cf SDR: {sdr_display}", sdr_color)

        self._set_status_label(self.status_freq, f"{self._frequency:.1f} MHz", skin_value('status_freq', self._skin_name))

        with self._audio_lock:
            audio_count = self._audio_count

        if self._audio_error_msg:
            self._set_status_label(self.status_audio, f"\u25cf Audio: {self._audio_error_msg[:24]}", skin_value('status_error', self._skin_name))
        elif self._playing and self._audio_stream is None:
            self._set_status_label(self.status_audio, "\u25cf Audio: Starting", skin_value('status_warning', self._skin_name))
        elif self._playing and self._effective_audio_muted():
            self._set_status_label(self.status_audio, "\u25cf Audio: Muted", skin_value('status_warning', self._skin_name))
        elif self._playing and not self._audio_primed:
            self._set_status_label(self.status_audio, "\u25cf Audio: Buffering", skin_value('status_warning', self._skin_name))
        elif self._playing and self._audio_callback_status:
            self._set_status_label(self.status_audio, f"\u25cf Audio: {self._audio_callback_status[:24]}", skin_value('status_warning', self._skin_name))
        elif self._playing:
            self._set_status_label(self.status_audio, "\u25cf Audio: Playing", skin_value('status_ok', self._skin_name))
        else:
            self._set_status_label(self.status_audio, "\u25cf Audio: Stopped", skin_value('status_idle', self._skin_name))

        if not self._playing:
            target_buf_level = 0.0
        elif not self._audio_primed:
            target_buf_level = 0.0
        else:
            buf_reference = max(self._audio_prime_fill - self._audio_low_water, 1)
            target_buf_level = clamp_unit((audio_count - self._audio_low_water) / buf_reference)
        current_buf_level = getattr(self.status_buffer, '_level', 0.0)
        self.status_buffer.set_level(current_buf_level + (target_buf_level - current_buf_level) * 0.22)

    def _update_waveform_display(self):
        """Trigger waveform repaint at ~25 fps."""
        has_new_visuals = self._drain_visual_audio_queue()
        if has_new_visuals and self.waveform.isVisible():
            self.waveform.update()

    def _auto_scan_up(self):
        """Start auto-scanning upward."""
        self._scanning = True
        self._scan_direction = 1
        self._scan_next_action_at = time.monotonic()
        self._scan_steps = 0
        self._scan_wait_for_release = True
        self._reset_scan_search_state()
        self.btn_scan_up.set_active(True)
        self.btn_scan_down.set_active(False)
        self._active_preset = -1
        self._update_preset_buttons()
        if not self._playing:
            self._toggle_play()
            self._scan_next_action_at = time.monotonic() + SCAN_SETTLE_SECONDS

    def _auto_scan_down(self):
        """Start auto-scanning downward."""
        self._scanning = True
        self._scan_direction = -1
        self._scan_next_action_at = time.monotonic()
        self._scan_steps = 0
        self._scan_wait_for_release = True
        self._reset_scan_search_state()
        self.btn_scan_down.set_active(True)
        self.btn_scan_up.set_active(False)
        self._active_preset = -1
        self._update_preset_buttons()
        if not self._playing:
            self._toggle_play()
            self._scan_next_action_at = time.monotonic() + SCAN_SETTLE_SECONDS

    def _update_rds_display(self):
        """Poll decoded RDS data and push to VFD display."""
        if not self._playing:
            return

        if not self._rds_enabled:
            self.vfd.set_rds_text(f"{format_station_label(self._frequency)} | RDS Off")
            self.ind_rds.set_on(False)
            return

        pi, station_name, radio_text = self._current_rds_state()
        now = time.monotonic()
        if self._rds_blocked_pi and pi and pi != self._rds_blocked_pi:
            self._rds_blocked_pi = ""
            self._rds_ignore_until = 0.0
        elif self._rds_blocked_pi and now < self._rds_ignore_until and pi == self._rds_blocked_pi:
            pi, station_name, radio_text = "", "", ""

        station = station_name.strip()
        rt = format_display_radiotext(radio_text.strip())

        if station != self._rds_station or rt != self._rds_text or pi != self._rds_pi:
            self._rds_station = station
            self._rds_text = rt
            self._rds_pi = pi

        if station or rt:
            display = station if station else format_station_label(self._frequency)
            if rt:
                display = f"{display} | {rt}" if display else rt
            self.vfd.set_rds_text(display)
            self.ind_rds.set_on(True)
        elif pi:
            self.vfd.set_rds_text(f"PI {pi} | Decoding RDS")
            self.ind_rds.set_on(True)
        else:
            age = time.monotonic() - self._last_tune_at
            if age < 6.0:
                self.vfd.set_rds_text(f"{format_station_label(self._frequency)} | Tuning...")
            else:
                self.vfd.set_rds_text(f"{format_station_label(self._frequency)} | No RDS")
            self.ind_rds.set_on(False)

    def closeEvent(self, event):
        """Clean up on exit."""
        self._closing = True
        self._set_loading_overlay(False)
        self._stop_playback()
        self._sample_processor_stop.set()
        self._sample_queue_event.set()
        self._sim.stop()
        self._rds_hw.stop()
        self._rds_sim.stop()
        self._sdr.disconnect_device()
        if self._sample_processor_thread.is_alive():
            self._sample_processor_thread.join(timeout=1.0)
        destroy_windows_icon_handles(self._native_icon_handles)
        self._native_icon_handles = []
        self._save_presets()
        event.accept()

    def _toggle_play(self):
        if self._playing:
            self._stop_playback()
            return

        self._playing = True
        self.btn_play.set_active(True)
        self._audio_error_msg = ""
        self._audio_callback_status = ""
        self._last_tune_at = time.monotonic()
        self._last_audio_push_at = self._last_tune_at
        self._hardware_watchdog_grace_until = self._last_tune_at + 2.0
        self._last_hardware_recovery_at = 0.0
        self._rds_blocked_pi = ""
        self._rds_ignore_until = 0.0
        self._rds_resume_at = self._last_tune_at + 0.9
        self._reset_active_pipeline()
        self._sync_tuned_frequency(flush_stream=False)
        self._start_audio()
        with self._audio_lock:
            self._audio_play_started_at = time.monotonic()
        if self._use_sim:
            self._sim.start()
        else:
            self._sdr.start_streaming()


# ═══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def main(
    on_window_shown: Optional[Callable[[], None]] = None,
    startup_pulse: Optional[Callable[[], None]] = None,
) -> int:
    set_windows_app_id()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("PyRadio SDR")
    app.setDesktopFileName("PyRadioSDR")
    app_icon = load_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    if startup_pulse is not None:
        try:
            startup_pulse()
        except Exception:
            pass

    # Attempt to load a nicer font
    app.setFont(QFont("Segoe UI", 10))

    if startup_pulse is not None:
        try:
            startup_pulse()
        except Exception:
            pass

    window = MainWindow(startup_pulse=startup_pulse)
    window.show()
    window.raise_()
    window.activateWindow()
    app.processEvents()

    if startup_pulse is not None:
        try:
            startup_pulse()
        except Exception:
            pass

    if on_window_shown is not None:
        try:
            on_window_shown()
        except Exception:
            pass

    # Recall first preset if any exist
    if window._presets:
        QTimer.singleShot(0, lambda: window._recall_preset(0))

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
