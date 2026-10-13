from __future__ import annotations

import logging
import sys

logger = logging.getLogger("claw.winctl.dpi")


def init_dpi_awareness() -> bool:
    """Set process DPI awareness to Per-Monitor v2 on Windows to ensure accurate coordinates."""
    if sys.platform != "win32":
        return False

    try:
        import ctypes

        shcore = ctypes.windll.shcore
        # 2 = PROCESS_PER_MONITOR_DPI_AWARE_V2
        # 1 = PROCESS_PER_MONITOR_DPI_AWARE
        res = shcore.SetProcessDpiAwareness(2)
        if res == 0:
            logger.debug("DPI awareness set to Per-Monitor v2.")
            return True
    except Exception as e:
        try:
            import ctypes

            ctypes.windll.user32.SetProcessDPIAware()
            logger.debug("DPI awareness set to system default.")
            return True
        except Exception:
            logger.debug(f"Failed to set DPI awareness: {e}")

    return False


set_dpi_awareness = init_dpi_awareness
