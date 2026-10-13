from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from claw.config import get_config
from claw.tools.base import Tool, ToolContext, ToolResult
from claw.winctl.browser import BrowserController

logger = logging.getLogger("claw.tools.browser")

_controller: BrowserController | None = None


def get_browser_controller() -> BrowserController:
    global _controller
    if _controller is None:
        cfg = get_config().desktop
        _controller = BrowserController(
            browser_name=cfg.browser,
            profile_dir=cfg.browser_profile,
        )
    return _controller


class BrowserGotoArgs(BaseModel):
    url: str = Field(..., description="Đường dẫn URL cần chuyển đến trên trình duyệt")


class BrowserGotoTool(Tool):
    name = "browser_goto"
    description = "Mở một trang web trên trình duyệt điều khiển riêng của claw."
    risk = "input"
    args_model = BrowserGotoArgs

    async def run(self, args: BrowserGotoArgs, ctx: ToolContext) -> ToolResult:
        ctl = get_browser_controller()
        ok, msg = await ctl.goto(args.url)
        if ok:
            return ToolResult.success(msg)
        return ToolResult.fail(msg)


class BrowserClickArgs(BaseModel):
    selector: str = Field(..., description="CSS selector của phần tử cần click trên trang web (ví dụ: 'button#submit', 'a.video-title')")


class BrowserClickTool(Tool):
    name = "browser_click"
    description = "Click vào một phần tử trên trang web qua CSS selector."
    risk = "input"
    args_model = BrowserClickArgs

    async def run(self, args: BrowserClickArgs, ctx: ToolContext) -> ToolResult:
        ctl = get_browser_controller()
        ok, msg = await ctl.click(args.selector)
        if ok:
            return ToolResult.success(msg)
        return ToolResult.fail(msg)


class BrowserTypeArgs(BaseModel):
    selector: str = Field(..., description="CSS selector của ô nhập liệu (ví dụ: 'input[name=q]', 'textarea')")
    text: str = Field(..., description="Văn bản cần nhập vào")


class BrowserTypeTool(Tool):
    name = "browser_type"
    description = "Nhập văn bản vào ô tìm kiếm hoặc ô nhập liệu trên trang web."
    risk = "input"
    args_model = BrowserTypeArgs

    async def run(self, args: BrowserTypeArgs, ctx: ToolContext) -> ToolResult:
        ctl = get_browser_controller()
        ok, msg = await ctl.type(args.selector, args.text)
        if ok:
            return ToolResult.success(msg)
        return ToolResult.fail(msg)


class BrowserPressArgs(BaseModel):
    key: str = Field(..., description="Phím cần nhấn trên trang web (ví dụ: 'Enter', 'k', 'Escape', 'ArrowDown')")


class BrowserPressTool(Tool):
    name = "browser_press"
    description = "Bấm một phím trên trang web đang mở."
    risk = "input"
    args_model = BrowserPressArgs

    async def run(self, args: BrowserPressArgs, ctx: ToolContext) -> ToolResult:
        ctl = get_browser_controller()
        ok, msg = await ctl.press(args.key)
        if ok:
            return ToolResult.success(msg)
        return ToolResult.fail(msg)


class BrowserReadArgs(BaseModel):
    selector: str | None = Field(default=None, description="CSS selector của phần tử cần đọc (nếu để trống sẽ đọc toàn bộ nội dung trang)")


class BrowserReadTool(Tool):
    name = "browser_read"
    description = "Đọc nội dung văn bản từ trang web hoặc từ một phần tử cụ thể."
    risk = "input"
    args_model = BrowserReadArgs

    async def run(self, args: BrowserReadArgs, ctx: ToolContext) -> ToolResult:
        ctl = get_browser_controller()
        ok, msg = await ctl.read(args.selector)
        if ok:
            return ToolResult.success(msg)
        return ToolResult.fail(msg)
