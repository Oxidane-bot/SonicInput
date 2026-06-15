from unittest.mock import Mock

from sonicinput.core.interfaces import ISpeechService
from sonicinput.core.services.ui_services import UIModelService, UISettingsService


class _ContainerStub:
    def __init__(self, resolved=None, should_fail=False):
        self.resolved = resolved
        self.should_fail = should_fail

    def resolve(self, interface):
        if self.should_fail:
            raise RuntimeError("resolve failed")
        if interface is ISpeechService:
            return self.resolved
        raise RuntimeError(f"unsupported interface: {interface}")


def test_ui_settings_service_prefers_container_for_transcription_service():
    fallback_service = Mock(name="fallback_service")
    fresh_service = Mock(name="fresh_service")

    service = UISettingsService(
        config_service=Mock(),
        event_service=Mock(),
        history_service=Mock(),
        transcription_service=fallback_service,
        container=_ContainerStub(resolved=fresh_service),
    )

    assert service.get_transcription_service() is fresh_service


def test_ui_settings_service_falls_back_to_initial_transcription_service():
    fallback_service = Mock(name="fallback_service")

    service = UISettingsService(
        config_service=Mock(),
        event_service=Mock(),
        history_service=Mock(),
        transcription_service=fallback_service,
        container=_ContainerStub(should_fail=True),
    )

    assert service.get_transcription_service() is fallback_service


def test_ui_settings_service_syncs_runtime_dependencies():
    initial_transcription = Mock(name="initial_transcription")
    initial_ai_controller = Mock(name="initial_ai_controller")
    fresh_transcription = Mock(name="fresh_transcription")
    fresh_ai_controller = Mock(name="fresh_ai_controller")

    service = UISettingsService(
        config_service=Mock(),
        event_service=Mock(),
        history_service=Mock(),
        transcription_service=initial_transcription,
        ai_processing_controller=initial_ai_controller,
    )

    service.sync_runtime_dependencies(
        transcription_service=fresh_transcription,
        ai_processing_controller=fresh_ai_controller,
    )

    assert service.get_transcription_service() is fresh_transcription
    assert service.get_ai_processing_controller() is fresh_ai_controller


def test_ui_settings_service_exposes_review_suggestion_actions():
    review_storage = Mock(name="review_storage")
    review_storage.list_pending_suggestions.return_value = [{"suggestion_id": "s1"}]
    review_storage.list_review_jobs.return_value = [{"id": "job-1"}]
    review_storage.list_active_lexicon_entries.return_value = [{"term": "PyTorch"}]

    service = UISettingsService(
        config_service=Mock(),
        event_service=Mock(),
        history_service=Mock(),
        review_storage_service=review_storage,
    )

    assert service.list_review_suggestions(limit=5) == [{"suggestion_id": "s1"}]
    assert service.list_review_jobs(limit=2) == [{"id": "job-1"}]
    assert service.decide_review_suggestion("s1", "accepted", note="ok") is True
    assert service.list_lexicon_entries(limit=5) == [{"term": "PyTorch"}]
    assert service.clear_lexicon_entries() is True
    assert service.clear_review_learning_data() is True

    review_storage.list_pending_suggestions.assert_called_once_with(limit=5)
    review_storage.list_review_jobs.assert_called_once_with(limit=2)
    review_storage.record_decision.assert_called_once_with(
        "s1", "accepted", note="ok"
    )
    review_storage.list_active_lexicon_entries.assert_called_once_with(limit=5)
    review_storage.clear_lexicon_entries.assert_called_once_with()
    review_storage.clear_learning_data.assert_called_once_with()


def test_ui_settings_service_review_methods_are_safe_without_storage():
    service = UISettingsService(
        config_service=Mock(),
        event_service=Mock(),
        history_service=Mock(),
    )

    assert service.list_review_suggestions() == []
    assert service.list_review_jobs() == []
    assert service.decide_review_suggestion("missing", "accepted") is False
    assert service.list_lexicon_entries() == []
    assert service.clear_lexicon_entries() is False
    assert service.clear_review_learning_data() is False
    assert service.export_review_debug_report()["success"] is False


def test_ui_settings_service_can_run_idle_review_once_from_container():
    from sonicinput.core.services.review_scheduler_service import (
        ReviewSchedulerRunResult,
        ReviewSchedulerService,
    )

    config = Mock()
    config.get_setting.return_value = True
    scheduler = Mock()
    scheduler.run_once_if_idle.return_value = ReviewSchedulerRunResult(
        True,
        "completed",
        job_id="job-1",
        reviewed_record_count=12,
        suggestion_count=2,
    )

    class Container:
        def resolve(self, interface):
            if interface is ReviewSchedulerService:
                return scheduler
            raise RuntimeError(f"unsupported interface: {interface}")

    service = UISettingsService(
        config_service=config,
        event_service=Mock(),
        history_service=Mock(),
        container=Container(),
    )

    assert service.run_idle_review_once() == {
        "ran": True,
        "reason": "completed",
        "jobId": "job-1",
        "reviewedRecordCount": 12,
        "suggestionCount": 2,
    }
    scheduler.run_once_if_idle.assert_called_once_with()


def test_ui_settings_service_idle_review_respects_disabled_config():
    config = Mock()
    config.get_setting.return_value = False

    service = UISettingsService(
        config_service=config,
        event_service=Mock(),
        history_service=Mock(),
        container=Mock(),
    )

    result = service.run_idle_review_once()

    assert result["ran"] is False
    assert result["reason"] == "review_disabled"


def test_ui_model_service_updates_runtime_speech_service():
    original_speech_service = Mock(name="original_speech_service")
    replacement_speech_service = Mock(name="replacement_speech_service")
    replacement_speech_service.is_model_loaded = False

    service = UIModelService(original_speech_service)
    service.set_speech_service(replacement_speech_service)

    assert service.speech_service is replacement_speech_service
