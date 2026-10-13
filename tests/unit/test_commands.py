from __future__ import annotations

import pytest

from claw.voice.commands import match_voice_command


@pytest.mark.parametrize(
    "text,expected_cmd",
    [
        ("dừng", "cancel"),
        ("Dừng lại!", "cancel"),
        ("thôi", "cancel"),
        ("huỷ", "cancel"),
        ("hủy bỏ", "cancel"),
        ("stop", "cancel"),
        ("đồng ý", "approve"),
        ("ĐỒNG Ý", "approve"),
        ("ok", "approve"),
        ("làm đi", "approve"),
        ("chạy đi", "approve"),
        ("có", "approve"),
        ("không", "reject"),
        ("đừng", "reject"),
        ("từ chối", "reject"),
        ("nói lại", "repeat"),
        ("lặp lại", "repeat"),
        ("đọc lại", "repeat"),
        ("xoá phiên", "reset"),
        ("xóa phiên", "reset"),
        ("làm mới", "reset"),
        ("im lặng", "mute"),
        ("tắt tiếng", "mute"),
        ("bật tiếng", "unmute"),
        ("mở loa", "unmute"),
        # Normal prompts that should NOT match meta commands
        ("hãy đọc file readme.md", "none"),
        ("chạy test cho tôi", "none"),
        ("tạo thư mục mới tên là test", "none"),
    ],
)
def test_match_voice_command(text: str, expected_cmd: str) -> None:
    assert match_voice_command(text) == expected_cmd
