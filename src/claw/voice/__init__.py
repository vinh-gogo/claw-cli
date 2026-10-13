"""Voice package."""

from claw.voice.commands import VoiceCommand, match_voice_command
from claw.voice.devices import list_audio_devices
from claw.voice.player import AudioPlayer
from claw.voice.recorder import AudioRecorder
from claw.voice.vad import SileroVAD, UtteranceDetector
from claw.voice.wakeword import WakeWordDetector

__all__ = [
    "AudioPlayer",
    "AudioRecorder",
    "SileroVAD",
    "UtteranceDetector",
    "VoiceCommand",
    "WakeWordDetector",
    "list_audio_devices",
    "match_voice_command",
]
