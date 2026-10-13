from __future__ import annotations

import asyncio
from typing import AsyncIterator

from claw.agent.context import AgentContext
from claw.config import LLMConfig
from claw.events import (
    ApprovalRequest,
    ApprovalResponse,
    CancelEvent,
    Event,
    Final,
    SayEvent,
    TextDelta,
    ToolCallStart,
    ToolResultEvent,
)
from claw.llm.client import LLMClient
from claw.llm.prompt_tools import generate_tool_instructions, parse_prompt_tool_calls
from claw.llm.schema import LLMResponse, Message
from claw.safety.approval import ApprovalManager
from claw.safety.policy import SafetyPolicy
from claw.tools.base import ToolContext, ToolRegistry, ToolResult


class AgentLoop:
    def __init__(
        self,
        llm: LLMClient,
        ctx: AgentContext,
        tools: ToolRegistry,
        safety: SafetyPolicy,
        approval: ApprovalManager,
        cfg: LLMConfig,
    ) -> None:
        self.llm = llm
        self.ctx = ctx
        self.tools = tools
        self.safety = safety
        self.approval = approval
        self.cfg = cfg
        self._cancel_event = asyncio.Event()

    def cancel(self) -> None:
        """Trigger cancellation for any ongoing turn."""
        self._cancel_event.set()

    def reset_cancel(self) -> None:
        self._cancel_event.clear()

    async def run_turn(self, user_text: str) -> AsyncIterator[Event]:
        self.reset_cancel()
        self.ctx.add_user(user_text)

        recent_calls: list[tuple[str, str]] = []
        said_something = False

        for step in range(self.cfg.max_steps):
            if self._cancel_event.is_set():
                yield CancelEvent("Lượt xử lý đã bị huỷ theo yêu cầu người dùng.")
                return

            self.ctx.prune_or_compress_if_needed()

            # Handle tool prompt injection for prompt mode
            messages_to_send = list(self.ctx.messages)
            if self.cfg.tool_mode == "prompt":
                instructions = generate_tool_instructions(self.tools.schemas())
                # Add instructions to a temporary system message
                messages_to_send = [
                    Message(role="system", content=(self.ctx.messages[0].content or "") + "\n\n" + instructions)
                ] + self.ctx.messages[1:]

            # Stream response from LLM
            llm_response: LLMResponse | None = None
            try:
                stream_iter = self.llm.stream_chat(
                    messages=messages_to_send,
                    tools=self.tools.schemas() if self.cfg.tool_mode != "prompt" else None,
                )
                async for item in stream_iter:
                    if self._cancel_event.is_set():
                        yield CancelEvent("Đã huỷ trong khi nhận phản hồi từ mô hình.")
                        return

                    if isinstance(item, str):
                        yield TextDelta(text=item)
                    elif isinstance(item, LLMResponse):
                        llm_response = item
            except Exception as e:
                yield Final(text=f"Lỗi khi giao tiếp với LLM: {e}")
                return

            if not llm_response:
                yield Final(text="Không nhận được phản hồi hợp lệ từ mô hình.")
                return

            # Check prompt tool calls if in prompt mode
            if self.cfg.tool_mode == "prompt" and not llm_response.tool_calls:
                llm_response.tool_calls = parse_prompt_tool_calls(llm_response.content)

            self.ctx.add_assistant(
                content=llm_response.content if llm_response.content else None,
                tool_calls=llm_response.tool_calls if llm_response.tool_calls else None,
            )

            # If no tool calls, this is the final answer
            if not llm_response.tool_calls:
                # If model hasn't called say() during this turn, generate a spoken summary
                if not said_something and llm_response.content:
                    fallback_speech = self._extract_spoken_summary(llm_response.content)
                    if fallback_speech:
                        yield SayEvent(text=fallback_speech)

                yield Final(text=llm_response.content, usage=None)
                return

            # Process tool calls
            for call in llm_response.tool_calls:
                if self._cancel_event.is_set():
                    yield CancelEvent("Đã huỷ trước khi thực thi công cụ.")
                    return

                call_signature = (call.name, str(call.arguments))
                recent_calls.append(call_signature)
                # Loop detection: 3 identical consecutive calls
                if len(recent_calls) >= 3 and recent_calls[-1] == recent_calls[-2] == recent_calls[-3]:
                    err_msg = f"Phát hiện vòng lặp vô ích: Công cụ '{call.name}' được gọi lặp lại 3 lần với cùng tham số. Dừng bước này."
                    self.ctx.add_tool_result(call.id, err_msg, tool_name=call.name)
                    yield ToolResultEvent(call_id=call.id, tool=call.name, output="", error=err_msg, is_error=True)
                    continue

                yield ToolCallStart(call_id=call.id, tool=call.name, args=call.get_args_dict())

                if call.name == "say":
                    said_something = True

                # Safety check
                decision = self.safety.check(call)
                if decision.denied:
                    result = ToolResult.denied(decision.reason)
                    yield ToolResultEvent(
                        call_id=call.id,
                        tool=call.name,
                        output=result.output,
                        error=result.error,
                        is_error=True,
                    )
                    self.ctx.add_tool_result(call.id, result.for_llm(), tool_name=call.name)
                    continue

                if decision.ask:
                    yield ApprovalRequest(
                        call_id=call.id,
                        tool=call.name,
                        args=call.get_args_dict(),
                        risk_level=decision.level,
                        reason=decision.reason,
                        diff=decision.diff,
                    )
                    approved = await self.approval.request_approval(call, decision)
                    yield ApprovalResponse(call_id=call.id, approved=approved)
                    if not approved:
                        result = ToolResult.denied("Người dùng đã từ chối thao tác.")
                        self.ctx.add_tool_result(call.id, result.for_llm(), tool_name=call.name)
                        yield ToolResultEvent(
                            call_id=call.id,
                            tool=call.name,
                            output=result.output,
                            error=result.error,
                            is_error=True,
                        )
                        continue

                # Execute tool
                tool_ctx = ToolContext(
                    workdir=self.safety.sandbox.workdir,
                    cancel_event=self._cancel_event,
                )
                result = await self.tools.execute(call.name, call.get_args_dict(), tool_ctx)

                self.ctx.add_tool_result(call.id, result.for_llm(), tool_name=call.name)
                yield ToolResultEvent(
                    call_id=call.id,
                    tool=call.name,
                    output=result.output,
                    error=result.error,
                    is_error=result.is_error,
                )

        yield Final(text="Đã đạt giới hạn tối đa số bước xử lý (max_steps); tạm dừng để bảo đảm an toàn.")

    def _extract_spoken_summary(self, text: str) -> str:
        """Extract a clean 1-2 sentence speech summary from markdown answer."""
        import re

        # Remove code blocks
        clean = re.sub(r"```[\s\S]*?```", "", text)
        # Remove markdown headers and URLs
        clean = re.sub(r"https?://\S+", "", clean)
        clean = re.sub(r"[#*`_>\[\]]", " ", clean)
        clean = " ".join(clean.split())

        # Split into sentences
        sentences = re.split(r"(?<=[.!?])\s+", clean)
        selected = [s.strip() for s in sentences if len(s.strip()) > 5][:2]
        return " ".join(selected)
