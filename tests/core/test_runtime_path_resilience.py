import uuid
from pathlib import Path

from sonicinput.speech.sherpa_models import SherpaModelManager
from sonicinput.utils.unified_logger import LogCategory, LogLevel, UnifiedLogger


class _InaccessiblePath:
    def exists(self):
        raise PermissionError("denied")

    def is_dir(self):
        raise PermissionError("denied")


def test_is_model_cached_returns_false_when_cache_path_is_inaccessible(monkeypatch):
    manager = SherpaModelManager(cache_dir=".tmp_pytest/models")
    monkeypatch.setattr(
        manager, "_get_model_dir", lambda _model_name: _InaccessiblePath()
    )

    assert manager.is_model_cached("paraformer") is False


def test_logger_disables_file_output_after_write_permission_error(monkeypatch, capsys):
    logger = UnifiedLogger()
    temp_dir = Path(".tmp_pytest")
    temp_dir.mkdir(exist_ok=True)
    tmp_path = temp_dir / f"runtime_path_resilience_{uuid.uuid4().hex}"
    tmp_path.mkdir()
    monkeypatch.setattr(logger, "_log_file", tmp_path / "app.log", raising=False)
    monkeypatch.setattr(logger, "_file_logging_disabled", False, raising=False)
    monkeypatch.setattr(logger, "_file_logging_error_reported", False, raising=False)
    monkeypatch.setattr(logger, "_console_output_enabled", False, raising=False)
    monkeypatch.setattr(logger, "_min_level", LogLevel.DEBUG, raising=False)
    monkeypatch.setattr(
        logger, "_enabled_categories", {LogCategory.AUDIO}, raising=False
    )

    monkeypatch.setattr(
        "builtins.open",
        lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError("denied")),
    )

    logger._write_log(LogLevel.INFO, LogCategory.AUDIO, "first")
    logger._write_log(LogLevel.INFO, LogCategory.AUDIO, "second")

    captured = capsys.readouterr()
    assert captured.err.count("Failed to write to log file") == 1
    assert logger._file_logging_disabled is True
