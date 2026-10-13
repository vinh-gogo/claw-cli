from __future__ import annotations

from claw.winctl.apps import AppManager
from claw.winctl.inputs import type_text_sync
from claw.winctl.media import press_media_key


def test_app_manager_find_app():
    mgr = AppManager()

    # Exact matches
    assert mgr.find_app("notepad") is not None
    assert mgr.find_app("calc") is not None

    # Vietnamese aliases
    res_chrome = mgr.find_app("crôm")
    assert res_chrome is not None
    assert res_chrome[0] == "chrome"

    res_excel = mgr.find_app("ếch xen")
    assert res_excel is not None
    assert res_excel[0] == "excel"

    res_notepad = mgr.find_app("sổ tay")
    assert res_notepad is not None
    assert res_notepad[0] == "notepad"

    res_zalo = mgr.find_app("da lô")
    assert res_zalo is not None
    assert res_zalo[0] == "zalo"

    res_vscode = mgr.find_app("vi es cốt")
    assert res_vscode is not None
    assert res_vscode[0] == "code"


def test_app_manager_fuzzy_matching():
    mgr = AppManager()

    # Slight typos or spacing
    res = mgr.find_app("cờ rôm")
    assert res is not None
    assert res[0] == "chrome"


def test_inputs_type_empty():
    assert type_text_sync("") is True


def test_media_keys():
    # Valid actions
    ok, msg = press_media_key("play_pause")
    # Will be True on Windows, False on non-Windows
    assert "play_pause" in msg

    # Invalid action
    bad_ok, bad_msg = press_media_key("invalid_action_xyz")
    assert bad_ok is False
    assert "không hợp lệ" in bad_msg
