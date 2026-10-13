from __future__ import annotations

import asyncio

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from claw.llm.schema import ToolCall
from claw.safety.policy import SafetyDecision

console = Console()


class ApprovalManager:
    def __init__(self) -> None:
        self._session_approved_levels: set[str] = set()
        self._session_approved_tools: set[str] = set()
        self._pending_future: asyncio.Future[bool] | None = None
        self._current_decision: SafetyDecision | None = None

    def is_session_approved(self, tool_name: str, level: str) -> bool:
        if level == "dangerous":
            return False  # dangerous is never session-approved
        return (level in self._session_approved_levels) or (tool_name in self._session_approved_tools)

    def handle_voice_answer(self, text: str) -> bool | None:
        """Called when a voice command is recognized during approval.

        Returns True (approved), False (rejected), or None (not an approval answer).
        """
        if self._pending_future is None or self._pending_future.done():
            return None

        if self._current_decision and self._current_decision.level == "dangerous":
            # Voice cannot approve dangerous commands
            return None

        norm = text.strip().lower()
        if norm in ("đồng ý", "ok", "làm đi", "chạy đi", "duyệt", "có", "yes"):
            if not self._pending_future.done():
                self._pending_future.set_result(True)
            return True
        elif norm in ("không", "thôi", "huỷ", "dừng", "đừng", "no"):
            if not self._pending_future.done():
                self._pending_future.set_result(False)
            return False
        return None

    async def request_approval(self, call: ToolCall, decision: SafetyDecision) -> bool:
        """Prompt user for approval and return True if approved, False otherwise."""
        if self.is_session_approved(call.name, decision.level):
            return True

        self._current_decision = decision
        loop = asyncio.get_running_loop()
        self._pending_future = loop.create_future()

        # Render approval panel
        level_style = "bold red" if decision.level == "dangerous" else "bold yellow"
        body = f"[bold]Công cụ:[/bold] {call.name}\n"
        body += f"[bold]Mức độ:[/bold] [{level_style}]{decision.level.upper()}[/{level_style}]\n"
        body += f"[bold]Lý do:[/bold] {decision.reason}\n"
        body += f"[bold]Tham số:[/bold] `{call.arguments}`"

        console.print(Panel(body, title="⚠️ YÊU CẦU XÁC NHẬN HÀNH ĐỘNG", border_style="yellow"))

        if decision.diff:
            console.print(Syntax(decision.diff, "diff", theme="monokai", line_numbers=True))

        # Handle user keyboard input in a non-blocking background thread task
        async def prompt_user() -> bool:
            if decision.level == "dangerous":
                console.print(
                    "[bold red]CẢNH BÁO NGUY HIỂM:[/bold red] Lệnh này có thể làm thay đổi hệ thống không thể đảo ngược."
                )
                console.print("Gõ chính xác [bold green]'yes'[/bold green] để xác nhận, hoặc bất kỳ phím nào khác để huỷ: ", end="")
                ans = await asyncio.to_thread(input)
                return ans.strip().lower() == "yes"
            else:
                console.print("Xác nhận: [bold green]y[/bold green]=Đồng ý · [bold red]n[/bold red]=Huỷ · [bold cyan]a[/bold cyan]=Luôn duyệt phiên này: ", end="")
                ans = await asyncio.to_thread(input)
                clean_ans = ans.strip().lower()
                if clean_ans == "a":
                    self._session_approved_levels.add(decision.level)
                    return True
                return clean_ans in ("y", "yes", "ok", "1")

        terminal_task = asyncio.create_task(prompt_user())

        def on_terminal_done(t: asyncio.Task[bool]) -> None:
            if self._pending_future is not None and not self._pending_future.done():
                try:
                    self._pending_future.set_result(t.result())
                except Exception:
                    self._pending_future.set_result(False)

        terminal_task.add_done_callback(on_terminal_done)

        try:
            assert self._pending_future is not None
            result = await self._pending_future
        finally:
            if not terminal_task.done():
                terminal_task.cancel()
            self._pending_future = None
            self._current_decision = None

        return result
