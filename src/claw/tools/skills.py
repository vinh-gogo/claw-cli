from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from claw.skills.layout import snap_two_windows
from claw.skills.web_search import open_and_search
from claw.skills.youtube import youtube_play
from claw.tools.base import Tool, ToolContext, ToolResult

logger = logging.getLogger("claw.tools.skills")


class YoutubePlayArgs(BaseModel):
    query: str = Field(..., description="Tên bài hát, ca sĩ hoặc video cần tìm và phát (ví dụ: 'Sơn Tùng M-TP', 'lofi chill')")
    pick: int | None = Field(default=None, description="Số thứ tự video muốn chọn trong top 5 kết quả (mặc định chọn video phù hợp nhất)")


class YoutubePlayTool(Tool):
    name = "youtube_play"
    description = "Tìm kiếm và tự động phát nhạc/video trên YouTube bằng trình duyệt mặc định."
    risk = "low"
    args_model = YoutubePlayArgs

    async def run(self, args: YoutubePlayArgs, ctx: ToolContext) -> ToolResult:
        res = await youtube_play(args.query, pick=args.pick)
        if res.get("ok"):
            say_text = res.get("say", "")
            return ToolResult.success(f"{say_text} (URL: {res.get('url', '')})", metadata=res)
        return ToolResult.fail(res.get("error", "Không thể phát video YouTube"))


class WebSearchArgs(BaseModel):
    query: str = Field(..., description="Nội dung cần tìm kiếm trên web")
    engine: Literal["google", "bing", "duckduckgo", "coccoc", "youtube"] = Field(
        default="google", description="Công cụ tìm kiếm: google, bing, duckduckgo, coccoc, youtube"
    )
    browser: str | None = Field(default=None, description="Trình duyệt muốn dùng (chrome, msedge, coccoc...) hoặc để trống dùng mặc định")


class WebSearchTool(Tool):
    name = "web_search"
    description = "Mở trình duyệt và tìm kiếm thông tin trên công cụ tìm kiếm chỉ định (Google, Bing, Cốc Cốc...)."
    risk = "low"
    args_model = WebSearchArgs

    async def run(self, args: WebSearchArgs, ctx: ToolContext) -> ToolResult:
        res = open_and_search(args.query, engine=args.engine, browser=args.browser)
        if res.get("ok"):
            return ToolResult.success(f"{res.get('say', '')} (URL: {res.get('url', '')})", metadata=res)
        return ToolResult.fail(res.get("error", "Lỗi tìm kiếm web"))


class WindowLayoutArgs(BaseModel):
    left_target: str = Field(..., description="Tiêu đề hoặc tên app muốn đặt ở nửa bên trái màn hình (ví dụ: 'chrome')")
    right_target: str = Field(..., description="Tiêu đề hoặc tên app muốn đặt ở nửa bên phải màn hình (ví dụ: 'code', 'notepad')")


class WindowLayoutTool(Tool):
    name = "window_layout"
    description = "Sắp xếp 2 cửa sổ ứng dụng chia đôi màn hình (một bên trái, một bên phải)."
    risk = "low"
    args_model = WindowLayoutArgs

    async def run(self, args: WindowLayoutArgs, ctx: ToolContext) -> ToolResult:
        res = snap_two_windows(args.left_target, args.right_target)
        if res.get("ok"):
            return ToolResult.success(res.get("say", "Đã chia đôi màn hình 2 cửa sổ."))
        return ToolResult.fail(res.get("say", "Lỗi khi sắp xếp cửa sổ"))
