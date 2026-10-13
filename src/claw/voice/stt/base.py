from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np


@dataclass
class Segment:
    start: float
    end: float
    text: str
    avg_logprob: float = 0.0
    no_speech_prob: float = 0.0


@dataclass
class Transcript:
    text: str
    language: str = "vi"
    confidence: float = 1.0
    segments: list[Segment] = field(default_factory=list)


class STTProvider(Protocol):
    async def transcribe(self, pcm: np.ndarray, sample_rate: int = 16000, language: str = "vi") -> Transcript:
        ...
