"""Application identity and path constants."""


class AppInfo:
    """Application metadata constants."""

    NAME = "Sonic Input"
    VERSION = "0.7.4"
    DESCRIPTION = "AI-powered voice input software with speech recognition"
    AUTHOR = "Sonic Input Team"
    COPYRIGHT = "c 2024 Sonic Input"


class Paths:
    """Path and filename constants."""

    CONFIG_DIR_NAME = "SonicInput"
    CONFIG_FILE_NAME = "config.json"
    LOG_FILE_NAME = "app.log"

    BACKUP_DIR_NAME = "backups"

    TEMP_AUDIO_PREFIX = "voice_input_"
    TEMP_AUDIO_SUFFIX = ".wav"

    ICON_DIR = "resources/icons"
    THEMES_DIR = "resources/themes"
    MODELS_DIR = "models"


class Versions:
    """Version requirement constants."""

    CONFIG_VERSION = "1.0"
    MIN_WHISPER_VERSION = "20231117"
    MIN_PYTHON_VERSION = (3, 8)
    MIN_PYTORCH_VERSION = "2.0.0"
