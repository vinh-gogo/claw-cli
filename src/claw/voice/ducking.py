from __future__ import annotations

import logging

from claw.config import DesktopConfig
from claw.winctl.volume import get_volume, set_volume

logger = logging.getLogger("claw.voice.ducking")


class AudioDucker:
    """Manages audio ducking: lowers system volume while recording voice input to prevent feedback."""

    def __init__(self, config: DesktopConfig | None = None) -> None:
        self.config = config or DesktopConfig()
        self._saved_volume: int | None = None
        self._is_ducked: bool = False

    def start_duck(self) -> None:
        """Lower volume if ducking is enabled in config."""
        if not self.config.duck_media_on_listen or self._is_ducked:
            return

        try:
            current = get_volume()
            self._saved_volume = current
            target = max(5, int(self.config.duck_level * 100))
            if current > target:
                set_volume(target)
                self._is_ducked = True
                logger.debug(f"Audio ducked: {current}% -> {target}%")
        except Exception as e:
            logger.debug(f"Error during audio ducking: {e}")

    def restore_duck(self) -> None:
        """Restore volume back to saved pre-duck level."""
        if not self._is_ducked or self._saved_volume is None:
            return

        try:
            set_volume(self._saved_volume)
            logger.debug(f"Audio restored back to {self._saved_volume}%")
        except Exception as e:
            logger.debug(f"Error restoring audio: {e}")
        finally:
            self._saved_volume = None
            self._is_ducked = False
