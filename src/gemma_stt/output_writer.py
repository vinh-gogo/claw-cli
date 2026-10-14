from __future__ import annotations

import csv
import json
import logging
import shutil
import threading
from pathlib import Path
from typing import Callable

from gemma_stt.config_schema import OutputConfig
from gemma_stt.metrics import TranscriptionResult

logger = logging.getLogger("gemma_stt.output_writer")

CSV_FIELDNAMES = [
    "segment_id",
    "duration_s",
    "speech_duration_s",
    "vad_delay_s",
    "queue_wait_s",
    "inference_s",
    "e2e_voice_end_s",
    "e2e_buffer_end_s",
    "rtf",
    "peak_vram_mb",
    "dropped",
    "had_audio_drop",
    "emit_reason",
    "is_forced_split",
    "backend",
    "text",
]


class OutputWriter:
    """Order-preserving writer for console, transcript.txt, results.jsonl, and metrics.csv.

    Ensures segments are written strictly in ascending segment_id order even if
    dropped notifications and completed inferences arrive slightly out of order.
    """

    def __init__(
        self,
        cfg: OutputConfig,
        console_callback: Callable[[TranscriptionResult], None] | None = None,
    ) -> None:
        self.cfg = cfg
        self.console_callback = console_callback
        self._lock = threading.Lock()
        self._expected_segment_id: int = 1
        self._pending: dict[int, TranscriptionResult] = {}
        self.history: list[TranscriptionResult] = []

        self._ensure_directories()

    def _ensure_directories(self) -> None:
        self.cfg.transcript_path.parent.mkdir(parents=True, exist_ok=True)
        self.cfg.results_path.parent.mkdir(parents=True, exist_ok=True)
        self.cfg.metrics_path.parent.mkdir(parents=True, exist_ok=True)
        if self.cfg.save_debug_wav:
            self.cfg.debug_wav_dir.mkdir(parents=True, exist_ok=True)

        if not self.cfg.metrics_path.is_file() or self.cfg.metrics_path.stat().st_size == 0:
            with open(self.cfg.metrics_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
                writer.writeheader()

    def write(self, result: TranscriptionResult) -> list[TranscriptionResult]:
        """Submit a TranscriptionResult and flush all consecutive in-order segments."""
        flushed: list[TranscriptionResult] = []
        with self._lock:
            self._pending[result.segment_id] = result
            while self._expected_segment_id in self._pending:
                next_res = self._pending.pop(self._expected_segment_id)
                self._write_single(next_res)
                flushed.append(next_res)
                self._expected_segment_id += 1
        return flushed

    def flush_remaining(self) -> list[TranscriptionResult]:
        """Flush any remaining buffered results in ascending segment_id order on shutdown."""
        flushed: list[TranscriptionResult] = []
        with self._lock:
            for seg_id in sorted(self._pending.keys()):
                res = self._pending.pop(seg_id)
                self._write_single(res)
                flushed.append(res)
                self._expected_segment_id = max(self._expected_segment_id, seg_id + 1)
        return flushed

    def _write_single(self, result: TranscriptionResult) -> None:
        self.history.append(result)

        # 1. Write JSONL entry (includes both completed and dropped segments)
        jsonl_line = json.dumps(result.to_jsonl_dict(), ensure_ascii=False)
        with open(self.cfg.results_path, "a", encoding="utf-8") as jf:
            jf.write(jsonl_line + "\n")

        # 2. Write CSV metrics row
        with open(self.cfg.metrics_path, "a", encoding="utf-8", newline="") as cf:
            writer = csv.DictWriter(cf, fieldnames=CSV_FIELDNAMES)
            row = {k: result.to_jsonl_dict().get(k, "") for k in CSV_FIELDNAMES}
            writer.writerow(row)

        # 3. Write transcript.txt (only non-empty non-dropped speech, or explicit drop marker)
        if result.dropped:
            with open(self.cfg.transcript_path, "a", encoding="utf-8") as tf:
                tf.write(f"[SEGMENT #{result.segment_id} DROPPED - OVERLOAD]\n")
        elif result.text.strip():
            with open(self.cfg.transcript_path, "a", encoding="utf-8") as tf:
                tf.write(result.text.strip() + "\n")

        # 4. Console callback
        if self.console_callback is not None:
            self.console_callback(result)


def clean_outputs(cfg: OutputConfig) -> list[Path]:
    """Delete transcript, JSONL, metrics CSV, and debug WAV files for user privacy (Section G5)."""
    removed: list[Path] = []
    for path in (cfg.transcript_path, cfg.results_path, cfg.metrics_path):
        if path.is_file():
            path.unlink()
            removed.append(path)
    if cfg.debug_wav_dir.is_dir():
        shutil.rmtree(cfg.debug_wav_dir)
        removed.append(cfg.debug_wav_dir)
    return removed
