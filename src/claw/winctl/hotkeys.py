from __future__ import annotations

import logging
import sys
from typing import Callable

logger = logging.getLogger("claw.winctl.hotkeys")


class GlobalHotkeyManager:
    """Manages system-wide global hotkeys for Push-To-Talk and Kill Switch."""

    def __init__(self) -> None:
        self._ptt_callback: Callable[[], None] | None = None
        self._kill_callback: Callable[[], None] | None = None
        self._ptt_hotkey: str = "ctrl+alt+space"
        self._kill_hotkey: str = "ctrl+alt+x"
        self._is_running: bool = False

    def setup(
        self,
        ptt_hotkey: str = "ctrl+alt+space",
        kill_hotkey: str = "ctrl+alt+x",
        on_ptt: Callable[[], None] | None = None,
        on_kill: Callable[[], None] | None = None,
    ) -> None:
        self._ptt_hotkey = ptt_hotkey.lower().strip()
        self._kill_hotkey = kill_hotkey.lower().strip()
        self._ptt_callback = on_ptt
        self._kill_callback = on_kill

    def start(self) -> bool:
        """Register hooks with the keyboard library."""
        if self._is_running:
            return True

        if sys.platform != "win32":
            logger.debug("Global hotkeys only supported on Windows")
            return False

        try:
            import keyboard

            if self._ptt_callback:
                keyboard.add_hotkey(self._ptt_hotkey, self._ptt_callback, suppress=True)
                logger.info(f"Registered global PTT hotkey: {self._ptt_hotkey}")

            if self._kill_callback:
                keyboard.add_hotkey(self._kill_hotkey, self._kill_callback, suppress=True)
                logger.info(f"Registered global kill-switch hotkey: {self._kill_hotkey}")

            self._is_running = True
            return True
        except Exception as e:
            logger.warning(
                f"Failed to register global hotkeys ({self._ptt_hotkey}, {self._kill_hotkey}): {e}. "
                "Global shortcuts may require running in an elevated shell."
            )
            return False

    def stop(self) -> None:
        """Unregister keyboard hooks."""
        if not self._is_running:
            return

        try:
            import keyboard

            keyboard.clear_all_hotkeys()
        except Exception as e:
            logger.debug(f"Error unregistering hotkeys: {e}")
        finally:
            self._is_running = False
