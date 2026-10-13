from __future__ import annotations

from claw.config import DesktopConfig, SafetyConfig
from claw.llm.schema import ToolCall
from claw.safety.app_policy import AppPolicy
from claw.safety.policy import SafetyPolicy
from claw.safety.sandbox import PathSandbox
from claw.tools import create_default_registry


def test_registry_contains_desktop_tools():
    registry = create_default_registry()
    names = [t.name for t in registry.list_tools()]

    # Verify all Tier 1-4 and Skill tools exist
    expected = [
        "open_app",
        "open_url",
        "list_windows",
        "get_active_window",
        "focus_window",
        "window_action",
        "clipboard_get",
        "clipboard_set",
        "notify",
        "system_action",
        "media",
        "volume",
        "now_playing",
        "youtube_play",
        "web_search",
        "window_layout",
        "ui_tree",
        "ui_click",
        "ui_type",
        "key_press",
        "type_text",
        "wait_for",
        "browser_goto",
        "browser_click",
        "browser_type",
        "browser_press",
        "browser_read",
        "screenshot",
        "mouse_click",
        "scroll",
    ]
    for exp in expected:
        assert exp in names, f"Tool '{exp}' missing from default registry"


def test_desktop_safety_checks(tmp_path):
    sandbox = PathSandbox(tmp_path)
    safety_cfg = SafetyConfig(yolo=False)
    desktop_cfg = DesktopConfig()
    app_policy = AppPolicy(desktop_cfg)
    policy = SafetyPolicy(safety_cfg, sandbox, app_policy)

    # 1. Dangerous app open -> denied
    tc_denied_app = ToolCall(id="1", name="open_app", arguments='{"name": "regedit"}')
    dec_app = policy.check(tc_denied_app)
    assert dec_app.denied is True

    # 2. Safe app open in ask mode (allowlist)
    tc_allowed_app = ToolCall(id="2", name="open_app", arguments='{"name": "notepad"}')
    dec_notepad = policy.check(tc_allowed_app)
    assert dec_notepad.denied is False

    # 3. Dangerous system actions (shutdown, restart) -> level dangerous, keyboard ask
    tc_shutdown = ToolCall(id="3", name="system_action", arguments='{"action": "shutdown"}')
    dec_shutdown = policy.check(tc_shutdown)
    assert dec_shutdown.level == "dangerous"
    assert dec_shutdown.ask is True

    # 4. Input level system action (lock, sleep)
    tc_lock = ToolCall(id="4", name="system_action", arguments='{"action": "lock"}')
    dec_lock = policy.check(tc_lock)
    assert dec_lock.level == "input"

    # 5. Dangerous URL scheme -> denied
    tc_bad_url = ToolCall(id="5", name="open_url", arguments='{"url": "file:///etc/passwd"}')
    dec_url = policy.check(tc_bad_url)
    assert dec_url.denied is True

    # 6. Sensitive window title interaction -> denied
    tc_bad_ui = ToolCall(id="6", name="ui_tree", arguments='{"window": "Vietcombank Đăng nhập"}')
    dec_ui = policy.check(tc_bad_ui)
    assert dec_ui.denied is True
