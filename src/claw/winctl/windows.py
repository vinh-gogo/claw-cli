from __future__ import annotations

import logging
import sys
from typing import Any

import psutil

logger = logging.getLogger("claw.winctl.windows")


def get_process_name_by_pid(pid: int) -> str:
    try:
        return psutil.Process(pid).name()
    except Exception:
        return ""


def list_windows() -> list[dict[str, Any]]:
    """List all top-level visible application windows."""
    if sys.platform != "win32":
        return []

    import win32gui
    import win32process

    active_hwnd = win32gui.GetForegroundWindow()
    windows: list[dict[str, Any]] = []

    def enum_handler(hwnd: int, _: Any) -> bool:
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd).strip()
            if title and not win32gui.IsIconic(hwnd) or title:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                proc_name = get_process_name_by_pid(pid)
                # Filter out system shell components like Progman
                if proc_name.lower() in ("progman", "shellexperiencehost", "searchhost"):
                    return True
                windows.append(
                    {
                        "hwnd": hwnd,
                        "title": title,
                        "process": proc_name,
                        "pid": pid,
                        "is_active": (hwnd == active_hwnd),
                    }
                )
        return True

    try:
        win32gui.EnumWindows(enum_handler, None)
    except Exception as e:
        logger.debug(f"EnumWindows error: {e}")

    return windows


def get_active_window() -> dict[str, Any] | None:
    """Return the currently focused foreground window."""
    if sys.platform != "win32":
        return None

    import win32gui
    import win32process

    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return None

    title = win32gui.GetWindowText(hwnd).strip()
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    proc_name = get_process_name_by_pid(pid)
    return {
        "hwnd": hwnd,
        "title": title,
        "process": proc_name,
        "pid": pid,
        "is_active": True,
    }


def find_window(target: str | int) -> dict[str, Any] | None:
    """Find a window by its hwnd or title/process substring match."""
    windows = list_windows()
    if isinstance(target, int):
        for w in windows:
            if w["hwnd"] == target:
                return w
        return None

    target_str = str(target).lower().strip()
    if target_str.isdigit():
        target_hwnd = int(target_str)
        for w in windows:
            if w["hwnd"] == target_hwnd:
                return w

    for w in windows:
        if target_str in w["title"].lower() or target_str in w["process"].lower():
            return w

    return None


def focus_window(target: str | int) -> tuple[bool, str]:
    """Bring target window to the foreground, bypassing Windows foreground lock."""
    if sys.platform != "win32":
        return False, "Chỉ hỗ trợ trên Windows"

    w = find_window(target)
    if not w:
        return False, f"Không tìm thấy cửa sổ nào khớp với '{target}'"

    hwnd = w["hwnd"]
    import win32api
    import win32con
    import win32gui
    import win32process

    try:
        # Check if minimized and restore
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

        # AttachThreadInput trick to grant SetForegroundWindow permission
        foreground_hwnd = win32gui.GetForegroundWindow()
        cur_thread_id = win32api.GetCurrentThreadId()
        fore_thread_id, _ = win32process.GetWindowThreadProcessId(foreground_hwnd)

        if cur_thread_id != fore_thread_id:
            win32process.AttachThreadInput(cur_thread_id, fore_thread_id, True)

        win32gui.SetForegroundWindow(hwnd)

        if cur_thread_id != fore_thread_id:
            win32process.AttachThreadInput(cur_thread_id, fore_thread_id, False)

        return True, f"Đã kích hoạt cửa sổ '{w['title']}' ({w['process']})"
    except Exception as e:
        # Fallback to ShowWindow
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            win32gui.BringWindowToTop(hwnd)
            return True, f"Đã đưa cửa sổ '{w['title']}' lên trước"
        except Exception as e2:
            return False, f"Không thể focus cửa sổ: {e} / {e2}"


def window_action(target: str | int, action: str) -> tuple[bool, str]:
    """Execute action on window: minimize, maximize, restore, snap_left, snap_right, close."""
    if sys.platform != "win32":
        return False, "Chỉ hỗ trợ trên Windows"

    w = find_window(target)
    if not w:
        return False, f"Không tìm thấy cửa sổ '{target}'"

    hwnd = w["hwnd"]
    import win32api
    import win32con
    import win32gui

    action_lower = action.lower().strip()

    try:
        if action_lower == "minimize":
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            return True, f"Đã thu nhỏ cửa sổ '{w['title']}'"
        elif action_lower == "maximize":
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            return True, f"Đã phóng to cửa sổ '{w['title']}'"
        elif action_lower == "restore":
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            return True, f"Đã khôi phục kích thước cửa sổ '{w['title']}'"
        elif action_lower == "close":
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            return True, f"Đã gửi lệnh đóng cửa sổ '{w['title']}'"
        elif action_lower in ("snap_left", "snap_right"):
            # Get monitor work area
            monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
            mon_info = win32api.GetMonitorInfo(monitor)
            work_area = mon_info["Work"]  # (left, top, right, bottom)
            w_left, w_top, w_right, w_bottom = work_area
            width = (w_right - w_left) // 2
            height = w_bottom - w_top

            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            if action_lower == "snap_left":
                win32gui.MoveWindow(hwnd, w_left, w_top, width, height, True)
                return True, f"Đã chia cửa sổ '{w['title']}' sang nửa bên trái"
            else:
                win32gui.MoveWindow(hwnd, w_left + width, w_top, width, height, True)
                return True, f"Đã chia cửa sổ '{w['title']}' sang nửa bên phải"
        else:
            return False, f"Hành động '{action}' không hợp lệ (hỗ trợ: minimize, maximize, restore, snap_left, snap_right, close)"
    except Exception as e:
        return False, f"Lỗi khi thực hiện hành động trên cửa sổ: {e}"
