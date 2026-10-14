# Project Brief — `claw-cli` & `gemma_stt`

## 1. Tổng quan dự án (Project Overview)
**`claw-cli`** là trợ lý dòng lệnh (CLI) và điều khiển máy tính Windows thông minh bằng **tiếng Việt** (hỗ trợ cả giọng nói và văn bản), tích hợp cùng gói **`gemma_stt`** (nhận dạng giọng nói tiếng Việt gần realtime bằng Gemma 4) và **Google Colab Unified AI Gateway** (`llama.cpp` CUDA server + FastAPI Gateway + Ngrok).

## 2. Mục tiêu cốt lõi (Core Goals)
1. **Điều khiển bằng giọng nói & văn bản tiếng Việt:**
   - Cho phép người dùng tương tác qua terminal (`claw`) bằng văn bản hoặc giọng nói tiếng Việt tự nhiên.
   - Hỗ trợ chuyển đổi linh hoạt giữa các chế độ đầu vào:
     - Hỗn hợp (`hybrid`): Nhấn `Space` để nói hoặc gõ phím trực tiếp.
     - `/speech on`: Chỉ nhận lệnh bằng giọng nói (lắng nghe liên tục, tự động chốt câu khi ngừng nói).
     - `/speech off`: Chỉ nhận lệnh bằng văn bản.
2. **Tự động phát hiện kết thúc câu nói (Automatic End-of-Utterance / VAD):**
   - Sử dụng **Silero VAD v5 ONNX** (`state` + `context` 64 mẫu) kết hợp ngưỡng năng lượng thích nghi (Adaptive Noise Floor + Hysteresis) để phân biệt giọng nói tiếng Việt với tiếng ồn nền và tự động chốt câu ngay khi người dùng ngừng nói ~`600 ms`.
3. **Kiến trúc AI hợp nhất qua một `base_url` duy nhất trên Google Colab:**
   - Phục vụ đồng thời **Main LLM** (`gemma-4-26B-A4B-it-Q4_K_M.gguf` trên Port `8001`) và **STT Model** (`gemma-4-E2B-it-Q4_0.gguf` + `mmproj-gemma-4-E2B-it-Q8_0.gguf` trên Port `8003`) phía sau **FastAPI API Gateway (Port `8000`)** qua một đường hầm Ngrok duy nhất (`.../v1`).
   - Hỗ trợ chạy **Gemma 4 E2B STT cục bộ** (`local_gemma` trên GPU NVIDIA Windows với lượng tử hóa 4-bit/8-bit) hoặc tự động định tuyến lên Colab (`remote_v1` / `auto`).
4. **An toàn & Kiểm soát máy tính Windows (`winctl` + `safety`):**
   - Hỗ trợ các công cụ đọc/ghi file, chạy lệnh shell, điều khiển cửa sổ Windows (UI Automation, hotkeys, mở ứng dụng, trình duyệt, tìm kiếm YouTube/Web) với cơ chế phân quyền an toàn (`read`, `write`, `exec`, `dangerous`) và nhật ký kiểm toán (`audit.jsonl`).

## 3. Phạm vi dự án (Project Scope)
- **Trong phạm vi (In Scope):**
  - Ứng dụng CLI tương tác `claw` (`src/claw/`) trên Windows 10/11.
  - Gói độc lập & tích hợp `gemma_stt` (`src/gemma_stt/`) cho nhận dạng tiếng Việt gần realtime từ microphone hoặc file WAV.
  - Notebook triển khai nhanh trên Google Colab (`colab/colab_llama_cpp_ngrok.ipynb`) với thời gian khởi động ~45 giây (dùng pre-built CUDA binary của `ggml-org/llama.cpp` + `hf_transfer` song song).
  - Bộ kiểm thử tự động (`tests/`) với `pytest`, `ruff`, `mypy`.
- **Ngoài phạm vi (Out of Scope hiện tại):**
  - Streaming ASR từng từ theo thời gian thực dưới 100ms (hiện dùng kiến trúc near-real-time theo từng câu/đoạn sau khoảng lặng 600ms).
  - Speaker diarization (phân biệt nhiều người nói cùng lúc).
