from __future__ import annotations

import asyncio
import io
import logging
from typing import Any

import numpy as np

logger = logging.getLogger("claw.voice.player")


class AudioPlayer:
    def __init__(self, device: str | int | None = None) -> None:
        self.device = device
        self._is_playing = False
        self._stop_event = asyncio.Event()

    def is_playing(self) -> bool:
        return self._is_playing

    def stop(self) -> None:
        """Immediately interrupt playback."""
        self._stop_event.set()
        self._is_playing = False

    async def play_audio_bytes(self, audio_data: bytes) -> None:
        """Decode audio data (MP3/WAV) and play it via sounddevice with interrupt support."""
        if not audio_data:
            return

        self._stop_event.clear()
        self._is_playing = True

        try:
            # Decode audio using av (PyAV)
            import av

            container: Any = av.open(io.BytesIO(audio_data))
            frames: list[np.ndarray] = []
            sample_rate = 24000
            channels = 1

            for frame in container.decode(audio=0):
                sample_rate = frame.sample_rate
                channels = len(frame.layout.channels)
                # Convert to numpy float32
                array = frame.to_ndarray()
                if array.dtype == np.int16:
                    array = array.astype(np.float32) / 32768.0
                frames.append(array.T if array.ndim > 1 else array)

            if not frames:
                return

            full_audio = np.concatenate(frames)

            # Play using sounddevice OutputStream in chunks
            import sounddevice as sd

            dev: int | str | None = None
            if self.device is not None and self.device != "default":
                try:
                    dev = int(self.device)
                except ValueError:
                    dev = self.device

            chunk_size = 2048
            total_samples = len(full_audio)

            with sd.OutputStream(
                samplerate=sample_rate,
                channels=channels,
                dtype="float32",
                device=dev,
            ) as stream:
                for i in range(0, total_samples, chunk_size):
                    if self._stop_event.is_set():
                        break
                    chunk = full_audio[i : i + chunk_size]
                    if len(chunk) < chunk_size:
                        chunk = np.pad(chunk, ((0, chunk_size - len(chunk)), (0, 0)) if chunk.ndim > 1 else (0, chunk_size - len(chunk)))
                    stream.write(chunk)
                    await asyncio.sleep(0.001)

        except Exception as e:
            logger.warning(f"Audio playback error: {e}")
        finally:
            self._is_playing = False
