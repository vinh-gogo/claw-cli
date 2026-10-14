# Progress — Tiến độ dự án

## 1. Những hạng mục đã hoàn thành & Hoạt động tốt (What Works)
- [x] **Gói `gemma_stt` (`src/gemma_stt/`):**
  - Thu âm liên tục `16kHz mono`, ring buffer/queue giới hạn chống tràn bộ nhớ.
  - VAD hỗ trợ cả `rms` và `silero` (Silero v5 & v4 ONNX).
  - Runner hỗ trợ `remote_v1` (Colab Gateway `/v1/audio/transcriptions` và `/v1/chat/completions`), `local_gemma` (CUDA + lượng tử hóa 4-bit/8-bit), và `auto`.
  - Benchmark CLI, đánh giá WER/CER tiếng Việt, kiểm thử độ ổn định (soak test).
- [x] **Colab Unified AI Gateway (`colab/colab_llama_cpp_ngrok.ipynb`):**
  - Cài đặt nhanh trong ~45 giây (Pre-built CUDA binary + `hf_transfer` tải song song).
  - Chạy đồng thời `Gemma 4 26B A4B` (Port `8001`) và `Gemma 4 E2B STT + mmproj` (Port `8003`) phía sau FastAPI Gateway (Port `8000`) qua một URL Ngrok duy nhất (`.../v1`).
- [x] **Tích hợp `claw-cli` (`src/claw/`):**
  - Mặc định dùng `gemma-stt` (`gemma-4-stt`) qua Colab Gateway, không còn lỗi `cublas64_12.dll`.
  - Hỗ trợ lệnh `/speech on` (chỉ nhận giọng nói) và `/speech off` (chỉ nhận văn bản).
  - Tự động phát hiện khi người nói kết thúc câu (Silero VAD v5 ONNX + `silence_ms=600ms` + gửi tự động không cần bấm Enter).
  - Không còn lỗi in lặp 2 lần phản hồi của LLM trên console.
- [x] **Kiểm thử & Chất lượng mã nguồn:**
  - `134 passed` trong `pytest`.
  - `0 errors` với `ruff check src tests`.
  - `0 issues` với `mypy src` (83 file nguồn).

## 2. Những gì còn lại / Hướng mở rộng (What's Left to Build)
- [ ] Tùy chọn streaming âm thanh qua WebSocket (`/v1/audio/stream`) nếu trong tương lai muốn hiển thị phụ đề từng từ khi đang nói.
- [ ] Tùy chọn lệnh chỉnh nhanh độ trễ ngắt câu ngay trong CLI (ví dụ `/vad 500` hoặc `/vad 800`).

## 3. Các vấn đề đã biết & Cách xử lý (Known Issues & Mitigations)
- **Môi trường Python kép trên máy Windows:** Máy có cả Python 3.11 toàn cục và `.venv` (Python 3.12 tại `D:\claw-cli\.venv`). Lệnh `claw` chạy trên `.venv`. Mọi tính năng của `claw` đã được đảm bảo chạy độc lập trong `.venv` mà không phụ thuộc vào DLL CUDA cục bộ.
