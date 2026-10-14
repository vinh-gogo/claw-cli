from __future__ import annotations

import json
from pathlib import Path

from gemma_stt.config_schema import OutputConfig
from gemma_stt.metrics import (
    TranscriptionResult,
    compute_cer,
    compute_wer,
    normalize_vietnamese_text,
    summarize_metrics,
)
from gemma_stt.output_writer import OutputWriter, clean_outputs


def test_vietnamese_normalization_and_wer_cer() -> None:
    ref = "Xin chào, hôm nay trời đẹp quá!"
    hyp = "xin chào hôm nay trời đẹp quá"
    assert normalize_vietnamese_text(ref) == "xin chào hôm nay trời đẹp quá"
    assert compute_wer(ref, hyp) == 0.0
    assert compute_cer(ref, hyp) == 0.0

    # Test diacritic mismatch (đẹp -> dep) counts as 1 word error out of 7 words
    hyp_wrong_tone = "xin chào hôm nay trời dep quá"
    wer = compute_wer(ref, hyp_wrong_tone)
    assert abs(wer - (1.0 / 7.0)) < 1e-6
    assert compute_cer(ref, hyp_wrong_tone) > 0.0


def test_output_writer_preserves_segment_order_and_formats(tmp_path: Path) -> None:
    cfg = OutputConfig(
        transcript_path=tmp_path / "transcript.txt",
        results_path=tmp_path / "results.jsonl",
        metrics_path=tmp_path / "metrics.csv",
    )
    writer = OutputWriter(cfg)

    r2 = TranscriptionResult(
        segment_id=2,
        text="Câu thứ hai.",
        duration_s=2.5,
        inference_s=0.8,
        queue_wait_s=0.05,
        e2e_voice_end_s=1.25,
        e2e_buffer_end_s=0.85,
        rtf=0.32,
        dropped=False,
    )
    r1 = TranscriptionResult(
        segment_id=1,
        text="Xin chào mọi người.",
        duration_s=2.0,
        inference_s=0.6,
        queue_wait_s=0.02,
        e2e_voice_end_s=1.05,
        e2e_buffer_end_s=0.62,
        rtf=0.30,
        dropped=False,
    )

    # Write segment 2 before segment 1
    assert writer.write(r2) == []
    flushed = writer.write(r1)
    assert [x.segment_id for x in flushed] == [1, 2]

    # Verify transcript.txt
    lines = cfg.transcript_path.read_text(encoding="utf-8").splitlines()
    assert lines == ["Xin chào mọi người.", "Câu thứ hai."]

    # Verify results.jsonl schema
    jsonl_lines = cfg.results_path.read_text(encoding="utf-8").splitlines()
    assert len(jsonl_lines) == 2
    parsed_1 = json.loads(jsonl_lines[0])
    parsed_2 = json.loads(jsonl_lines[1])
    assert parsed_1["segment_id"] == 1
    assert parsed_1["text"] == "Xin chào mọi người."
    assert parsed_1["dropped"] is False
    assert parsed_2["segment_id"] == 2

    # Verify summary statistics
    summary = summarize_metrics(writer.history)
    assert summary["total_segments"] == 2
    assert summary["completed_segments"] == 2
    assert summary["dropped_segments"] == 0
    assert summary["p50_e2e_voice_s"] > 0.0

    # Verify privacy clean_outputs
    removed = clean_outputs(cfg)
    assert len(removed) == 3
    assert not cfg.transcript_path.exists()
    assert not cfg.results_path.exists()
    assert not cfg.metrics_path.exists()
