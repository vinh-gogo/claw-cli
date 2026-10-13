from __future__ import annotations

import logging
from typing import Any

from claw.winctl.windows import focus_window, window_action

logger = logging.getLogger("claw.skills.layout")


def snap_two_windows(left_target: str, right_target: str) -> dict[str, Any]:
    """Snap two target windows side by side (left and right)."""
    # 1. Snap left
    focus_window(left_target)
    ok_left, msg_left = window_action(left_target, "snap_left")

    # 2. Snap right
    focus_window(right_target)
    ok_right, msg_right = window_action(right_target, "snap_right")

    success = ok_left and ok_right
    if success:
        say_text = f"Đã chia đôi màn hình: {left_target} bên trái và {right_target} bên phải."
    else:
        say_text = f"Kết quả sắp xếp cửa sổ: bên trái ({msg_left}), bên phải ({msg_right})."

    return {
        "ok": success,
        "left": {"target": left_target, "ok": ok_left, "message": msg_left},
        "right": {"target": right_target, "ok": ok_right, "message": msg_right},
        "say": say_text,
    }
