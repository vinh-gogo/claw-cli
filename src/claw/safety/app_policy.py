from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from claw.config import DesktopConfig
from claw.safety.policy import SafetyDecision

DANGEROUS_EXTENSIONS = {".exe", ".msi", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".reg", ".lnk"}


class AppPolicy:
    def __init__(self, cfg: DesktopConfig) -> None:
        self.cfg = cfg
        self._title_re = re.compile(cfg.sensitive_title_regex, re.IGNORECASE)

    def is_app_denied(self, proc_name: str) -> bool:
        clean = proc_name.lower().replace(".exe", "")
        for denied in self.cfg.app_denylist:
            if denied.lower() in clean:
                return True
        return False

    def is_app_in_allowlist(self, proc_name: str) -> bool:
        clean = proc_name.lower().replace(".exe", "")
        for allowed in self.cfg.app_allowlist:
            if allowed.lower() in clean:
                return True
        return False

    def check_app(self, proc_name: str) -> SafetyDecision:
        if not self.cfg.enabled:
            return SafetyDecision(
                level="dangerous",
                ask=False,
                denied=True,
                reason="Tính năng điều khiển máy tính (Desktop Control) đang bị tắt trong cấu hình.",
            )

        if self.is_app_denied(proc_name):
            return SafetyDecision(
                level="dangerous",
                ask=False,
                denied=True,
                reason=f"Ứng dụng '{proc_name}' nằm trong danh sách cấm (denylist) vì lý do an toàn bảo mật.",
            )

        if self.cfg.control_mode == "allowlist":
            if not self.is_app_in_allowlist(proc_name):
                return SafetyDecision(
                    level="input",
                    ask=True,
                    reason=f"Ứng dụng '{proc_name}' không nằm trong allowlist của chế độ điều khiển máy.",
                )
        elif self.cfg.control_mode == "ask":
            if not self.is_app_in_allowlist(proc_name):
                return SafetyDecision(
                    level="input",
                    ask=True,
                    reason=f"Yêu cầu tương tác với ứng dụng ngoài allowlist: '{proc_name}'",
                )

        return SafetyDecision(
            level="low",
            ask=False,
            reason=f"Ứng dụng '{proc_name}' được phép điều khiển.",
        )

    def check_window_title(self, title: str) -> SafetyDecision:
        if self._title_re.search(title):
            return SafetyDecision(
                level="dangerous",
                ask=False,
                denied=True,
                reason=f"Tiêu đề cửa sổ chứa từ khoá bảo mật/ngân hàng/mật khẩu nhạy cảm: '{title}'",
            )
        return SafetyDecision(level="read", ask=False, reason="Tiêu đề cửa sổ an toàn")

    def check_url(self, url: str) -> SafetyDecision:
        try:
            parsed = urlparse(url)
            scheme = (parsed.scheme or "http").lower()
        except Exception:
            return SafetyDecision(
                level="dangerous",
                ask=False,
                denied=True,
                reason=f"URL không hợp lệ: '{url}'",
            )

        # Check dangerous schemes
        if scheme not in self.cfg.url_schemes_allow:
            return SafetyDecision(
                level="dangerous",
                ask=False,
                denied=True,
                reason=f"URL scheme '{scheme}:' không nằm trong danh sách được phép ({self.cfg.url_schemes_allow}).",
            )

        # Check dangerous file download extensions
        path = parsed.path.lower()
        for ext in DANGEROUS_EXTENSIONS:
            if path.endswith(ext):
                return SafetyDecision(
                    level="dangerous",
                    ask=False,
                    denied=True,
                    reason=f"URL trỏ tới tệp thực thi có thể gây hại '{ext}': '{url}'",
                )

        return SafetyDecision(level="low", ask=False, reason=f"URL an toàn: {url}")

    def check_ui_element(self, element: dict[str, Any]) -> SafetyDecision:
        """Deny interacting with password fields or secure controls."""
        if element.get("is_password"):
            return SafetyDecision(
                level="dangerous",
                ask=False,
                denied=True,
                reason="Phần tử giao diện là ô nhập mật khẩu (IsPassword=True). Từ chối truy cập để bảo vệ tài khoản.",
            )

        ctrl_type = str(element.get("control_type", "")).lower()
        name = str(element.get("name", "")).lower()
        auto_id = str(element.get("automation_id", "")).lower()

        for kw in ("password", "mật khẩu", "pin", "otp", "cvv", "security"):
            if kw in name or kw in auto_id or kw in ctrl_type:
                return SafetyDecision(
                    level="dangerous",
                    ask=False,
                    denied=True,
                    reason=f"Phần tử UI liên quan tới bảo mật/mật khẩu ('{name or auto_id}').",
                )

        return SafetyDecision(level="input", ask=False, reason="Phần tử UI an toàn")
