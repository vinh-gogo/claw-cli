from __future__ import annotations

from claw.config import DesktopConfig
from claw.safety.app_policy import AppPolicy


def test_app_policy_denylist():
    cfg = DesktopConfig()
    policy = AppPolicy(cfg)

    # Denied apps
    assert policy.is_app_denied("keepass.exe") is True
    assert policy.is_app_denied("1Password") is True
    assert policy.is_app_denied("Bitwarden.exe") is True
    assert policy.is_app_denied("regedit.exe") is True
    assert policy.is_app_denied("mmc.exe") is True
    assert policy.is_app_denied("SecHealthUI.exe") is True

    decision = policy.check_app("regedit.exe")
    assert decision.denied is True
    assert decision.level == "dangerous"

    # Allowed app
    assert policy.is_app_denied("notepad.exe") is False
    assert policy.is_app_in_allowlist("notepad.exe") is True


def test_app_policy_control_modes():
    # allowlist mode
    cfg = DesktopConfig(control_mode="allowlist", app_allowlist=["notepad", "chrome"])
    policy = AppPolicy(cfg)

    # In allowlist
    dec1 = policy.check_app("notepad.exe")
    assert dec1.denied is False
    assert dec1.ask is False
    assert dec1.level == "low"

    # Outside allowlist
    dec2 = policy.check_app("vlc.exe")
    assert dec2.denied is False
    assert dec2.ask is True
    assert dec2.level == "input"


def test_sensitive_window_titles():
    cfg = DesktopConfig()
    policy = AppPolicy(cfg)

    assert policy.check_window_title("Vietcombank - Đăng nhập Internet Banking").denied is True
    assert policy.check_window_title("Techcombank - Xác nhận chuyển khoản").denied is True
    assert policy.check_window_title("Enter password to unlock").denied is True
    assert policy.check_window_title("Thanh toán đơn hàng - Shopee").denied is True

    # Safe title
    safe_dec = policy.check_window_title("Visual Studio Code - main.py")
    assert safe_dec.denied is False
    assert safe_dec.level == "read"


def test_url_schemes_and_extensions():
    cfg = DesktopConfig()
    policy = AppPolicy(cfg)

    # Safe URLs
    assert policy.check_url("https://www.youtube.com/watch?v=123").denied is False
    assert policy.check_url("http://google.com").denied is False
    assert policy.check_url("mailto:test@example.com").denied is False
    assert policy.check_url("ms-settings:wifi").denied is False

    # Dangerous schemes
    assert policy.check_url("file:///C:/Windows/System32/cmd.exe").denied is True
    assert policy.check_url("javascript:alert(1)").denied is True
    assert policy.check_url("ms-msdt:/id PCWDiagnostic").denied is True
    assert policy.check_url("search-ms:query=test").denied is True

    # Dangerous file downloads
    assert policy.check_url("https://example.com/malware.exe").denied is True
    assert policy.check_url("https://example.com/script.ps1").denied is True
    assert policy.check_url("https://example.com/payload.bat").denied is True


def test_ui_element_password_protection():
    cfg = DesktopConfig()
    policy = AppPolicy(cfg)

    # IsPassword flag
    elem_pwd = {"name": "Pass", "control_type": "Edit", "is_password": True}
    assert policy.check_ui_element(elem_pwd).denied is True

    # Name containing password/otp
    elem_otp = {"name": "Nhập mã OTP", "control_type": "Edit", "is_password": False}
    assert policy.check_ui_element(elem_otp).denied is True

    elem_pin = {"name": "Mã PIN", "automation_id": "txtPin", "control_type": "Edit"}
    assert policy.check_ui_element(elem_pin).denied is True

    # Safe element
    elem_btn = {"name": "Gửi bình luận", "control_type": "Button", "is_password": False}
    dec = policy.check_ui_element(elem_btn)
    assert dec.denied is False
    assert dec.level == "input"
