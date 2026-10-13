from __future__ import annotations

import asyncio

from pydantic import BaseModel, Field
from rich.console import Console
from rich.panel import Panel

from claw.tools.base import RiskLevel, Tool, ToolContext, ToolResult

console = Console()


class AskUserArgs(BaseModel):
    question: str = Field(description="Câu hỏi cần làm rõ từ người dùng")
    options: list[str] | None = Field(default=None, description="Danh sách các lựa chọn gợi ý (nếu có)")


class AskUserTool(Tool):
    name = "ask_user"
    description = "Hỏi lại người dùng khi yêu cầu bị mơ hồ, thiếu thông tin hoặc nghi ngờ nhận diện giọng nói bị sai."
    risk: RiskLevel = "none"
    args_model = AskUserArgs

    async def run(self, args: AskUserArgs, ctx: ToolContext) -> ToolResult:
        body = f"[bold cyan]{args.question}[/bold cyan]"
        if args.options:
            body += "\n\nCác lựa chọn:\n" + "\n".join(f"- {opt}" for opt in args.options)

        console.print(Panel(body, title="❓ CLAW HỎI LẠI BẠN", border_style="cyan"))

        def get_input() -> str:
            console.print("Nhập câu trả lời của bạn: ", end="")
            return input().strip()

        answer = await asyncio.to_thread(get_input)
        return ToolResult.success(f"Người dùng trả lời: {answer}")
