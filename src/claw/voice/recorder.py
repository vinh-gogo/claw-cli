from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator

import numpy as np

logger = logging.getLogger("claw.voice.recorder")


class AudioRecorder:
    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        block_size: int = 512,
        device: str | int | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_size = block_size
        self.device = device
        self._queue: asyncio.Queue[np.ndarray] = asyncio.Queue()
        self._stream: Any = None
        self._is_recording = False
        self._loop: asyncio.AbstractEventLoop | None = None

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        if status:
            logger.debug(f"Audio input status: {status}")
        if self._is_recording and self._loop:
            # Copy data to prevent buffer overwrite by sounddevice
            audio_frame = indata.copy().flatten()
            self._loop.call_soon_threadsafe(self._queue.put_nowait, audio_frame)

    async def start(self) -> None:
        if self._is_recording:
            return

        try:
            import sounddevice as sd
        except ImportError:
            raise RuntimeError("Thư viện sounddevice chưa được cài đặt.")

        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        self._is_recording = True

        dev: int | str | None = None
        if self.device is not None and self.device != "default":
            try:
                dev = int(self.device)
            except ValueError:
                dev = self.device

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
                blocksize=self.block_size,
                device=dev,
                callback=self._audio_callback,
            )
            self._stream.start()
        except Exception as e:
            self._is_recording = False
            raise RuntimeError(f"Không thể mở microphone: {e}")

    async def stop(self) -> None:
        self._is_recording = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    async def stream_frames(self) -> AsyncIterator[np.ndarray]:
        """Stream recorded PCM frames until stopped."""
        while self._is_recording:
            try:
                frame = await asyncio.wait_for(self._queue.get(), timeout=0.1)
                yield frame
            except asyncio.TimeoutError:
                continue

    @property
    def is_recording(self) -> bool:
        return self._is_recording
