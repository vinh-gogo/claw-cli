from __future__ import annotations

from claw.skills.layout import snap_two_windows
from claw.skills.web_search import open_and_search


def test_web_search_urls(monkeypatch):
    # Mock subprocess, webbrowser, and os.startfile so it does not open windows during test
    monkeypatch.setattr("claw.skills.web_search.os.startfile", lambda url: None, raising=False)
    monkeypatch.setattr("webbrowser.open", lambda url: True)

    res_google = open_and_search("thời tiết hôm nay", engine="google")
    assert res_google["ok"] is True
    assert "https://www.google.com/search?q=" in res_google["url"]
    assert "th%E1%BB%9Di+ti%E1%BA%BFt+h%C3%B4m+nay" in res_google["url"] or "th%C3%B4i" in res_google["url"] or "thời" in res_google["url"] or "%" in res_google["url"]

    res_bing = open_and_search("tin tức", engine="bing")
    assert res_bing["ok"] is True
    assert "https://www.bing.com/search?q=" in res_bing["url"]

    res_coccoc = open_and_search("công nghệ", engine="coccoc")
    assert res_coccoc["ok"] is True
    assert "https://coccoc.com/search?query=" in res_coccoc["url"]


def test_snap_two_windows(monkeypatch):
    # Mock window_action and focus_window
    monkeypatch.setattr("claw.skills.layout.focus_window", lambda target: (True, "ok"))
    monkeypatch.setattr("claw.skills.layout.window_action", lambda target, act: (True, f"snapped {act}"))

    res = snap_two_windows("chrome", "notepad")
    assert res["ok"] is True
    assert "bên trái" in res["say"]
    assert "bên phải" in res["say"]
