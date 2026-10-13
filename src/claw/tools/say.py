from __future__ import annotations

from pydantic import BaseModel, Field

from claw.events import SayEvent
from claw.tools.base import RiskLevel, Tool, ToolContext, ToolResult


class SayArgs(BaseModel):
    text: str = Field(description="1-2 câu ngắn gọn tóm tắt kết quả bằng tiếng Việt để đọc to cho người dùng")


class SayTool(Tool):
    name = "say"
    description = "Nói to một tóm tắt ngắn gọn tự nhiên (1-2 câu tiếng Việt) cho người dùng nghe."
    risk: RiskLevel = "none"
    args_model = SayArgs

    async def run(self, args: SayArgs, ctx: ToolContext) -> ToolResult:
        if ctx.emit_event:
            await ctx.emit_event(SayEvent(text=args.text))
        return ToolResult.success(f"Đã đọc to: '{args.text}'")
