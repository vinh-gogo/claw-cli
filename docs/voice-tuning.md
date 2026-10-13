# Hướng dẫn tinh chỉnh giọng nói (Voice Tuning)

## 1. Silero VAD
- `speech_prob`: 0.5 (mặc định).
- `silence_ms`: 900ms (chờ kết thúc câu nói).
- `min_speech_ms`: 250ms (loại bỏ tiếng lách cách bàn phím hoặc tặc lưỡi).
- `pre_roll_ms`: 300ms (buffer giữ lại âm thanh trước khi VAD phát hiện để không nuốt âm đầu).

## 2. Faster-Whisper (STT)
- Model đề xuất:
  - CPU: `medium` (hoặc `small` nếu CPU yếu), `compute_type="int8"`.
  - GPU: `large-v3-turbo` (rất nhanh và chuẩn).
- `language`: Luôn gán cứng `"vi"`.
- `initial_prompt`: `"git, commit, pytest, docker, npm, python, thư mục, tệp tin, chạy test, kiểm tra, tạo file"`.

## 3. Edge-TTS & Audio Player
- Giọng nữ: `vi-VN-HoaiMyNeural`
- Giọng nam: `vi-VN-NamMinhNeural`
- Chế độ Half-duplex: Ngắt mic trong lúc đang phát giọng nói để tránh hiện tượng vòng lặp tiếng vang (echo).
