#!/usr/bin/env python3
"""Record test WAV files from microphone or generate baseline audio fixtures."""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "src"))

from gemma_stt.audio_capture import MicrophoneCapture  # noqa: E402
from gemma_stt.model_runner import pcm_float32_to_wav_bytes  # noqa: E402
from gemma_stt.vad import compute_rms  # noqa: E402


def record_single_wav(
    out_path: Path,
    duration_s: float = 3.0,
    device: str | int | None = None,
    sample_rate: int = 16000,
) -> Path:
    cap = MicrophoneCapture(sample_rate=sample_rate, channels=1, block_ms=20, device=device)
    chunks: list[np.ndarray] = []
    target_samples = int(duration_s * sample_rate)
    collected = 0

    print(f"🎙 Đang thu âm {duration_s:.1f} giây vào '{out_path}'... Hãy bắt đầu nói!")
    cap.start()
    start_t = time.monotonic()
    try:
        while collected < target_samples and (time.monotonic() - start_t) < (duration_s + 2.0):
            block = cap.get_block(timeout=0.1)
            if block is not None:
                chunks.append(block.samples)
                collected += int(block.samples.size)
    finally:
        cap.stop()

    audio = np.concatenate(chunks)[:target_samples] if chunks else np.zeros(target_samples, dtype=np.float32)
    rms = compute_rms(audio)
    peak = float(np.max(np.abs(audio))) if audio.size > 0 else 0.0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(pcm_float32_to_wav_bytes(audio, sample_rate))
    print(f"[✔] Đã lưu {out_path} ({len(audio)/sample_rate:.2f}s, RMS={rms:.4f}, Peak={peak:.4f})")
    return out_path


def generate_synthetic_fixtures(reference_csv: Path, sample_rate: int = 16000) -> int:
    """Generate deterministic 16kHz mono WAV fixtures corresponding to reference.csv if missing."""
    if not reference_csv.is_file():
        print(f"Không tìm thấy {reference_csv}")
        return 1

    fixture_dir = reference_csv.parent
    rng = np.random.default_rng(42)
    count = 0

    with open(reference_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            wav_name = row["file"].strip()
            category = row.get("category", "short_quiet").strip()
            wav_path = fixture_dir / wav_name
            duration_s = float(row.get("duration_s", 2.5))
            n_samples = int(duration_s * sample_rate)
            t = np.linspace(0.0, duration_s, n_samples, endpoint=False, dtype=np.float32)

            if category == "silence":
                audio = np.zeros(n_samples, dtype=np.float32)
            elif category == "noise":
                # Simulated fan/background low-amplitude noise
                audio = rng.normal(0.0, 0.004, size=n_samples).astype(np.float32)
            else:
                # Simulated speech envelope (silence pad + voiced harmonic bursts + silence pad)
                amp = 0.025 if category == "low_volume" else 0.12
                carrier = (
                    0.6 * np.sin(2.0 * np.pi * 180.0 * t)
                    + 0.3 * np.sin(2.0 * np.pi * 360.0 * t)
                    + 0.1 * np.sin(2.0 * np.pi * 720.0 * t)
                ).astype(np.float32)
                envelope = np.zeros(n_samples, dtype=np.float32)
                start_idx = int(0.25 * sample_rate)
                end_idx = max(start_idx + 1600, n_samples - int(0.5 * sample_rate))
                envelope[start_idx:end_idx] = amp
                audio = carrier * envelope

            wav_path.write_bytes(pcm_float32_to_wav_bytes(audio, sample_rate))
            count += 1

    print(f"[✔] Đã khởi tạo {count} file WAV mẫu tại {fixture_dir}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Record test WAV from microphone or generate fixtures")
    parser.add_argument("--out", default="outputs/test_mic.wav", help="Output WAV path")
    parser.add_argument("--duration", type=float, default=3.0, help="Recording duration in seconds")
    parser.add_argument("--device", default=None, help="Microphone device ID or name")
    parser.add_argument(
        "--generate-fixtures",
        action="store_true",
        help="Generate baseline WAV files in tests/fixtures/ matching reference.csv",
    )
    parser.add_argument(
        "--reference",
        default="tests/fixtures/reference.csv",
        help="Path to reference.csv",
    )
    args = parser.parse_args()

    if args.generate_fixtures:
        return generate_synthetic_fixtures(Path(args.reference))

    record_single_wav(Path(args.out), duration_s=args.duration, device=args.device)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
