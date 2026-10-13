from __future__ import annotations

import logging
import sys
from typing import Any

from claw.winctl.windows import list_windows

logger = logging.getLogger("claw.winctl.media")

VK_MEDIA_CODES = {
    "play_pause": 0xB3,
    "play": 0xB3,
    "pause": 0xB3,
    "next": 0xB0,
    "prev": 0xB1,
    "previous": 0xB1,
    "stop": 0xB2,
    "volume_up": 0xAF,
    "volume_down": 0xAE,
    "mute": 0xAD,
}


def press_media_key(action: str) -> tuple[bool, str]:
    """Simulate Windows multimedia key press."""
    clean_act = action.lower().strip()
    vk = VK_MEDIA_CODES.get(clean_act)
    if not vk:
        return False, f"Hành động media '{action}' không hợp lệ (hỗ trợ: play_pause, next, prev, stop, volume_up, volume_down, mute)"

    if sys.platform != "win32":
        return False, "Chỉ hỗ trợ trên Windows"

    try:
        import ctypes

        user32 = ctypes.windll.user32
        # Press
        user32.keybd_event(vk, 0, 0, 0)
        # Release
        user32.keybd_event(vk, 0, 2, 0)
        return True, f"Đã gửi phím đa phương tiện: {action}"
    except Exception as e:
        return False, f"Lỗi khi gửi phím media: {e}"


async def get_now_playing() -> dict[str, Any]:
    """Query currently playing media track and playback status."""
    info: dict[str, Any] = {
        "title": None,
        "artist": None,
        "status": "Unknown",
        "source": None,
    }

    if sys.platform != "win32":
        return info

    # 1. Try Windows SMTC API
    try:
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as SMTCManager,
        )

        manager = await SMTCManager.request_async()
        session = manager.get_current_session()
        if session:
            media_props = await session.try_get_media_properties_async()
            playback_info = session.get_playback_info()
            if playback_info:
                info["status"] = playback_info.playback_status.name
            if media_props:
                info["title"] = media_props.title
                info["artist"] = media_props.artist
            info["source"] = session.source_app_user_model_id
            return info
    except Exception as e:
        logger.debug(f"SMTC query error: {e}")

    # 2. Fallback: inspect open window titles for YouTube or Spotify
    for w in list_windows():
        title = w["title"]
        proc = w["process"].lower()
        if "spotify" in proc or "spotify" in title.lower():
            if title and title != "Spotify":
                info["title"] = title
                info["source"] = "Spotify"
                info["status"] = "Playing"
                return info
        if "youtube" in title.lower():
            # YouTube title usually formatted as: "Video Title - YouTube - Browser"
            clean_title = title.split(" - YouTube")[0]
            info["title"] = clean_title
            info["source"] = proc
            info["status"] = "Playing"
            return info

    return info
