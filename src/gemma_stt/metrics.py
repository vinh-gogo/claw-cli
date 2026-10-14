from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np


@dataclass(slots=True)
class TranscriptionResult:
    """Complete transcription result and timing metrics for a single segment."""

    segment_id: int
    text: str
    duration_s: float
    speech_duration_s: float = 0.0
    vad_delay_s: float = 0.0
    queue_wait_s: float = 0.0
    inference_s: float = 0.0
    e2e_voice_end_s: float = 0.0
    e2e_buffer_end_s: float = 0.0
    rtf: float = 0.0
    peak_vram_mb: float = 0.0
    dropped: bool = False
    had_audio_drop: bool = False
    emit_reason: str = "silence_timeout"
    is_forced_split: bool = False
    backend: str = "local_gemma"

    def to_jsonl_dict(self) -> dict[str, Any]:
        """Return dictionary formatted for results.jsonl (Section G4 & I1)."""
        return {
            "segment_id": self.segment_id,
            "text": self.text,
            "duration_s": round(self.duration_s, 3),
            "speech_duration_s": round(self.speech_duration_s, 3),
            "vad_delay_s": round(self.vad_delay_s, 3),
            "queue_wait_s": round(self.queue_wait_s, 3),
            "inference_s": round(self.inference_s, 3),
            "e2e_voice_end_s": round(self.e2e_voice_end_s, 3),
            "e2e_buffer_end_s": round(self.e2e_buffer_end_s, 3),
            "rtf": round(self.rtf, 3),
            "peak_vram_mb": round(self.peak_vram_mb, 1),
            "dropped": self.dropped,
            "had_audio_drop": self.had_audio_drop,
            "emit_reason": self.emit_reason,
            "is_forced_split": self.is_forced_split,
            "backend": self.backend,
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_vietnamese_text(text: str, strip_punctuation: bool = True) -> str:
    """Normalize Vietnamese text for WER/CER evaluation while preserving all diacritics.

    Normalization rules (Section I2):
    - Unicode NFC normalization (canonical Vietnamese tone mark composition)
    - Lowercase conversion
    - Strip punctuation (commas, periods, question marks, etc.) if strip_punctuation=True
    - Collapse multiple whitespace into single space
    """
    norm = unicodedata.normalize("NFC", text).lower().strip()
    if strip_punctuation:
        norm = _PUNCT_RE.sub(" ", norm)
    norm = _WHITESPACE_RE.sub(" ", norm).strip()
    return norm


def levenshtein_distance(seq1: list[str] | str, seq2: list[str] | str) -> int:
    """Compute Levenshtein edit distance between two sequences."""
    m, n = len(seq1), len(seq2)
    if m == 0:
        return n
    if n == 0:
        return m

    prev = list(range(n + 1))
    curr = [0] * (n + 1)
    for i in range(1, m + 1):
        curr[0] = i
        s1_item = seq1[i - 1]
        for j in range(1, n + 1):
            cost = 0 if s1_item == seq2[j - 1] else 1
            curr[j] = min(
                prev[j] + 1,      # deletion
                curr[j - 1] + 1,  # insertion
                prev[j - 1] + cost,  # substitution
            )
        prev, curr = curr, prev
    return prev[n]


def compute_wer(reference: str, hypothesis: str) -> float:
    """Compute Word Error Rate (WER) on normalized Vietnamese text."""
    ref_norm = normalize_vietnamese_text(reference)
    hyp_norm = normalize_vietnamese_text(hypothesis)
    ref_words = ref_norm.split() if ref_norm else []
    hyp_words = hyp_norm.split() if hyp_norm else []
    if not ref_words:
        return 0.0 if not hyp_words else 1.0
    dist = levenshtein_distance(ref_words, hyp_words)
    return float(dist) / float(len(ref_words))


def compute_cer(reference: str, hypothesis: str) -> float:
    """Compute Character Error Rate (CER) on normalized Vietnamese text (excluding spaces)."""
    ref_norm = normalize_vietnamese_text(reference)
    hyp_norm = normalize_vietnamese_text(hypothesis)
    ref_chars = "".join(ref_norm.split())
    hyp_chars = "".join(hyp_norm.split())
    if not ref_chars:
        return 0.0 if not hyp_chars else 1.0
    dist = levenshtein_distance(ref_chars, hyp_chars)
    return float(dist) / float(len(ref_chars))


def summarize_metrics(results: list[TranscriptionResult]) -> dict[str, Any]:
    """Compute p50/p95 latencies, RTF, peak VRAM, and drop statistics from a run."""
    total_segments = len(results)
    dropped_segments = sum(1 for r in results if r.dropped)
    completed = [r for r in results if not r.dropped]

    if not completed:
        return {
            "total_segments": total_segments,
            "completed_segments": 0,
            "dropped_segments": dropped_segments,
            "p50_e2e_voice_s": 0.0,
            "p95_e2e_voice_s": 0.0,
            "p50_e2e_buffer_s": 0.0,
            "p95_e2e_buffer_s": 0.0,
            "p50_inference_s": 0.0,
            "p95_inference_s": 0.0,
            "mean_rtf": 0.0,
            "p95_rtf": 0.0,
            "max_queue_wait_s": 0.0,
            "peak_vram_mb": 0.0,
        }

    e2e_voice = np.array([r.e2e_voice_end_s for r in completed], dtype=np.float64)
    e2e_buf = np.array([r.e2e_buffer_end_s for r in completed], dtype=np.float64)
    inf_lat = np.array([r.inference_s for r in completed], dtype=np.float64)
    rtfs = np.array([r.rtf for r in completed], dtype=np.float64)
    q_waits = np.array([r.queue_wait_s for r in completed], dtype=np.float64)
    vrams = np.array([r.peak_vram_mb for r in completed], dtype=np.float64)

    return {
        "total_segments": total_segments,
        "completed_segments": len(completed),
        "dropped_segments": dropped_segments,
        "p50_e2e_voice_s": round(float(np.percentile(e2e_voice, 50)), 3),
        "p95_e2e_voice_s": round(float(np.percentile(e2e_voice, 95)), 3),
        "p50_e2e_buffer_s": round(float(np.percentile(e2e_buf, 50)), 3),
        "p95_e2e_buffer_s": round(float(np.percentile(e2e_buf, 95)), 3),
        "p50_inference_s": round(float(np.percentile(inf_lat, 50)), 3),
        "p95_inference_s": round(float(np.percentile(inf_lat, 95)), 3),
        "mean_rtf": round(float(np.mean(rtfs)), 3),
        "p95_rtf": round(float(np.percentile(rtfs, 95)), 3),
        "max_queue_wait_s": round(float(np.max(q_waits)), 3),
        "peak_vram_mb": round(float(np.max(vrams)), 1),
    }
