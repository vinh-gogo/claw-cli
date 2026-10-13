from __future__ import annotations

import asyncio
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Coroutine, Literal

from pydantic import BaseModel

RiskLevel = Literal["none", "read", "low", "input", "write", "exec", "dangerous"]


@dataclass
class ToolContext:
    workdir: Path = field(default_factory=Path.cwd)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    emit_event: Callable[[Any], Coroutine[Any, Any, None]] | None = None
    max_output_chars: int = 8000

    def scrubbed_env(self) -> dict[str, str]:
        """Return environment variables excluding sensitive credentials."""
        sensitive_keywords = {"KEY", "TOKEN", "SECRET", "PASSWORD", "AUTH", "CREDENTIALS"}
        clean: dict[str, str] = {}
        for k, v in os.environ.items():
            k_upper = k.upper()
            if any(secret in k_upper for secret in sensitive_keywords):
                continue
            clean[k] = v
        return clean


@dataclass
class ToolResult:
    output: str
    error: str | None = None
    is_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(cls, output: str, **kwargs: Any) -> ToolResult:
        return cls(output=output, is_error=False, **kwargs)

    @classmethod
    def fail(cls, error: str, output: str = "", **kwargs: Any) -> ToolResult:
        return cls(output=output, error=error, is_error=True, **kwargs)

    @classmethod
    def denied(cls, reason: str) -> ToolResult:
        return cls(
            output=f"Hành động bị từ chối: {reason}",
            error="Action denied by user or policy",
            is_error=True,
        )

    def for_llm(self) -> str:
        if self.is_error:
            msg = f"ERROR: {self.error}"
            if self.output:
                msg += f"\nOutput:\n{self.output}"
            return msg
        return self.output


class Tool(ABC):
    name: str
    description: str
    risk: RiskLevel = "read"
    args_model: type[BaseModel]

    @abstractmethod
    async def run(self, args: Any, ctx: ToolContext) -> ToolResult:
        pass

    def to_openai_schema(self) -> dict[str, Any]:
        schema = self.args_model.model_json_schema()
        # Clean up title/description for clean OpenAI schema
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.to_openai_schema() for tool in self._tools.values()]

    async def execute(self, name: str, raw_args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        tool = self.get(name)
        if not tool:
            return ToolResult.fail(f"Tool '{name}' không tồn tại.")

        try:
            parsed_args = tool.args_model.model_validate(raw_args)
        except Exception as e:
            return ToolResult.fail(f"Tham số không hợp lệ cho tool '{name}': {e}")

        try:
            return await tool.run(parsed_args, ctx)
        except Exception as e:
            return ToolResult.fail(f"Lỗi khi thực thi tool '{name}': {e}")
