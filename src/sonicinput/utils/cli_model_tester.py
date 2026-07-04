"""
Command-line model testing utility.

Provides functionality to test Whisper model transcription without GUI,
reusing the same test logic as the UI implementation.
"""

import time
from typing import Any, Callable, Dict, Optional, Union

import numpy as np

from sonicinput.core.interfaces import ISpeechService

# Note: Using print() instead of complex logger for CLI simplicity
# The UI version uses full logging integration


class CLIModelTester:
    """
    Command-line interface for testing Whisper model transcription.

    Replicates the functionality of the GUI ModelTestThread but designed
    for CLI usage with progress callbacks.
    """

    # Common hallucinations from low-amplitude audio
    COMMON_HALLUCINATIONS = [
        "thank you",
        "thanks for watching",
        "bye",
        "goodbye",
        "yes",
        "no",
        "okay",
        "yeah",
        "music",
        "applause",
        "laughter",
        "silence",
        "quiet",
        "pause",
        "thank you for watching",
        "thanks for your attention",
    ]

    def __init__(
        self,
        whisper_engine: ISpeechService,
        timeout_seconds: int = 120,
        sample_rate: int = 16000,
    ):
        """
        Initialize the CLI model tester.

        Args:
            whisper_engine: The Whisper speech service to test
            timeout_seconds: Maximum time to wait for transcription
            sample_rate: Audio sample rate (default: 16000 Hz)
        """
        self.whisper_engine = whisper_engine
        self.timeout_seconds = timeout_seconds
        self.sample_rate = sample_rate
        self._progress_callback: Optional[Callable[[str], None]] = None

    def register_progress_callback(self, callback: Callable[[str], None]) -> None:
        """
        Register a callback for progress updates.

        Args:
            callback: Function that takes a progress message string
        """
        self._progress_callback = callback

    def _report_progress(self, message: str) -> None:
        """Report progress to callback or logger."""
        if self._progress_callback:
            self._progress_callback(message)
        else:
            print(f"[TEST] {message}")

    def _generate_test_audio(
        self, duration: float = 2.0, amplitude: float = 0.001
    ) -> np.ndarray:
        """
        Generate test audio with very low amplitude.

        This simulates a silent/low-noise environment to test if the model
        produces hallucinations or correctly identifies silence.

        Args:
            duration: Audio duration in seconds (default: 2.0)
            amplitude: Standard deviation of normal distribution (default: 0.001)

        Returns:
            numpy array of float32 audio samples
        """
        audio_length = int(duration * self.sample_rate)
        test_audio = np.random.normal(0, amplitude, audio_length).astype(np.float32)
        return test_audio

    def _is_likely_hallucination(self, text: str) -> bool:
        """
        Check if transcription text is likely a hallucination.

        Whisper sometimes generates common phrases when presented with
        silence or low-amplitude audio.

        Args:
            text: Transcribed text to check

        Returns:
            True if text matches common hallucination patterns
        """
        clean_text = text.lower().strip()

        for hallucination in self.COMMON_HALLUCINATIONS:
            if hallucination in clean_text:
                return True

        return False

    def run_test(self, auto_load_model: bool = False) -> Dict[str, Any]:
        """
        Run the complete model test.

        Args:
            auto_load_model: If True, load model before testing

        Returns:
            Dictionary with test results:
            {
                "success": bool,
                "text": str,
                "language": str,
                "confidence": float,
                "is_hallucination": bool,
                "transcription_time": float,
                "error": Optional[str]
            }
        """
        result = {
            "success": False,
            "text": "",
            "language": "",
            "confidence": 0.0,
            "is_hallucination": False,
            "transcription_time": 0.0,
            "error": None,
        }

        try:
            # Check if model is loaded
            if not self.whisper_engine.is_model_loaded:
                if auto_load_model:
                    self._report_progress("Model not loaded. Loading model...")
                    self.whisper_engine.load_model()
                    self._report_progress("Model loaded successfully")
                else:
                    error_msg = "Model is not loaded. Use --auto-load-model to load it."
                    self._report_progress(f"ERROR: {error_msg}")
                    result["error"] = error_msg
                    return result

            # Generate test audio
            self._report_progress("Generating test audio (2 seconds, low noise)...")
            test_audio = self._generate_test_audio(duration=2.0, amplitude=0.001)

            # Run transcription
            self._report_progress("Running transcription...")
            start_time = time.time()

            try:
                transcription_result: Union[Dict[str, Any], str] = (
                    self.whisper_engine.transcribe(
                        test_audio,
                        language=None,  # Auto-detect
                    )
                )
            except Exception as e:
                # Handle case where transcribe returns string instead of dict
                transcription_result = str(e)

            transcription_time = time.time() - start_time

            # Extract results - handle both dict and string cases
            if isinstance(transcription_result, dict):
                text = transcription_result.get("text", "").strip()
                language = transcription_result.get("language", "unknown")
                confidence = transcription_result.get("confidence", 0.0)
            else:
                # Handle case where we get a string instead of dict
                text = str(transcription_result).strip()
                language = "unknown"
                confidence = 0.0

            # Check for hallucinations
            is_hallucination = self._is_likely_hallucination(text)

            # Build result
            result.update(
                {
                    "success": True,
                    "text": text,
                    "language": language,
                    "confidence": confidence,
                    "is_hallucination": is_hallucination,
                    "transcription_time": transcription_time,
                }
            )

            self._report_progress("Test completed successfully")

        except Exception as e:
            error_msg = str(e)
            self._report_progress(f"ERROR: {error_msg}")
            result["error"] = error_msg
            import traceback

            traceback.print_exc()

        return result

    def format_results(self, result: Dict[str, Any]) -> str:
        """
        Format test results for console output.

        Args:
            result: Test result dictionary from run_test()

        Returns:
            Formatted string for display
        """
        if not result["success"]:
            return f"""
{"=" * 60}
MODEL TEST FAILED
{"=" * 60}
Error: {result.get("error", "Unknown error")}
{"=" * 60}
"""

        # Determine result interpretation
        if result["is_hallucination"]:
            interpretation = "WARNING: Possible hallucination detected"
            status = "[!] NEEDS REVIEW"
        elif not result["text"]:
            interpretation = "Model correctly identified silence/low noise"
            status = "[OK] PASS"
        else:
            interpretation = "Model produced unexpected output for low-noise audio"
            status = "[!] UNEXPECTED"

        # Clean text to remove Unicode characters for Windows console
        safe_text = (
            result["text"].encode("ascii", errors="ignore").decode("ascii")
            if result["text"]
            else ""
        )

        return f"""
{"=" * 60}
MODEL TEST RESULTS
{"=" * 60}
Status: {status}

Transcription:
  Text: "{safe_text}" {" (empty)" if not safe_text else ""}
  Language: {result["language"]}
  Confidence: {result["confidence"]:.2%}

Performance:
  Transcription Time: {result["transcription_time"]:.2f}s
  RTF (Real-Time Factor): {result["transcription_time"] / 2.0:.2f}x

Analysis:
  Is Hallucination: {result["is_hallucination"]}
  Interpretation: {interpretation}

{"=" * 60}
"""
