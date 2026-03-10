"""
Cloud Chunk Accumulator - Buffer and transcribe audio chunks for cloud providers.

This module implements chunked streaming transcription for cloud providers (Groq, SiliconFlow, Qwen)
to avoid rate limits on long recordings by sending audio in periodic chunks during recording.
"""

import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import TYPE_CHECKING, Any, Dict, List, Tuple

import numpy as np

from ..utils.logger import app_logger

if TYPE_CHECKING:
    from ..core.interfaces.speech import ISpeechService


class CloudChunkAccumulator:
    """
    Accumulate audio chunks and trigger cloud transcription at intervals.

    This class buffers incoming audio data and triggers asynchronous transcription
    when the buffer duration reaches the configured chunk duration threshold.
    Results from all chunks are combined in order when requested.
    """

    def __init__(
        self,
        speech_service: "ISpeechService",
        chunk_duration: float = 15.0,
        sample_rate: int = 16000,
    ):
        """
        Initialize the cloud chunk accumulator.

        Args:
            speech_service: The speech service to use for transcription
            chunk_duration: Duration in seconds for each chunk (default: 15.0)
            sample_rate: Audio sample rate in Hz (default: 16000)
        """
        self._speech_service = speech_service
        self._chunk_duration = chunk_duration
        self._sample_rate = sample_rate

        # Buffering state
        self._buffer: List[np.ndarray] = []
        self._buffer_duration = 0.0

        # Chunk tracking: (chunk_id, future, audio_length)
        self._chunks: List[Tuple[int, Future, int]] = []
        self._chunk_counter = 0

        # Thread pool for async transcription (max 3 concurrent chunks)
        self._executor = ThreadPoolExecutor(max_workers=3)

        app_logger.log_audio_event(
            "CloudChunkAccumulator initialized",
            {
                "chunk_duration": chunk_duration,
                "sample_rate": sample_rate,
                "max_workers": 3,
            },
        )

    def add_audio(self, audio_data: np.ndarray) -> None:
        """
        Add audio data and immediately trigger transcription.

        Since AudioRecorder already handles chunking at the configured interval,
        we flush each chunk immediately instead of accumulating.

        Args:
            audio_data: Audio samples as numpy array (already chunked by AudioRecorder)
        """
        # Add to buffer
        self._buffer.append(audio_data)
        self._buffer_duration += len(audio_data) / self._sample_rate

        # Immediately flush this chunk for transcription
        # (AudioRecorder already handles the chunking interval)
        self._flush_chunk()

    def _flush_chunk(self) -> None:
        """
        Flush current buffer as a chunk and start async transcription.

        Combines buffered audio into a single chunk, assigns a chunk ID,
        and submits to thread pool for asynchronous transcription.
        """
        if not self._buffer:
            return

        # Combine buffer into single chunk
        chunk_audio = np.concatenate(self._buffer)
        chunk_id = self._chunk_counter
        self._chunk_counter += 1

        app_logger.log_audio_event(
            "Flushing audio chunk for transcription",
            {
                "chunk_id": chunk_id,
                "duration": self._buffer_duration,
                "samples": len(chunk_audio),
            },
        )

        # Submit async transcription and store audio length for dynamic timeout
        future = self._executor.submit(self._transcribe_chunk, chunk_id, chunk_audio)
        self._chunks.append((chunk_id, future, len(chunk_audio)))

        # Reset buffer
        self._buffer = []
        self._buffer_duration = 0.0

    def _transcribe_chunk(
        self, chunk_id: int, audio_data: np.ndarray
    ) -> Tuple[int, str]:
        """
        Transcribe a single chunk (runs in thread pool).

        Implements retry logic with exponential backoff for transient failures.

        Args:
            chunk_id: Unique identifier for this chunk
            audio_data: Audio samples to transcribe

        Returns:
            Tuple of (chunk_id, transcribed_text)

        Raises:
            Exception: If all retry attempts fail
        """
        max_retries = 3
        retry_delay = 1.0  # Initial delay in seconds

        for attempt in range(max_retries):
            try:
                result = self._speech_service.transcribe(audio_data)
                if not isinstance(result, dict):
                    raise RuntimeError(
                        f"Unexpected transcription result type: {type(result).__name__}"
                    )

                # Cloud speech services return {"error": "..."} on failures.
                # Treating that as empty text would silently hide backend failures.
                if result.get("error"):
                    error_code = result.get("error_code", "unknown")
                    raise RuntimeError(
                        f"Cloud transcription error ({error_code}): {result.get('error')}"
                    )

                text = result.get("text", "")
                if text is None:
                    text = ""
                elif not isinstance(text, str):
                    text = str(text)

                app_logger.log_audio_event(
                    "Cloud chunk transcription completed",
                    {
                        "chunk_id": chunk_id,
                        "attempt": attempt + 1,
                        "text_length": len(text),
                        "text_preview": text[:50] if text else "",
                    },
                )
                return (chunk_id, text)

            except Exception as e:
                is_last_attempt = attempt == max_retries - 1

                if is_last_attempt:
                    app_logger.log_error(
                        e,
                        f"cloud_chunk_transcription_{chunk_id}_failed_all_retries",
                    )
                    raise
                else:
                    wait_time = retry_delay * (2**attempt)
                    app_logger.log_audio_event(
                        "Cloud chunk transcription failed, retrying",
                        {
                            "chunk_id": chunk_id,
                            "attempt": attempt + 1,
                            "max_retries": max_retries,
                            "wait_time": wait_time,
                            "error": str(e),
                        },
                    )
                    time.sleep(wait_time)

        # Should never reach here due to raise in last attempt
        return (chunk_id, "")

    def get_results(self, timeout: float = 30.0) -> Dict[str, Any]:
        """
        Wait for all chunks to complete and combine results.

        Flushes any remaining buffered audio, waits for all chunk transcriptions
        to complete (with dynamic timeout per chunk), and combines the results in order.

        Args:
            timeout: Minimum wait time in seconds (actual timeout is dynamic based on audio length)

        Returns:
            Dictionary with keys:
                - text: Combined transcription text from all successful chunks
                - stats: Statistics about chunk processing
        """
        # Flush any remaining audio
        self._flush_chunk()

        # Wait for all futures and collect results with dynamic timeout per chunk
        results: List[Tuple[int, str]] = []
        failed_chunks: List[int] = []
        timed_out_chunks: List[int] = []
        started_at = time.monotonic()
        future_to_meta: Dict[Future, Tuple[int, float, float]] = {}
        deadlines: Dict[Future, float] = {}

        for chunk_id, future, audio_length in self._chunks:
            audio_duration = (
                audio_length / self._sample_rate if audio_length > 0 else 0.0
            )
            per_chunk_timeout = max(timeout, audio_duration * 2.0)
            future_to_meta[future] = (chunk_id, audio_duration, per_chunk_timeout)
            deadlines[future] = started_at + per_chunk_timeout

        pending = set(future_to_meta.keys())
        while pending:
            now = time.monotonic()

            expired_futures = [future for future in pending if now >= deadlines[future]]
            for future in expired_futures:
                pending.remove(future)
                chunk_id, audio_duration, per_chunk_timeout = future_to_meta[future]
                timed_out_chunks.append(chunk_id)
                failed_chunks.append(chunk_id)
                app_logger.log_audio_event(
                    "Cloud chunk transcription timeout",
                    {
                        "chunk_id": chunk_id,
                        "timeout": per_chunk_timeout,
                        "audio_duration": audio_duration,
                    },
                )

            if not pending:
                break

            wait_timeout = min(
                max(deadlines[future] - time.monotonic(), 0.0) for future in pending
            )
            done, _ = wait(pending, timeout=wait_timeout, return_when=FIRST_COMPLETED)

            if not done:
                continue

            for future in done:
                pending.remove(future)
                chunk_id, _, _ = future_to_meta[future]
                try:
                    chunk_result = future.result()
                    results.append(chunk_result)
                except Exception as e:
                    app_logger.log_error(
                        e,
                        f"cloud_chunk_{chunk_id}_transcription_failed",
                    )
                    failed_chunks.append(chunk_id)

        if timed_out_chunks:
            app_logger.log_audio_event(
                "Cloud chunks timed out",
                {"chunk_ids": timed_out_chunks},
            )

        # Sort by chunk_id and combine text
        results.sort(key=lambda x: x[0])
        text_parts = []
        for _, text in results:
            if not isinstance(text, str):
                continue
            cleaned = text.strip()
            if cleaned:
                text_parts.append(cleaned)
        combined_text = " ".join(text_parts)

        stats = {
            "total_chunks": self._chunk_counter,
            "successful_chunks": len(results),
            "failed_chunks": len(failed_chunks),
            "failed_chunk_ids": failed_chunks,
            "non_empty_chunks": len(text_parts),
            "empty_chunks": len(results) - len(text_parts),
            "streaming_mode": "chunked",
        }

        app_logger.log_audio_event(
            "Cloud chunk accumulator results combined",
            {
                "total_chunks": stats["total_chunks"],
                "successful": stats["successful_chunks"],
                "failed": stats["failed_chunks"],
                "non_empty_chunks": stats["non_empty_chunks"],
                "empty_chunks": stats["empty_chunks"],
                "text_length": len(combined_text),
            },
        )

        return {"text": combined_text, "stats": stats}

    def shutdown(self) -> None:
        """
        Shutdown the thread pool executor.

        Should be called when the accumulator is no longer needed to clean up resources.
        """
        self._executor.shutdown(wait=True)
        app_logger.log_audio_event("CloudChunkAccumulator shutdown", {})
