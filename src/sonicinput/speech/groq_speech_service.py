"""Groq Cloud Speech Service - Simplified implementation"""

from typing import Any, Dict, List, Optional

from ..utils import app_logger
from .cloud_base import CloudTranscriptionBase

# Lazy import groq to avoid dependency issues
groq = None


def _ensure_groq_imported():
    """Ensure groq is imported when needed"""
    global groq
    if groq is None:
        try:
            from groq import Groq

            groq = Groq
            app_logger.log_model_loading_step("Groq module imported successfully", {})
        except ImportError as e:
            error_msg = f"Failed to import groq: {e}. Install with: pip install groq"
            app_logger.log_error(e, "groq_import")
            raise ImportError(error_msg)
    return groq


class GroqSpeechService(CloudTranscriptionBase):
    """Groq Cloud Whisper API implementation - simplified version"""

    # Provider metadata
    provider_id = "groq"
    display_name = "Groq Cloud"
    description = "Fast cloud-based transcription with Whisper models"
    api_endpoint = "https://api.groq.com/openai/v1/audio/transcriptions"
    default_base_url = "https://api.groq.com/openai/v1"

    # Available models
    AVAILABLE_MODELS = ["whisper-large-v3-turbo", "whisper-large-v3"]

    def __init__(
        self,
        api_key: str = "",
        model: str = "whisper-large-v3-turbo",
        base_url: Optional[str] = None,
        config_service=None,
    ):
        """Initialize Groq Speech Service

        Args:
            api_key: Groq API key (default: empty, must be set via initialize)
            model: Whisper model to use
            base_url: Optional custom base URL for Groq API
            config_service: Optional config service for streaming chunk duration
        """
        super().__init__(api_key, config_service)
        self.model = model
        self.model_name = model  # Alias for compatibility
        self.base_url = base_url if base_url else self.default_base_url
        self._available_models = self.AVAILABLE_MODELS.copy()

        # Keep model configurable even when provider adds new IDs before local defaults update
        if model and model not in self._available_models:
            app_logger.log_audio_event(
                "Groq model is not in built-in defaults",
                {"requested": model, "defaults": self._available_models},
            )
            self._available_models.append(model)
        elif not model:
            self.model = self.AVAILABLE_MODELS[0]
            self.model_name = self.model

    def prepare_request_data(self, **kwargs) -> Dict[str, Any]:
        """Prepare Groq-specific request data

        Args:
            **kwargs: Transcription parameters

        Returns:
            Groq API request parameters
        """
        request_data = {
            "model": self.model,
            "response_format": "verbose_json",
            "temperature": kwargs.get("temperature", 0.0),
        }

        # Add language if specified (not "auto")
        language = kwargs.get("language")
        if language and language != "auto":
            request_data["language"] = language

        return request_data

    def parse_response(self, response_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Groq API response into standard format

        Args:
            response_data: Raw Groq API response

        Returns:
            Standard transcription result format
        """
        text = response_data.get("text", "").strip()
        language = response_data.get("language", "unknown")

        # Convert segments to standard format
        segments = []
        if "segments" in response_data and response_data["segments"]:
            for seg in response_data["segments"]:
                # Handle both dict and object formats
                if isinstance(seg, dict):
                    segments.append(
                        {
                            "start": seg.get("start", 0.0),
                            "end": seg.get("end", 0.0),
                            "text": seg.get("text", ""),
                            "avg_logprob": seg.get("avg_logprob", 0.0),
                            "no_speech_prob": seg.get("no_speech_prob", 0.0),
                        }
                    )
                else:
                    # Object attribute access
                    segments.append(
                        {
                            "start": getattr(seg, "start", 0.0),
                            "end": getattr(seg, "end", 0.0),
                            "text": getattr(seg, "text", ""),
                            "avg_logprob": getattr(seg, "avg_logprob", 0.0),
                            "no_speech_prob": getattr(seg, "no_speech_prob", 0.0),
                        }
                    )

        # Calculate confidence from segments
        confidence = 0.5  # Default confidence
        if segments:
            avg_logprob = sum(seg.get("avg_logprob", 0.0) for seg in segments) / len(
                segments
            )
            confidence = max(0.0, min(1.0, (avg_logprob + 1.0) / 2.0))

        return {
            "text": text,
            "language": language,
            "confidence": confidence,
            "segments": segments,
        }

    def get_auth_headers(self) -> Dict[str, str]:
        """Get Groq-specific authentication headers

        Returns:
            Authentication headers dictionary
        """
        return {"Authorization": f"Bearer {self.api_key}"}

    def _models_endpoint(self) -> str:
        """Build models list endpoint from configured base URL."""
        return f"{self.base_url.rstrip('/')}/models"

    def fetch_available_models(self, timeout: int = 10) -> List[str]:
        """Fetch available speech-capable models from Groq models API.

        Args:
            timeout: HTTP timeout in seconds

        Returns:
            Updated model ID list. Falls back to in-memory list if no speech models are found.

        Raises:
            RuntimeError: Models API request/parsing failed
        """
        session = self._get_session()
        try:
            response = session.get(self._models_endpoint(), timeout=timeout)
            response.raise_for_status()
            payload = response.json()
        except Exception as e:
            raise RuntimeError(f"Failed to fetch Groq models: {e}") from e

        data = payload.get("data", [])
        if not isinstance(data, list):
            raise RuntimeError("Unexpected Groq models response format")

        model_ids = []
        for item in data:
            if isinstance(item, dict):
                model_id = item.get("id")
                if isinstance(model_id, str) and model_id.strip():
                    model_ids.append(model_id.strip())

        # Groq models endpoint contains mixed model families; keep speech list for STT UI.
        speech_models = sorted({m for m in model_ids if "whisper" in m.lower()})
        if speech_models:
            self._available_models = speech_models
            app_logger.log_audio_event(
                "Groq models refreshed",
                {"count": len(speech_models), "models": speech_models},
            )
            return speech_models

        app_logger.log_audio_event(
            "Groq models refresh returned no speech models, using fallback defaults",
            {"received_count": len(model_ids), "fallback": self._available_models},
        )
        return self._available_models.copy()

    def load_model(self, model_name: Optional[str] = None) -> bool:
        """Load model (for Groq, just validate configuration)

        Args:
            model_name: Model name to use

        Returns:
            True if successful
        """
        if model_name:
            if model_name not in self._available_models:
                app_logger.log_audio_event(
                    "Groq model requested outside current model list",
                    {"requested": model_name, "available": self._available_models},
                )
                self._available_models.append(model_name)
            self.model = model_name
            self.model_name = model_name

        # For cloud service, just mark as loaded
        self._is_model_loaded = True
        app_logger.log_audio_event(
            "Groq service marked as loaded",
            {"model": self.model, "endpoint": self.api_endpoint},
        )
        return True

    def get_available_models(self) -> List[str]:
        """Get list of available Groq models

        Returns:
            List of model names
        """
        return self._available_models.copy()

    def test_connection(self) -> Dict[str, Any]:
        """Test Groq API connection

        Returns:
            Connection test result
        """
        result = super().test_connection()
        result.update(
            {
                "details": {
                    "model": self.model,
                    "base_url": self.base_url or "default",
                    "endpoint": self.api_endpoint,
                }
            }
        )
        return result

    def initialize(self, config: Dict[str, Any]) -> None:
        """Initialize Groq service with configuration

        Args:
            config: Configuration dictionary

        Raises:
            ValueError: Invalid configuration
            RuntimeError: Initialization failed
        """
        # Extract configuration
        self.api_key = config.get("api_key", "")
        model = config.get("model", "whisper-large-v3-turbo")
        self.base_url = config.get("base_url", self.default_base_url)

        # Validate API key
        if not self.api_key or self.api_key.strip() == "":
            raise ValueError("Groq API key is required")

        if not model:
            raise ValueError("Groq model is required")

        self.model = model
        self.model_name = model
        if model not in self._available_models:
            self._available_models.append(model)

        # Mark as loaded
        self._is_model_loaded = True

        app_logger.log_model_loading_step(
            "Groq provider initialized",
            {
                "model": self.model,
                "base_url": self.base_url or "default",
            },
        )
