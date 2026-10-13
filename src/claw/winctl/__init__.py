from __future__ import annotations

from claw.winctl.apps import AppManager
from claw.winctl.browser import BrowserController
from claw.winctl.dpi import set_dpi_awareness
from claw.winctl.hotkeys import GlobalHotkeyManager
from claw.winctl.inputs import click_mouse, press_keys, scroll_mouse, type_text, type_text_sync
from claw.winctl.media import get_now_playing, press_media_key
from claw.winctl.screen import capture_screen, capture_window, image_to_base64
from claw.winctl.uia import dump_ui_tree, find_element, ui_click, ui_type
from claw.winctl.volume import (
    change_volume,
    get_volume,
    is_muted,
    set_mute,
    set_volume,
    toggle_mute,
)
from claw.winctl.windows import (
    find_window,
    focus_window,
    get_active_window,
    list_windows,
    window_action,
)

__all__ = [
    "AppManager",
    "BrowserController",
    "GlobalHotkeyManager",
    "capture_screen",
    "capture_window",
    "change_volume",
    "click_mouse",
    "dump_ui_tree",
    "find_element",
    "find_window",
    "focus_window",
    "get_active_window",
    "get_now_playing",
    "get_volume",
    "image_to_base64",
    "is_muted",
    "list_windows",
    "press_keys",
    "press_media_key",
    "scroll_mouse",
    "set_dpi_awareness",
    "set_mute",
    "set_volume",
    "toggle_mute",
    "type_text",
    "type_text_sync",
    "ui_click",
    "ui_type",
    "window_action",
]
