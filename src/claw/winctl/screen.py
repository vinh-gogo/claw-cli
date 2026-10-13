from __future__ import annotations

import base64
import io
import logging
import sys

from PIL import Image

logger = logging.getLogger("claw.winctl.screen")


def capture_screen(monitor_index: int = 1, max_dimension: int = 1920) -> Image.Image | None:
    """Capture full screen of specified monitor using mss and return PIL Image."""
    try:
        import mss

        with mss.mss() as sct:
            monitors = sct.monitors
            if monitor_index >= len(monitors):
                monitor_index = 1 if len(monitors) > 1 else 0

            target_mon = monitors[monitor_index]
            sct_img = sct.grab(target_mon)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

            if max_dimension > 0 and (img.width > max_dimension or img.height > max_dimension):
                img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

            return img
    except Exception as e:
        logger.error(f"Error capturing screen: {e}")
        return None


def capture_window(hwnd: int, max_dimension: int = 1920) -> Image.Image | None:
    """Capture target window by hwnd using DWM extended frame bounds or GetWindowRect."""
    if sys.platform != "win32":
        return None

    try:
        import ctypes

        import mss
        import win32gui

        if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
            return None

        # Try DwmGetWindowAttribute for accurate border without invisible drop shadows
        rect = None
        try:
            from ctypes import wintypes

            dwmapi = ctypes.windll.dwmapi
            DWMWA_EXTENDED_FRAME_BOUNDS = 9
            r = wintypes.RECT()
            hr = dwmapi.DwmGetWindowAttribute(
                hwnd,
                DWMWA_EXTENDED_FRAME_BOUNDS,
                ctypes.byref(r),
                ctypes.sizeof(r),
            )
            if hr == 0:
                rect = (r.left, r.top, r.right, r.bottom)
        except Exception:
            pass

        if not rect:
            rect = win32gui.GetWindowRect(hwnd)

        left, top, right, bottom = rect
        width = right - left
        height = bottom - top

        if width <= 0 or height <= 0:
            return None

        with mss.mss() as sct:
            region = {"left": left, "top": top, "width": width, "height": height}
            sct_img = sct.grab(region)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

            if max_dimension > 0 and (img.width > max_dimension or img.height > max_dimension):
                img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

            return img
    except Exception as e:
        logger.error(f"Error capturing window hwnd={hwnd}: {e}")
        return None


def image_to_base64(image: Image.Image, format: str = "PNG") -> str:
    """Convert PIL Image to base64 data string."""
    buf = io.BytesIO()
    image.save(buf, format=format)
    return base64.b64encode(buf.getvalue()).decode("utf-8")
