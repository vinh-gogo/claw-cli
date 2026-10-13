from __future__ import annotations

from claw.llm.schema import Message, ToolCall


class AgentContext:
    def __init__(self, system_prompt: str, max_tokens: int = 16384) -> None:
        self.max_tokens = max_tokens
        self.messages: list[Message] = [Message(role="system", content=system_prompt)]

    def add_user(self, text: str) -> None:
        self.messages.append(Message(role="user", content=text))

    def add_assistant(self, content: str | None = None, tool_calls: list[ToolCall] | None = None) -> None:
        self.messages.append(Message(role="assistant", content=content, tool_calls=tool_calls))

    def add_tool_result(self, call_id: str, output: str, tool_name: str | None = None) -> None:
        self.messages.append(
            Message(
                role="tool",
                content=output,
                tool_call_id=call_id,
                name=tool_name,
            )
        )

    def estimate_tokens(self) -> int:
        """Estimate token count based on total characters (~3.5 chars per token for VI/EN mix)."""
        total_chars = 0
        for m in self.messages:
            if m.content:
                total_chars += len(m.content)
            if m.tool_calls:
                for tc in m.tool_calls:
                    total_chars += len(tc.name) + len(str(tc.arguments))
        return int(total_chars / 3.5)

    def prune_or_compress_if_needed(self) -> bool:
        """If token budget exceeds 75%, compress or trim older non-system turns."""
        est_tokens = self.estimate_tokens()
        if est_tokens <= int(self.max_tokens * 0.75):
            return False

        # Keep system prompt (index 0) and the most recent 6 messages
        if len(self.messages) > 8:
            system_msg = self.messages[0]
            recent_msgs = self.messages[-6:]
            middle_msgs = self.messages[1:-6]

            # Create a compact summary note of pruned messages
            summary_note = f"[Đã nén và lưu trữ {len(middle_msgs)} tin nhắn trao đổi trước đó để tiết kiệm ngữ cảnh.]"
            summary_msg = Message(role="system", content=summary_note)

            self.messages = [system_msg, summary_msg] + recent_msgs
            return True

        return False

    def clear_history(self) -> None:
        if self.messages:
            system_msg = self.messages[0]
            self.messages = [system_msg]
