from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title="Fake OpenAI Server for claw-cli tests")

MODELS = [
    {"id": "qwen2.5-coder-7b", "object": "model", "owned_by": "organization"},
    {"id": "mock-gpt-4o", "object": "model", "owned_by": "openai"},
]


@app.get("/v1/models")
async def list_models() -> dict[str, Any]:
    return {"object": "list", "data": MODELS}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Any:
    body = await request.json()
    messages = body.get("messages", [])
    stream = body.get("stream", False)

    last_user_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user_msg = m.get("content", "")
            break

    # Check if a tool result has already been provided
    has_tool_result = any(m.get("role") == "tool" for m in messages)

    # Determine scenario based on user input
    # Scenario 1: Tool call request (e.g. list files)
    if not has_tool_result and ("liệt kê" in last_user_msg.lower() or "list" in last_user_msg.lower()):
        if stream:
            async def generate_tool_stream() -> AsyncIterator[str]:
                # Send tool call chunk
                tc_chunk = {
                    "id": "chatcmpl-test",
                    "object": "chat.completion.chunk",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_mock_123",
                                        "type": "function",
                                        "function": {
                                            "name": "list_dir",
                                            "arguments": '{"path": "."}',
                                        },
                                    }
                                ],
                            },
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(tc_chunk)}\n\n"
                finish_chunk = {
                    "id": "chatcmpl-test",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
                }
                yield f"data: {json.dumps(finish_chunk)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(generate_tool_stream(), media_type="text/event-stream")
        else:
            return JSONResponse(
                {
                    "id": "chatcmpl-test",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_mock_123",
                                        "type": "function",
                                        "function": {
                                            "name": "list_dir",
                                            "arguments": '{"path": "."}',
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                }
            )

    # Scenario 2: Second turn after tool result (final answer)
    has_tool_result = any(m.get("role") == "tool" for m in messages)
    reply_text = (
        "Đã liệt kê xong các tệp tin trong thư mục hiện tại."
        if has_tool_result
        else f"Xin chào! Bạn vừa nói: '{last_user_msg}'"
    )

    if stream:
        async def generate_text_stream() -> AsyncIterator[str]:
            words = reply_text.split()
            for w in words:
                chunk = {
                    "id": "chatcmpl-test",
                    "choices": [{"index": 0, "delta": {"content": w + " "}, "finish_reason": None}],
                }
                yield f"data: {json.dumps(chunk)}\n\n"
                await asyncio.sleep(0.01)
            yield f"data: {json.dumps({'id': 'chatcmpl-test', 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(generate_text_stream(), media_type="text/event-stream")
    else:
        return JSONResponse(
            {
                "id": "chatcmpl-test",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": reply_text},
                        "finish_reason": "stop",
                    }
                ],
            }
        )
