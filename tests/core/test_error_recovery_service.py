import threading
from unittest.mock import Mock

import numpy as np

from sonicinput.core.services.error_recovery_service import (
    ErrorRecoveryService,
    ErrorSeverity,
    RecoveryAction,
)
from sonicinput.core.services.transcription_service_refactored import (
    RefactoredTranscriptionService,
)


def test_medium_audio_error_is_stable_before_service_start() -> None:
    service = ErrorRecoveryService()

    result = service.handle_error(
        RuntimeError("audio device retry"),
        {"operation": "transcribe_sync"},
    )

    assert result["category"] == "audio_error"
    assert result["severity"] == "medium"
    assert result["message"] == "audio device retry"
    assert result["auto_recovery"] is None
    assert service.get_recent_errors(1)[0]["recovery_attempts"] == 0
    assert service.get_recent_errors(1)[0]["resolved"] is False


def test_start_does_not_enable_placeholder_recovery_actions() -> None:
    service = ErrorRecoveryService()

    assert service.start() is True

    result = service.handle_error(RuntimeError("audio device retry"))

    assert result["auto_recovery"] is None
    assert service.get_error_stats()["recovery_actions_count"] == 0
    assert service.get_error_stats()["auto_recoveries"] == 0


def test_registered_recovery_action_reports_first_attempt_as_one() -> None:
    service = ErrorRecoveryService()
    service.register_recovery_action(
        RecoveryAction(
            action_id="reset_audio_device",
            description="Reset the test audio device",
            severity=ErrorSeverity.MEDIUM,
            action_func=lambda: True,
            cooldown_period=0,
        )
    )

    result = service.handle_error(RuntimeError("audio device retry"))

    assert result["auto_recovery"] == {
        "action_id": "reset_audio_device",
        "description": "Reset the test audio device",
        "success": True,
        "attempt": 1,
    }


def test_transcription_service_starts_error_recovery_component() -> None:
    service = RefactoredTranscriptionService.__new__(RefactoredTranscriptionService)
    service._service_lock = threading.RLock()
    service.model_manager = Mock()
    service.model_manager.get_whisper_engine.return_value = None
    service.model_manager.is_model_loaded.return_value = False
    service.task_queue_manager = Mock()
    service.error_recovery_service = Mock()
    service.event_service = None
    service._init_transcription_pool = Mock()
    service.transcription_core = None

    assert service._do_start() is True

    service.error_recovery_service.start.assert_called_once_with()


def test_transcribe_sync_reports_unavailable_core_instead_of_raising() -> None:
    service = RefactoredTranscriptionService.__new__(RefactoredTranscriptionService)
    service.ensure_transcription_core = Mock(return_value=False)
    service.error_recovery_service = Mock()
    service.error_recovery_service.handle_error.return_value = {"error_id": "error-1"}

    result = service.transcribe_sync(np.array([0.0], dtype=np.float32))

    assert result["success"] is False
    assert result["error_result"] == {"error_id": "error-1"}
    service.error_recovery_service.handle_error.assert_called_once()


def test_transcribe_sync_reports_core_failure_result() -> None:
    service = RefactoredTranscriptionService.__new__(RefactoredTranscriptionService)
    service.ensure_transcription_core = Mock(return_value=True)
    service.transcription_core = Mock()
    service.transcription_core.transcribe_audio.return_value = {
        "success": False,
        "text": "",
        "error": "model inference failed",
    }
    service.error_recovery_service = Mock()
    service.error_recovery_service.handle_error.return_value = {"error_id": "error-2"}

    result = service.transcribe_sync(np.array([0.0], dtype=np.float32))

    assert result["success"] is False
    assert result["error_result"] == {"error_id": "error-2"}
    service.error_recovery_service.handle_error.assert_called_once()


def test_ensure_transcription_core_replaces_a_stale_core() -> None:
    service = RefactoredTranscriptionService.__new__(RefactoredTranscriptionService)
    stale_core = Mock()
    stale_core.is_ready.return_value = False
    engine = Mock()
    service.transcription_core = stale_core
    service.model_manager = Mock()
    service.model_manager.get_whisper_engine.return_value = engine

    assert service.ensure_transcription_core() is True
    assert service.transcription_core.whisper_engine is engine
