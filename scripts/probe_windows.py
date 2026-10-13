#!/usr/bin/env python3
"""
Windows Environment Probe for claw-cli:
- DPI awareness
- pycaw volume control
- SMTC media playback status (winrt)
- yt-dlp search
- pywin32 window enumeration
- pywinauto UIA support
"""

import asyncio
import sys

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")


def probe_dpi() -> bool:
    try:
        import ctypes

        # Set per-monitor DPI awareness v2 (value 2) or v1 (value 1)
        shcore = ctypes.windll.shcore
        shcore.SetProcessDpiAwareness(2)
        print("[✔] DPI Awareness: SetProcessDpiAwareness(2) OK")
        return True
    except Exception as e:
        print(f"[!] DPI Awareness: {e}")
        return False


def probe_volume() -> bool:
    try:
        from ctypes import POINTER, cast

        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        current_vol = volume.GetMasterVolumeLevelScalar()
        print(f"[✔] pycaw Volume: OK (Current volume: {int(current_vol * 100)}%)")
        return True
    except Exception as e:
        print(f"[✘] pycaw Volume failed: {e}")
        return False


async def probe_smtc() -> bool:
    try:
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as SMTCManager,
        )

        manager = await SMTCManager.request_async()
        session = manager.get_current_session()
        if session:
            media_props = await session.try_get_media_properties_async()
            playback_info = session.get_playback_info()
            status = playback_info.playback_status.name if playback_info else "Unknown"
            title = media_props.title if media_props else "None"
            artist = media_props.artist if media_props else "None"
            print(f"[✔] SMTC Media: OK (Status: {status}, Title: '{title}', Artist: '{artist}')")
        else:
            print("[✔] SMTC Media: Manager OK (Hiện không có ứng dụng nào đang phát media)")
        return True
    except Exception as e:
        print(f"[!] SMTC Media check: {e}")
        return False


def probe_ytdlp() -> bool:
    try:
        import yt_dlp

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            res = ydl.extract_info("ytsearch1:Son Tung M-TP", download=False)
            entries = res.get("entries", [])
            if entries:
                first = entries[0]
                print(f"[✔] yt-dlp: OK (Found: '{first.get('title')}' id={first.get('id')})")
                return True
            else:
                print("[!] yt-dlp: No search entries returned")
                return False
    except Exception as e:
        print(f"[✘] yt-dlp failed: {e}")
        return False


def probe_windows_enum() -> bool:
    try:
        import win32gui

        windows = []

        def enum_cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).strip()
                if title:
                    windows.append((hwnd, title))
            return True

        win32gui.EnumWindows(enum_cb, None)
        print(f"[✔] pywin32 Window Enumeration: OK (Found {len(windows)} visible windows)")
        return True
    except Exception as e:
        print(f"[✘] pywin32 failed: {e}")
        return False


async def main() -> None:
    print("=== Windows Environment Probe for claw-cli ===")
    probe_dpi()
    probe_volume()
    await probe_smtc()
    probe_windows_enum()
    probe_ytdlp()
    print("=== Probe Completed ===")


if __name__ == "__main__":
    asyncio.run(main())
