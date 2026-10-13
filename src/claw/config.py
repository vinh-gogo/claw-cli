from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, Literal

import platformdirs
from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    base_url: str = Field(
        default="https://snowcapped-denice-unprudent.ngrok-free.dev/v1",
        description="Base URL for OpenAI-compatible server",
    )
    api_key_env: str = Field(default="CLAW_API_KEY")
    api_key: str = Field(default="not-needed")
    model: str = Field(default="auto")
    temperature: float = Field(default=0.2)
    tool_mode: Literal["native", "prompt", "auto"] = Field(
        default="native",
        description="Tool calling mode: native, prompt (JSON block), or auto-detect",
    )
    max_steps: int = Field(default=25)
    timeout_s: float = Field(default=120.0)
    max_retries: int = Field(default=3)
    extra_headers: dict[str, str] = Field(
        default_factory=lambda: {"ngrok-skip-browser-warning": "true"}
    )


class STTConfig(BaseModel):
    provider: Literal["faster-whisper", "openai-compatible", "mock"] = Field(
        default="faster-whisper"
    )
    model: str = Field(default="medium")
    language: str = Field(default="vi")
    device: str = Field(default="auto")
    compute_type: str = Field(default="int8")
    initial_prompt: str = Field(
        default="git, commit, pytest, docker, npm, python, thư mục, tệp tin, chạy test, kiểm tra"
    )


class TTSConfig(BaseModel):
    provider: Literal["edge-tts", "piper", "system", "openai-compatible", "off"] = Field(
        default="edge-tts"
    )
    voice: str = Field(default="vi-VN-HoaiMyNeural")
    speak_mode: Literal["summary", "full", "off"] = Field(default="summary")
    barge_in: bool = Field(default=False)


class AudioConfig(BaseModel):
    input_device: str | int = Field(default="default")
    output_device: str | int = Field(default="default")
    sample_rate: int = Field(default=16000)
    input_mode: Literal["toggle", "hands-free", "wake-word"] = Field(default="toggle")
    silence_ms: int = Field(default=900)
    min_speech_ms: int = Field(default=250)
    pre_roll_ms: int = Field(default=300)
    review_transcript: bool = Field(default=True)
    auto_send_ms: int = Field(default=1500)


class SafetyConfig(BaseModel):
    workdir_only: bool = Field(default=True)
    auto_approve: list[str] = Field(default_factory=lambda: ["read"])
    voice_confirm: list[str] = Field(default_factory=lambda: ["write", "exec"])
    keyboard_only: list[str] = Field(default_factory=lambda: ["dangerous"])
    yolo: bool = Field(default=False)


class SessionConfig(BaseModel):
    dir: Path = Field(
        default_factory=lambda: Path(platformdirs.user_data_dir("claw", "claw-cli")) / "sessions"
    )
    audit_file: Path = Field(
        default_factory=lambda: Path(platformdirs.user_data_dir("claw", "claw-cli")) / "audit.jsonl"
    )


class DesktopConfig(BaseModel):
    enabled: bool = Field(default=True)
    control_mode: Literal["ask", "allowlist", "free"] = Field(default="ask")
    app_allowlist: list[str] = Field(
        default_factory=lambda: [
            "chrome",
            "msedge",
            "coccoc",
            "spotify",
            "notepad",
            "explorer",
            "code",
            "WindowsTerminal",
        ]
    )
    app_denylist: list[str] = Field(
        default_factory=lambda: [
            "KeePass",
            "1Password",
            "Bitwarden",
            "regedit",
            "mmc",
            "SecHealthUI",
        ]
    )
    sensitive_title_regex: str = Field(
        default=r"(?i)(ngân hàng|bank|đăng nhập|login|password|mật khẩu|payment|thanh toán)"
    )
    url_schemes_allow: list[str] = Field(
        default_factory=lambda: ["http", "https", "mailto", "ms-settings", "spotify"]
    )
    max_ui_actions_per_turn: int = Field(default=30)
    ptt_hotkey: str = Field(default="ctrl+alt+space")
    kill_switch: str = Field(default="ctrl+alt+x")
    show_overlay: bool = Field(default=True)
    duck_media_on_listen: bool = Field(default=True)
    duck_level: float = Field(default=0.2)
    music_source: Literal["youtube", "youtube-music", "spotify"] = Field(default="youtube")
    browser: Literal["chrome", "msedge", "coccoc"] = Field(default="chrome")
    browser_profile: str = Field(
        default_factory=lambda: str(
            Path(platformdirs.user_data_dir("claw", "claw-cli")) / "browser-profile"
        )
    )
    vision: bool = Field(default=False)


class Config(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    stt: STTConfig = Field(default_factory=STTConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    desktop: DesktopConfig = Field(default_factory=DesktopConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)

    @classmethod
    def find_config_file(cls) -> Path | None:
        local_cfg = Path("claw.toml")
        if local_cfg.is_file():
            return local_cfg
        user_cfg = Path(platformdirs.user_config_dir("claw", "claw-cli")) / "config.toml"
        if user_cfg.is_file():
            return user_cfg
        home_cfg = Path.home() / ".config" / "claw" / "config.toml"
        if home_cfg.is_file():
            return home_cfg
        return None

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> Config:
        # Load from .env if present
        env_path = Path(".env")
        if env_path.is_file():
            try:
                from dotenv import load_dotenv

                load_dotenv(env_path)
            except ImportError:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            os.environ.setdefault(k.strip(), v.strip())

        cfg_dict: dict[str, Any] = {}
        target_path = Path(config_path) if config_path else cls.find_config_file()
        if target_path and target_path.is_file():
            with open(target_path, "rb") as f:
                cfg_dict = tomllib.load(f)

        # Apply Environment Variable Overrides
        llm_data = cfg_dict.get("llm", {})
        if "CLAW_BASE_URL" in os.environ:
            llm_data["base_url"] = os.environ["CLAW_BASE_URL"]
        if "CLAW_API_KEY" in os.environ:
            llm_data["api_key"] = os.environ["CLAW_API_KEY"]
        elif llm_data.get("api_key_env") and llm_data["api_key_env"] in os.environ:
            llm_data["api_key"] = os.environ[llm_data["api_key_env"]]
        if "CLAW_MODEL" in os.environ:
            llm_data["model"] = os.environ["CLAW_MODEL"]
        if "CLAW_TOOL_MODE" in os.environ:
            llm_data["tool_mode"] = os.environ["CLAW_TOOL_MODE"]
        cfg_dict["llm"] = llm_data

        safety_data = cfg_dict.get("safety", {})
        if "CLAW_YOLO" in os.environ:
            safety_data["yolo"] = os.environ["CLAW_YOLO"].lower() in ("1", "true", "yes")
        cfg_dict["safety"] = safety_data

        return cls.model_validate(cfg_dict)


_active_config: Config | None = None


def get_config() -> Config:
    global _active_config
    if _active_config is None:
        _active_config = Config.load()
    return _active_config


def set_config(cfg: Config) -> None:
    global _active_config
    _active_config = cfg
