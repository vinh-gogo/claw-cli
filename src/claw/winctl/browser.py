from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger("claw.winctl.browser")

DEFAULT_CDP_PORT = 9222

COMMON_BROWSER_PATHS = {
    "chrome": [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ],
    "msedge": [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
    ],
    "coccoc": [
        os.path.expandvars(r"%ProgramFiles%\CocCoc\Browser\Application\browser.exe"),
        os.path.expandvars(r"%LocalAppData%\CocCoc\Browser\Application\browser.exe"),
    ],
}


def find_browser_executable(browser_name: str = "chrome") -> str | None:
    """Find installed browser executable path on Windows."""
    name = browser_name.lower().strip()
    candidates = COMMON_BROWSER_PATHS.get(name, COMMON_BROWSER_PATHS["chrome"])
    for path in candidates:
        if Path(path).is_file():
            return path

    # Fallback to general search
    for b_paths in COMMON_BROWSER_PATHS.values():
        for path in b_paths:
            if Path(path).is_file():
                return path

    return None


class BrowserController:
    """Browser automation controller via Playwright connect_over_cdp."""

    def __init__(
        self,
        browser_name: str = "chrome",
        profile_dir: str | Path | None = None,
        cdp_port: int = DEFAULT_CDP_PORT,
    ) -> None:
        self.browser_name = browser_name
        self.profile_dir = (
            Path(os.path.expandvars(str(profile_dir)))
            if profile_dir
            else Path(os.environ.get("LOCALAPPDATA", "")) / "claw" / "browser-profile"
        )
        self.cdp_port = cdp_port
        self._pw: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._process: subprocess.Popen[Any] | None = None

    async def ensure_running(self) -> bool:
        """Launch browser with CDP enabled if not already running, then connect."""
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        exe_path = find_browser_executable(self.browser_name)
        if not exe_path:
            logger.error(f"Cannot find executable for browser '{self.browser_name}'")
            return False

        # Check if already connected
        if self._browser and self._browser.is_connected():
            return True

        # Launch process if port not reachable
        import urllib.request

        cdp_url = f"http://127.0.0.1:{self.cdp_port}/json/version"
        is_up = False
        try:
            req = urllib.request.urlopen(cdp_url, timeout=1.0)
            if req.status == 200:
                is_up = True
        except Exception:
            is_up = False

        if not is_up:
            cmd = [
                exe_path,
                f"--remote-debugging-port={self.cdp_port}",
                f"--user-data-dir={self.profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
            ]
            try:
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                logger.info(f"Launched browser with CDP: {' '.join(cmd)}")
                # Wait briefly for CDP server to bind
                for _ in range(20):
                    await asyncio.sleep(0.25)
                    try:
                        req = urllib.request.urlopen(cdp_url, timeout=0.5)
                        if req.status == 200:
                            is_up = True
                            break
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"Failed to launch browser: {e}")
                return False

        # Connect via Playwright
        try:
            from playwright.async_api import async_playwright

            if self._pw is None:
                self._pw = await async_playwright().start()

            self._browser = await self._pw.chromium.connect_over_cdp(
                f"http://127.0.0.1:{self.cdp_port}"
            )
            contexts = self._browser.contexts
            self._context = contexts[0] if contexts else await self._browser.new_context()
            pages = self._context.pages
            self._page = pages[0] if pages else await self._context.new_page()
            return True
        except Exception as e:
            logger.error(f"Failed to connect over CDP: {e}")
            return False

    async def get_page(self) -> Any:
        ok = await self.ensure_running()
        if not ok or not self._page:
            raise RuntimeError("Browser is not running or CDP connection failed.")
        return self._page

    async def goto(self, url: str) -> tuple[bool, str]:
        try:
            page = await self.get_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            title = await page.title()
            return True, f"Đã chuyển đến '{url}' (Tiêu đề: {title})"
        except Exception as e:
            return False, f"Lỗi điều hướng đến '{url}': {e}"

    async def click(self, selector: str) -> tuple[bool, str]:
        try:
            page = await self.get_page()
            await page.click(selector, timeout=8000)
            return True, f"Đã click phần tử '{selector}'"
        except Exception as e:
            return False, f"Lỗi click '{selector}': {e}"

    async def type(self, selector: str, text: str) -> tuple[bool, str]:
        try:
            page = await self.get_page()
            await page.fill(selector, text, timeout=8000)
            return True, f"Đã nhập văn bản vào '{selector}'"
        except Exception as e:
            return False, f"Lỗi nhập dữ liệu '{selector}': {e}"

    async def press(self, key: str) -> tuple[bool, str]:
        try:
            page = await self.get_page()
            await page.keyboard.press(key)
            return True, f"Đã bấm phím '{key}' trên trình duyệt"
        except Exception as e:
            return False, f"Lỗi bấm phím '{key}': {e}"

    async def read(self, selector: str | None = None, max_chars: int = 4000) -> tuple[bool, str]:
        try:
            page = await self.get_page()
            if selector:
                elem = await page.query_selector(selector)
                if not elem:
                    return False, f"Không tìm thấy phần tử '{selector}'"
                text = await elem.inner_text()
            else:
                text = await page.inner_text("body")

            cleaned = " ".join((text or "").split())
            if len(cleaned) > max_chars:
                cleaned = cleaned[:max_chars] + f" ...[đã cắt {len(cleaned) - max_chars} ký tự]"
            return True, cleaned
        except Exception as e:
            return False, f"Lỗi đọc nội dung trang: {e}"

    async def is_video_playing(self) -> bool:
        """Check if any HTML5 video on the active page is playing."""
        try:
            page = await self.get_page()
            playing = await page.evaluate(
                "() => Array.from(document.querySelectorAll('video')).some(v => !v.paused && v.readyState >= 2)"
            )
            return bool(playing)
        except Exception:
            return False

    async def get_active_tab_title(self) -> str:
        try:
            page = await self.get_page()
            return await page.title()
        except Exception:
            return ""

    async def close(self) -> None:
        try:
            if self._browser:
                await self._browser.close()
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass
        finally:
            self._browser = None
            self._pw = None
            self._page = None
            self._context = None
