from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any, AsyncIterator

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)

from claw.config import LLMConfig, discover_remote_base_url
from claw.llm.schema import LLMResponse, Message, ToolCall

logger = logging.getLogger("claw.llm")


class LLMClient:
    def __init__(self, cfg: LLMConfig, http_client: Any = None) -> None:
        self.cfg = cfg
        self._http_client = http_client
        self._resolved_model: str | None = None

        if "127.0.0.1" in cfg.base_url or "localhost" in cfg.base_url:
            cur = os.environ.get("NO_PROXY", "")
            if "127.0.0.1" not in cur:
                os.environ["NO_PROXY"] = f"{cur},127.0.0.1,localhost".strip(",")

        self.client = self._build_client(cfg.base_url)

    def _build_client(self, base_url: str) -> AsyncOpenAI:
        return AsyncOpenAI(
            base_url=base_url.rstrip("/"),
            api_key=self.cfg.api_key or "not-needed",
            default_headers=self.cfg.extra_headers,
            timeout=self.cfg.timeout_s,
            max_retries=0,  # We implement custom retry with exponential backoff
            http_client=self._http_client,
        )

    async def _try_refresh_endpoint(self) -> bool:
        """Check discovery_url for a newer gradio.live /v1 URL if the current one failed."""
        if not self.cfg.discovery_url or self._http_client is not None:
            return False
        if "CLAW_BASE_URL" in os.environ or "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ:
            return False
        new_url = await asyncio.to_thread(discover_remote_base_url, self.cfg.discovery_url)
        if new_url and new_url.rstrip("/") != self.cfg.base_url.rstrip("/"):
            logger.info("Auto-discovered new Colab endpoint: %s", new_url)
            self.cfg.base_url = new_url
            self.client = self._build_client(new_url)
            self._resolved_model = None
            return True
        return False

    async def get_model(self) -> str:
        if self.cfg.model != "auto" and self.cfg.model:
            return self.cfg.model

        if self._resolved_model:
            return self._resolved_model

        for attempt in range(2):
            try:
                models_page = await self.client.models.list()
                model_ids = [m.id for m in models_page.data]
                if model_ids:
                    self._resolved_model = model_ids[0]
                    logger.info(f"Auto-detected model: {self._resolved_model}")
                    return self._resolved_model
                break
            except Exception as e:
                if attempt == 0 and await self._try_refresh_endpoint():
                    continue
                logger.warning(f"Failed to auto-detect model from {self.cfg.base_url}: {e}")
                break

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

            except (APIConnectionError, APIStatusError, RateLimitError, InternalServerError, httpx.RequestError) as e:
                last_err = e
                if attempt < self.cfg.max_retries:
                    if await self._try_refresh_endpoint():
                        kwargs["model"] = await self.get_model()
                        continue
                    backoff = (2**attempt) * 1.0
                    logger.warning(f"LLM request failed ({e}). Retrying in {backoff}s...")
                    await asyncio.sleep(backoff)
                else:
                    raise last_err
            except Exception as e:
                raise e
