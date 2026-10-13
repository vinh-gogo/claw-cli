from __future__ import annotations

import re

import httpx
from pydantic import BaseModel, Field

from claw.tools.base import RiskLevel, Tool, ToolContext, ToolResult


class WebFetchArgs(BaseModel):
    url: str = Field(description="URL trang web cần đọc nội dung")
    max_chars: int = Field(default=5000, description="Số lượng ký tự tối đa trả về")


class WebFetchTool(Tool):
    name = "web_fetch"
    description = "Tải và trích xuất nội dung văn bản chính từ một trang web."
    risk: RiskLevel = "read"
    args_model = WebFetchArgs

    async def run(self, args: WebFetchArgs, ctx: ToolContext) -> ToolResult:
        headers = {
            "User-Agent": "claw-cli/0.0.1 (Terminal Assistant)",
        }
        try:
            async with httpx.AsyncClient(headers=headers, timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(args.url)
                if resp.status_code != 200:
                    return ToolResult.fail(f"HTTP lỗi {resp.status_code} khi tải {args.url}")

                html = resp.text
                # Simple HTML to text extraction
                cleaned = re.sub(r"<(script|style)[^>]*>[\s\S]*?</\1>", "", html, flags=re.IGNORECASE)
                cleaned = re.sub(r"<[^>]+>", " ", cleaned)
                cleaned = re.sub(r"\s+", " ", cleaned).strip()

                if len(cleaned) > args.max_chars:
                    cleaned = cleaned[: args.max_chars] + f"\n... [Đã cắt sau {args.max_chars} ký tự]"

                return ToolResult.success(f"Nội dung từ {args.url}:\n{cleaned}")
        except Exception as e:
            return ToolResult.fail(f"Lỗi khi tải trang web {args.url}: {e}")
