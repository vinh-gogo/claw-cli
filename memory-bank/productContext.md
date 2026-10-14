# Product Context — `claw-cli` & `gemma_stt`

## 1. Tại sao dự án này tồn tại? (Why This Project Exists)
Người dùng Windows tại Việt Nam cần một trợ lý AI tốc độ cao có thể điều khiển máy tính, chạy lệnh lập trình, mở ứng dụng và trả lời câu hỏi hoàn toàn bằng **tiếng Việt** (cả nói và gõ chữ), đồng thời tận dụng sức mạnh của mô hình **Google Gemma 4** (26B cho suy luận/gọi công cụ và E2B Multimodal cho nhận dạng giọng nói tiếng Việt) mà không bị giới hạn bởi VRAM hạn chế trên laptop cá nhân (như RTX 4050 6GB).

## 2. Các vấn đề giải quyết (Problems Solved)
1. **Rào cản VRAM trên máy cá nhân & Chi phí API:**
   - Chạy đồng thời LLM lớn (`Gemma 4 26B`) và STT đa phương thức (`Gemma 4 E2B` + Audio Encoder `mmproj`) trên một phiên Google Colab GPU (L4 24GB / A100) thông qua **một URL Ngrok duy nhất** (`.../v1`).
   - Trên máy Windows cục bộ, `claw` không cần cài đặt nặng `cublas64_12.dll` hay nạp model lớn vào VRAM nếu dùng Colab Gateway, nhưng vẫn có chế độ dự phòng cục bộ (`local_gemma` hoặc `faster-whisper` CPU fallback).
2. **Thời gian khởi động Colab quá lâu (~10 phút):**
   - Thay thế việc biên dịch `llama.cpp` CUDA từ mã nguồn (~8 phút) bằng tải bản **Pre-built Ubuntu CUDA Binary chính thức** từ GitHub Releases (~10 giây) và tải song song 3 file GGUF bằng **`hf_transfer` (Rust)** (~35 giây), rút ngắn tổng thời gian khởi động xuống **~45 giây**.
3. **Trải nghiệm rảnh tay (Hands-free Voice UX):**
   - Người dùng không cần bấm phím sau mỗi câu nói: nhờ **Silero VAD v5 ONNX** và bộ phát hiện kết thúc câu (`UtteranceDetector`), chỉ cần ngừng nói `0.6 giây` là hệ thống tự động chốt câu, nhận diện văn bản tiếng Việt và thực thi lệnh.
   - Lệnh `/speech on` và `/speech off` giúp khóa cứng chế độ **chỉ nhận giọng nói** hoặc **chỉ nhận văn bản** rõ ràng.

## 3. Mục tiêu trải nghiệm người dùng (User Experience Goals)
- **Khởi động tức thì:** Gõ `claw` tại bất kỳ thư mục nào trong PowerShell (`C:\Users\...` hoặc `D:\claw-cli`) là vào ngay giao diện tương tác.
- **Chuyển đổi chế độ trực quan:**
  - `/speech on`: Tự động nghe liên tục từng câu, tự chốt câu khi ngừng nói 0.6s, tự trả lời bằng giọng nói (`edge-tts` giọng `vi-VN-HoaiMyNeural`) và nghe câu tiếp theo.
  - `/speech off`: Tắt hoàn toàn kích hoạt mic, chỉ nhận văn bản gõ từ bàn phím.
- **Không in lặp nội dung:** Phản hồi streaming (`TextDelta`) hiển thị mượt trên terminal mà không bị in lặp lại lần 2 khi kết thúc lượt (`Final`).
