#!/usr/bin/env python3

import os
import sys
import threading
import time
import traceback

from app_metadata import APP_ICON_PATH, APP_NAME, APP_TAGLINE, APP_VERSION


APP_TITLE = APP_NAME
SPLASH_BG = "#0b1018"
SPLASH_PANEL = "#161e2b"
SPLASH_PANEL_EDGE = "#4a607f"
SPLASH_PANEL_INNER = "#1e2a3b"
SPLASH_ACCENT = "#ffb547"
SPLASH_ACCENT_SOFT = "#d79a3d"
SPLASH_TEXT = "#edf3fb"
SPLASH_TEXT_DIM = "#97aac6"
SPLASH_TEXT_MUTED = "#6f84a4"
SPLASH_LOGO_BG = "#101722"
SPLASH_LOGO_EDGE = "#30445f"
SPLASH_GLOW = "#ffd38b"
SPLASH_PROGRESS_TRACK = "#223854"
SPLASH_PROGRESS_EDGE = "#4f74b2"
SPLASH_PROGRESS_FILL = "#2d63cf"
SPLASH_PROGRESS_SHINE = "#bbd4ff"


def _resource_path(*parts: str) -> str:
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, *parts)


def _draw_radio_logo(canvas):
    canvas.create_rectangle(0, 0, 150, 150, fill=SPLASH_LOGO_BG, outline="")
    outline = "#eef4fc"
    muted = "#8ba1c2"

    canvas.create_oval(12, 12, 138, 138, outline="#2c4260", width=2)
    canvas.create_line(70, 34, 108, 48, fill=outline, width=3, capstyle="round")
    canvas.create_oval(65, 29, 73, 37, fill=outline, outline="")

    canvas.create_rectangle(40, 54, 110, 100, outline=outline, width=3)
    canvas.create_rectangle(49, 62, 79, 79, outline=outline, width=2)
    canvas.create_line(54, 70, 74, 70, fill=muted, width=2)
    canvas.create_oval(89, 63, 105, 79, outline=outline, width=2)
    canvas.create_line(89, 88, 105, 88, fill=outline, width=2)
    canvas.create_line(89, 94, 105, 94, fill=outline, width=2)
    canvas.create_line(46, 108, 104, 108, fill=muted, width=2)


def _update_progress_bar(splash, force: bool = False):
    if not splash:
        return
    progress = splash.get("progress")
    progress_fill = splash.get("progress_fill")
    progress_shine = splash.get("progress_shine")
    root = splash.get("root")
    progress_width = splash.get("progress_width")
    if progress is None or progress_fill is None or progress_shine is None or root is None or progress_width is None:
        return

    now = time.monotonic()
    if not force and now - splash.get("progress_last", 0.0) < 0.04:
        return

    phase = (splash.get("progress_phase", 0.0) + 0.065) % 1.0
    segment_width = max(68, int(progress_width * 0.28))
    travel_width = progress_width + segment_width
    left = int(phase * travel_width) - segment_width
    right = left + segment_width

    clipped_left = max(3, left)
    clipped_right = min(progress_width - 3, right)
    if clipped_left >= clipped_right:
        progress.coords(progress_fill, -40, 5, -40, 13)
        progress.coords(progress_shine, -40, 6, -40, 12)
    else:
        progress.coords(progress_fill, clipped_left, 5, clipped_right, 13)
        shine_width = max(22, int(segment_width * 0.34))
        shine_right = clipped_right - 3
        shine_left = max(clipped_left + 4, shine_right - shine_width)
        progress.coords(progress_shine, shine_left, 6, shine_right, 12)

    splash["progress_phase"] = phase
    splash["progress_last"] = now


def _pump_splash(splash, force: bool = False):
    if not splash:
        return False

    root = splash.get("root")
    if root is None:
        return False

    try:
        _update_progress_bar(splash, force=force)
        root.update_idletasks()
        root.update()
        return True
    except Exception:
        return False


def _create_splash():
    try:
        import tkinter as tk
    except Exception:
        return None

    root = tk.Tk()
    root.title(APP_TITLE)
    root.overrideredirect(True)
    root.configure(bg=SPLASH_BG)
    root.attributes("-topmost", True)

    icon_path = _resource_path(*APP_ICON_PATH)
    if os.path.exists(icon_path):
        try:
            root.iconbitmap(default=icon_path)
        except Exception:
            pass

    width, height = 516, 240
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    pos_x = max(0, (screen_w - width) // 2)
    pos_y = max(0, (screen_h - height) // 2)
    root.geometry(f"{width}x{height}+{pos_x}+{pos_y}")

    panel = tk.Frame(root, bg=SPLASH_PANEL, highlightthickness=1, highlightbackground=SPLASH_PANEL_EDGE)
    panel.pack(fill="both", expand=True, padx=1, pady=1)

    top_gloss = tk.Frame(panel, bg="#60779a", height=2)
    top_gloss.pack(fill="x")

    content = tk.Frame(panel, bg=SPLASH_PANEL)
    content.pack(fill="both", expand=True, padx=16, pady=16)

    logo_shell = tk.Frame(content, bg=SPLASH_LOGO_BG, highlightthickness=1, highlightbackground=SPLASH_LOGO_EDGE)
    logo_shell.pack(side="left", fill="y", padx=(0, 16))
    logo_canvas = tk.Canvas(logo_shell, width=150, height=150, bg=SPLASH_LOGO_BG, highlightthickness=0)
    logo_canvas.pack(padx=10, pady=10)
    _draw_radio_logo(logo_canvas)

    brand = tk.Frame(content, bg=SPLASH_PANEL)
    brand.pack(side="left", fill="both", expand=True)

    brand_mark = tk.Frame(brand, bg=SPLASH_PANEL)
    brand_mark.pack(anchor="w", pady=(8, 0))

    title_left = tk.Label(brand_mark, text="PyRadio", bg=SPLASH_PANEL, fg=SPLASH_TEXT, font=("Tahoma", 28, "bold"))
    title_left.pack(side="left")
    title_right = tk.Label(brand_mark, text=" SDR", bg=SPLASH_PANEL, fg=SPLASH_ACCENT, font=("Tahoma", 28, "bold"))
    title_right.pack(side="left")

    tagline = tk.Label(
        brand,
        text=APP_TAGLINE.upper(),
        bg=SPLASH_PANEL,
        fg=SPLASH_TEXT_DIM,
        font=("Lucida Console", 10, "bold"),
        anchor="w",
    )
    tagline.pack(anchor="w", pady=(6, 0))

    subline = tk.Label(
        brand,
        text="RTL-SDR FM receiver with car-radio styling",
        bg=SPLASH_PANEL,
        fg=SPLASH_TEXT_MUTED,
        font=("Segoe UI", 10),
        anchor="w",
    )
    subline.pack(anchor="w", pady=(12, 0))

    version_frame = tk.Frame(brand, bg=SPLASH_PANEL_INNER, highlightthickness=1, highlightbackground="#2f425d")
    version_frame.pack(anchor="w", pady=(18, 0))
    version_label = tk.Label(
        version_frame,
        text=f"Version {APP_VERSION}",
        bg=SPLASH_PANEL_INNER,
        fg=SPLASH_GLOW,
        font=("Segoe UI", 10, "bold"),
        padx=12,
        pady=5,
    )
    version_label.pack()

    progress_row = tk.Frame(brand, bg=SPLASH_PANEL)
    progress_row.pack(anchor="w", fill="x", pady=(18, 0))

    progress_width = 244
    progress = tk.Canvas(progress_row, width=progress_width, height=18, bg=SPLASH_PANEL, highlightthickness=0)
    progress.pack(anchor="w")
    progress.create_rectangle(2, 4, progress_width - 2, 14, fill=SPLASH_PROGRESS_TRACK, outline=SPLASH_PROGRESS_EDGE, width=1)
    progress_fill = progress.create_rectangle(3, 5, 71, 13, fill=SPLASH_PROGRESS_FILL, outline=SPLASH_PROGRESS_FILL)
    progress_shine = progress.create_rectangle(35, 6, 67, 12, fill=SPLASH_PROGRESS_SHINE, outline="")

    accent_rule = tk.Frame(brand, bg=SPLASH_ACCENT_SOFT, height=2)
    accent_rule.pack(fill="x", pady=(18, 0))

    footer_row = tk.Frame(brand, bg=SPLASH_PANEL)
    footer_row.pack(fill="x", pady=(10, 0))

    footer = tk.Label(
        footer_row,
        text="Windows desktop build",
        bg=SPLASH_PANEL,
        fg=SPLASH_TEXT_MUTED,
        font=("Segoe UI", 9),
        anchor="w",
    )
    footer.pack(side="left")

    splash = {
        "root": root,
        "progress": progress,
        "progress_fill": progress_fill,
        "progress_shine": progress_shine,
        "progress_phase": 0.0,
        "progress_last": 0.0,
        "progress_width": progress_width,
    }
    _pump_splash(splash, force=True)
    return splash


def _destroy_splash(splash):
    if not splash:
        return
    root = splash.get("root")
    try:
        if root is not None:
            root.withdraw()
            root.update_idletasks()
            root.destroy()
    except Exception:
        pass


def main() -> int:
    splash = _create_splash()
    result = {}

    def import_target():
        try:
            import sdr_radio

            result["module"] = sdr_radio
        except Exception as exc:
            result["error"] = exc
            result["traceback"] = traceback.format_exc()

    worker = threading.Thread(target=import_target, daemon=True)
    worker.start()

    while worker.is_alive():
        if splash and not _pump_splash(splash):
            splash = None
        time.sleep(0.016)

    if "error" in result:
        _destroy_splash(splash)
        if splash is None:
            raise result["error"]

        try:
            from tkinter import messagebox

            messagebox.showerror(APP_TITLE, f"Startup failed:\n\n{result['error']}")
        except Exception:
            pass
        return 1

    try:
        if splash:
            _pump_splash(splash, force=True)
            _destroy_splash(splash)
            splash = None
        return result["module"].main()
    finally:
        _destroy_splash(splash)


if __name__ == "__main__":
    raise SystemExit(main())
