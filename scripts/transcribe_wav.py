#!/usr/bin/env python3
"""Phase C Quality Gate: Transcribe single WAV or reference.csv suite and evaluate Vietnamese output."""

from __future__ import annotations

import argparse
import csv
import sys
import time
import unicodedata
from pathlib import Path

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "src"))

from gemma_stt.config_schema import GemmaSTTConfig  # noqa: E402
from gemma_stt.metrics import compute_cer, compute_wer  # noqa: E402
from gemma_stt.model_runner import create_model_runner, load_wav_float32_16k  # noqa: E402


def has_vietnamese_diacritics(text: str) -> bool:
    """Check if text contains Vietnamese accented characters."""
    for ch in unicodedata.normalize("NFC", text):
        if ord(ch) > 127 and ch.isalpha():
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Transcribe WAV file(s) using Gemma 4 STT")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--input", required=True, help="Path to .wav file or reference.csv")
    parser.add_argument("--backend", choices=["local_gemma", "remote_v1", "auto"], default=None)
    parser.add_argument("--out-md", default=None, help="Optional path to save Markdown report")
    args = parser.parse_args()

    cfg = GemmaSTTConfig.load(args.config)
    if args.backend:
        cfg.backend.mode = args.backend  # type: ignore[assignment]

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"Lỗi: Không tìm thấy file {input_path}")
        return 1

    runner = create_model_runner(cfg)

    if input_path.suffix.lower() == ".wav":
        audio = load_wav_float32_16k(input_path, cfg.audio.sample_rate)
        t0 = time.perf_counter()
        text, vram_mb = runner.transcribe(audio, cfg.audio.sample_rate)
        elapsed = time.perf_counter() - t0
        print(f"File: {input_path.name} ({len(audio)/cfg.audio.sample_rate:.2f}s)")
        print(f"Transcript: {text}")
        print(f"Runtime: {elapsed:.3f}s | Peak VRAM: {vram_mb:.1f} MB")
        return 0

    # Batch evaluation mode on reference.csv (Section C2 & C3)
    rows_out: list[str] = [
        "# Kết Quả Kiểm Chứng Bộ Mẫu WAV (Giai đoạn C)\n",
        f"- **Backend:** `{runner.backend_name}`",
        f"- **Model:** `{cfg.model.id}`\n",
        "| Mẫu | Expected | Actual | Đúng dấu? | WER | CER | Runtime (s) | Peak VRAM (MB) | Ghi chú |",
        "|---|---|---|---|---:|---:|---:|---:|---|",
    ]

    total_wer = 0.0
    total_cer = 0.0
    speech_count = 0

    with open(input_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            wav_rel = row["file"].strip()
            expected = row["expected"].strip()
            category = row.get("category", "").strip()
            wav_file = input_path.parent / wav_rel

            if not wav_file.is_file():
                rows_out.append(
                    f"| {wav_rel} | {expected} | *(thiếu file WAV)* | - | - | - | - | - | {category} |"
                )
                continue

            audio = load_wav_float32_16k(wav_file, cfg.audio.sample_rate)
            t0 = time.perf_counter()
            actual, vram_mb = runner.transcribe(audio, cfg.audio.sample_rate)
            runtime = time.perf_counter() - t0

            if expected:
                wer = compute_wer(expected, actual)
                cer = compute_cer(expected, actual)
                total_wer += wer
                total_cer += cer
                speech_count += 1
                diacritics_ok = "Có" if has_vietnamese_diacritics(actual) else "Không"
                wer_str = f"{wer:.1%}"
                cer_str = f"{cer:.1%}"
            else:
                wer_str = "0.0%" if not actual else "100.0%"
                cer_str = "0.0%" if not actual else "100.0%"
                diacritics_ok = "N/A (im lặng)"

            rows_out.append(
                f"| {wav_rel} | {expected or '*(im lặng)*'} | {actual or '*(trống)*'} | "
                f"{diacritics_ok} | {wer_str} | {cer_str} | {runtime:.2f} | {vram_mb:.1f} | {category} |"
            )

    if speech_count > 0:
        rows_out.append(
            f"\n**Trung bình trên {speech_count} mẫu có tiếng nói:** "
            f"WER = `{total_wer / speech_count:.2%}`, CER = `{total_cer / speech_count:.2%}`"
        )

    report_md = "\n".join(rows_out)
    print(report_md)

    if args.out_md:
        out_p = Path(args.out_md)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(report_md, encoding="utf-8")
        print(f"\n[✔] Đã lưu báo cáo vào {out_p}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
