from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, AsyncIterator

import httpx
from openai import APIConnectionError, AsyncOpenAI, InternalServerError, RateLimitError

from claw.config import LLMConfig
from claw.llm.schema import LLMResponse, Message, ToolCall

logger = logging.getLogger("claw.llm")


class LLMClient:
    def __init__(self, cfg: LLMConfig, http_client: Any = None) -> None:
        self.cfg = cfg
        self._resolved_model: str | None = None

        if "127.0.0.1" in cfg.base_url or "localhost" in cfg.base_url:
            cur = os.environ.get("NO_PROXY", "")
            if "127.0.0.1" not in cur:
                os.environ["NO_PROXY"] = f"{cur},127.0.0.1,localhost".strip(",")

        self.client = AsyncOpenAI(
            base_url=cfg.base_url.rstrip("/"),
            api_key=cfg.api_key or "not-needed",
            default_headers=cfg.extra_headers,
            timeout=cfg.timeout_s,
            max_retries=0,  # We implement custom retry with exponential backoff
            http_client=http_client,
        )

    async def get_model(self) -> str:
        if self.cfg.model != "auto" and self.cfg.model:
            return self.cfg.model

        if self._resolved_model:
            return self._resolved_model

        try:
            models_page = await self.client.models.list()
            model_ids = [m.id for m in models_page.data]
            if model_ids:
                self._resolved_model = model_ids[0]
                logger.info(f"Auto-detected model: {self._resolved_model}")
                return self._resolved_model
        except Exception as e:
            logger.warning(f"Failed to auto-detect model from {self.cfg.base_url}: {e}")

        self._resolved_model = "default"
        return self._resolved_model

    async def stream_chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str | ToolCall | LLMResponse]:
        """Stream completion, yielding text delta strings, and finally yielding the complete LLMResponse."""
        model = await self.get_model()
        formatted_messages = [m.to_openai_dict() for m in messages]

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": formatted_messages,
            "temperature": self.cfg.temperature,
            "stream": True,
        }
        if tools and self.cfg.tool_mode == "native":
            kwargs["tools"] = tools

        last_err: Exception | None = None
        for attempt in range(self.cfg.max_retries + 1):
            try:
                stream = await self.client.chat.completions.create(**kwargs)
                full_content: list[str] = []
                tool_calls_map: dict[int, dict[str, Any]] = {}

                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta

                    # Text delta
                    if delta.content:
                        full_content.append(delta.content)
                        yield delta.content

                    # Tool call deltas
                    if delta.tool_calls:
                        for tc_chunk in delta.tool_calls:
                            idx = tc_chunk.index
                            if idx not in tool_calls_map:
                                tool_calls_map[idx] = {
                                    "id": tc_chunk.id or f"call_{idx}",
                                    "name": tc_chunk.function.name if tc_chunk.function else "",
                                    "arguments": "",
                                }
                            if tc_chunk.id:
                                tool_calls_map[idx]["id"] = tc_chunk.id
                            if tc_chunk.function:
                                if tc_chunk.function.name:
                                    tool_calls_map[idx]["name"] = tc_chunk.function.name
                                if tc_chunk.function.arguments:
                                    tool_calls_map[idx]["arguments"] += tc_chunk.function.arguments

                parsed_tool_calls: list[ToolCall] = []
                for idx in sorted(tool_calls_map.keys()):
                    tc_data = tool_calls_map[idx]
                    raw_args = tc_data["arguments"]
                    try:
                        args = json.loads(raw_args) if raw_args else {}
                    except Exception:
                        args = {"raw": raw_args}
                    parsed_tool_calls.append(
                        ToolCall(
                            id=tc_data["id"],
                            name=tc_data["name"],
                            arguments=args,
                        )
                    )

                response = LLMResponse(
                    content="".join(full_content),
                    tool_calls=parsed_tool_calls,
                )
                yield response
                return

            except (APIConnectionError, RateLimitError, InternalServerError, httpx.RequestError) as e:
                last_err = e
                if attempt < self.cfg.max_retries:
                    backoff = (2**attempt) * 1.0
                    logger.warning(f"LLM request failed ({e}). Retrying in {backoff}s...")
                    await asyncio.sleep(backoff)
                else:
                    raise last_err
            except Exception as e:
                raise e
