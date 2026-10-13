from __future__ import annotations

import logging
import sys
from typing import Any

from claw.winctl.windows import get_active_window

logger = logging.getLogger("claw.winctl.uia")

# Cached tree nodes for ID resolution
_last_nodes_cache: dict[int, dict[str, Any]] = {}


def dump_ui_tree(hwnd: int | None = None, max_nodes: int = 150, max_depth: int = 4) -> tuple[str, list[dict[str, Any]]]:
    """Inspect and dump compact UI Automation tree for target window with numbered #id references."""
    global _last_nodes_cache
    _last_nodes_cache.clear()

    if sys.platform != "win32":
        return "UI Automation chỉ hỗ trợ trên Windows.", []

    if hwnd is None:
        act = get_active_window()
        if not act:
            return "Không có cửa sổ nào đang active.", []
        hwnd = act["hwnd"]

    import win32gui
    title = win32gui.GetWindowText(hwnd).strip()

    try:
        from pywinauto import Application

        app = Application(backend="uia").connect(handle=hwnd)
        dlg = app.window(handle=hwnd)

        nodes: list[dict[str, Any]] = []
        counter = 1

        def _traverse(elem: Any, depth: int) -> None:
            nonlocal counter
            if depth > max_depth or counter > max_nodes:
                return

            try:
                ctrl_type = elem.friendly_class_name()
                name = elem.window_text().strip()
                auto_id = getattr(elem.element_info, "automation_id", "")
                is_password = getattr(elem.element_info, "is_password", False)

                # Skip password elements completely
                if is_password:
                    return

                # Only include interactive or named elements
                is_relevant = (
                    bool(name)
                    or bool(auto_id)
                    or ctrl_type in ("Edit", "Button", "Hyperlink", "CheckBox", "RadioButton", "ComboBox", "ListItem", "MenuItem")
                )

                if is_relevant:
                    node_id = counter
                    counter += 1
                    node_info = {
                        "id": node_id,
                        "control_type": ctrl_type,
                        "name": name,
                        "automation_id": auto_id,
                        "element": elem,
                    }
                    nodes.append(node_info)
                    _last_nodes_cache[node_id] = node_info

                for child in elem.children():
                    _traverse(child, depth + 1)
            except Exception:
                pass

        _traverse(dlg, 1)

        lines = [f"[Cửa sổ] \"{title}\" (hwnd=0x{hwnd:X}, tìm thấy {len(nodes)} phần tử UI):"]
        for n in nodes:
            label = f"\"{n['name']}\"" if n['name'] else f"id='{n['automation_id']}'"
            lines.append(f"  #{n['id']:<3} {n['control_type']:<12} {label}")

        return "\n".join(lines), nodes

    except Exception as e:
        logger.debug(f"UI Automation error: {e}")
        return f"Lỗi khi đọc cây UI Automation của cửa sổ (hwnd=0x{hwnd:X}): {e}", []


def find_element(selector: str | int, nodes: list[dict[str, Any]] | None = None) -> Any | None:
    """Find element by #id, automation_id, or name from cache or provided nodes."""
    target_nodes = nodes if nodes is not None else list(_last_nodes_cache.values())

    # 1. Number ID
    if isinstance(selector, int) or (isinstance(selector, str) and (selector.isdigit() or selector.startswith("#"))):
        sel_id = int(str(selector).lstrip("#"))
        for n in target_nodes:
            if n["id"] == sel_id:
                return n["element"]

    # 2. Automation ID or Name match
    sel_str = str(selector).lower().strip()
    for n in target_nodes:
        if sel_str == n.get("automation_id", "").lower() or sel_str == n.get("name", "").lower():
            return n["element"]

    # Substring match
    for n in target_nodes:
        if sel_str in n.get("name", "").lower():
            return n["element"]

    return None


def ui_click(selector: str | int, hwnd: int | None = None) -> tuple[bool, str]:
    """Click on UI element identified by #id, automation_id, or name."""
    if not _last_nodes_cache:
        dump_ui_tree(hwnd)

    elem = find_element(selector)
    if not elem:
        return False, f"Không tìm thấy phần tử UI khớp với '{selector}'"

    try:
        if hasattr(elem, "invoke"):
            elem.invoke()
        else:
            elem.click_input()
        return True, f"Đã click vào phần tử '{selector}'"
    except Exception as e:
        # Fallback to click
        try:
            elem.click()
            return True, f"Đã click vào phần tử '{selector}'"
        except Exception as e2:
            return False, f"Lỗi khi click vào phần tử '{selector}': {e} / {e2}"


def ui_type(selector: str | int, text: str, hwnd: int | None = None) -> tuple[bool, str]:
    """Set text or type into UI edit element."""
    if not _last_nodes_cache:
        dump_ui_tree(hwnd)

    elem = find_element(selector)
    if not elem:
        return False, f"Không tìm thấy phần tử UI '{selector}'"

    try:
        if hasattr(elem, "set_text"):
            elem.set_text(text)
            return True, f"Đã nhập văn bản vào '{selector}'"
        else:
            from claw.winctl.inputs import type_text_sync

            type_text_sync(text)
            return True, f"Đã gõ văn bản vào '{selector}'"
    except Exception as e:
        return False, f"Lỗi khi nhập dữ liệu vào '{selector}': {e}"
