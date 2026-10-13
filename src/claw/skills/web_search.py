from __future__ import annotations

import logging
import os
import subprocess
import sys
from typing import Any
from urllib.parse import quote_plus

from claw.winctl.apps import AppManager

logger = logging.getLogger("claw.skills.web_search")

SEARCH_ENGINES = {
    "google": "https://www.google.com/search?q={query}",
    "bing": "https://www.bing.com/search?q={query}",
    "duckduckgo": "https://duckduckgo.com/?q={query}",
    "coccoc": "https://coccoc.com/search?query={query}",
    "youtube": "https://www.youtube.com/results?search_query={query}",
}


def open_and_search(
    query: str, engine: str = "google", browser: str | None = None
) -> dict[str, Any]:
    """Search query on given search engine in default or specified browser."""
    engine_key = engine.lower().strip()
    template = SEARCH_ENGINES.get(engine_key, SEARCH_ENGINES["google"])
    url = template.format(query=quote_plus(query))

    try:
        if browser:
            # Launch specified browser with url
            app_mgr = AppManager()
            found = app_mgr.find_app(browser)
            if found:
                target_exe = found[1]
                subprocess.Popen([target_exe, url], shell=True)
            else:
                if sys.platform == "win32":
                    os.startfile(url)
                else:
                    subprocess.Popen([browser, url])
        else:
            if sys.platform == "win32":
                os.startfile(url)
            else:
                import webbrowser

                webbrowser.open(url)

        return {
            "ok": True,
            "engine": engine_key,
            "query": query,
            "url": url,
            "say": f"Đang tìm kiếm '{query}' trên {engine_key}",
        }
    except Exception as e:
        logger.error(f"Error opening search: {e}")
        return {
            "ok": False,
            "error": str(e),
            "say": f"Không thể mở tìm kiếm '{query}'",
        }
