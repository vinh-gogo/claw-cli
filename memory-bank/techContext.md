# Tech Context — Công nghệ, Môi trường & Cấu hình

## 1. Công nghệ sử dụng (Tech Stack)
- **Hệ điều hành máy trạm:** Windows 10/11 (PowerShell).
- **Ngôn ngữ & Runtime:**
  - Môi trường ảo chính của dự án: `D:\claw-cli\.venv\Scripts\python.exe` (Python 3.12, dùng bởi lệnh `claw` qua `D:\claw-cli\claw.cmd` và `C:\Users\lea26\.local\bin\claw.cmd`).
- **Thư viện chính (`pyproject.toml`):**
  - **CLI & UI:** `typer`, `rich`, `prompt_toolkit`.
  - **AI & HTTP Client:** `openai` (`AsyncOpenAI`), `httpx`, `pydantic`, `pyyaml`.
  - **Audio, VAD & TTS:** `sounddevice`, `numpy`, `onnxruntime` (Silero VAD v5 ONNX), `edge-tts` (`vi-VN-HoaiMyNeural`), `scipy`, `soundfile`.
  - **Windows Control (`winctl`):** `pywin32`, `pywinauto`, `pycaw`, `pyautogui`, `mss`, `Pillow`, `psutil`, `keyboard`, `playwright`, `yt-dlp`.
- **Colab Server (`colab/colab_llama_cpp_ngrok.ipynb`):**
  - `ggml-org/llama.cpp` Pre-built Ubuntu 24.04 CUDA 13.4 / 12.8 binaries (`llama-server`).
  - `hf_transfer` + `huggingface_hub` (tải song song tốc độ 500–800 MB/s).
  - `fastapi`, `uvicorn`, `python-multipart`, `pyngrok`.

## 2. Cấu hình mặc định (`src/claw/config.py` & `config.yaml`)
- **LLM (`LLMConfig`):**
  - `base_url`: `"https://snowcapped-denice-unprudent.ngrok-free.dev/v1"` (ghi đè qua `CLAW_BASE_URL`).
  - `model`: `"auto"` (tự chọn `gemma-4-26B-A4B-it-Q4_K_M.gguf` từ `/v1/models`).
- **STT (`STTConfig` & `GemmaSTTConfig`):**
  - `provider`: `"gemma-stt"` (mặc định trong `claw`, ghi đè qua `CLAW_STT_PROVIDER`).
  - `model`: `"gemma-4-stt"` (ghi đè qua `CLAW_STT_MODEL`).
  - `config.yaml`: Tự động được tìm thấy tại `D:\claw-cli\config.yaml` ngay cả khi người dùng chạy lệnh `claw` từ thư mục khác (ví dụ `C:\Users\lea26`).
- **Audio (`AudioConfig`):**
  - `sample_rate`: `16000` Hz mono.
  - `silence_ms`: `600` ms (tự động chốt câu sau 0.6s ngừng nói).
  - `review_transcript`: `False` (thực thi ngay sau khi STT nhận diện xong).

## 3. Lệnh kiểm thử & kiểm tra chất lượng mã nguồn
```powershell
pytest -q
ruff check src tests
mypy src
```
