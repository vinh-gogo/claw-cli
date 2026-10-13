from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from claw.config import SafetyConfig
from claw.llm.schema import ToolCall
from claw.safety.patterns import RiskLevel, classify_shell_command
from claw.safety.sandbox import PathSandbox

if TYPE_CHECKING:
    from claw.safety.app_policy import AppPolicy


@dataclass
class SafetyDecision:
    level: RiskLevel
    ask: bool
    reason: str
    denied: bool = False
    diff: str | None = None


class SafetyPolicy:
    def __init__(
        self,
        cfg: SafetyConfig,
        sandbox: PathSandbox,
        app_policy: AppPolicy | None = None,
    ) -> None:
        self.cfg = cfg
        self.sandbox = sandbox
        self.app_policy = app_policy

    def check(self, call: ToolCall) -> SafetyDecision:
        name = call.name
        args = call.get_args_dict()

        # 1. Non-destructive conversational tools
        if name in ("say", "ask_user"):
            return SafetyDecision(
                level="none",
                ask=False,
                reason="Conversational tool",
            )

        # 2. Filesystem read tools
        if name in ("list_dir", "glob", "grep", "read_file"):
            target_path = args.get("path") or args.get("file_path") or "."
            if not self.sandbox.is_safe(target_path):
                return SafetyDecision(
                    level="dangerous",
                    ask=False,
                    denied=True,
                    reason=f"Đường dẫn '{target_path}' nằm ngoài thư mục làm việc hoặc chạm file nhạy cảm.",
                )
            return SafetyDecision(
                level="read",
                ask=False,
                reason="Thao tác đọc an toàn trong thư mục làm việc",
            )

        # 3. Filesystem write tools
        if name in ("write_file", "edit_file"):
            target_path = args.get("path") or args.get("file_path") or ""
            if not target_path or not self.sandbox.is_safe(target_path):
                return SafetyDecision(
                    level="dangerous",
                    ask=False,
                    denied=True,
                    reason=f"Ghi ra ngoài thư mục làm việc hoặc tệp nhạy cảm '{target_path}' bị từ chối.",
                )

            # Generate diff if applicable
            diff_text: str | None = None
            try:
                resolved = self.sandbox.resolve_safe(target_path)
                existing_content = resolved.read_text(encoding="utf-8") if resolved.is_file() else ""
                if name == "write_file":
                    new_content = args.get("content", "")
                else:
                    old_str = args.get("old", "")
                    new_str = args.get("new", "")
                    new_content = existing_content.replace(old_str, new_str, 1)

                diff_lines = list(
                    difflib.unified_diff(
                        existing_content.splitlines(keepends=True),
                        new_content.splitlines(keepends=True),
                        fromfile=f"a/{resolved.name}",
                        tofile=f"b/{resolved.name}",
                    )
                )
                diff_text = "".join(diff_lines)
            except Exception:
                diff_text = None

            ask_user = not self.cfg.yolo
            return SafetyDecision(
                level="write",
                ask=ask_user,
                reason=f"Chỉnh sửa tệp tin '{target_path}'",
                diff=diff_text,
            )

        # 4. Shell execution tool
        if name in ("shell", "bash"):
            cmd = args.get("cmd") or args.get("command") or ""
            level = classify_shell_command(cmd)

            if level == "dangerous":
                return SafetyDecision(
                    level="dangerous",
                    ask=True,
                    reason=f"Lệnh nguy hiểm: `{cmd}`",
                )

            if level in ("exec", "write"):
                ask_user = not self.cfg.yolo
                return SafetyDecision(
                    level=level,
                    ask=ask_user,
                    reason=f"Thực thi lệnh shell: `{cmd}`",
                )

            # read level shell command
            if "read" in self.cfg.auto_approve:
                return SafetyDecision(
                    level="read",
                    ask=False,
                    reason=f"Lệnh shell chỉ-đọc tự động duyệt: `{cmd}`",
                )

            return SafetyDecision(
                level="read",
                ask=True,
                reason=f"Lệnh shell chỉ-đọc: `{cmd}`",
            )

        # 5. Web fetch
        if name == "web_fetch":
            return SafetyDecision(
                level="read",
                ask=False,
                reason=f"Tải nội dung web từ {args.get('url', '')}",
            )

        # 6. Windows Computer Control Tools
        if name == "open_app":
            app_name = args.get("name", "")
            if self.app_policy:
                return self.app_policy.check_app(app_name)
            return SafetyDecision(level="low", ask=False, reason=f"Mở ứng dụng '{app_name}'")

        if name in ("open_url", "browser_goto"):
            url = args.get("url", "")
            if self.app_policy:
                return self.app_policy.check_url(url)
            return SafetyDecision(level="low", ask=False, reason=f"Mở URL: {url}")

        if name in ("list_windows", "get_active_window", "now_playing", "clipboard_get"):
            return SafetyDecision(level="read", ask=False, reason="Đọc thông tin hệ thống")

        if name in ("media", "volume", "notify"):
            return SafetyDecision(level="low", ask=False, reason="Điều khiển phương tiện / âm lượng")

        if name == "focus_window":
            target = str(args.get("target", ""))
            if self.app_policy:
                dec = self.app_policy.check_window_title(target)
                if dec.denied:
                    return dec
            return SafetyDecision(level="low", ask=False, reason=f"Focus cửa sổ '{target}'")

        if name == "window_action":
            action = str(args.get("action", "")).lower()
            target = str(args.get("target", ""))
            if self.app_policy:
                dec = self.app_policy.check_window_title(target)
                if dec.denied:
                    return dec
            if action == "close":
                return SafetyDecision(level="input", ask=not self.cfg.yolo, reason=f"Đóng cửa sổ '{target}'")
            return SafetyDecision(level="low", ask=False, reason=f"Thao tác cửa sổ ({action}) trên '{target}'")

        if name == "system_action":
            action = str(args.get("action", "")).lower()
            if action in ("shutdown", "restart", "tắt máy", "khởi động lại"):
                return SafetyDecision(
                    level="dangerous",
                    ask=True,
                    reason=f"Hành động hệ thống phá huỷ ({action}) - Bắt buộc xác nhận bằng bàn phím (gõ 'yes')",
                )
            return SafetyDecision(level="input", ask=not self.cfg.yolo, reason=f"Hành động hệ thống ({action})")

        if name == "clipboard_set":
            return SafetyDecision(level="input", ask=not self.cfg.yolo, reason="Ghi vào bộ nhớ tạm (clipboard)")

        if name == "ui_tree":
            window = str(args.get("window", ""))
            if window and self.app_policy:
                dec = self.app_policy.check_window_title(window)
                if dec.denied:
                    return dec
            return SafetyDecision(level="read", ask=False, reason="Đọc cây UI Automation")

        if name in ("ui_click", "ui_type", "ui_select", "key_press", "type_text", "wait_for"):
            target = str(args.get("target") or args.get("window") or "")
            if target and self.app_policy:
                dec = self.app_policy.check_window_title(target)
                if dec.denied:
                    return dec
            elem_id = str(args.get("element_id") or args.get("element_name") or "")
            if elem_id and self.app_policy:
                dec = self.app_policy.check_ui_element({"name": elem_id, "automation_id": elem_id})
                if dec.denied:
                    return dec
            return SafetyDecision(level="input", ask=not self.cfg.yolo, reason=f"Thao tác UI: {name}")

        if name in ("browser_click", "browser_type", "browser_read", "browser_press"):
            return SafetyDecision(level="input", ask=not self.cfg.yolo, reason=f"Thao tác trình duyệt: {name}")

        if name == "screenshot":
            target = str(args.get("target", ""))
            if target and self.app_policy:
                dec = self.app_policy.check_window_title(target)
                if dec.denied:
                    return dec
            return SafetyDecision(level="read", ask=False, reason="Chụp ảnh màn hình")

        if name in ("mouse_click", "scroll"):
            return SafetyDecision(level="input", ask=not self.cfg.yolo, reason=f"Thao tác chuột: {name}")

        # High-level skills
        if name in ("youtube_play", "web_search", "window_layout"):
            return SafetyDecision(level="low", ask=False, reason=f"Skill cấp cao: {name}")

        # Default fallback: treat as exec and ask
        return SafetyDecision(
            level="exec",
            ask=not self.cfg.yolo,
            reason=f"Tool không xác định '{name}'",
        )
