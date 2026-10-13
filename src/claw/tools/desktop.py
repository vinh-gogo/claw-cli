from __future__ import annotations

import logging
import os
import subprocess
import sys
from typing import Literal

import pyperclip
from pydantic import BaseModel, Field

from claw.tools.base import Tool, ToolContext, ToolResult
from claw.winctl.apps import AppManager
from claw.winctl.windows import (
    focus_window,
    get_active_window,
    list_windows,
    window_action,
)

logger = logging.getLogger("claw.tools.desktop")


class OpenAppArgs(BaseModel):
    name: str = Field(..., description="Tên ứng dụng hoặc tên tiếng Việt (ví dụ: 'chrome', 'crôm', 'notepad', 'sổ tay', 'excel', 'zalo')")


class OpenAppTool(Tool):
    name = "open_app"
    description = "Mở ứng dụng trên Windows theo tên, tên viết tắt hoặc alias tiếng Việt."
    risk = "low"
    args_model = OpenAppArgs

    async def run(self, args: OpenAppArgs, ctx: ToolContext) -> ToolResult:
        mgr = AppManager()
        ok, app_name = mgr.launch(args.name)
        if ok:
            return ToolResult.success(f"Đã mở ứng dụng: {app_name}")
        return ToolResult.fail(f"Không thể mở ứng dụng '{args.name}': {app_name}")


class OpenUrlArgs(BaseModel):
    url: str = Field(..., description="Đường dẫn URL cần mở (ví dụ: 'https://youtube.com', 'https://google.com')")


class OpenUrlTool(Tool):
    name = "open_url"
    description = "Mở đường dẫn URL trên trình duyệt web mặc định của hệ thống."
    risk = "low"
    args_model = OpenUrlArgs

    async def run(self, args: OpenUrlArgs, ctx: ToolContext) -> ToolResult:
        url = args.url.strip()
        try:
            if sys.platform == "win32":
                os.startfile(url)
            else:
                import webbrowser

                webbrowser.open(url)
            return ToolResult.success(f"Đã mở URL: {url}")
        except Exception as e:
            return ToolResult.fail(f"Lỗi khi mở URL '{url}': {e}")


class EmptyArgs(BaseModel):
    pass


class ListWindowsTool(Tool):
    name = "list_windows"
    description = "Liệt kê danh sách các cửa sổ ứng dụng đang mở (tiêu đề, tên tiến trình, hwnd, trạng thái active)."
    risk = "read"
    args_model = EmptyArgs

    async def run(self, args: EmptyArgs, ctx: ToolContext) -> ToolResult:
        wins = list_windows()
        if not wins:
            return ToolResult.success("Không có cửa sổ ứng dụng nào đang mở.")

        lines = [f"Danh sách {len(wins)} cửa sổ đang mở:"]
        for w in wins:
            active_marker = " [ACTIVE]" if w["is_active"] else ""
            lines.append(f"- hwnd=0x{w['hwnd']:X} | PID={w['pid']} | {w['process']} | \"{w['title']}\"{active_marker}")

        return ToolResult.success("\n".join(lines))


class GetActiveWindowTool(Tool):
    name = "get_active_window"
    description = "Lấy thông tin chi tiết về cửa sổ đang được focus/active hiện tại."
    risk = "read"
    args_model = EmptyArgs

    async def run(self, args: EmptyArgs, ctx: ToolContext) -> ToolResult:
        w = get_active_window()
        if not w:
            return ToolResult.success("Không xác định được cửa sổ active hiện tại.")
        return ToolResult.success(
            f"Cửa sổ active: \"{w['title']}\" (tiến trình: {w['process']}, PID: {w['pid']}, hwnd: 0x{w['hwnd']:X})"
        )


class FocusWindowArgs(BaseModel):
    target: str = Field(..., description="Tiêu đề, tên tiến trình hoặc hwnd của cửa sổ cần focus (ví dụ: 'chrome', 'Notepad')")


class FocusWindowTool(Tool):
    name = "focus_window"
    description = "Đưa cửa sổ ứng dụng lên trước màn hình để tương tác."
    risk = "low"
    args_model = FocusWindowArgs

    async def run(self, args: FocusWindowArgs, ctx: ToolContext) -> ToolResult:
        ok, msg = focus_window(args.target)
        if ok:
            return ToolResult.success(msg)
        return ToolResult.fail(msg)


class WindowActionArgs(BaseModel):
    target: str = Field(..., description="Tiêu đề, tên tiến trình hoặc hwnd của cửa sổ")
    action: Literal["minimize", "maximize", "restore", "snap_left", "snap_right", "close"] = Field(
        ..., description="Hành động: minimize, maximize, restore, snap_left, snap_right, close"
    )


class WindowActionTool(Tool):
    name = "window_action"
    description = "Thực hiện hành động trên cửa sổ: thu nhỏ, phóng to, khôi phục, chia nửa trái/phải, hoặc đóng."
    risk = "low"
    args_model = WindowActionArgs

    async def run(self, args: WindowActionArgs, ctx: ToolContext) -> ToolResult:
        ok, msg = window_action(args.target, args.action)
        if ok:
            return ToolResult.success(msg)
        return ToolResult.fail(msg)


class ClipboardGetTool(Tool):
    name = "clipboard_get"
    description = "Đọc nội dung văn bản hiện tại trong clipboard."
    risk = "read"
    args_model = EmptyArgs

    async def run(self, args: EmptyArgs, ctx: ToolContext) -> ToolResult:
        try:
            content = pyperclip.paste()
            return ToolResult.success(f"Nội dung clipboard: {content}")
        except Exception as e:
            return ToolResult.fail(f"Lỗi khi đọc clipboard: {e}")


class ClipboardSetArgs(BaseModel):
    text: str = Field(..., description="Nội dung văn bản cần lưu vào clipboard")


class ClipboardSetTool(Tool):
    name = "clipboard_set"
    description = "Ghi nội dung văn bản vào clipboard."
    risk = "input"
    args_model = ClipboardSetArgs

    async def run(self, args: ClipboardSetArgs, ctx: ToolContext) -> ToolResult:
        try:
            pyperclip.copy(args.text)
            return ToolResult.success(f"Đã lưu văn bản vào clipboard ({len(args.text)} ký tự)")
        except Exception as e:
            return ToolResult.fail(f"Lỗi khi ghi clipboard: {e}")


class NotifyArgs(BaseModel):
    text: str = Field(..., description="Nội dung thông báo")
    title: str = Field(default="claw", description="Tiêu đề thông báo")


class NotifyTool(Tool):
    name = "notify"
    description = "Hiển thị thông báo trên màn hình Windows."
    risk = "low"
    args_model = NotifyArgs

    async def run(self, args: NotifyArgs, ctx: ToolContext) -> ToolResult:
        try:
            if sys.platform == "win32":
                # PowerShell balloon / toast notification
                cmd = (
                    f"powershell -NoProfile -Command \"Add-Type -AssemblyName System.Windows.Forms; "
                    f"$n = New-Object System.Windows.Forms.NotifyIcon; "
                    f"$n.Icon = [System.Drawing.SystemIcons]::Information; "
                    f"$n.BalloonTipTitle = '{args.title}'; "
                    f"$n.BalloonTipText = '{args.text}'; "
                    f"$n.Visible = $True; $n.ShowBalloonTip(3000)\""
                )
                subprocess.Popen(cmd, shell=True)
            return ToolResult.success(f"Đã gửi thông báo: {args.title} - {args.text}")
        except Exception as e:
            return ToolResult.fail(f"Lỗi hiển thị thông báo: {e}")


class SystemActionArgs(BaseModel):
    action: Literal["lock", "sleep", "shutdown", "restart"] = Field(
        ..., description="Hành động hệ thống: lock (khoá máy), sleep (ngủ), shutdown (tắt máy), restart (khởi động lại)"
    )


class SystemActionTool(Tool):
    name = "system_action"
    description = "Thực hiện thao tác hệ thống: lock, sleep, shutdown, restart."
    risk = "dangerous"
    args_model = SystemActionArgs

    async def run(self, args: SystemActionArgs, ctx: ToolContext) -> ToolResult:
        if sys.platform != "win32":
            return ToolResult.fail("Chỉ hỗ trợ trên Windows")

        act = args.action
        try:
            if act == "lock":
                subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"])
                return ToolResult.success("Đã khoá máy tính.")
            elif act == "sleep":
                subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
                return ToolResult.success("Đã đưa máy tính vào chế độ ngủ.")
            elif act == "shutdown":
                subprocess.Popen(["shutdown", "/s", "/t", "60", "/c", "claw: Tắt máy tính sau 60 giây"])
                return ToolResult.success("Đã lên lịch tắt máy tính sau 60 giây (hủy bằng: shutdown /a).")
            elif act == "restart":
                subprocess.Popen(["shutdown", "/r", "/t", "60", "/c", "claw: Khởi động lại sau 60 giây"])
                return ToolResult.success("Đã lên lịch khởi động lại máy sau 60 giây (hủy bằng: shutdown /a).")
            return ToolResult.fail(f"Hành động '{act}' không được hỗ trợ.")
        except Exception as e:
            return ToolResult.fail(f"Lỗi khi thực hiện '{act}': {e}")
