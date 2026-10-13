from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process

logger = logging.getLogger("claw.winctl.apps")

DEFAULT_ALIASES: dict[str, list[str]] = {
    "chrome": ["crôm", "cờ rôm", "google chrome", "trình duyệt chrome", "trình duyệt"],
    "msedge": ["edge", "microsoft edge", "trình duyệt edge"],
    "coccoc": ["cốc cốc", "trình duyệt cốc cốc"],
    "excel": ["ếch xen", "bảng tính", "excel", "microsoft excel"],
    "code": ["vi es cốt", "vscode", "visual studio code", "code"],
    "zalo": ["da lô", "za lô", "zalo"],
    "notepad": ["sổ tay", "notepad", "ghi chú"],
    "spotify": ["spotify", "nhạc spotify"],
    "explorer": ["thư mục", "explorer", "file explorer", "quản lý file"],
    "calc": ["máy tính", "calculator", "calc"],
    "cmd": ["command prompt", "cmd", "dòng lệnh cmd"],
    "powershell": ["powershell", "pwsh"],
    "settings": ["cài đặt", "settings", "cài đặt hệ thống", "windows settings"],
}

COMMON_WINDOWS_APPS = {
    "chrome": "chrome",
    "msedge": "msedge",
    "coccoc": "browser",
    "notepad": "notepad",
    "calc": "calc",
    "explorer": "explorer",
    "code": "code",
    "cmd": "cmd",
    "powershell": "powershell",
    "spotify": "spotify",
    "settings": "ms-settings:",
}


def normalize_name(text: str) -> str:
    return text.lower().strip()


class AppManager:
    def __init__(self, custom_aliases: dict[str, list[str]] | None = None) -> None:
        self.aliases: dict[str, list[str]] = dict(DEFAULT_ALIASES)
        if custom_aliases:
            for k, v in custom_aliases.items():
                self.aliases.setdefault(k, []).extend(v)

        self._installed_apps: dict[str, str] = dict(COMMON_WINDOWS_APPS)
        self._scan_installed_apps()

    def _scan_installed_apps(self) -> None:
        """Scan Start Menu folders on Windows for installed applications."""
        if sys.platform != "win32":
            return

        start_dirs = [
            Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
            Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        ]

        for s_dir in start_dirs:
            if not s_dir.is_dir():
                continue
            try:
                for lnk in s_dir.rglob("*.lnk"):
                    clean_name = lnk.stem.lower()
                    if clean_name not in self._installed_apps:
                        self._installed_apps[clean_name] = str(lnk)
            except Exception as e:
                logger.debug(f"Error scanning {s_dir}: {e}")

    def list_apps(self) -> list[dict[str, Any]]:
        """Return list of known applications and their aliases."""
        items: list[dict[str, Any]] = []
        for app_id, target in sorted(self._installed_apps.items()):
            aliases = self.aliases.get(app_id, [])
            items.append(
                {
                    "app_id": app_id,
                    "target": target,
                    "aliases": aliases,
                }
            )
        return items

    def find_app(self, query: str) -> tuple[str, str] | None:
        """Find matching app ID and target path from query string using alias and fuzzy matching."""
        q_clean = normalize_name(query)

        # 1. Exact match with app_id or common apps
        if q_clean in self._installed_apps:
            return q_clean, self._installed_apps[q_clean]

        # 2. Match against aliases
        for app_id, alias_list in self.aliases.items():
            for alias in alias_list:
                if q_clean == normalize_name(alias):
                    target = self._installed_apps.get(app_id, app_id)
                    return app_id, target

        # 3. Fuzzy match across all known aliases and app names
        all_candidates: dict[str, str] = {}
        for app_id, target in self._installed_apps.items():
            all_candidates[app_id] = app_id
        for app_id, alias_list in self.aliases.items():
            for alias in alias_list:
                all_candidates[alias] = app_id

        match = process.extractOne(q_clean, list(all_candidates.keys()), scorer=fuzz.token_sort_ratio)
        if match and match[1] >= 65:
            matched_key = match[0]
            app_id = all_candidates[matched_key]
            target = self._installed_apps.get(app_id, app_id)
            logger.info(f"Fuzzy matched '{query}' -> '{app_id}' (score={match[1]})")
            return app_id, target

        return None

    def launch(self, query: str) -> tuple[bool, str]:
        """Launch an application by query or name."""
        found = self.find_app(query)
        target = found[1] if found else query.strip()
        app_name = found[0] if found else query.strip()

        if target.startswith("ms-settings:"):
            try:
                os.startfile(target)
                return True, "Cài đặt Windows"
            except Exception as e:
                return False, str(e)

        try:
            if sys.platform == "win32":
                os.startfile(target)
            else:
                subprocess.Popen([target], shell=True)
            return True, app_name
        except Exception as e:
            # Fallback to powershell Start-Process
            try:
                subprocess.Popen(["powershell", "-NoProfile", "-Command", f"Start-Process '{target}'"], shell=True)
                return True, app_name
            except Exception as e2:
                return False, f"Không thể mở '{query}': {e} / {e2}"
