from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from claw.tools.base import Tool, ToolContext, ToolResult
from claw.winctl.inputs import click_mouse, scroll_mouse
from claw.winctl.screen import capture_screen, capture_window
from claw.winctl.windows import find_window

logger = logging.getLogger("claw.tools.vision")


class ScreenshotArgs(BaseModel):
    target: str | None = Field(default=None, description="Tiêu đề, tên tiến trình hoặc hwnd của cửa sổ cần chụp (nếu để trống sẽ chụp toàn màn hình)")


class ScreenshotTool(Tool):
    name = "screenshot"
    description = "Chụp ảnh màn hình hoặc ảnh một cửa sổ ứng dụng cụ thể."
    risk = "read"
    args_model = ScreenshotArgs

    async def run(self, args: ScreenshotArgs, ctx: ToolContext) -> ToolResult:
        img = None
        if args.target:
            w = find_window(args.target)
            if not w:
                return ToolResult.fail(f"Không tìm thấy cửa sổ nào khớp với '{args.target}'")
            img = capture_window(w["hwnd"])
            if img is None:
                return ToolResult.fail(f"Không thể chụp ảnh cửa sổ '{w['title']}'")
            title_desc = f"cửa sổ '{w['title']}'"
        else:
            img = capture_screen()
            if img is None:
                return ToolResult.fail("Không thể chụp toàn màn hình")
            title_desc = "toàn màn hình"

        # Save to temp file
        temp_dir = Path(tempfile.gettempdir()) / "claw_screenshots"
        temp_dir.mkdir(parents=True, exist_ok=True)
        out_file = temp_dir / "latest_screenshot.png"
        img.save(out_file)

        return ToolResult.success(
            f"Đã chụp ảnh {title_desc} ({img.width}x{img.height}px). Đã lưu tại: {out_file}",
            metadata={"file_path": str(out_file), "width": img.width, "height": img.height},
        )


class MouseClickArgs(BaseModel):
    x: int = Field(..., description="Toạ độ X trên màn hình")
    y: int = Field(..., description="Toạ độ Y trên màn hình")
    button: Literal["left", "right", "middle"] = Field(default="left", description="Nút chuột: left, right, middle")
    clicks: int = Field(default=1, description="Số lần bấm chuột (1 = đơn, 2 = đúp)")


class MouseClickTool(Tool):
    name = "mouse_click"
    description = "Mô phỏng click chuột tại toạ độ màn hình (x, y)."
    risk = "input"
    args_model = MouseClickArgs

    async def run(self, args: MouseClickArgs, ctx: ToolContext) -> ToolResult:
        ok, msg = await click_mouse(args.x, args.y, button=args.button, clicks=args.clicks)
        if ok:
            return ToolResult.success(msg)
        return ToolResult.fail(msg)


class ScrollArgs(BaseModel):
    amount: int = Field(..., description="Số bước cuộn chuột (dương = cuộn lên, âm = cuộn xuống)")


class ScrollTool(Tool):
    name = "scroll"
    description = "Mô phỏng cuộn con lăn chuột lên hoặc xuống."
    risk = "input"
    args_model = ScrollArgs

    async def run(self, args: ScrollArgs, ctx: ToolContext) -> ToolResult:
        ok, msg = await scroll_mouse(args.amount)
        if ok:
            return ToolResult.success(msg)
        return ToolResult.fail(msg)
