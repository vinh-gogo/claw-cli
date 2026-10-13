from __future__ import annotations

from claw.agent.context import AgentContext


def test_context_token_estimation_and_pruning() -> None:
    ctx = AgentContext(system_prompt="Hệ thống trợ lý", max_tokens=100)

    # Initially token estimate is low
    assert ctx.estimate_tokens() > 0

    # Add messages
    for i in range(15):
        ctx.add_user(f"Câu hỏi số {i}: Hãy cho tôi biết chi tiết về các tệp tin trong hệ thống...")
        ctx.add_assistant(f"Trả lời số {i}: Đây là câu trả lời chi tiết rất dài với nhiều thông tin...")

    # Should have accumulated messages and exceeded 75 tokens
    assert ctx.estimate_tokens() > 75
    pruned = ctx.prune_or_compress_if_needed()
    assert pruned is True
    # System message preserved
    assert ctx.messages[0].role == "system"
    assert "Hệ thống trợ lý" in ctx.messages[0].content
    # Middle summarized
    assert any("Đã nén" in (m.content or "") for m in ctx.messages)
