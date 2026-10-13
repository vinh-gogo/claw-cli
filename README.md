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

## 📄 Giấy phép

Dự án được phân phối dưới giấy phép MIT.
