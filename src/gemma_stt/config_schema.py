from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field


class BackendConfig(BaseModel):
    mode: Literal["local_gemma", "remote_v1", "auto"] = Field(default="local_gemma")
    cache_dir: str = Field(default="D:/claw-cli/.cache/huggingface")
    offline: bool = Field(default=False)


class ModelConfig(BaseModel):
    id: str = Field(default="google/gemma-4-E2B-it")
    dtype: str = Field(default="auto")
    attention: str = Field(default="sdpa")
    quantization: Literal["auto", "none", "int4", "int8"] = Field(default="auto")
    max_new_tokens: int = Field(default=128, ge=1, le=2048)
    enable_thinking: bool = Field(default=False)
    warmup_runs: int = Field(default=1, ge=0, le=5)
    prompt: str = Field(
        default=(
            "Transcribe the following Vietnamese speech into Vietnamese text. "
            "Preserve Vietnamese diacritics. Output transcription only."
        )
    )


class RemoteV1Config(BaseModel):
    base_url: str = Field(default="https://snowcapped-denice-unprudent.ngrok-free.dev/v1")
    api_key_env: str = Field(default="CLAW_API_KEY")
    api_key: str = Field(default="not-needed")
    model: str = Field(default="auto")
    endpoint_type: Literal["auto", "chat_audio", "transcriptions"] = Field(default="auto")
    timeout_s: float = Field(default=30.0, gt=0.0)
    extra_headers: dict[str, str] = Field(
        default_factory=lambda: {"ngrok-skip-browser-warning": "true"}
    )


class AudioCaptureConfig(BaseModel):
    device: str | int | None = Field(default=None)
    sample_rate: int = Field(default=16000, gt=0)
    channels: int = Field(default=1, ge=1, le=2)
    block_ms: int = Field(default=20, ge=10, le=100)

    @property
    def block_size(self) -> int:
        return (self.sample_rate * self.block_ms) // 1000


class VADConfig(BaseModel):
    engine: Literal["rms", "silero"] = Field(default="rms")
    threshold: float = Field(default=0.012, ge=0.0)
    silero_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    pre_roll_ms: int = Field(default=200, ge=0)
    silence_ms: int = Field(default=450, ge=50)
    min_speech_ms: int = Field(default=350, ge=20)
    max_segment_ms: int = Field(default=4000, ge=500, le=30000)
    overlap_ms: int = Field(default=160, ge=0, le=2000)


class QueueConfig(BaseModel):
    audio_max_blocks: int = Field(default=150, ge=10)
    inference_max_segments: int = Field(default=4, ge=1)
    policy: Literal["preserve_segments", "ultra_low_latency"] = Field(
        default="preserve_segments"
    )


class OutputConfig(BaseModel):
    transcript_path: Path = Field(default=Path("outputs/transcript.txt"))
    results_path: Path = Field(default=Path("outputs/results.jsonl"))
    metrics_path: Path = Field(default=Path("outputs/metrics.csv"))
    save_debug_wav: bool = Field(default=False)
    debug_wav_dir: Path = Field(default=Path("outputs/debug_wav"))


class GemmaSTTConfig(BaseModel):
    backend: BackendConfig = Field(default_factory=BackendConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    remote_v1: RemoteV1Config = Field(default_factory=RemoteV1Config)
    audio: AudioCaptureConfig = Field(default_factory=AudioCaptureConfig)
    vad: VADConfig = Field(default_factory=VADConfig)
    queue: QueueConfig = Field(default_factory=QueueConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)

    def apply_Runtime_env(self) -> None:
        """Apply HF cache directory and offline flags to environment variables."""
        if self.backend.cache_dir:
            cache_path = Path(self.backend.cache_dir).resolve()
            cache_path.mkdir(parents=True, exist_ok=True)
            os.environ.setdefault("HF_HOME", str(cache_path))
            os.environ.setdefault("HF_HUB_CACHE", str(cache_path / "hub"))
        if self.backend.offline:
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"

    @classmethod
    def load(cls, config_path: str | Path | None = "config.yaml") -> GemmaSTTConfig:
        # Load .env if present
        env_file = Path(".env")
        if env_file.is_file():
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip())

        raw_data: dict[str, Any] = {}
        if config_path is not None:
            path_obj = Path(config_path)
            if not path_obj.is_file() and str(config_path) == "config.yaml":
                repo_cfg = Path(__file__).resolve().parents[2] / "config.yaml"
                if repo_cfg.is_file():
                    path_obj = repo_cfg
            if path_obj.is_file():
                with open(path_obj, "r", encoding="utf-8") as f:
                    loaded = yaml.safe_load(f)
                    if isinstance(loaded, dict):
                        raw_data = loaded

        # Apply environment overrides for remote_v1 and backend
        remote_data = dict(raw_data.get("remote_v1", {}) or {})
        if "CLAW_BASE_URL" in os.environ:
            remote_data["base_url"] = os.environ["CLAW_BASE_URL"]
        api_key_env = remote_data.get("api_key_env", "CLAW_API_KEY")
        if api_key_env and api_key_env in os.environ:
            remote_data["api_key"] = os.environ[api_key_env]
        elif "CLAW_API_KEY" in os.environ:
            remote_data["api_key"] = os.environ["CLAW_API_KEY"]
        raw_data["remote_v1"] = remote_data

        backend_data = dict(raw_data.get("backend", {}) or {})
        if "GEMMA_STT_BACKEND" in os.environ:
            backend_data["mode"] = os.environ["GEMMA_STT_BACKEND"]
        if os.environ.get("HF_HUB_OFFLINE") in ("1", "true", "True"):
            backend_data["offline"] = True
        raw_data["backend"] = backend_data

        cfg = cls.model_validate(raw_data)
        cfg.apply_Runtime_env()
        return cfg
