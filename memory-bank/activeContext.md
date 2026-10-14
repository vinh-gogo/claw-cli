# Active Context — Trạng thái công việc hiện tại

## 1. Trọng tâm hiện tại (Current Work Focus)
Hoàn thiện trải nghiệm điều khiển giọng nói tiếng Việt gần realtime cho `claw-cli` kết nối với Colab Unified Gateway (`Gemma 4 26B` + `Gemma 4 E2B STT`) và thiết lập hệ thống tài liệu **Cline Memory Bank** (`memory-bank/` + `.clinerules`).

## 2. Các thay đổi vừa thực hiện (Recent Changes)
1. **Tối ưu thời gian khởi động Colab Notebook (`colab/colab_llama_cpp_ngrok.ipynb`):**
   - Giảm thời gian chạy Ô 1 từ **~10 phút xuống ~45 giây** bằng cách tải bản Pre-built Ubuntu CUDA binary chính thức từ GitHub Releases của `ggml-org/llama.cpp` (~10s) và tải song song 3 file GGUF qua `hf_transfer` (~35s).
2. **Sửa lỗi `Library cublas64_12.dll is not found` khi dùng giọng nói trong `claw`:**
   - Chuyển `STTConfig.provider` mặc định trong `src/claw/config.py` từ `"faster-whisper"` sang `"gemma-stt"` (`model = "gemma-4-stt"`).
   - Cập nhật `GemmaSTTConfig.load()` (`src/gemma_stt/config_schema.py`) và `Gemma4STTProvider` (`src/claw/voice/stt/gemma.py`) để tự động tìm `D:\claw-cli\config.yaml` và đồng bộ `base_url` từ `LLMConfig` khi chạy `claw` ở bất kỳ thư mục nào (như `C:\Users\lea26`).
   - Bổ sung cơ chế tự động fallback về `device="cpu"` trong `FasterWhisperSTT` (`src/claw/voice/stt/faster_whisper.py`) nếu thiếu DLL CUDA trên Windows.
   - Sửa lỗi in lặp 2 lần nội dung trả lời cuối lượt trong `ConsoleRenderer` (`src/claw/ui/console.py`).
3. **Bổ sung lệnh `/speech on` và `/speech off` (`src/claw/app.py`, `src/claw/ui/prompt.py`, `src/claw/ui/status.py`, `src/claw/agent/router.py`):**
   - `/speech on`: Chuyển sang chế độ **chỉ nhận lệnh bằng giọng nói** (tự động bật mic nghe liên tục qua từng lượt).
   - `/speech off`: Chuyển sang chế độ **chỉ nhận lệnh bằng văn bản** (vô hiệu hóa phím `Space` bật mic).
4. **Tự động phát hiện kết thúc câu nói (Automatic End-of-Utterance Detection):**
   - Sửa lỗi tương thích **Silero VAD v5 ONNX** (`inputs: ['input', 'state', 'sr']` với `state=(2, 1, 128)` và `context=(1, 64)`) trong `src/claw/voice/vad.py` và `src/gemma_stt/vad.py`.
   - Giảm `silence_ms` xuống `600 ms` và đặt `review_transcript = False` để tự động chốt câu và thực thi ngay khi người nói dừng 0.6 giây.
5. **Khởi tạo Memory Bank (`memory-bank/` & `.clinerules`):**
   - Tạo đầy đủ 6 file cốt lõi trong `memory-bank/` và `.clinerules`.

## 3. Các bước tiếp theo (Next Steps)
- Theo dõi phản hồi thực tế của người dùng khi sử dụng `/speech on` với Colab Gateway.
- Nếu cần tinh chỉnh độ nhạy ngắt câu theo môi trường micro cụ thể, có thể điều chỉnh `audio.silence_ms` (ví dụ `500`–`800` ms) hoặc ngưỡng `vad.threshold`.
