# claw-cli 🎙️🤖

> **Trợ lý terminal điều khiển bằng giọng nói tiếng Việt và văn bản dành cho lập trình viên.**
> Nói vào microphone → `claw` nghe, hiểu, tự động dùng công cụ (đọc/ghi file, chạy lệnh shell…) để làm việc trong terminal → báo cáo kết quả bằng chữ và giọng nói tự nhiên.

---

## 🌟 Điểm nổi bật

- **Điều khiển terminal bằng tiếng Việt tự nhiên:** Hỗ trợ nói tiếng Việt xen lẫn thuật ngữ kỹ thuật tiếng Anh (`git`, `commit`, `docker`, `pytest`, `npm`...).
- **Vòng lặp Agent thông minh (Agent Loop):** Tự động lập kế hoạch, gọi công cụ, kiểm tra kết quả và tự sửa lỗi đến khi hoàn thành mục tiêu.
- **Bảo mật & An toàn tối đa (Safety-First):**
  - Phân loại rủi ro 4 cấp độ: `read`, `write`, `exec`, `dangerous`.
  - Các lệnh nguy hiểm (`rm -rf`, `sudo`, `git push --force`, `git reset --hard`...) **bắt buộc xác nhận trực tiếp từ bàn phím** (gõ `yes`), không cho phép duyệt bằng giọng nói.
  - Sandbox giới hạn đường dẫn trong thư mục làm việc hiện tại, chống path traversal (`../`) và bảo vệ các file nhạy cảm (`.env`, SSH keys).
  - Tự động lọc sạch các biến môi trường nhạy cảm (`KEY`, `SECRET`, `TOKEN`) trước khi chạy lệnh shell.
- **Đa phương thức linh hoạt:** Dùng song song cả **gõ phím lẫn nói** trong cùng một phiên làm việc (nhấn `Space` để nói, gõ phím như bình thường).
- **Hỗ trợ mọi LLM OpenAI-Compatible:** Kết nối mượt mà với Ollama, vLLM, llama.cpp, OpenAI, hoặc ngrok endpoint với khả năng tự động thích ứng giữa native tool calling và prompt fallback mode.

---

## 🚀 Cài đặt & Khởi động nhanh

### Yêu cầu hệ thống
- Python 3.11+
- Microphone và Loa (để dùng tính năng giọng nói)

### Cài đặt qua `uv` hoặc `pip`

```bash
# Clone repository
git clone https://github.com/vinh-gogo/claw-cli.git
cd claw-cli

# Cài đặt môi trường ảo và dependencies với uv
uv venv --python 3.12
uv pip install -e ".[dev]"
```

### Cấu hình môi trường

Tạo file `.env` hoặc cấu hình qua `~/.config/claw/config.toml`:

```bash
cp .env.example .env
```

Nội dung `.env`:
```env
CLAW_BASE_URL=https://your-llm-server.ngrok-free.dev/v1
CLAW_API_KEY=not-needed
```

---

## 💻 Hướng dẫn sử dụng

### 1. Phiên tương tác đầy đủ (Interactive Voice + Text REPL)

```bash
claw
```
- Gõ lệnh bình thường hoặc nhấn **`Space`** khi ô nhập trống để chuyển sang nói.
- Nhấn **`Esc`** hoặc nói **`"dừng"`** để huỷ hành động ngay lập tức.
- Nhấn **`Ctrl+T`** hoặc nói **`"im lặng"` / `"bật tiếng"`** để bật/tắt đọc kết quả to.

### 2. Thực thi một lệnh duy nhất (One-shot)

```bash
claw ask "Liệt kê các file python trong thư mục này rồi đếm tổng số dòng"
claw ask "Chạy test và cho tôi biết bài nào bị lỗi" --yolo
```

### 3. Kiểm tra thiết bị âm thanh & chẩn đoán hệ thống

```bash
# Liệt kê micro và loa
claw devices

# Chẩn đoán toàn diện môi trường (Mic, STT, TTS, LLM latency)
claw doctor

# Xem các model đang có trên LLM server
claw models
```

### 4. Quản lý phiên làm việc

```bash
# Xem danh sách các phiên trước
claw sessions

# Tiếp tục một phiên cũ
claw resume <SESSION_ID>
```

---

## 🛡️ Bảng phân loại rủi ro an toàn

| Cấp độ | Hành động ví dụ | Hành vi mặc định |
| :--- | :--- | :--- |
| `read` | `ls`, `cat`, `git status`, `grep`, `pytest --collect-only` | Tự động duyệt chạy ngay |
| `write` | `write_file`, `edit_file`, ghi file trong workdir | Hiển thị diff, hỏi xác nhận (cho phép duyệt bằng giọng nói) |
| `exec` | `pytest`, `python main.py`, `npm install`, lệnh shell | Hiển thị lệnh, hỏi xác nhận (cho phép duyệt bằng giọng nói) |
| `dangerous` | `rm -rf`, `sudo`, `git push --force`, `dd`, `format` | **Chỉ cho phép gõ tay `yes` trên bàn phím**, cấm duyệt bằng giọng |

---

## 🧪 Chạy kiểm thử tự động

```bash
uv run pytest -v
```

Bộ kiểm thử bao gồm:
- **Unit tests:** Hơn 50 ca kiểm tra phân loại lệnh shell an toàn, path traversal sandbox, các thao tác file/edit/bash/say/ask_user, nhận diện lệnh meta tiếng Việt, quản lý ngữ cảnh & token.
- **Integration tests:** Giả lập máy chủ OpenAI SSE streaming & tool calling chuẩn xác (`fake_server.py`) để kiểm thử trọn vẹn vòng lặp agent mà không cần phụ thuộc vào mạng ngoài.

---

## 🎙️ Gemma 4 Nhận Dạng Giọng Nói Tiếng Việt Gần Realtime (`gemma_stt`)

Dự án tích hợp sẵn package độc lập `gemma_stt` (xem chi tiết tại [`PLAN_GEMMA4_VIETNAMESE_STT.md`](file:///D:/claw-cli/PLAN_GEMMA4_VIETNAMESE_STT.md)) hỗ trợ nhận dạng giọng nói tiếng Việt gần realtime với 2 chế độ:
1. **`local_gemma`:** Chạy `google/gemma-4-E2B-it` trực tiếp trên GPU NVIDIA cục bộ (tự động lượng tử hóa `int4`/`int8` cho GPU 6 GB VRAM như RTX 4050 Laptop và lưu cache sang ổ `D:` qua `HF_HOME`).
2. **`remote_v1`:** Gửi đoạn âm thanh từ VAD local lên Colab / OpenAI-compatible server (`.../v1/chat/completions` với `input_audio` hoặc `/v1/audio/transcriptions`).
3. **Kết hợp với Gemma 4 26B trên Colab (`--forward-claw`):** Dùng `gemma-4-E2B-it` nhận dạng tiếng Việt ở máy local rồi chuyển văn bản sang `gemma-4-26B-A4B-it` trên Colab (`.../v1`) để điều khiển máy tính/terminal (do bản 26B A4B MoE chỉ có Vision+Text encoder, không có Audio encoder).

### Quy trình khởi chạy nhanh `gemma_stt`

```powershell
# 1. Khảo sát GPU, CUDA, dung lượng ổ đĩa, Microphone và kết nối Colab /v1
python scripts/check_env.py

# 2. Liệt kê thiết bị microphone và kiểm tra hỗ trợ 16 kHz mono
python scripts/list_microphones.py

# 3. Thu âm thử 3 giây từ microphone hoặc sinh bộ WAV kiểm thử
python scripts/record_test_wav.py --duration 3 --out outputs/test_mic.wav
python scripts/record_test_wav.py --generate-fixtures

# 4. Kiểm chứng nhận dạng từ file WAV / bộ mẫu reference.csv (Cổng chất lượng Phase C)
python scripts/transcribe_wav.py --config config.yaml --input tests/fixtures/reference.csv

# 5. Chạy nhận dạng giọng nói tiếng Việt gần realtime từ microphone
python -m gemma_stt --config config.yaml

# 6. Chạy nhận dạng kèm chuyển tiếp lệnh sang Claw Agent (Gemma 4 26B trên Colab /v1)
python -m gemma_stt --config config.yaml --forward-claw

# 7. Chạy ma trận benchmark độ trễ (p50/p95, RTF) và WER/CER (T01 -> T06)
python scripts/benchmark.py --config config.yaml

# 8. Xóa toàn bộ dữ liệu transcript/log/metrics để bảo mật riêng tư
python -m gemma_stt --config config.yaml --clean-outputs
```

### Tinh chỉnh cấu hình (`config.yaml`)
- **`vad.engine`:** Chọn `rms` (nhẹ, nhanh) hoặc `silero` (ONNX học máy giúp lọc tiếng quạt/gõ phím).
- **`vad.silence_ms` / `vad.max_segment_ms`:** Mặc định chốt câu sau `450 ms` khoảng lặng hoặc cắt đoạn ở `4000 ms` (kèm `overlap_ms: 160` để không mất từ ở ranh giới).
- **`queue.policy`:** Chọn `preserve_segments` (ưu tiên đầy đủ transcript, áp dụng backpressure) hoặc `ultra_low_latency` (ưu tiên độ trễ thấp, bỏ đoạn cũ khi quá tải nhưng luôn ghi rõ `dropped=True` vào `outputs/results.jsonl`).

---

## 📄 Giấy phép

Dự án được phân phối dưới giấy phép MIT.
