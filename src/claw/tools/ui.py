from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel, Field

from claw.tools.base import Tool, ToolContext, ToolResult
from claw.winctl.inputs import press_keys, type_text
from claw.winctl.uia import dump_ui_tree, ui_click, ui_type
from claw.winctl.windows import find_window, focus_window

logger = logging.getLogger("claw.tools.ui")


class UiTreeArgs(BaseModel):
    window: str | None = Field(default=None, description="Tiêu đề, tên tiến trình hoặc hwnd của cửa sổ cần đọc (nếu để trống sẽ đọc cửa sổ active)")
    max_depth: int = Field(default=4, description="Độ sâu tối đa của cây UI")


class UiTreeTool(Tool):
    name = "ui_tree"
    description = "Dump cây UI Automation rút gọn của cửa sổ để xem các phần tử có thể click/nhập liệu (được đánh số #id)."
    risk = "read"
    args_model = UiTreeArgs

    async def run(self, args: UiTreeArgs, ctx: ToolContext) -> ToolResult:
        hwnd = None
        if args.window:
            w = find_window(args.window)
            if not w:
                return ToolResult.fail(f"Không tìm thấy cửa sổ nào khớp với '{args.window}'")
            hwnd = w["hwnd"]

        text_tree, nodes = dump_ui_tree(hwnd=hwnd, max_depth=args.max_depth)
        return ToolResult.success(text_tree)


class UiClickArgs(BaseModel):
    selector: str = Field(..., description="Mã phần tử dạng #id (ví dụ: '#1', '1') hoặc tên nút, AutomationId")
    window: str | None = Field(default=None, description="Cửa sổ chứa phần tử (nếu để trống dùng cửa sổ hiện tại)")


class UiClickTool(Tool):
    name = "ui_click"
    description = "Click vào phần tử UI bằng số thứ tự #id, AutomationId hoặc tên phần tử."
    risk = "input"
    args_model = UiClickArgs

    async def run(self, args: UiClickArgs, ctx: ToolContext) -> ToolResult:
        hwnd = None
        if args.window:
            w = find_window(args.window)
            if w:
                hwnd = w["hwnd"]
                focus_window(hwnd)

        ok, msg = ui_click(args.selector, hwnd=hwnd)
        if ok:
            return ToolResult.success(msg)
        return ToolResult.fail(msg)


class UiTypeArgs(BaseModel):
    selector: str = Field(..., description="Mã phần tử dạng #id (ví dụ: '#1') hoặc tên ô nhập liệu")
    text: str = Field(..., description="Văn bản cần nhập vào")
    window: str | None = Field(default=None, description="Cửa sổ chứa phần tử")


class UiTypeTool(Tool):
    name = "ui_type"
    description = "Nhập văn bản vào ô nhập liệu UI theo #id hoặc tên phần tử (hỗ trợ tiếng Việt có dấu)."
    risk = "input"
    args_model = UiTypeArgs

    async def run(self, args: UiTypeArgs, ctx: ToolContext) -> ToolResult:
        hwnd = None
        if args.window:
            w = find_window(args.window)
            if w:
                hwnd = w["hwnd"]
                focus_window(hwnd)

        ok, msg = ui_type(args.selector, args.text, hwnd=hwnd)
        if ok:
            return ToolResult.success(msg)
        return ToolResult.fail(msg)


class KeyPressArgs(BaseModel):
    keys: str = Field(..., description="Phím hoặc tổ hợp phím cần bấm (ví dụ: 'enter', 'esc', 'ctrl+l', 'alt+f4', 'win+d')")


class KeyPressTool(Tool):
    name = "key_press"
    description = "Mô phỏng bấm một phím hoặc tổ hợp phím bàn phím."
    risk = "input"
    args_model = KeyPressArgs

    async def run(self, args: KeyPressArgs, ctx: ToolContext) -> ToolResult:
        ok, msg = await press_keys(args.keys)
        if ok:
            return ToolResult.success(msg)
        return ToolResult.fail(msg)


class TypeTextArgs(BaseModel):
    text: str = Field(..., description="Văn bản tiếng Việt hoặc ký tự cần gõ vào vị trí con trỏ hiện tại")
    target: str | None = Field(default=None, description="Tên cửa sổ cần đảm bảo focus trước khi gõ (tuỳ chọn)")


class TypeTextTool(Tool):
    name = "type_text"
    description = "Gõ văn bản vào cửa sổ hoặc ô đang focus (hỗ trợ 100% tiếng Việt có dấu)."
    risk = "input"
    args_model = TypeTextArgs

    async def run(self, args: TypeTextArgs, ctx: ToolContext) -> ToolResult:
        if args.target:
            focus_window(args.target)
            await asyncio.sleep(0.1)

        ok = await type_text(args.text)
        if ok:
            return ToolResult.success(f"Đã gõ văn bản: \"{args.text}\"")
        return ToolResult.fail(f"Lỗi khi gõ văn bản: \"{args.text}\"")


class WaitForArgs(BaseModel):
    target: str = Field(..., description="Tiêu đề hoặc tên tiến trình của cửa sổ cần đợi")
    timeout_s: float = Field(default=5.0, description="Thời gian chờ tối đa tính bằng giây")


class WaitForTool(Tool):
    name = "wait_for"
    description = "Chờ cho đến khi cửa sổ chỉ định xuất hiện trên màn hình."
    risk = "read"
    args_model = WaitForArgs

    async def run(self, args: WaitForArgs, ctx: ToolContext) -> ToolResult:
        deadline = asyncio.get_event_loop().time() + args.timeout_s
        while asyncio.get_event_loop().time() < deadline:
            w = find_window(args.target)
            if w:
                return ToolResult.success(f"Cửa sổ '{w['title']}' ({w['process']}) đã xuất hiện.")
            await asyncio.sleep(0.25)
        return ToolResult.fail(f"Hết thời gian {args.timeout_s}s chờ cửa sổ '{args.target}'")
