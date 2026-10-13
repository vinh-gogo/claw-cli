from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any
from urllib.parse import quote_plus

from claw.winctl.media import get_now_playing, press_media_key

logger = logging.getLogger("claw.skills.youtube")


def _ytdlp_search_sync(query: str, limit: int = 5) -> list[dict[str, Any]]:
    try:
        import yt_dlp

        ydl_opts = {
            "quiet": True,
            "extract_flat": True,
            "skip_download": True,
            "no_warnings": True,
            "ignoreerrors": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            res = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
            if not res or "entries" not in res:
                return []

            results = []
            for entry in res["entries"]:
                if not entry:
                    continue
                v_id = entry.get("id")
                title = entry.get("title", "")
                channel = entry.get("channel") or entry.get("uploader", "")
                duration = entry.get("duration")
                if v_id:
                    results.append(
                        {
                            "id": v_id,
                            "title": title,
                            "channel": channel,
                            "duration": duration,
                            "url": f"https://www.youtube.com/watch?v={v_id}",
                        }
                    )
            return results
    except Exception as e:
        logger.warning(f"yt-dlp search error for '{query}': {e}")
        return []


async def search_youtube(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search YouTube videos using yt-dlp asynchronously."""
    return await asyncio.to_thread(_ytdlp_search_sync, query, limit)


def open_url_in_browser(url: str) -> bool:
    """Open URL using Windows default browser."""
    try:
        if sys.platform == "win32":
            os.startfile(url)
            return True
        else:
            import webbrowser

            return webbrowser.open(url)
    except Exception as e:
        logger.error(f"Error opening URL '{url}': {e}")
        return False


async def youtube_play(query: str, pick: int | None = None) -> dict[str, Any]:
    """
    Search and play YouTube video directly.
    Tier 1 skill: search yt-dlp -> open default browser -> verify playing -> press play if needed.
    """
    results = await search_youtube(query, limit=5)

    if results:
        selected_idx = 0
        if pick is not None and 1 <= pick <= len(results):
            selected_idx = pick - 1

        video = results[selected_idx]
        url = video["url"]
        title = video["title"]
        channel = video.get("channel", "")

        opened = open_url_in_browser(url)
        if not opened:
            return {
                "ok": False,
                "error": f"Không thể mở trình duyệt để phát URL: {url}",
                "say": f"Không thể mở YouTube để phát '{title}'",
            }

        # Verify playback
        await asyncio.sleep(2.0)
        now_info = await get_now_playing()

        # If playback not started, simulate media play_pause key
        if now_info.get("status") != "Playing":
            press_media_key("play_pause")

        say_msg = f"Đang phát {title}"
        if channel:
            say_msg += f" của {channel}"

        return {
            "ok": True,
            "title": title,
            "channel": channel,
            "url": url,
            "top_candidates": [r["title"] for r in results[:3]],
            "say": say_msg,
        }

    # Fallback to opening YouTube search results directly
    fallback_url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
    opened = open_url_in_browser(fallback_url)
    return {
        "ok": opened,
        "title": query,
        "url": fallback_url,
        "fallback": True,
        "say": f"Đang mở trang tìm kiếm YouTube cho '{query}'",
    }
