from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from claw.agent.context import AgentContext
from claw.agent.loop import AgentLoop
from claw.config import LLMConfig, SafetyConfig
from claw.events import Final, ToolCallStart, ToolResultEvent
from claw.llm.client import LLMClient
from claw.safety.approval import ApprovalManager
from claw.safety.policy import SafetyPolicy
from claw.safety.sandbox import PathSandbox
from claw.tools import create_default_registry

from .fake_server import app


@pytest.mark.asyncio
async def test_agent_loop_end_to_end_with_fake_server(tmp_path: Path) -> None:
    # Create sample file in tmp_path
    (tmp_path / "hello.py").write_text("print('hello')", encoding="utf-8")

    llm_cfg = LLMConfig(
        base_url="http://fake-test/v1",
        api_key="test-key",
        model="qwen2.5-coder-7b",
        tool_mode="native",
        timeout_s=5.0,
        max_retries=1,
    )
    # Use in-memory ASGI transport for direct, reliable testing
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://fake-test/v1") as test_http_client:
        llm = LLMClient(llm_cfg, http_client=test_http_client)
        sandbox = PathSandbox(tmp_path)
        safety = SafetyPolicy(SafetyConfig(yolo=True), sandbox)
        approval = ApprovalManager()
        tools = create_default_registry()
        ctx = AgentContext("Bạn là trợ lý terminal.")

        agent_loop = AgentLoop(
            llm=llm,
            ctx=ctx,
            tools=tools,
            safety=safety,
            approval=approval,
            cfg=llm_cfg,
        )

        events = []
        async for event in agent_loop.run_turn("Hãy liệt kê các file trong thư mục này."):
            events.append(event)

        # Verify tool call was initiated and completed
        tool_call_starts = [e for e in events if isinstance(e, ToolCallStart)]
        tool_results = [e for e in events if isinstance(e, ToolResultEvent)]
        finals = [e for e in events if isinstance(e, Final)]

        assert len(tool_call_starts) >= 1
        assert tool_call_starts[0].tool == "list_dir"
        assert len(tool_results) >= 1
        assert "hello.py" in tool_results[0].output
        assert len(finals) == 1
        assert "liệt kê" in finals[0].text
