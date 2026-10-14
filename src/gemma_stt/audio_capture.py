from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

logger = logging.getLogger("gemma_stt.audio_capture")


class AudioDeviceError(RuntimeError):
    """Raised when microphone stream fails or disconnects."""


@dataclass(slots=True)
class AudioBlock:
    """Single block of captured audio samples."""

    samples: np.ndarray
    captured_at: float
    sample_rate: int
    block_index: int
    dropped_before: int = 0


class MicrophoneCapture:
    """Continuous microphone capture using sounddevice InputStream and a bounded queue.

    Design principles (Section D & Section 14):
    - Callback only copies block into bounded queue; no inference, network, or file I/O.
    - Never silently ignores queue.Full: counts every dropped block and attaches drop count
      to the next successfully queued AudioBlock so downstream logs/metrics reflect any loss.
    - Supports automatic resampling to 16 kHz in the consumer thread if the device only
      supports a different hardware sample rate (e.g., 44.1 kHz or 48 kHz).
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        block_ms: int = 20,
        max_blocks: int = 150,
        device: str | int | None = None,
    ) -> None:
        self.target_sample_rate = sample_rate
        self.hardware_sample_rate = sample_rate
        self.channels = channels
        self.block_ms = block_ms
        self.target_block_size = (sample_rate * block_ms) // 1000
        self.hardware_block_size = self.target_block_size
        self.max_blocks = max_blocks
        self.device = device

        self._queue: queue.Queue[AudioBlock | None] = queue.Queue(maxsize=max_blocks)
        self._stream: Any = None
        self._running = False
        self._lock = threading.Lock()

        # Metrics & error state
        self.total_blocks_captured: int = 0
        self.dropped_blocks: int = 0
        self.status_warnings: int = 0
        self._pending_drops: int = 0
        self._last_drop_log_at: float = 0.0
        self._stream_error: str | None = None

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    @property
    def is_running(self) -> bool:
        if not self._running:
            return False
        if self._stream is not None and hasattr(self._stream, "active"):
            if not self._stream.active and self._stream_error is None:
                self._stream_error = "Microphone stream became inactive (device disconnected?)."
        return self._running and self._stream_error is None

    @property
    def stream_error(self) -> str | None:
        return self._stream_error

    def _resolve_device(self, sd_module: Any) -> int | str | None:
        if self.device is None or self.device == "default" or self.device == "":
            return None
        if isinstance(self.device, int):
            return self.device
        try:
            return int(self.device)
        except ValueError:
            return self.device

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        now = time.monotonic()
        if status:
            self.status_warnings += 1

        if not self._running:
            return

        # Extract mono channel as float32 copy
        if indata.ndim == 2:
            mono = indata[:, 0].astype(np.float32, copy=True)
        else:
            mono = indata.astype(np.float32, copy=True).reshape(-1)

        idx = self.total_blocks_captured
        self.total_blocks_captured += 1

        block = AudioBlock(
            samples=mono,
            captured_at=now,
            sample_rate=self.hardware_sample_rate,
            block_index=idx,
            dropped_before=self._pending_drops,
        )

        try:
            self._queue.put_nowait(block)
            self._pending_drops = 0
        except queue.Full:
            self.dropped_blocks += 1
            self._pending_drops += 1
            if now - self._last_drop_log_at >= 1.0:
                self._last_drop_log_at = now
                logger.warning(
                    "Audio queue full (maxsize=%d)! Dropped %d audio blocks total.",
                    self.max_blocks,
                    self.dropped_blocks,
                )

    def _stream_finished_callback(self) -> None:
        if self._running:
            self._stream_error = "Microphone stream unexpectedly finished or device was unplugged."
            logger.error(self._stream_error)

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            try:
                import sounddevice as sd
            except ImportError as exc:
                raise AudioDeviceError("Thư viện sounddevice chưa được cài đặt.") from exc

            dev = self._resolve_device(sd)
            self._stream_error = None
            self._running = True

            # Try opening at target_sample_rate (16000 Hz) first
            try:
                self.hardware_sample_rate = self.target_sample_rate
                self.hardware_block_size = self.target_block_size
                self._stream = sd.InputStream(
                    samplerate=self.hardware_sample_rate,
                    channels=self.channels,
                    dtype="float32",
                    blocksize=self.hardware_block_size,
                    device=dev,
                    callback=self._audio_callback,
                    finished_callback=self._stream_finished_callback,
                )
                self._stream.start()
                logger.info(
                    "Microphone started at %d Hz, block=%d samples (%d ms), device=%s",
                    self.hardware_sample_rate,
                    self.hardware_block_size,
                    self.block_ms,
                    dev if dev is not None else "default",
                )
            except Exception as first_err:
                # Fallback: query device default sample rate and resample in consumer thread
                try:
                    dev_info = sd.query_devices(dev, "input")
                    native_sr = int(dev_info.get("default_samplerate", 48000))
                    self.hardware_sample_rate = native_sr
                    self.hardware_block_size = (native_sr * self.block_ms) // 1000
                    self._stream = sd.InputStream(
                        samplerate=self.hardware_sample_rate,
                        channels=self.channels,
                        dtype="float32",
                        blocksize=self.hardware_block_size,
                        device=dev,
                        callback=self._audio_callback,
                        finished_callback=self._stream_finished_callback,
                    )
                    self._stream.start()
                    logger.warning(
                        "Device did not accept %d Hz (%s); opened at %d Hz with consumer resampling.",
                        self.target_sample_rate,
                        first_err,
                        self.hardware_sample_rate,
                    )
                except Exception as second_err:
                    self._running = False
                    self._stream = None
                    raise AudioDeviceError(
                        f"Không thể mở microphone (device={dev}): {second_err}"
                    ) from second_err

    def stop(self) -> None:
        with self._lock:
            self._running = False
            stream = self._stream
            self._stream = None
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception as exc:
                    logger.debug("Error closing audio stream: %s", exc)
            # Push sentinel to wake consumer if waiting
            try:
                self._queue.put_nowait(None)
            except queue.Full:
                pass

    def get_block(self, timeout: float = 0.1) -> AudioBlock | None:
        """Read next audio block in consumer thread, resampling to target_sample_rate if needed."""
        if self._stream_error:
            raise AudioDeviceError(self._stream_error)

        if self._stream is not None and hasattr(self._stream, "active") and not self._stream.active:
            if self._running:
                self._stream_error = "Microphone stream inactive (device disconnected)."
                raise AudioDeviceError(self._stream_error)

        try:
            block = self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

        if block is None:
            return None

        if block.sample_rate != self.target_sample_rate:
            block = self._resample_block(block)

        return block

    def _resample_block(self, block: AudioBlock) -> AudioBlock:
        import math

        from scipy.signal import resample_poly

        gcd = math.gcd(self.target_sample_rate, block.sample_rate)
        up = self.target_sample_rate // gcd
        down = block.sample_rate // gcd
        resampled = resample_poly(block.samples, up, down).astype(np.float32)
        return AudioBlock(
            samples=resampled,
            captured_at=block.captured_at,
            sample_rate=self.target_sample_rate,
            block_index=block.block_index,
            dropped_before=block.dropped_before,
        )
