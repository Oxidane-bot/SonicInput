"""Sonic Input - Windows语音输入软件

一个基于Whisper和AI优化的Windows语音转文本输入解决方案
"""

from typing import TYPE_CHECKING, Any

__version__ = "0.8.4"
__author__ = "Oxidane-bot"
__description__ = "SonicInput"

if TYPE_CHECKING:
    from .core.voice_input_app import VoiceInputApp as VoiceInputApp
    from .utils import app_logger as app_logger

__all__ = ["VoiceInputApp", "app_logger"]


def __getattr__(name: str) -> Any:
    """Load heavyweight compatibility exports only when requested."""
    if name == "VoiceInputApp":
        from .core.voice_input_app import VoiceInputApp

        globals()[name] = VoiceInputApp
        return VoiceInputApp
    if name == "app_logger":
        from .utils import app_logger

        globals()[name] = app_logger
        return app_logger
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
