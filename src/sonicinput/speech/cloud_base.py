"""Cloud Transcription Base Class

Unified base class for all cloud-based transcription services.
Provides common HTTP request handling, audio conversion, and retry logic.
"""

import io
import threading
import time
import wave
from typing import Any, Dict, Optional

import numpy as np
import requests

from ..core.interfaces import ISpeechService
from ..utils import app_logger


class CloudTranscriptionBase(ISpeechService):
    """Base class for cloud transcription services

    Provides unified HTTP request handling, audio conversion,
    retry logic, and common functionality for all cloud providers.
    """

    # Provider metadata - to be overridden by subclasses
    provider_id: str = ""
    display_name: str = ""
    description: str = ""
    api_endpoint: str = ""

    def __init__(self, api_key: str = "", config_service=None):
        """Initialize cloud transcription service

        Args:
            api_key: API key for the service (can be set later via initialize)
            config_service: Optional config service for streaming chunk duration
        """
        self.api_key = api_key
        self._is_model_loaded = False
        self.device = "cloud"
        self.use_gpu = False
        self._config_service = config_service

        # HTTP session with connection pooling
        self._session: Optional[requests.Session] = None
        self._session_lock = threading.RLock()

        # Performance tracking
        self._request_count = 0
        self._total_request_time = 0.0
        self._error_count = 0

        # Cloud chunk accumulator for streaming mode
        self._chunk_accumulator: Optional[Any] = None  # CloudChunkAccumulator instance

    # ========== Abstract Methods (must be implemented by subclasses) ==========

    def prepare_request_data(self, **kwargs) -> Dict[str, Any]:
        """Prepare API-specific request data

        Args:
            **kwargs: Transcription parameters (language, temperature, etc.)

        Returns:
            Dictionary with API-specific request parameters
        """
        raise NotImplementedError("Subclasses must implement prepare_request_data")

    def parse_response(self, response_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse API response into standard format

        Args:
            response_data: Raw API response data

        Returns:
            Standard transcription result format
        """
        raise NotImplementedError("Subclasses must implement parse_response")

    def get_auth_headers(self) -> Dict[str, str]:
        """Get API authentication headers

        Returns:
            Dictionary with authentication headers
        """
        return {"Authorization": f"Bearer {self.api_key}"}

    # ========== Common HTTP and Audio Processing ==========

    def _get_session(self) -> requests.Session:
        """Get or create HTTP session with connection pooling"""
        with self._session_lock:
            if self._session is None:
                self._session = requests.Session()
                self._session.headers.update(
                    {"User-Agent": "SonicInput/1.4", **self.get_auth_headers()}
                )
            return self._session

    def _numpy_to_wav_bytes(
        self, audio_data: np.ndarray, sample_rate: int = 16000
    ) -> bytes:
        """Convert numpy audio data to WAV bytes

        Args:
            audio_data: Audio data as numpy array
            sample_rate: Sample rate in Hz

        Returns:
            WAV file as bytes
        """
        # Ensure audio is in correct format
        if audio_data.dtype != np.float32:
            audio_data = audio_data.astype(np.float32)

        # Convert to 16-bit integers
        audio_int16 = (audio_data * 32767).astype(np.int16)

        # Create WAV file in memory
        with io.BytesIO() as wav_buffer:
            with wave.open(wav_buffer, "wb") as wav_file:
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(audio_int16.tobytes())

            return wav_buffer.getvalue()

    def _make_request_with_retry(
        self,
        files: Dict[str, Any],
        data: Dict[str, Any],
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """Make HTTP request with exponential backoff retry

        Args:
            files: Files to upload
            data: Form data
            max_retries: Maximum number of retries
            retry_delay: Initial retry delay in seconds
            timeout: Request timeout in seconds

        Returns:
            Parsed response data or error information
        """
        session = self._get_session()
        last_error = None
        retry_count = 0

        while retry_count <= max_retries:
            try:
                app_logger.log_audio_event(
                    "Sending cloud transcription request",
                    {
                        "provider": self.provider_id,
                        "url": self.api_endpoint,
                        "retry_count": retry_count,
                        "timeout": timeout,
                    },
                )

                response = session.post(
                    self.api_endpoint,
                    data=data,
                    files=files,
                    timeout=timeout,
                )

                # Update statistics
                self._request_count += 1

                # Handle successful response
                if response.status_code == 200:
                    app_logger.log_audio_event(
                        "Cloud transcription successful",
                        {
                            "provider": self.provider_id,
                            "status_code": response.status_code,
                            "retry_count": retry_count,
                        },
                    )
                    return response.json()

                # Handle error response
                self._error_count += 1
                error_data = self._handle_api_error(response)

                # Check if we should retry
                if self._should_retry(response.status_code, retry_count, max_retries):
                    retry_count += 1
                    wait_time = retry_delay * (2 ** (retry_count - 1))

                    app_logger.log_audio_event(
                        "Retrying cloud transcription",
                        {
                            "provider": self.provider_id,
                            "status_code": response.status_code,
                            "retry_count": retry_count,
                            "max_retries": max_retries,
                            "wait_time": wait_time,
                            "error": last_error,
                        },
                    )

                    time.sleep(wait_time)
                    continue
                else:
                    return error_data

            except requests.exceptions.Timeout as e:
                last_error = f"Request timeout ({timeout}s): {str(e)}"
                self._error_count += 1

                if retry_count < max_retries:
                    retry_count += 1
                    wait_time = retry_delay * (2 ** (retry_count - 1))
                    time.sleep(wait_time)
                    continue
                else:
                    return {
                        "error": last_error,
                        "error_code": "TIMEOUT",
                        "provider": self.provider_id,
                        "retry_count": retry_count,
                    }

            except requests.exceptions.ConnectionError as e:
                last_error = f"Connection error: {str(e)}"
                self._error_count += 1

                if retry_count < max_retries:
                    retry_count += 1
                    wait_time = retry_delay * (2 ** (retry_count - 1))
                    time.sleep(wait_time)
                    continue
                else:
                    return {
                        "error": last_error,
                        "error_code": "CONNECTION_ERROR",
                        "provider": self.provider_id,
                        "retry_count": retry_count,
                    }

            except Exception as e:
                last_error = f"Unexpected error: {str(e)}"
                app_logger.log_error(e, f"{self.provider_id}_transcribe")
                break

        # All retries failed
        return {
            "error": last_error or "Unknown error",
            "error_code": "MAX_RETRIES_EXCEEDED",
            "provider": self.provider_id,
            "retry_count": retry_count,
        }

    def _handle_api_error(self, response: requests.Response) -> Dict[str, Any]:
        """Handle API error response

        Args:
            response: HTTP response object

        Returns:
            Error result dictionary
        """
        try:
            error_data = response.json()
            error_message = error_data.get("error", {}).get("message", "Unknown error")
        except Exception as e:
            app_logger.log_error(
                e,
                "cloud_error_response_parse_failed",
                {
                    "context": "Failed to parse error response JSON, using raw text",
                    "status_code": response.status_code,
                },
            )
            error_message = f"HTTP {response.status_code}: {response.text}"

        return {
            "error": error_message,
            "error_code": response.status_code,
            "provider": self.provider_id,
        }

    def _should_retry(
        self, status_code: int, retry_count: int, max_retries: int
    ) -> bool:
        """Determine if request should be retried

        Args:
            status_code: HTTP status code
            retry_count: Current retry count
            max_retries: Maximum retries allowed

        Returns:
            Whether to retry the request
        """
        if retry_count >= max_retries:
            return False

        # Retry on server errors (5xx)
        if 500 <= status_code <= 599:
            return True

        # Retry on rate limiting (429)
        if status_code == 429:
            return True

        # Retry on timeout (408)
        if status_code == 408:
            return True

        # Don't retry on client errors (4xx except 429)
        return False

    # ========== ISpeechService Implementation ==========

    def transcribe(
        self,
        audio_data: np.ndarray,
        language: Optional[str] = None,
        temperature: float = 0.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        **kwargs,
    ) -> Dict[str, Any]:
        """Transcribe audio data using cloud API

        Args:
            audio_data: Audio data as numpy array (16kHz, mono)
            language: Language code (optional for auto-detection)
            temperature: Sampling temperature (0.0-1.0)
            max_retries: Maximum retry attempts
            retry_delay: Initial retry delay in seconds
            **kwargs: Additional provider-specific parameters

        Returns:
            Transcription result with text, language, confidence, etc.
        """
        start_time = time.time()

        # Validate input
        if audio_data is None or len(audio_data) == 0:
            return {
                "text": "",
                "error": "Empty audio data",
                "provider": self.provider_id,
            }

        # Convert audio to WAV format
        wav_bytes = self._numpy_to_wav_bytes(audio_data)

        # Prepare request data
        request_data = self.prepare_request_data(
            language=language, temperature=temperature, **kwargs
        )

        # Prepare files for upload
        files = {"file": ("audio.wav", wav_bytes, "audio/wav")}

        # Make request with retry logic
        result = self._make_request_with_retry(
            files=files,
            data=request_data,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )

        # Calculate timing
        processing_time = time.time() - start_time
        audio_duration = len(audio_data) / 16000.0

        # Update statistics
        self._total_request_time += processing_time

        # Parse and format response
        if "error" not in result:
            try:
                parsed_result = self.parse_response(result)
                parsed_result.update(
                    {
                        "processing_time": processing_time,
                        "duration": audio_duration,
                        "real_time_factor": processing_time / audio_duration
                        if audio_duration > 0
                        else 0,
                        "provider": self.provider_id,
                    }
                )

                app_logger.log_transcription(
                    audio_length=audio_duration,
                    text=parsed_result.get("text", ""),
                    confidence=parsed_result.get("confidence", 0.0),
                )

                return parsed_result

            except Exception as e:
                app_logger.log_error(e, f"{self.provider_id}_parse_response")
                return {
                    "text": "",
                    "error": f"Response parsing failed: {str(e)}",
                    "processing_time": processing_time,
                    "duration": audio_duration,
                    "provider": self.provider_id,
                }
        else:
            # Error occurred during request
            result.update(
                {
                    "processing_time": processing_time,
                    "duration": audio_duration,
                    "real_time_factor": processing_time / audio_duration
                    if audio_duration > 0
                    else 0,
                }
            )
            return result

    def load_model(self, model_name: Optional[str] = None) -> bool:
        """Load model (for cloud services, just mark as loaded)

        Args:
            model_name: Model name (not used for cloud services)

        Returns:
            True if successful
        """
        self._is_model_loaded = True
        app_logger.log_audio_event(
            "Cloud service marked as loaded",
            {
                "provider": self.provider_id,
                "note": "API will be validated on first request",
            },
        )
        return True

    def unload_model(self) -> None:
        """Unload model (cleanup session)

        For cloud services, this means cleaning up the HTTP session.
        """
        with self._session_lock:
            if self._session:
                self._session.close()
                self._session = None

        self._is_model_loaded = False
        app_logger.log_audio_event(
            "Cloud service unloaded",
            {"provider": self.provider_id},
        )

    @property
    def is_model_loaded(self) -> bool:
        """Check if model/service is ready

        For cloud services, this checks if API key is set.
        """
        return self._is_model_loaded

    def test_connection(self) -> Dict[str, Any]:
        """Test API connection with minimal request

        Returns:
            Connection test result
        """
        if not self.api_key or self.api_key.strip() == "":
            return {
                "success": False,
                "message": "API key not configured",
                "provider": self.provider_id,
            }

        try:
            # Generate minimal test audio (0.1 second silence)
            test_audio = np.zeros(1600, dtype=np.float32)

            # Try transcription with minimal retries
            result = self.transcribe(
                test_audio,
                language=None,
                temperature=0.0,
                max_retries=1,
                retry_delay=1.0,
            )

            if "error" in result and result["error"]:
                return {
                    "success": False,
                    "message": f"API test failed: {result['error']}",
                    "provider": self.provider_id,
                    "error_code": result.get("error_code"),
                }

            return {
                "success": True,
                "message": "Connection successful",
                "provider": self.provider_id,
                "details": {
                    "model": getattr(self, "model_name", "default"),
                    "endpoint": self.api_endpoint,
                },
            }

        except Exception as e:
            app_logger.log_error(e, f"{self.provider_id}_test_connection")
            return {
                "success": False,
                "message": f"Connection test error: {str(e)}",
                "provider": self.provider_id,
            }

    def get_statistics(self) -> Dict[str, Any]:
        """Get usage statistics

        Returns:
            Statistics dictionary
        """
        avg_request_time = (
            self._total_request_time / self._request_count
            if self._request_count > 0
            else 0
        )

        return {
            "request_count": self._request_count,
            "error_count": self._error_count,
            "average_request_time": avg_request_time,
            "total_request_time": self._total_request_time,
            "success_rate": (self._request_count - self._error_count)
            / self._request_count
            if self._request_count > 0
            else 0,
            "provider": self.provider_id,
        }

    def transcribe_sync(
        self,
        audio_data: np.ndarray,
        language: Optional[str] = None,
        temperature: float = 0.0,
        emit_event: bool = False,
    ) -> Dict[str, Any]:
        """Synchronous transcription (alias for transcribe for API compatibility)

        This method provides compatibility with TranscriptionService API.
        Cloud providers don't use emit_event parameter as they handle transcription directly.

        Args:
            audio_data: Audio data as numpy array
            language: Language code (optional)
            temperature: Sampling temperature (0.0-1.0)
            emit_event: Ignored for cloud providers (kept for API compatibility)

        Returns:
            Transcription result dictionary
        """
        return self.transcribe(
            audio_data=audio_data,
            language=language,
            temperature=temperature,
        )

    # ========== Streaming API (cloud chunked streaming support) ==========

    def start_streaming(self) -> None:
        """Start cloud streaming mode (chunked accumulation).

        Creates a CloudChunkAccumulator instance to buffer and transcribe audio chunks
        asynchronously during recording. This avoids API rate limits on long recordings
        by distributing transcription requests over time.

        The chunk duration is read from config (audio.streaming.chunk_duration, default 15s).
        Each chunk is transcribed independently in a thread pool, with results combined
        when stop_streaming() is called.
        """
        from .cloud_chunk_accumulator import CloudChunkAccumulator

        # Get chunk duration from config (default 15 seconds)
        chunk_duration = 15.0
        if self._config_service:
            # Read from nested config: audio.streaming.chunk_duration
            chunk_duration = self._config_service.get_setting(
                "audio.streaming.chunk_duration", 15.0
            )

        self._chunk_accumulator = CloudChunkAccumulator(
            speech_service=self,
            chunk_duration=chunk_duration,
            sample_rate=16000,
        )

        app_logger.log_audio_event(
            "Cloud provider streaming started (chunked mode)",
            {
                "provider": self.provider_id,
                "chunk_duration": chunk_duration,
            },
        )

    def stop_streaming(self) -> Dict[str, Any]:
        """Stop streaming and get combined results from all chunks.

        Waits for all pending chunk transcriptions to complete (with 30s timeout per chunk),
        combines the results in order by chunk ID, and cleans up the accumulator.

        Returns:
            Dictionary with keys:
                - text: Combined transcription text from all successful chunks
                - stats: Statistics including total_chunks, successful_chunks,
                        failed_chunks, failed_chunk_ids, streaming_mode, provider
        """
        if not self._chunk_accumulator:
            return {
                "text": "",
                "stats": {
                    "total_chunks": 0,
                    "streaming_mode": "disabled",
                    "provider": self.provider_id,
                },
            }

        # Get results from accumulator
        result = self._chunk_accumulator.get_results(timeout=30.0)

        # Cleanup
        self._chunk_accumulator.shutdown()
        self._chunk_accumulator = None

        app_logger.log_audio_event(
            "Cloud provider streaming stopped",
            {
                "provider": self.provider_id,
                "text_length": len(result.get("text", "")),
                "stats": result.get("stats", {}),
            },
        )

        return result

    def add_streaming_chunk(self, audio_chunk: np.ndarray) -> Optional[str]:
        """Add streaming audio chunk to accumulator.

        Forwards the audio chunk to CloudChunkAccumulator, which immediately triggers
        asynchronous transcription. This is called periodically (every ~15s) during
        recording to send audio chunks to the API.

        Args:
            audio_chunk: Audio chunk data as numpy array (typically 15s of audio)

        Returns:
            None (chunk is transcribed asynchronously, results collected in stop_streaming())
        """
        if not self._chunk_accumulator:
            app_logger.log_audio_event(
                "Cloud streaming not started, ignoring chunk",
                {
                    "provider": self.provider_id,
                    "chunk_length": len(audio_chunk),
                },
            )
            return None

        self._chunk_accumulator.add_audio(audio_chunk)
        return None  # Results returned in stop_streaming()

    def __del__(self):
        """Cleanup on destruction"""
        try:
            self.unload_model()
        except Exception:
            pass  # Ignore errors during cleanup
