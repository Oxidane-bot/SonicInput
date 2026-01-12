"""Validation-related constants."""


class Limits:
    """Validation limits."""

    MIN_SAMPLE_RATE = 8000
    MAX_SAMPLE_RATE = 48000
    MIN_CHUNK_SIZE = 256
    MAX_CHUNK_SIZE = 8192

    MIN_TIMEOUT = 5
    MAX_TIMEOUT = 120
    MIN_RETRIES = 1
    MAX_RETRIES = 10

    MIN_WINDOW_WIDTH = 300
    MIN_WINDOW_HEIGHT = 200
    MAX_OVERLAY_SIZE = 1000

    MAX_TRANSCRIPTION_LENGTH = 10000
    MAX_ERROR_MESSAGE_LENGTH = 500

    MAX_LOG_SIZE_MB = 100


class Patterns:
    """Validation patterns."""

    HOTKEY_PATTERN = r"^(ctrl\+)?(shift\+)?(alt\+)?\w+$"
    OPENROUTER_API_KEY_PATTERN = r"^sk-[a-zA-Z0-9]{32,}$"
    SAFE_FILENAME_PATTERN = r"^[a-zA-Z0-9_\-\.]+$"
    LANGUAGE_CODE_PATTERN = r"^[a-z]{2}(-[A-Z]{2})?$"
