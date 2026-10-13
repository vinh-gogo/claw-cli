from __future__ import annotations

from typing import Literal

VoiceCommand = Literal[
    "cancel",
    "approve",
    "reject",
    "repeat",
    "reset",
    "mute",
    "unmute",
    "none",
]

COMMAND_DICTIONARY: dict[VoiceCommand, list[str]] = {
    "cancel": [
        "dừng",
        "thôi",
        "huỷ",
        "hủy",
        "dừng lại",
        "thôi đi",
        "huỷ bỏ",
        "hủy bỏ",
        "stop",
        "cancel",
    ],
    "approve": [
        "đồng ý",
        "ok",
        "làm đi",
        "chạy đi",
        "tiến hành",
        "duyệt",
        "có",
        "yes",
        "chấp nhận",
    ],
    "reject": [
        "không",
        "đừng",
        "thôi đừng",
        "bỏ qua",
        "từ chối",
        "no",
    ],
    "repeat": [
        "nói lại",
        "lặp lại",
        "đọc lại",
        "nhắc lại",
        "nghe lại",
    ],
    "reset": [
        "xoá phiên",
        "xóa phiên",
        "làm mới",
        "xoá lịch sử",
        "xóa lịch sử",
        "bắt đầu lại",
        "phiên mới",
    ],
    "mute": [
        "im lặng",
        "tắt tiếng",
        "tắt âm",
        "tắt loa",
        "mute",
    ],
    "unmute": [
        "bật tiếng",
        "bật âm",
        "mở tiếng",
        "mở loa",
        "unmute",
    ],
}


def normalize_vietnamese_text(text: str) -> str:
    """Normalize text: strip accents comparison or clean spacing and punctuation."""
    text = text.lower().strip()
    # Strip punctuation
    text = "".join(ch for ch in text if ch.isalnum() or ch.isspace())
    return " ".join(text.split())


def match_voice_command(text: str) -> VoiceCommand:
    """Matches a spoken Vietnamese transcript against recognized meta commands."""
    normalized = normalize_vietnamese_text(text)
    if not normalized:
        return "none"

    for cmd, keywords in COMMAND_DICTIONARY.items():
        for kw in keywords:
            clean_kw = normalize_vietnamese_text(kw)
            if normalized == clean_kw:
                return cmd

    return "none"
