from __future__ import annotations

import copy
from pathlib import Path

import pytest

from sonicinput.core.services.config import ConfigKeys
from sonicinput.core.services.config.config_service_refactored import (
    RefactoredConfigService,
)
from sonicinput.speech.null_speech_service import NullSpeechService
from sonicinput.utils.exceptions import ConfigurationError


def test_config_service_returns_null_when_cloud_key_missing(tmp_path: Path) -> None:
    """配置文件里残留 cloud provider 但 key 为空时（用户手改/迁移残留），
    _create_speech_service 应 fallback 到 NullSpeechService，而不是崩溃。
    """
    config_path = tmp_path / "config.json"
    service = RefactoredConfigService(config_path=str(config_path))

    assert service.start() is True

    # 绕过 set_setting 的校验，直接写入 writer 来还原"损坏配置"场景
    service._writer.set_setting(ConfigKeys.TRANSCRIPTION_PROVIDER, "qwen")
    service._writer.set_setting(ConfigKeys.TRANSCRIPTION_QWEN_API_KEY, "")
    service._reader._config = copy.deepcopy(service._writer._config)

    speech_service = service._create_speech_service()

    assert isinstance(speech_service, NullSpeechService)


def test_set_setting_rejects_cloud_provider_without_key(tmp_path: Path) -> None:
    """通过 set_setting 切到没有 key 的 cloud provider 时必须报错。"""
    config_path = tmp_path / "config.json"
    service = RefactoredConfigService(config_path=str(config_path))
    assert service.start() is True

    with pytest.raises(ConfigurationError, match="Groq provider requires an API key"):
        service.set_setting(ConfigKeys.TRANSCRIPTION_PROVIDER, "groq", immediate=True)


def test_set_settings_batch_accepts_provider_with_paired_key(tmp_path: Path) -> None:
    """同一批次同时设置 provider 和 api_key 时应通过校验。"""
    config_path = tmp_path / "config.json"
    service = RefactoredConfigService(config_path=str(config_path))
    assert service.start() is True

    service.set_settings_batch(
        {
            ConfigKeys.TRANSCRIPTION_PROVIDER: "groq",
            ConfigKeys.TRANSCRIPTION_GROQ_API_KEY: "gsk_test_key",
        },
        immediate=False,
    )

    assert service.get_setting(ConfigKeys.TRANSCRIPTION_PROVIDER) == "groq"


def test_set_settings_batch_rejects_provider_with_empty_paired_key(
    tmp_path: Path,
) -> None:
    """同一批次 provider 配 cloud 但 key 为空时也要被拒绝。"""
    config_path = tmp_path / "config.json"
    service = RefactoredConfigService(config_path=str(config_path))
    assert service.start() is True

    with pytest.raises(ConfigurationError):
        service.set_settings_batch(
            {
                ConfigKeys.TRANSCRIPTION_PROVIDER: "groq",
                ConfigKeys.TRANSCRIPTION_GROQ_API_KEY: "",
            },
            immediate=False,
        )


def test_set_setting_rejects_provider_change_while_recording(tmp_path: Path) -> None:
    """录音进行中禁止切换 provider（保护正在进行的转录）。"""
    config_path = tmp_path / "config.json"

    class _FakeContainer:
        def __init__(self, recording: bool) -> None:
            self._recording = recording

        def resolve(self, _interface):
            outer = self

            class _State:
                def is_recording(self) -> bool:
                    return outer._recording

            return _State()

    service = RefactoredConfigService(
        config_path=str(config_path), container=_FakeContainer(recording=True)
    )
    assert service.start() is True
    # 先准备好 groq api key（绕开校验直接写入）
    service._writer.set_setting(ConfigKeys.TRANSCRIPTION_GROQ_API_KEY, "gsk_test")

    with pytest.raises(ConfigurationError, match="while recording"):
        service.set_setting(ConfigKeys.TRANSCRIPTION_PROVIDER, "groq", immediate=True)
