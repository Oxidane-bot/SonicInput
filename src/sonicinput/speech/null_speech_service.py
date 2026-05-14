"""Fallback speech service when local/cloud engines are unavailable."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import numpy as np

from ..core.interfaces.speech import ISpeechService
from ..utils import app_logger


class NullSpeechService(ISpeechService):
    """No-op speech service that keeps the app running when ASR is unavailable."""

    provider_id = "unavailable"
    display_name = "Unavailable"
    description = "Speech service unavailable"

    def __init__(self, reason: str = "Speech service unavailable"):
        self._reason = reason
        self._is_model_loaded = False

    @property
    def is_model_loaded(self) -> bool:
        return False

    @property
    def is_running(self) -> bool:
        return False

    def transcribe(
        self, audio_data: np.ndarray, language: Optional[str] = None
    ) -> Dict[str, Any]:
        app_logger.log_audio_event(
            "NullSpeechService transcribe called", {"reason": self._reason}
        )
        raise RuntimeError(self._reason)

    def transcribe_sync(
        self,
        audio_data: np.ndarray,
        language: Optional[str] = None,
        temperature: float = 0.0,
        emit_event: bool = False,
    ) -> Dict[str, Any]:
        return self.transcribe(audio_data, language=language)

    def transcribe_async(
        self,
        audio_data: np.ndarray,
        language: Optional[str] = None,
        callback: Optional[Callable] = None,
        error_callback: Optional[Callable] = None,
    ) -> str:
        if error_callback:
            error_callback(self._reason)
        return "noop"

    def load_model(self, model_name: Optional[str] = None) -> bool:
        app_logger.log_audio_event(
            "NullSpeechService load_model called", {"reason": self._reason}
        )
        return False

    def load_model_async(
        self,
        model_name: Optional[str] = None,
        timeout: int = 300,
        callback: Optional[Callable] = None,
        error_callback: Optional[Callable] = None,
    ) -> str:
        if error_callback:
            error_callback(self._reason)
        return "noop"

    def reload_model(
        self,
        model_name: Optional[str] = None,
        use_gpu: Optional[bool] = None,
        callback: Optional[Callable] = None,
        error_callback: Optional[Callable] = None,
    ) -> str:
        if error_callback:
            error_callback(self._reason)
        return "noop"

    def unload_model(self) -> None:
        return None

    def get_available_models(self) -> List[str]:
        return []

    def get_available_models_async(self) -> List[str]:
        return []

    def start_streaming(self) -> None:
        return None

    def stop_streaming(self) -> Dict[str, Any]:
        return {"text": "", "stats": {}}

    def add_streaming_chunk(self, audio_data: np.ndarray) -> int:
        return -1

    def start_streaming_mode(self) -> None:
        return None

    def start_streaming_processing(self) -> None:
        return None
