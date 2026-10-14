#!/usr/bin/env python3
"""Phase I Benchmark & Experiment Matrix (T01..T06) for Gemma 4 Vietnamese STT."""

from __future__ import annotations

import argparse
import copy
import csv
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "src"))

from gemma_stt.audio_capture import AudioBlock  # noqa: E402
from gemma_stt.config_schema import GemmaSTTConfig  # noqa: E402
from gemma_stt.metrics import (  # noqa: E402
    compute_cer,
    compute_wer,
    summarize_metrics,
)
from gemma_stt.model_runner import (  # noqa: E402
    STTModelRunner,
    create_model_runner,
    load_wav_float32_16k,
)
from gemma_stt.output_writer import OutputWriter  # noqa: E402
from gemma_stt.pipeline import NearRealtimeSTTPipeline  # noqa: E402

TRIAL_MATRIX: list[dict[str, Any]] = [
    {"id": "T01", "silence_ms": 450, "max_segment_ms": 4000, "vad": "rms"},
    {"id": "T02", "silence_ms": 350, "max_segment_ms": 4000, "vad": "rms"},
    {"id": "T03", "silence_ms": 600, "max_segment_ms": 4000, "vad": "rms"},
    {"id": "T04", "silence_ms": 450, "max_segment_ms": 3000, "vad": "rms"},
    {"id": "T05", "silence_ms": 450, "max_segment_ms": 5000, "vad": "rms"},
    {"id": "T06", "silence_ms": 450, "max_segment_ms": 4000, "vad": "silero"},
]


class MockBenchmarkRunner:
    """Fast deterministic runner for dry-run verification of pipeline timing & segmentation."""

    backend_name: str = "mock_benchmark"

    def __init__(self, simulated_rtf: float = 0.25) -> None:
        self.simulated_rtf = simulated_rtf

    def load(self) -> None:
        pass

    def warmup(self, runs: int = 1) -> None:
        pass

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> tuple[str, float]:
        dur = len(audio) / float(sample_rate)
        time.sleep(min(0.05, dur * self.simulated_rtf * 0.1))
        return ("Xin chào Việt Nam", 0.0)


def run_trial(
    base_cfg: GemmaSTTConfig,
    runner: STTModelRunner,
    trial: dict[str, Any],
    samples: list[tuple[np.ndarray, str, str]],
) -> dict[str, Any]:
    cfg = copy.deepcopy(base_cfg)
    cfg.vad.silence_ms = int(trial["silence_ms"])
    cfg.vad.max_segment_ms = int(trial["max_segment_ms"])
    cfg.vad.engine = trial["vad"]
    cfg.output.transcript_path = Path(f"outputs/bench_{trial['id']}_transcript.txt")
    cfg.output.results_path = Path(f"outputs/bench_{trial['id']}_results.jsonl")
    cfg.output.metrics_path = Path(f"outputs/bench_{trial['id']}_metrics.csv")

    for p in (cfg.output.transcript_path, cfg.output.results_path, cfg.output.metrics_path):
        if p.is_file():
            p.unlink()

    writer = OutputWriter(cfg.output)
    pipeline = NearRealtimeSTTPipeline(cfg=cfg, model_runner=runner, output_writer=writer)

    sr = cfg.audio.sample_rate
    block_size = cfg.audio.block_size
    block_idx = 0

    wers: list[float] = []
    cers: list[float] = []
    false_positives = 0
    silent_noise_trials = 0

    for audio, expected_text, category in samples:
        pipeline.segmenter.reset()
        # Pad 650ms of trailing silence so VAD emits naturally
        padded = np.concatenate([audio, np.zeros(int(0.65 * sr), dtype=np.float32)])
        emitted_texts: list[str] = []

        for offset in range(0, len(padded), block_size):
            chunk = padded[offset : offset + block_size]
            if len(chunk) < block_size:
                chunk = np.pad(chunk, (0, block_size - len(chunk)))
            block = AudioBlock(
                samples=chunk,
                captured_at=time.monotonic(),
                sample_rate=sr,
                block_index=block_idx,
            )
            block_idx += 1
            seg = pipeline.segmenter.process_block(block)
            if seg is not None:
                res = pipeline.process_segment_sync(seg)
                if res.text:
                    emitted_texts.append(res.text)

        flushed = pipeline.segmenter.flush()
        if flushed is not None:
            res = pipeline.process_segment_sync(flushed)
            if res.text:
                emitted_texts.append(res.text)

        combined_hyp = " ".join(emitted_texts).strip()
        if category in ("silence", "noise") or not expected_text:
            silent_noise_trials += 1
            if combined_hyp:
                false_positives += 1
        else:
            wers.append(compute_wer(expected_text, combined_hyp))
            cers.append(compute_cer(expected_text, combined_hyp))

    summary = summarize_metrics(writer.history)
    summary["trial_id"] = trial["id"]
    summary["silence_ms"] = trial["silence_ms"]
    summary["max_segment_s"] = trial["max_segment_ms"] / 1000.0
    summary["vad"] = trial["vad"]
    summary["wer"] = round(float(np.mean(wers)) if wers else 0.0, 4)
    summary["cer"] = round(float(np.mean(cers)) if cers else 0.0, 4)
    summary["false_positives"] = f"{false_positives}/{silent_noise_trials}"
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase I Benchmark Matrix (T01..T06)")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--reference", default="tests/fixtures/reference.csv", help="Path to reference.csv")
    parser.add_argument("--mock", action="store_true", help="Use deterministic mock runner for pipeline timing test")
    parser.add_argument("--out", default="outputs/benchmark_report.md", help="Output Markdown report path")
    args = parser.parse_args()

    cfg = GemmaSTTConfig.load(args.config)
    ref_path = Path(args.reference)
    if not ref_path.is_file():
        print(f"Không tìm thấy {ref_path}")
        return 1

    samples: list[tuple[np.ndarray, str, str]] = []
    with open(ref_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            wav_path = ref_path.parent / row["file"].strip()
            if wav_path.is_file():
                audio = load_wav_float32_16k(wav_path, cfg.audio.sample_rate)
                samples.append((audio, row["expected"].strip(), row.get("category", "").strip()))

    if not samples:
        print("Chưa có file WAV trong tests/fixtures/. Hãy chạy: python scripts/record_test_wav.py --generate-fixtures")
        return 1

    runner: STTModelRunner = MockBenchmarkRunner() if args.mock else create_model_runner(cfg)

    md_lines = [
        "# Báo Cáo Benchmark Tiếng Việt & Độ Trễ (Giai đoạn I)\n",
        f"- **Backend:** `{runner.backend_name}`",
        f"- **Model:** `{cfg.model.id}`",
        f"- **Số mẫu kiểm thử:** `{len(samples)}`\n",
        "| Trial | Silence ms | Max segment s | VAD | GPU dtype | p50 E2E (s) | p95 E2E (s) | Mean RTF | WER | CER | False Positives | Drop |",
        "|---|---:|---:|---|---|---:|---:|---:|---:|---:|---|---:|",
    ]

    for trial in TRIAL_MATRIX:
        res = run_trial(cfg, runner, trial, samples)
        md_lines.append(
            f"| {res['trial_id']} | {res['silence_ms']} | {res['max_segment_s']:.1f} | "
            f"{res['vad']} | {cfg.model.dtype} | {res['p50_e2e_voice_s']:.3f} | "
            f"{res['p95_e2e_voice_s']:.3f} | {res['mean_rtf']:.3f} | "
            f"{res['wer']:.1%} | {res['cer']:.1%} | {res['false_positives']} | {res['dropped_segments']} |"
        )

    report_text = "\n".join(md_lines)
    print(report_text)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report_text, encoding="utf-8")
    print(f"\n[✔] Đã lưu báo cáo benchmark tại {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
