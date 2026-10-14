from __future__ import annotations

import base64
import io
import logging
import re
import tempfile
import time
import wave
from pathlib import Path
from typing import Any, Protocol

import httpx
import numpy as np

from gemma_stt.config_schema import GemmaSTTConfig, ModelConfig, RemoteV1Config
from gemma_stt.vad import compute_rms

logger = logging.getLogger("gemma_stt.model_runner")

_THOUGHT_BLOCK_RE = re.compile(r"<\|thought\|>.*?<\|/thought\|>", flags=re.DOTALL)
_SPECIAL_TAG_RE = re.compile(r"<\|[^>]+?\|>")
_WHITESPACE_RE = re.compile(r"\s+")


def clean_transcription_output(raw_text: str) -> str:
    """Strip special tokens, thinking blocks, and normalize whitespace without inventing content."""
    text = _THOUGHT_BLOCK_RE.sub("", raw_text)
    text = _SPECIAL_TAG_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


def pcm_float32_to_wav_bytes(audio: np.ndarray, sample_rate: int = 16000) -> bytes:
    """Convert float32 mono PCM array [-1.0, 1.0] into in-memory 16-bit PCM WAV bytes."""
    arr = np.asarray(audio, dtype=np.float32).reshape(-1)
    clipped = np.clip(arr, -1.0, 1.0)
    pcm_int16 = (clipped * 32767.0).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_int16.tobytes())
    return buf.getvalue()


def load_wav_float32_16k(wav_path: Path | str, target_sr: int = 16000) -> np.ndarray:
    """Load WAV file into mono float32 16kHz numpy array."""
    with wave.open(str(wav_path), "rb") as wf:
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        sr = wf.getframerate()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)

    if sampwidth == 2:
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 4:
        audio = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        audio = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        audio = (audio - 128.0) / 128.0

    if channels > 1:
        audio = audio.reshape(-1, channels)[:, 0]

    if sr != target_sr and audio.size > 0:
        import math

        from scipy.signal import resample_poly

        gcd = math.gcd(target_sr, sr)
        audio = resample_poly(audio, target_sr // gcd, sr // gcd).astype(np.float32)

    return audio.astype(np.float32, copy=False)


class STTModelRunner(Protocol):
    """Protocol for STT inference backends."""

    backend_name: str

    def load(self) -> None:
        """Load model or verify remote connection once at startup."""
        ...

    def warmup(self, runs: int = 1) -> None:
        """Run warmup inference to eliminate cold-start latency."""
        ...

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> tuple[str, float]:
        """Transcribe 16kHz float32 audio array and return (text, peak_vram_mb)."""
        ...


class LocalGemmaRunner:
    """Local GPU inference runner for google/gemma-4-E2B-it using Hugging Face Transformers.

    Follows Section C1 & F1:
    - Verifies torch.cuda.is_available() is True; refuses to silently fall back to CPU.
    - Supports 4-bit/8-bit quantization (BitsAndBytes or Optimum-Quanto) on 6 GB VRAM GPUs
      (such as RTX 4050 Laptop) so the 5.1B total parameter checkpoint stays on GPU.
    - Passes in-memory float32 audio array to processor with fallback to WAV file if needed.
    - Disables thinking mode (enable_thinking=False) for direct ASR transcription.
    """

    backend_name: str = "local_gemma"

    def __init__(self, cfg: ModelConfig) -> None:
        self.cfg = cfg
        self.processor: Any = None
        self.model: Any = None
        self.device_map_summary: dict[str, Any] = {}
        self.silence_hallucinations: int = 0
        self._prefer_in_memory_audio: bool = True

    def load(self) -> None:
        import torch
        import transformers
        from transformers import AutoProcessor

        if not torch.cuda.is_available():
            raise RuntimeError(
                "torch.cuda.is_available() == False! "
                "LocalGemmaRunner yêu cầu NVIDIA GPU với CUDA hoạt động (không tự rơi sang CPU)."
            )

        if not hasattr(transformers, "AutoModelForMultimodalLM"):
            raise RuntimeError(
                f"Phiên bản transformers hiện tại ({transformers.__version__}) chưa có "
                "AutoModelForMultimodalLM cho Gemma 4. "
                "Hãy nâng cấp: pip install -U 'transformers>=5.19.0' accelerate"
            )

        from transformers import AutoModelForMultimodalLM

        vram_bytes = torch.cuda.get_device_properties(0).total_memory
        vram_gb = vram_bytes / (1024**3)
        gpu_name = torch.cuda.get_device_name(0)
        logger.info("Loading %s on %s (VRAM=%.2f GB)...", self.cfg.id, gpu_name, vram_gb)

        self.processor = AutoProcessor.from_pretrained(self.cfg.id, padding_side="left")

        load_kwargs: dict[str, Any] = {
            "device_map": "auto",
            "attn_implementation": self.cfg.attention,
            "dtype": self.cfg.dtype,
        }

        # Handle quantization for 6GB VRAM GPUs (RTX 4050 Laptop)
        quant_mode = self.cfg.quantization
        if quant_mode == "auto":
            quant_mode = "int4" if vram_gb <= 6.8 else "none"

        quant_config = self._build_quantization_config(quant_mode)
        if quant_config is not None:
            load_kwargs["quantization_config"] = quant_config
            load_kwargs["device_map"] = {"": 0}
            logger.info("Using quantization (%s) to fit %s in %.1f GB VRAM.", quant_mode, self.cfg.id, vram_gb)

        self.model = AutoModelForMultimodalLM.from_pretrained(self.cfg.id, **load_kwargs)
        self.model.eval()

        # Inspect hf_device_map to detect unintended CPU/disk offload
        hf_map = getattr(self.model, "hf_device_map", None) or {}
        self.device_map_summary = dict(hf_map)
        cpu_modules = [k for k, v in hf_map.items() if str(v) in ("cpu", "disk")]
        if cpu_modules:
            logger.warning(
                "CẢNH BÁO VRAM: %d module của model bị offload sang CPU/disk (%s...). "
                "Độ trễ sẽ tăng cao; khuyến nghị bật quantization: int4.",
                len(cpu_modules),
                cpu_modules[:3],
            )
        else:
            logger.info("Model loaded 100%% on CUDA device (%s).", self.model.device)

    def _build_quantization_config(self, quant_mode: str) -> Any | None:
        if quant_mode == "none":
            return None

        # Try BitsAndBytesConfig first if bitsandbytes is installed
        try:
            import importlib.util

            if importlib.util.find_spec("bitsandbytes") is not None:
                import torch
                from transformers import BitsAndBytesConfig

                if quant_mode == "int4":
                    return BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_compute_dtype=torch.bfloat16,
                        bnb_4bit_quant_type="nf4",
                    )
                if quant_mode == "int8":
                    return BitsAndBytesConfig(load_in_8bit=True)
        except Exception as exc:
            logger.debug("BitsAndBytesConfig not available: %s", exc)

        # Fallback: Optimum-Quanto (installed on system)
        try:
            from transformers import QuantoConfig

            weights = "int4" if quant_mode == "int4" else "int8"
            return QuantoConfig(weights=weights)
        except Exception as exc:
            logger.warning(
                "Không thể khởi tạo cấu hình lượng tử hóa (%s): %s. Tải với dtype=%s.",
                quant_mode,
                exc,
                self.cfg.dtype,
            )
            return None

    def warmup(self, runs: int = 1) -> None:
        if runs <= 0 or self.model is None:
            return
        logger.info("Running %d GPU warm-up iteration(s)...", runs)
        dummy_audio = np.zeros(16000, dtype=np.float32)
        for i in range(runs):
            t0 = time.perf_counter()
            self._run_model_on_audio(dummy_audio, 16000)
            logger.info("Warm-up #%d completed in %.2fs", i + 1, time.perf_counter() - t0)

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> tuple[str, float]:
        if self.model is None or self.processor is None:
            self.load()

        # Check for pure silence to track/filter silence hallucinations (Section F3)
        rms = compute_rms(audio)
        if rms < 1e-4:
            return ("", self._get_peak_vram_mb())

        raw_text = self._run_model_on_audio(audio, sample_rate)
        cleaned = clean_transcription_output(raw_text)

        if rms < 0.002 and cleaned:
            self.silence_hallucinations += 1
            logger.warning(
                "Filtered potential hallucination on near-silent audio (rms=%.5f): %r",
                rms,
                cleaned,
            )
            return ("", self._get_peak_vram_mb())

        return (cleaned, self._get_peak_vram_mb())

    def _run_model_on_audio(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        import torch

        audio_f32 = np.asarray(audio, dtype=np.float32).reshape(-1)
        temp_wav_path: str | None = None

        try:
            if self._prefer_in_memory_audio:
                try:
                    inputs = self._prepare_inputs(audio_f32)
                except Exception as mem_err:
                    logger.info(
                        "In-memory audio array not accepted by processor (%s); falling back to temporary WAV.",
                        mem_err,
                    )
                    self._prefer_in_memory_audio = False
                    temp_wav_path = self._write_temp_wav(audio_f32, sample_rate)
                    inputs = self._prepare_inputs(temp_wav_path)
            else:
                temp_wav_path = self._write_temp_wav(audio_f32, sample_rate)
                inputs = self._prepare_inputs(temp_wav_path)

            input_len = inputs["input_ids"].shape[-1]
            with torch.inference_mode():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=self.cfg.max_new_tokens,
                    do_sample=False,
                )

            decoded = self.processor.decode(outputs[0][input_len:], skip_special_tokens=True)
            return str(decoded)
        finally:
            if temp_wav_path is not None:
                try:
                    Path(temp_wav_path).unlink(missing_ok=True)
                except Exception:
                    pass

    def _prepare_inputs(self, audio_source: np.ndarray | str) -> Any:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": self.cfg.prompt},
                    {"type": "audio", "audio": audio_source},
                ],
            }
        ]
        template_kwargs: dict[str, Any] = {
            "tokenize": True,
            "add_generation_prompt": True,
            "return_dict": True,
            "return_tensors": "pt",
        }
        try:
            inputs = self.processor.apply_chat_template(
                messages,
                enable_thinking=self.cfg.enable_thinking,
                **template_kwargs,
            )
        except TypeError:
            inputs = self.processor.apply_chat_template(messages, **template_kwargs)

        return inputs.to(self.model.device, dtype=self.model.dtype)

    @staticmethod
    def _write_temp_wav(audio_f32: np.ndarray, sample_rate: int) -> str:
        wav_bytes = pcm_float32_to_wav_bytes(audio_f32, sample_rate)
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="gemma_stt_")
        with open(fd, "wb") as f:
            f.write(wav_bytes)
        return path

    @staticmethod
    def _get_peak_vram_mb() -> float:
        try:
            import torch

            if torch.cuda.is_available():
                return float(torch.cuda.max_memory_allocated(0)) / (1024.0 * 1024.0)
        except Exception:
            pass
        return 0.0


class RemoteV1Runner:
    """OpenAI-compatible /v1 runner for Colab Server (llama-server / vLLM / Whisper API).

    Supports:
    - endpoint_type = "chat_audio": POST /v1/chat/completions with input_audio base64 WAV
      (for Gemma 4 E2B/E4B/12B multimodal servers).
    - endpoint_type = "transcriptions": POST /v1/audio/transcriptions
      (for Whisper-compatible endpoints).
    - Detects and warns clearly if the remote /v1 server is running a text/image-only model
      like gemma-4-26B-A4B-it without audio support.
    """

    backend_name: str = "remote_v1"

    def __init__(self, remote_cfg: RemoteV1Config, prompt: str) -> None:
        self.cfg = remote_cfg
        self.prompt = prompt
        self.resolved_model: str = remote_cfg.model
        self.resolved_endpoint: str = remote_cfg.endpoint_type
        self._headers: dict[str, str] = dict(remote_cfg.extra_headers)
        if remote_cfg.api_key and remote_cfg.api_key != "not-needed":
            self._headers["Authorization"] = f"Bearer {remote_cfg.api_key}"

    def load(self) -> None:
        base = self.cfg.base_url.rstrip("/")
        with httpx.Client(headers=self._headers, timeout=10.0, follow_redirects=True) as client:
            try:
                resp = client.get(f"{base}/models")
                resp.raise_for_status()
                data = resp.json()
                models = [
                    m.get("id", "")
                    for m in data.get("data", [])
                    if isinstance(m, dict) and m.get("id")
                ]
            except Exception as exc:
                raise RuntimeError(
                    f"Không thể kết nối tới Colab server tại {base}/models: {exc}"
                ) from exc

            if self.resolved_model == "auto":
                preferred_stt = next(
                    (
                        m
                        for m in models
                        if any(k in m.lower() for k in ("gemma-4-stt", "stt", "e2b", "e4b", "12b", "whisper"))
                    ),
                    None,
                )
                self.resolved_model = preferred_stt or (models[0] if models else "gemma-4-stt")

            # Check if /v1/audio/transcriptions is available
            has_transcriptions = False
            try:
                tr_resp = client.get(f"{base}/audio/transcriptions")
                has_transcriptions = tr_resp.status_code not in (404, 501)
            except Exception:
                has_transcriptions = False

            model_lower = self.resolved_model.lower()
            is_text_image_only_gemma = ("26b" in model_lower or "31b" in model_lower) and not has_transcriptions

            if is_text_image_only_gemma:
                raise RuntimeError(
                    f"Server Colab ({base}) đang chạy model '{self.resolved_model}'. "
                    "Theo kiến trúc Google DeepMind, bản Gemma 4 26B A4B và 31B chỉ hỗ trợ Text + Image "
                    "(KHÔNG có Audio Encoder) và server chưa mở /v1/audio/transcriptions. "
                    "Để nhận dạng giọng nói: (1) dùng backend 'local_gemma' (Gemma 4 E2B trên GPU local) "
                    "rồi gửi text lên Gemma 4 26B trên Colab, hoặc (2) chạy Gemma 4 E2B/E4B/12B / Whisper endpoint trên Colab."
                )

            if self.resolved_endpoint == "auto":
                self.resolved_endpoint = "transcriptions" if has_transcriptions else "chat_audio"

            logger.info(
                "RemoteV1Runner connected to %s (model=%s, endpoint=%s)",
                base,
                self.resolved_model,
                self.resolved_endpoint,
            )

    def warmup(self, runs: int = 1) -> None:
        pass

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> tuple[str, float]:
        rms = compute_rms(audio)
        if rms < 1e-4:
            return ("", 0.0)

        wav_bytes = pcm_float32_to_wav_bytes(audio, sample_rate)
        base = self.cfg.base_url.rstrip("/")

        with httpx.Client(headers=self._headers, timeout=self.cfg.timeout_s, follow_redirects=True) as client:
            if self.resolved_endpoint == "transcriptions":
                files = {"file": ("segment.wav", wav_bytes, "audio/wav")}
                data = {"model": self.resolved_model, "language": "vi"}
                resp = client.post(f"{base}/audio/transcriptions", data=data, files=files)
                resp.raise_for_status()
                payload = resp.json()
                text = str(payload.get("text", ""))
                return (clean_transcription_output(text), 0.0)

            # endpoint_type == "chat_audio"
            b64_wav = base64.b64encode(wav_bytes).decode("ascii")
            body = {
                "model": self.resolved_model,
                "temperature": 0.0,
                "max_tokens": 128,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": self.prompt},
                            {
                                "type": "input_audio",
                                "input_audio": {"data": b64_wav, "format": "wav"},
                            },
                        ],
                    }
                ],
            }
            resp = client.post(f"{base}/chat/completions", json=body)
            resp.raise_for_status()
            payload = resp.json()
            choices = payload.get("choices", [])
            content = choices[0].get("message", {}).get("content", "") if choices else ""
            return (clean_transcription_output(str(content)), 0.0)


def create_model_runner(cfg: GemmaSTTConfig) -> STTModelRunner:
    """Create and initialize the configured STT model runner (local_gemma, remote_v1, or auto)."""
    mode = cfg.backend.mode
    if mode == "remote_v1":
        runner = RemoteV1Runner(cfg.remote_v1, prompt=cfg.model.prompt)
        runner.load()
        return runner

    if mode == "auto":
        try:
            remote_runner = RemoteV1Runner(cfg.remote_v1, prompt=cfg.model.prompt)
            remote_runner.load()
            return remote_runner
        except Exception as remote_err:
            logger.warning(
                "Chế độ auto: Remote /v1 chưa hỗ trợ audio trực tiếp (%s) -> chuyển sang LocalGemmaRunner trên GPU cục bộ.",
                remote_err,
            )

    local_runner = LocalGemmaRunner(cfg.model)
    local_runner.load()
    local_runner.warmup(cfg.model.warmup_runs)
    return local_runner
