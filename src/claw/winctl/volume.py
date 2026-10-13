from __future__ import annotations

import logging
import sys
from typing import Any

logger = logging.getLogger("claw.winctl.volume")


def _get_volume_endpoint() -> Any:
    if sys.platform != "win32":
        return None

    try:
        from pycaw.pycaw import AudioUtilities

        speakers = AudioUtilities.GetSpeakers()
        if hasattr(speakers, "EndpointVolume"):
            return speakers.EndpointVolume
    except Exception as e:
        logger.debug(f"pycaw initialization error: {e}")

    return None


def get_volume() -> int:
    """Return current master volume percentage (0 to 100)."""
    endpoint = _get_volume_endpoint()
    if not endpoint:
        return 50

    try:
        scalar = endpoint.GetMasterVolumeLevelScalar()
        return int(round(scalar * 100))
    except Exception as e:
        logger.debug(f"Error getting volume: {e}")
        return 50


def set_volume(percent: int) -> tuple[bool, int]:
    """Set master volume percentage (0 to 100)."""
    endpoint = _get_volume_endpoint()
    if not endpoint:
        return False, 50

    clamped = max(0, min(100, percent))
    scalar = clamped / 100.0
    try:
        endpoint.SetMasterVolumeLevelScalar(scalar, None)
        return True, clamped
    except Exception as e:
        logger.debug(f"Error setting volume: {e}")
        return False, get_volume()


def change_volume(delta_percent: int) -> tuple[bool, int]:
    """Increase or decrease volume by delta percentage points."""
    cur = get_volume()
    target = cur + delta_percent
    return set_volume(target)


def is_muted() -> bool:
    """Return True if volume is muted."""
    endpoint = _get_volume_endpoint()
    if not endpoint:
        return False
    try:
        return bool(endpoint.GetMute())
    except Exception:
        return False


def set_mute(mute: bool) -> bool:
    """Set volume mute status."""
    endpoint = _get_volume_endpoint()
    if not endpoint:
        return False
    try:
        endpoint.SetMute(int(mute), None)
        return True
    except Exception as e:
        logger.debug(f"Error setting mute: {e}")
        return False


def toggle_mute() -> tuple[bool, bool]:
    """Toggle mute and return (success, new_mute_state)."""
    cur = is_muted()
    new_state = not cur
    ok = set_mute(new_state)
    return ok, new_state
