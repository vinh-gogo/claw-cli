from __future__ import annotations

import asyncio
import logging
from typing import Any

try:
    import pyautogui as _pyautogui

    # Enable PyAutoGUI fail-safe: move mouse to upper-left corner stops actions
    _pyautogui.FAILSAFE = True
    _pyautogui.PAUSE = 0.05
    pyautogui: Any = _pyautogui
except Exception:
    pyautogui = None

try:
    import pyperclip as _pyperclip

    pyperclip: Any = _pyperclip
except Exception:
    pyperclip = None

logger = logging.getLogger("claw.winctl.inputs")


def type_text_sync(text: str) -> bool:
    """Type text accurately on Windows including Vietnamese diacritics using clipboard paste."""
    if not text:
        return True

    original_clipboard = ""
    try:
        original_clipboard = pyperclip.paste()
    except Exception:
        pass

    try:
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        import time

        time.sleep(0.05)
        return True
    except Exception as e:
        logger.debug(f"Clipboard paste error: {e}")
        try:
            pyautogui.write(text, interval=0.01)
            return True
        except Exception:
            return False
    finally:
        try:
            pyperclip.copy(original_clipboard)
        except Exception:
            pass


async def type_text(text: str) -> bool:
    """Type text accurately on Windows asynchronously."""
    return await asyncio.to_thread(type_text_sync, text)


async def press_keys(keys_str: str) -> tuple[bool, str]:
    """Press single key or hotkey combination (e.g. 'ctrl+l', 'win+d', 'alt+f4', 'enter')."""
    clean = keys_str.lower().strip()
    parts = [p.strip() for p in clean.split("+") if p.strip()]
    if not parts:
        return False, "Không có phím nào được chỉ định."

    # Map special key names
    key_map = {
        "win": "winleft",
        "windows": "winleft",
        "esc": "escape",
        "del": "delete",
        "ins": "insert",
        "pgup": "pageup",
        "pgdn": "pagedown",
    }
    mapped_parts = [key_map.get(p, p) for p in parts]

    def _do_press() -> None:
        if len(mapped_parts) == 1:
            pyautogui.press(mapped_parts[0])
        else:
            pyautogui.hotkey(*mapped_parts)

    try:
        await asyncio.to_thread(_do_press)
        return True, f"Đã bấm phím: {keys_str}"
    except Exception as e:
        return False, f"Lỗi khi bấm phím '{keys_str}': {e}"


async def click_mouse(x: int, y: int, button: str = "left", clicks: int = 1) -> tuple[bool, str]:
    """Click mouse at screen coordinates (x, y)."""
    def _do_click() -> None:
        pyautogui.click(x=x, y=y, button=button, clicks=clicks)

    try:
        await asyncio.to_thread(_do_click)
        return True, f"Đã click ({button}, {clicks} lần) tại toạ độ ({x}, {y})"
    except Exception as e:
        return False, f"Lỗi khi click chuột: {e}"


async def scroll_mouse(clicks: int) -> tuple[bool, str]:
    """Scroll mouse wheel (positive = up, negative = down)."""
    def _do_scroll() -> None:
        pyautogui.scroll(clicks)

    try:
        await asyncio.to_thread(_do_scroll)
        return True, f"Đã cuộn chuột {clicks} bước"
    except Exception as e:
        return False, f"Lỗi khi cuộn chuột: {e}"
