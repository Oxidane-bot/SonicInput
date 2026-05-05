"""Config integrity tests for default immutability and snapshot safety."""

import copy
import json

from sonicinput.core.services.config.config_reader import ConfigReader
from sonicinput.core.services.config.config_service import (
    ConfigService,
)


def test_config_reader_does_not_mutate_defaults(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "advanced": {"audio_processing": {"normalize_audio": False}},
                "logging": {"level": "DEBUG"},
            }
        ),
        encoding="utf-8",
    )

    reader = ConfigReader(config_path)
    defaults_before = copy.deepcopy(reader._default_config)

    assert reader.load_config() is True
    assert reader._default_config == defaults_before


def test_get_all_settings_returns_deep_copy(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"advanced": {"audio_processing": {"normalize_audio": False}}}),
        encoding="utf-8",
    )

    reader = ConfigReader(config_path)
    assert reader.load_config() is True

    snapshot = reader.get_all_settings()
    snapshot["advanced"]["audio_processing"]["normalize_audio"] = True

    assert reader.get_setting("advanced.audio_processing.normalize_audio") is False


def test_config_service_default_config_is_isolated(tmp_path):
    config_path = tmp_path / "config.json"
    service = ConfigService(config_path=str(config_path))

    defaults = service.get_default_config()
    defaults["logging"]["level"] = "DEBUG"

    fresh_defaults = service.get_default_config()
    assert fresh_defaults["logging"]["level"] == "WARNING"
