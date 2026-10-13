from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CommandType = Literal[
    "cancel",
    "approve",
    "reject",
    "repeat",
    "reset",
    "mute_tts",
    "unmute_tts",
    "prompt",
]


@dataclass
class RoutedInput:
    kind: CommandType
    raw_text: str
    cleaned_prompt: str = ""


META_COMMANDS: dict[CommandType, list[str]] = {
    "cancel": ["dừng", "thôi", "huỷ", "stop", "cancel", "dừng lại", "thôi đi"],
    "approve": ["đồng ý", "ok", "làm đi", "chạy đi", "duyệt", "yes"],
    "reject": ["không", "đừng", "bỏ qua", "từ chối", "no"],
    "repeat": ["nói lại", "lặp lại", "đọc lại", "nhắc lại", "repeat"],
    "reset": ["xoá phiên", "làm mới", "reset", "xoá lịch sử", "bắt đầu lại"],
    "mute_tts": ["im lặng", "tắt tiếng", "tắt âm", "mute"],
    "unmute_tts": ["bật tiếng", "bật âm", "mở tiếng", "unmute"],
}


def route_input(text: str) -> RoutedInput:
    """Classify input as a meta voice/text command or a general agent prompt."""
    normalized = text.strip().lower()

    for cmd_type, triggers in META_COMMANDS.items():
        if normalized in triggers:
            return RoutedInput(kind=cmd_type, raw_text=text)

    return RoutedInput(kind="prompt", raw_text=text, cleaned_prompt=text.strip())
