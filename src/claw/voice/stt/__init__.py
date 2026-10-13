"""STT Providers."""

from claw.voice.stt.base import Segment, STTProvider, Transcript
from claw.voice.stt.faster_whisper import FasterWhisperSTT
from claw.voice.stt.openai_compat import OpenAICompatibleSTT

__all__ = ["FasterWhisperSTT", "OpenAICompatibleSTT", "STTProvider", "Segment", "Transcript"]
