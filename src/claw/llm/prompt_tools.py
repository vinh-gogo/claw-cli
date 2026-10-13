from __future__ import annotations

import json
import re
import uuid
from typing import Any

from claw.llm.schema import ToolCall


def generate_tool_instructions(tools: list[dict[str, Any]]) -> str:
    """Generate prompt instructions explaining available tools and the JSON invocation format."""
    lines = [
        "## CÔNG CỤ CÓ SẴN (TOOLS)",
        "Bạn có quyền sử dụng các công cụ sau để thao tác trong hệ thống. Để gọi một công cụ, hãy trả về một khối JSON duy nhất theo định dạng:",
        '```json\n{"tool": "tên_công_cụ", "args": {"tham_số": "giá_trị"}}\n```',
        "",
    ]
    for t in tools:
        fn = t.get("function", {})
        name = fn.get("name", "unknown")
        desc = fn.get("description", "")
        params = fn.get("parameters", {})
        lines.append(f"### `{name}`")
        lines.append(f"- **Mô tả**: {desc}")
        lines.append(f"- **Tham số**: `{json.dumps(params.get('properties', {}), ensure_ascii=False)}`")
        if "required" in params and params["required"]:
            lines.append(f"- **Bắt buộc**: {', '.join(params['required'])}")
        lines.append("")
    lines.append(
        "Lưu ý: Nếu bạn muốn thực hiện hành động, chỉ xuất khối JSON của công cụ đó. Sau khi nhận được kết quả công cụ, bạn có thể giải thích tiếp cho người dùng."
    )
    return "\n".join(lines)


def parse_prompt_tool_calls(text: str) -> list[ToolCall]:
    """Extract tool calls from JSON blocks in LLM output."""
    tool_calls: list[ToolCall] = []

    # 1. Match code blocks ```json ... ``` or ``` ... ```
    pattern = r"```(?:json)?\s*(\{[\s\S]*?\})\s*```"
    matches = re.findall(pattern, text)

    candidate_strings = matches if matches else []

    # 2. If no code blocks found, check if the entire text or a subsegment is JSON
    if not candidate_strings:
        brace_pattern = r"(\{[^{}]*\"tool\"[^{}]*\})"
        candidate_strings = re.findall(brace_pattern, text)

    for s in candidate_strings:
        try:
            data = json.loads(s.strip())
            if isinstance(data, dict):
                tool_name = data.get("tool") or data.get("name")
                args = data.get("args") or data.get("arguments") or {}
                if tool_name and isinstance(tool_name, str):
                    tool_calls.append(
                        ToolCall(
                            id=f"call_{uuid.uuid4().hex[:8]}",
                            name=tool_name,
                            arguments=args,
                        )
                    )
        except Exception:
            continue

    return tool_calls
