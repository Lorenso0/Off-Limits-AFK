from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import threading
import time
from pathlib import Path

import webview

from .api import Api

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

    rgn = ctypes.windll.gdi32.CreateRoundRectRgn(
        0, 0, _WIDTH + 1, _HEIGHT + 1, diameter, diameter
    )
    ctypes.windll.user32.SetWindowRgn(hwnd, rgn, True)


def launch() -> None:
    api = Api()
    html_path = Path(__file__).resolve().parent / "frontend" / "index.html"
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
