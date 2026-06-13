from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import threading
import time
from pathlib import Path

import webview

from .api import Api
from .runtime import project_root

_WINDOW_TITLE = "Off Limits AFK Scripts"
_WIDTH = 860
_HEIGHT = 760
_CORNER_RADIUS = 14


def _find_hwnd_by_pid(pid: int) -> int:
    """Find the main visible top-level window belonging to this process."""
    result = ctypes.c_size_t(0)

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_size_t, ctypes.c_size_t)

    def _cb(hwnd: int, _: int) -> bool:
        found_pid = ctypes.c_ulong(0)
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(found_pid))
        if found_pid.value == pid and ctypes.windll.user32.IsWindowVisible(hwnd):
            result.value = hwnd
            return False  # stop
        return True

    cb = WNDENUMPROC(_cb)
    ctypes.windll.user32.EnumWindows(cb, 0)
    return result.value


def _apply_rounded_region() -> None:
    if os.name != "nt":
        return

    pid = os.getpid()
    diameter = _CORNER_RADIUS * 2

    hwnd = 0
    for _ in range(40):              # up to 2 s
        hwnd = _find_hwnd_by_pid(pid)
        if hwnd:
            break
        time.sleep(0.05)

    if not hwnd:
        return

    rect = ctypes.wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top

    rgn = ctypes.windll.gdi32.CreateRoundRectRgn(
        0, 0, w + 1, h + 1, diameter, diameter
    )
    ctypes.windll.user32.SetWindowRgn(hwnd, rgn, True)


def _set_dpi_aware() -> None:
    if os.name != "nt":
        return
    # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 (-4) — best option on Win10 1703+
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_ssize_t(-4))
        return
    except Exception:
        pass
    # Fallback: PROCESS_PER_MONITOR_DPI_AWARE (2) via shcore
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    # Last resort
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def launch() -> None:
    _set_dpi_aware()
    api = Api()
    html_path = project_root() / "app" / "frontend" / "index.html"
    window = webview.create_window(
        _WINDOW_TITLE,
        url=html_path.as_uri(),
        js_api=api,
        width=_WIDTH,
        height=_HEIGHT,
        resizable=False,
        frameless=True,
        easy_drag=False,
        transparent=True,
    )

    def on_shown():
        # Small delay — WebView2 compositing finishes slightly after WinForms Shown
        time.sleep(0.15)
        threading.Thread(target=_apply_rounded_region, daemon=True).start()

    window.events.shown += on_shown
    api.set_window(window)
    webview.start(debug=False)
