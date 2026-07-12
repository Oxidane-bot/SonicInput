"""User-friendly error message translation utilities."""

import re
from typing import Optional

try:
    from PySide6.QtCore import QCoreApplication
except Exception:
    QCoreApplication = None  # type: ignore[assignment,misc]


def _tr(text: str) -> str:
    if QCoreApplication is None:
        return text
    return QCoreApplication.translate("ErrorMessages", text)


class ErrorMessageTranslator:
    """Translate technical errors into user-friendly messages."""

    ERROR_PATTERNS = {
        r"Invalid number of channels|channels.*not supported": {
            "user_msg": (
                "Audio device does not support the current configuration. "
                "Please choose another device in Settings."
            ),
            "category": "audio_device",
        },
        r"Input overflowed|Overflow": {
            "user_msg": "Audio input overflow. Please lower microphone volume or switch devices.",
            "category": "audio_overflow",
        },
        r"No Default Input Device Available|device not found": {
            "user_msg": (
                "No available microphone device found. "
                "Please check your microphone connection."
            ),
            "category": "audio_device",
        },
        r"Pa.*Error|portaudio": {
            "user_msg": "Audio system error. Please restart the app or check your audio device.",
            "category": "audio_system",
        },
        r"API key.*not set|api.*key.*invalid": {
            "user_msg": (
                "AI service API key is not set or invalid. "
                "Please configure it in Settings."
            ),
            "category": "api_key",
        },
        r"(401|Unauthorized)": {
            "user_msg": "API authentication failed. Please verify your API key.",
            "category": "api_auth",
        },
        r"(429|Too Many Requests|rate limit)": {
            "user_msg": "API rate limit reached. Please try again later or upgrade your plan.",
            "category": "api_rate_limit",
        },
        r"(500|502|503|504|Internal Server Error|Bad Gateway|Service Unavailable|Gateway Timeout)": {
            "user_msg": "AI service is temporarily unavailable. Please try again later.",
            "category": "api_server",
        },
        r"Connection.*refused|Connection.*timeout|Network.*error": {
            "user_msg": "Network connection failed. Please check your network and try again.",
            "category": "network",
        },
        r"model.*not found|No such file": {
            "user_msg": (
                "Speech recognition model not found. The app will download it automatically. "
                "Please wait."
            ),
            "category": "model_not_found",
        },
        r"CUDA.*out of memory|out of memory": {
            "user_msg": "GPU out of memory. Switching to CPU mode (slower).",
            "category": "gpu_memory",
        },
        r"CUDA.*not available|No CUDA": {
            "user_msg": "GPU not available. Using CPU mode for recognition (slower).",
            "category": "gpu_unavailable",
        },
        r"hotkey.*already registered|hotkey.*in use": {
            "user_msg": (
                "Hotkey is already used by another application. "
                "Please change it in Settings."
            ),
            "category": "hotkey_conflict",
        },
        r"Invalid hotkey|hotkey.*invalid": {
            "user_msg": "Invalid hotkey format. Please check your hotkey settings.",
            "category": "hotkey_invalid",
        },
        r"Permission denied|Access denied": {
            "user_msg": "Insufficient permissions. Please run the app as administrator.",
            "category": "permission",
        },
        r"config.*corrupt|JSON.*decode": {
            "user_msg": "Configuration file is corrupted. It has been reset to defaults.",
            "category": "config_corrupt",
        },
    }

    @classmethod
    def translate(cls, error: Exception, context: Optional[str] = None) -> dict:
        """Translate an error into user-friendly info."""
        error_str = str(error)
        error_type = type(error).__name__

        for pattern, info in cls.ERROR_PATTERNS.items():
            if re.search(pattern, error_str, re.IGNORECASE):
                return {
                    "user_message": _tr(info["user_msg"]),
                    "technical_message": f"{error_type}: {error_str}",
                    "category": info["category"],
                    "suggestions": cls._get_suggestions(info["category"], context),
                }

        return cls._get_generic_message(error, context)

    @classmethod
    def _get_generic_message(cls, error: Exception, context: Optional[str]) -> dict:
        error_type = type(error).__name__
        error_str = str(error)
        context_messages = {
            "recording": "An error occurred during recording.",
            "transcription": "An error occurred during transcription.",
            "ai_processing": "An error occurred during AI processing.",
            "input": "An error occurred during input.",
            "hotkey": "An error occurred during hotkey handling.",
        }
        user_message = context_messages.get(
            context or "", "An unknown error occurred during the operation."
        )
        return {
            "user_message": f"{_tr(user_message)} {_tr('Please try again later.')}",
            "technical_message": f"{error_type}: {error_str}",
            "category": "unknown",
            "suggestions": cls._get_suggestions("unknown", context),
        }

    @classmethod
    def _get_suggestions(cls, category: str, context: Optional[str]) -> list:
        suggestions_map = {
            "audio_device": [
                "Check the audio device connection.",
                "Try a different audio device.",
                "Restart the app.",
            ],
            "audio_overflow": [
                "Lower the microphone volume.",
                "Adjust the input device gain.",
                "Try another microphone device.",
            ],
            "audio_system": [
                "Restart the app.",
                "Check the audio device driver.",
                "Reconnect the audio device.",
            ],
            "api_key": [
                "Open AI Settings and configure the API key.",
                "Verify the API key is correct.",
                "Confirm the API key has not expired.",
            ],
            "api_auth": [
                "Verify the API key is correct.",
                "Confirm the API key has not expired.",
                "Regenerate the API key.",
            ],
            "api_rate_limit": [
                "Try again later.",
                "Upgrade your API plan.",
                "Reduce API call frequency.",
            ],
            "api_server": [
                "Try again later.",
                "Check the service status page.",
                "Switch to another API provider.",
            ],
            "network": [
                "Check your network connection.",
                "Switch to another network.",
                "Disable VPN and try again.",
            ],
            "model_not_found": [
                "Confirm the model files are downloaded.",
                "Re-download the model.",
                "Check the model path settings.",
            ],
            "gpu_memory": [
                "Close other GPU-intensive programs.",
                "Use a smaller model size (e.g., small/medium).",
                "Consider CPU mode.",
            ],
            "gpu_unavailable": [
                "Confirm CUDA drivers are installed correctly.",
                "Check whether the GPU is supported.",
                "Consider CPU mode.",
            ],
            "hotkey_conflict": [
                "Change the hotkey combination.",
                "Close the application using the hotkey.",
                "Restart the app.",
            ],
            "hotkey_invalid": [
                "Check the hotkey format (e.g., ctrl+shift+v).",
                "Ensure the hotkey includes modifier keys.",
                "Reconfigure the hotkey.",
            ],
            "permission": [
                "Run the app as administrator.",
                "Check security software settings.",
                "Ensure the app has required permissions.",
            ],
            "config_corrupt": [
                "Reconfigure application settings.",
                "Check config file permissions.",
                "Contact support.",
            ],
        }
        suggestions = suggestions_map.get(
            category,
            ["Please try again later.", "Contact support if the issue persists."],
        )
        return [_tr(item) for item in suggestions]


def get_user_friendly_error(error: Exception, context: Optional[str] = None) -> str:
    """Return the user-facing message for an exception."""
    return ErrorMessageTranslator.translate(error, context)["user_message"]
