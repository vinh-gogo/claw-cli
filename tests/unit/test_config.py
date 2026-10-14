from __future__ import annotations

import pytest

from claw.config import Config, discover_remote_base_url, refresh_llm_base_url


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


def test_discover_remote_base_url_with_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyResp:
        def __init__(self, status_code: int, text: str, json_data: dict | None = None) -> None:
            self.status_code = status_code
            self.text = text
            self._json = json_data or {}

        def json(self) -> dict:
            return self._json

    class DummyClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> "DummyClient":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def get(self, url: str, **kwargs: object) -> DummyResp:
            if "/api/models/" in url:
                return DummyResp(200, '{"sha": "abc1234"}', {"sha": "abc1234"})
            return DummyResp(
                200,
                '{"base_url": "https://1234567890abcdef.gradio.live/v1", "tunnel_provider": "gradio"}',
            )

    monkeypatch.setattr("claw.config.httpx.Client", DummyClient)
    discovered = discover_remote_base_url(
        "https://huggingface.co/AlexHung29629/gemma-4-26B-A4B-it-GGUF/resolve/main/claw_endpoint.json"
    )
    assert discovered == "https://1234567890abcdef.gradio.live/v1"

    cfg = Config()
    updated = refresh_llm_base_url(cfg.llm, force=True)
    assert updated == "https://1234567890abcdef.gradio.live/v1"
    assert cfg.llm.base_url == "https://1234567890abcdef.gradio.live/v1"

