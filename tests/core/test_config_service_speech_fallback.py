from __future__ import annotations

from pathlib import Path

from sonicinput.core.services.config import ConfigKeys
from sonicinput.core.services.config.config_service import (
    ConfigService,
)
from sonicinput.speech.null_speech_service import NullSpeechService


def test_config_service_returns_null_when_cloud_key_missing(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    service = ConfigService(config_path=str(config_path))

    assert service.start() is True

    service.set_setting(ConfigKeys.TRANSCRIPTION_PROVIDER, "qwen", immediate=True)
    service.set_setting(ConfigKeys.TRANSCRIPTION_QWEN_API_KEY, "", immediate=True)

    speech_service = service._create_speech_service()

    assert isinstance(speech_service, NullSpeechService)
