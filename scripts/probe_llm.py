#!/usr/bin/env python3
"""
Probe script to verify capabilities of the LLM server:
- GET /v1/models
- Chat completion non-streaming
- Streaming SSE & TTFT (Time-to-first-token)
- Native tool/function calling support
- Audio transcriptions / speech endpoints support
"""

import argparse
import asyncio
import os
import sys
import time
from typing import Any

import httpx
from openai import AsyncOpenAI

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")


def load_env_file(filepath: str = ".env") -> None:
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


async def probe(base_url: str, api_key: str, model_override: str | None = None) -> dict[str, Any]:
    results: dict[str, Any] = {
        "base_url": base_url,
        "reachable": False,
        "models": [],
        "chat_completion": False,
        "streaming": False,
        "ttft_s": None,
        "tool_calling": False,
        "audio_transcriptions": False,
        "audio_speech": False,
        "recommended_tool_mode": "prompt",
        "error": None,
    }

    headers = {
        "ngrok-skip-browser-warning": "true",
    }
    if api_key and api_key != "not-needed":
        headers["Authorization"] = f"Bearer {api_key}"

    print(f"[*] Probing LLM server at {base_url}...")

    # 1. Test basic connectivity and models endpoint
    async with httpx.AsyncClient(headers=headers, timeout=10.0, follow_redirects=True) as http_client:
        try:
            resp = await http_client.get(f"{base_url.rstrip('/')}/models")
            if resp.status_code == 200:
                results["reachable"] = True
                data = resp.json()
                if isinstance(data, dict) and "data" in data:
                    results["models"] = [m.get("id") for m in data["data"] if isinstance(m, dict)]
                print(f"[✔] Models endpoint OK. Found {len(results['models'])} models: {results['models']}")
            else:
                print(f"[✘] Models endpoint returned HTTP {resp.status_code}: {resp.text[:200]}")
                results["error"] = f"HTTP {resp.status_code}: {resp.text[:200]}"
                return results
        except Exception as e:
            print(f"[✘] Failed to connect to server: {e}")
            results["error"] = str(e)
            return results

        # Check audio endpoints
        try:
            resp = await http_client.get(f"{base_url.rstrip('/')}/audio/transcriptions")
            results["audio_transcriptions"] = resp.status_code != 404
        except Exception:
            results["audio_transcriptions"] = False

        try:
            resp = await http_client.get(f"{base_url.rstrip('/')}/audio/speech")
            results["audio_speech"] = resp.status_code != 404
        except Exception:
            results["audio_speech"] = False

    target_model = model_override or (results["models"][0] if results["models"] else "default")
    print(f"[*] Using target model: {target_model}")

    client = AsyncOpenAI(
        base_url=base_url,
        api_key=api_key or "not-needed",
        default_headers={"ngrok-skip-browser-warning": "true"},
        timeout=30.0,
    )

    # 2. Test chat completion (non-streaming)
    try:
        t0 = time.perf_counter()
        resp = await client.chat.completions.create(
            model=target_model,
            messages=[{"role": "user", "content": "Xin chào! Bạn là ai?"}],
            temperature=0.2,
        )
        duration = time.perf_counter() - t0
        content = resp.choices[0].message.content or ""
        results["chat_completion"] = True
        print(f"[✔] Chat completion OK ({duration:.2f}s): {content[:80]}...")
    except Exception as e:
        print(f"[✘] Chat completion failed: {e}")

    # 3. Test streaming & TTFT
    try:
        t0 = time.perf_counter()
        stream = await client.chat.completions.create(
            model=target_model,
            messages=[{"role": "user", "content": "Đếm từ 1 đến 5 bằng tiếng Việt."}],
            stream=True,
            temperature=0.2,
        )
        first_token = True
        full_text = []
        async for chunk in stream:
            if first_token and chunk.choices and chunk.choices[0].delta.content:
                results["ttft_s"] = round(time.perf_counter() - t0, 3)
                first_token = False
            if chunk.choices and chunk.choices[0].delta.content:
                full_text.append(chunk.choices[0].delta.content)

        results["streaming"] = True
        print(f"[✔] Streaming OK (TTFT={results['ttft_s']}s): {''.join(full_text)[:80]}...")
    except Exception as e:
        print(f"[✘] Streaming failed: {e}")

    # 4. Test tool calling native
    test_tools = [
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List files in directory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "The directory path"}
                    },
                    "required": ["path"],
                },
            },
        }
    ]
    try:
        resp = await client.chat.completions.create(
            model=target_model,
            messages=[
                {
                    "role": "user",
                    "content": "Hãy gọi hàm list_files cho thư mục hiện tại '.' để xem danh sách file.",
                }
            ],
            tools=test_tools,
            tool_choice="auto",
        )
        choice = resp.choices[0]
        if choice.message.tool_calls:
            results["tool_calling"] = True
            results["recommended_tool_mode"] = "native"
            print(f"[✔] Tool calling native OK: {choice.message.tool_calls}")
        else:
            print("[!] Model did not return tool_calls (returned normal text). Fallback to prompt mode.")
            results["recommended_tool_mode"] = "prompt"
    except Exception as e:
        print(f"[✘] Tool calling native failed: {e}. Fallback to prompt mode.")
        results["recommended_tool_mode"] = "prompt"

    return results


async def main() -> None:
    parser = argparse.ArgumentParser(description="Probe LLM Server for claw-cli")
    parser.add_argument("--base-url", default=None, help="LLM base URL")
    parser.add_argument("--api-key", default=None, help="API key")
    parser.add_argument("--model", default=None, help="Model name override")
    parser.add_argument("--out", default="docs/llm-probe.md", help="Markdown output path")
    args = parser.parse_args()

    load_env_file()
    base_url = args.base_url or os.environ.get("CLAW_BASE_URL", "http://localhost:8000/v1")
    api_key = args.api_key or os.environ.get("CLAW_API_KEY", "not-needed")

    res = await probe(base_url, api_key, args.model)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("# Kết quả kiểm tra LLM Server (Spike Probe)\n\n")
        f.write(f"- **Thời gian:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"- **Base URL:** `{res['base_url']}`\n")
        f.write(f"- **Server online:** {'Có' if res['reachable'] else 'Không'}\n")
        if res["error"]:
            f.write(f"- **Lỗi:** `{res['error']}`\n")
        f.write(f"- **Danh sách models:** {res['models']}\n")
        f.write(f"- **Chat completion:** {'✔' if res['chat_completion'] else '✘'}\n")
        f.write(f"- **Streaming (SSE):** {'✔' if res['streaming'] else '✘'}\n")
        f.write(f"- **TTFT:** {res['ttft_s']}s\n")
        f.write(f"- **Tool calling native:** {'✔' if res['tool_calling'] else '✘'}\n")
        f.write(f"- **Audio Transcriptions:** {'✔' if res['audio_transcriptions'] else '✘'}\n")
        f.write(f"- **Audio Speech:** {'✔' if res['audio_speech'] else '✘'}\n")
        f.write(f"- **Chế độ tool đề xuất:** `{res['recommended_tool_mode']}`\n\n")
        f.write("## Quyết định kỹ thuật\n\n")
        f.write("1. **Hỗ trợ song song cả 2 chế độ (`tool_mode = 'native'` và `tool_mode = 'prompt'`)**:\n")
        f.write("   - Khi LLM hỗ trợ OpenAI function calling: dùng `native`.\n")
        f.write("   - Khi server offline hoặc model nhỏ không hỗ trợ tool calling: tự động fallback về `prompt` (JSON block parser).\n")
        f.write("2. **STT & TTS local:** Do server không có sẵn `/v1/audio/*`, sử dụng `faster-whisper` cho STT và `edge-tts` cho TTS theo đúng kế hoạch kiến trúc.\n")

    print(f"\n[✔] Report generated at {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
