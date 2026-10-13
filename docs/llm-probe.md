# Kết quả kiểm tra LLM Server (Spike Probe)

- **Thời gian:** 2026-10-13 09:36:39
- **Base URL:** `https://snowcapped-denice-unprudent.ngrok-free.dev/v1`
- **Server online:** Có
- **Danh sách models:** ['/content/gemma-4-26B-A4B-it-Q4_K_M.gguf']
- **Chat completion:** ✔
- **Streaming (SSE):** ✔
- **TTFT:** 0.751s
- **Tool calling native:** ✔
- **Audio Transcriptions:** ✘
- **Audio Speech:** ✘
- **Chế độ tool đề xuất:** `native`

## Quyết định kỹ thuật

1. **Hỗ trợ song song cả 2 chế độ (`tool_mode = 'native'` và `tool_mode = 'prompt'`)**:
   - Khi LLM hỗ trợ OpenAI function calling: dùng `native`.
   - Khi server offline hoặc model nhỏ không hỗ trợ tool calling: tự động fallback về `prompt` (JSON block parser).
2. **STT & TTS local:** Do server không có sẵn `/v1/audio/*`, sử dụng `faster-whisper` cho STT và `edge-tts` cho TTS theo đúng kế hoạch kiến trúc.
