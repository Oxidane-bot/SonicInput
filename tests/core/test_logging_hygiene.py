"""Logging hygiene tests for validation and retention."""

import os
import time

from sonicinput.utils.unified_logger import LogCategory, UnifiedLogger


class DummyConfigService:
    def __init__(self, settings):
        self._settings = settings

    def get_setting(self, key, default=None):
        return self._settings.get(key, default)


def test_logger_invalid_values_fallback(tmp_path, monkeypatch):
    logger = UnifiedLogger()

    monkeypatch.setattr(logger, "_log_file", tmp_path / "app.log", raising=False)
    logger._log_file.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(logger, "_cleanup_old_logs", lambda: None, raising=False)

    logger._max_log_size_mb = 10
    logger._max_backup_files = 2
    logger._keep_logs_days = 7

    config = DummyConfigService(
        {
            "logging.max_log_size_mb": "bad",
            "logging.max_backup_files": 0,
            "logging.keep_logs_days": -1,
            "logging.enabled_categories": ["audio", "unknown"],
        }
    )

    logger.set_config_service(config)

    assert logger._max_log_size_mb == 10
    assert logger._max_backup_files == 2
    assert logger._keep_logs_days == 7
    assert logger._enabled_categories == {LogCategory.AUDIO}


def test_logger_retention_removes_old_logs(tmp_path, monkeypatch):
    logger = UnifiedLogger()

    log_file = tmp_path / "app.log"
    log_file.write_text("current", encoding="utf-8")

    old_log = tmp_path / "app.log.1"
    old_log.write_text("old", encoding="utf-8")

    old_time = time.time() - (3 * 24 * 3600)
    os.utime(old_log, (old_time, old_time))

    monkeypatch.setattr(logger, "_log_file", log_file, raising=False)
    monkeypatch.setattr(logger, "_keep_logs_days", 1, raising=False)

    logger._cleanup_old_logs()

    assert old_log.exists() is False
    assert log_file.exists() is True
