from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger("claw.voice.wakeword")


class WakeWordDetector:
    """Wake-word detector (supporting openWakeWord or keyword model)."""

    def __init__(self, model_name: str = "hey_claw") -> None:
        self.model_name = model_name
        self._model: Any = None
        self._initialized = False

    def init_model(self) -> None:
        try:
            from openwakeword.model import Model

            self._model = Model(wakeword_models=[self.model_name])
            self._initialized = True
        except ImportError:
            logger.debug("openWakeWord not installed. Wake-word mode requires 'openwakeword'.")
        except Exception as e:
            logger.debug(f"Failed to load wakeword model: {e}")

    def predict(self, frame: np.ndarray) -> bool:
        """Process 16kHz audio frame and return True if wake word is detected."""
        if not self._initialized:
            return False

        try:
            prediction = self._model.predict(frame)
            for md, score in prediction.items():
                if score > 0.5:
                    return True
        except Exception:
            pass

        return False
