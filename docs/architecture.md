# Kiến trúc hệ thống claw-cli

## 1. Mô hình tổng thể
`claw-cli` hoạt động theo mô hình hướng sự kiện (Event-driven) và Provider interface cho mọi I/O:
- **Audio input:** Mic -> `AudioRecorder` -> `SileroVAD` -> `STTProvider` (faster-whisper) -> Text.
- **Input router:** Nhận diện lệnh meta giọng nói (dừng, đồng ý, huỷ...) vs prompt tác vụ cho Agent.
- **Agent Loop:**
  - Context & Prompt management
  - Streaming LLM Client (OpenAI-compatible)
  - Tool Parser (hỗ trợ cả OpenAI native tool_calls và JSON Prompt fallback)
  - Safety Policy & Sandbox
  - Tool Registry & Execution
- **Output:**
  - Rich Terminal UI (Console, Markdown, Progress, Panels)
  - TTS Streamer (`edge-tts` / `system`) với bộ lọc văn bản đọc to (loại bỏ code block, markdown, URLs).
- **Session:**
  - Session transcript JSONL
  - Audit logging.
