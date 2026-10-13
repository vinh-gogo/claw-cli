# Chính sách an toàn & Bảo mật cho claw-cli

## 1. Nguyên tắc cốt lõi
1. **Deny-by-default:** Mọi hành động có khả năng ghi, thực thi mã, hoặc tác động ra ngoài thư mục làm việc đều phải qua kiểm tra chính sách.
2. **Xác thực đa tầng đối với lệnh nguy hiểm (`dangerous`):**
   - Không bao giờ cho phép duyệt bằng giọng nói đối với các lệnh `rm -rf`, `sudo`, `git push --force`, `dd`, `mkfs`...
   - Bắt buộc người dùng gõ xác nhận trực tiếp từ bàn phím (`yes`).
3. **Sandbox đường dẫn làm việc (`workdir`):**
   - Mọi thao tác file phải được chuẩn hoá qua `Path.resolve()`.
   - Chặn đứng mọi nỗ lực path traversal (`../`, absolute paths, symlinks trỏ ra ngoài).
4. **Scrubbing biến môi trường:**
   - Khi chạy lệnh con (`subprocess`), tự động lọc sạch các biến môi trường nhạy cảm chứa:
     `KEY`, `TOKEN`, `SECRET`, `PASSWORD`, `AUTH`, `CREDENTIALS`.
5. **Audit log:**
   - Mọi tool call, đối số, kết quả, và quyết định phê duyệt đều được ghi vào `audit.jsonl`.
