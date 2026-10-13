from __future__ import annotations

import pytest

from claw.config import Config


def test_config_defaults() -> None:
    cfg = Config()
    assert cfg.llm.tool_mode == "native"
    assert cfg.stt.language == "vi"
    assert cfg.tts.voice == "vi-VN-HoaiMyNeural"
    assert "read" in cfg.safety.auto_approve
    assert "dangerous" in cfg.safety.keyboard_only


def test_config_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAW_BASE_URL", "http://test-server:9000/v1")
    monkeypatch.setenv("CLAW_MODEL", "gpt-4o")
    monkeypatch.setenv("CLAW_YOLO", "true")
    monkeypatch.setenv("CLAW_TOOL_MODE", "prompt")

    cfg = Config.load()
    assert cfg.llm.base_url == "http://test-server:9000/v1"
    assert cfg.llm.model == "gpt-4o"
    assert cfg.safety.yolo is True
    assert cfg.llm.tool_mode == "prompt"
