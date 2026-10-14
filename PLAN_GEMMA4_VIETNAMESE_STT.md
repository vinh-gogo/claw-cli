# KẾ HOẠCH TRIỂN KHAI — GEMMA 4 NHẬN DẠNG GIỌNG NÓI TIẾNG VIỆT GẦN REALTIME

> **Nền tảng:** Windows 10/11, NVIDIA GPU (RTX 4050 Laptop 6GB VRAM) + Colab Server (`.../v1`), Python 3.11+  
> **Model ưu tiên:** `google/gemma-4-E2B-it` (Audio ASR) & kết nối `google/gemma-4-26B-A4B-it` (Agent LLM qua `/v1`)  
> **Đầu vào:** microphone, tiếng Việt  
> **Đầu ra:** transcript UTF-8, console và file `.txt` / `.jsonl` / `.csv`  
> **Chế độ:** near-real-time (xử lý từng đoạn hội thoại sau khi phát hiện khoảng lặng), hỗ trợ chạy cục bộ trên CUDA hoặc gọi qua endpoint `.../v1`.

---

## 0. Tóm tắt và phạm vi

### 0.1. Mục tiêu
Xây dựng ứng dụng nhận âm thanh liên tục từ micro, phát hiện đoạn tiếng nói, chuyển đoạn âm thanh sang văn bản tiếng Việt bằng Gemma 4 E2B trên GPU NVIDIA (hoặc endpoint tương thích `/v1`), in kết quả và lưu lịch sử. Ứng dụng tiếp tục thu âm trong khi GPU đang xử lý và tránh tình trạng hàng đợi tăng vô hạn.

### 0.2. Điều cần hiểu trước
- **Near-real-time không phải streaming từng từ.** Câu được xuất sau khi VAD nhận thấy khoảng lặng hoặc đoạn đạt giới hạn thời lượng, cộng với thời gian chạy model.
- **Phân biệt biến thể Gemma 4:** Bản `E2B`, `E4B` và `12B Unified` có bộ mã hóa âm thanh (Audio Encoder) hỗ trợ nhận dạng giọng nói trực tiếp. Bản `26B A4B MoE` và `31B Dense` chỉ hỗ trợ Text + Image (không có Audio Encoder), phù hợp làm Agent LLM xử lý văn bản sau khi STT hoàn tất.
- Giới hạn âm thanh của model theo tài liệu là tối đa **30 giây mỗi đầu vào**. Mặc định chỉ gửi các đoạn ngắn **2–5 giây** (mặc định tối đa 4 giây).
- Với GPU 6 GB VRAM (RTX 4050 Laptop), bản `gemma-4-E2B-it` có 5.1B tổng tham số (kể cả Per-Layer Embeddings), nên ưu tiên lượng tử hóa `int4`/`int8` hoặc kiểm tra `hf_device_map` để tránh CPU offload ngoài ý muốn.

---

## 1. Thiết kế kiến trúc

```text
Windows Microphone (16 kHz, mono, float32, block 20 ms)
  │
  ▼
Audio Queue (bounded, max 150 blocks, drop logging)
  │
  ▼
VAD + Segmenter (RMS / Silero ONNX, pre-roll 200ms, silence 450ms, max 4000ms, overlap 160ms)
  │
  ▼
Inference Queue (bounded, max 4 segments, preserve_segments / ultra_low_latency)
  │
  ├─► [Mode 1: local_gemma] Gemma 4 E2B on local CUDA (enable_thinking=False, SDPA)
  └─► [Mode 2: remote_v1]   OpenAI-compatible /v1 server (chat_audio / transcriptions)
  │
  ▼
Result Processor (ordered by segment_id, strip special tokens, silence hallucination filter)
  │
  ▼
Console + outputs/transcript.txt + outputs/results.jsonl + outputs/metrics.csv
```

---

## 2. Lệnh sử dụng nhanh

1. **Kiểm tra môi trường, GPU, ổ đĩa, micro và kết nối server `/v1`:**
   ```powershell
   python scripts/check_env.py
   ```
2. **Liệt kê thiết bị thu âm (micro):**
   ```powershell
   python scripts/list_microphones.py
   ```
3. **Thu âm file WAV thử nghiệm hoặc tạo bộ fixture kiểm thử:**
   ```powershell
   python scripts/record_test_wav.py --duration 3 --out outputs/test_mic.wav
   ```
4. **Kiểm chứng nhận dạng từ file WAV (Cổng chất lượng Giai đoạn C):**
   ```powershell
   python scripts/transcribe_wav.py --config config.yaml --input tests/fixtures/reference.csv
   ```
5. **Chạy ứng dụng nhận dạng giọng nói tiếng Việt gần realtime từ micro:**
   ```powershell
   python -m gemma_stt --config config.yaml
   ```
6. **Chạy benchmark độ trễ (p50/p95, RTF) và độ chính xác (WER/CER):**
   ```powershell
   python scripts/benchmark.py --config config.yaml
   ```
