#!/usr/bin/env python3
"""
Evaluate STT accuracy using Word Error Rate (WER) and Character Error Rate (CER).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def levenshtein_distance(seq1: list[str] | str, seq2: list[str] | str) -> int:
    m, n = len(seq1), len(seq2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if seq1[i - 1] == seq2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
    return dp[m][n]


def compute_wer(ref: str, hyp: str) -> float:
    r_words = ref.lower().strip().split()
    h_words = hyp.lower().strip().split()
    if not r_words:
        return 0.0 if not h_words else 1.0
    dist = levenshtein_distance(r_words, h_words)
    return dist / len(r_words)


def compute_cer(ref: str, hyp: str) -> float:
    r_chars = "".join(ref.lower().split())
    h_chars = "".join(hyp.lower().split())
    if not r_chars:
        return 0.0 if not h_chars else 1.0
    dist = levenshtein_distance(r_chars, h_chars)
    return dist / len(r_chars)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate STT accuracy (WER/CER)")
    parser.add_argument("--ref", default="tests/fixtures/audio/expected.txt", help="Reference ground-truth file")
    parser.add_argument("--hyp", help="Hypothesis file from STT run")
    args = parser.parse_args()

    ref_path = Path(args.ref)
    if not ref_path.is_file():
        print(f"Reference file not found: {ref_path}")
        sys.exit(1)

    ref_lines = [line.strip() for line in ref_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    if not args.hyp:
        print(f"Found {len(ref_lines)} reference sentences in {ref_path}.")
        print("Provide --hyp <file> to compute WER against actual transcriptions.")
        return

    hyp_lines = [line.strip() for line in Path(args.hyp).read_text(encoding="utf-8").splitlines() if line.strip()]

    total_wer = 0.0
    total_cer = 0.0
    n = min(len(ref_lines), len(hyp_lines))

    for i in range(n):
        wer = compute_wer(ref_lines[i], hyp_lines[i])
        cer = compute_cer(ref_lines[i], hyp_lines[i])
        total_wer += wer
        total_cer += cer
        print(f"[{i+1}] Ref: {ref_lines[i]}")
        print(f"    Hyp: {hyp_lines[i]}")
        print(f"    WER: {wer:.2%}, CER: {cer:.2%}")

    avg_wer = total_wer / n if n > 0 else 0.0
    avg_cer = total_cer / n if n > 0 else 0.0
    print("\n--- Summary ---")
    print(f"Average WER: {avg_wer:.2%}")
    print(f"Average CER: {avg_cer:.2%}")


if __name__ == "__main__":
    main()
