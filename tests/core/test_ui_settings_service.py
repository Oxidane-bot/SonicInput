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


def test_ui_settings_service_exposes_lexicon_memory_actions():
    review_storage = Mock(name="review_storage")
    review_storage.list_active_lexicon_entries.return_value = [{"term": "PyTorch"}]

    service = UISettingsService(
        config_service=Mock(),
        event_service=Mock(),
        history_service=Mock(),
        review_storage_service=review_storage,
    )

    assert service.list_lexicon_entries() == [{"term": "PyTorch"}]
    review_storage.archive_lexicon_entry.return_value = True
    assert service.remove_lexicon_entry("lex-1") is True
    assert service.clear_lexicon_entries() is True

    review_storage.list_active_lexicon_entries.assert_called_once_with()
    review_storage.archive_lexicon_entry.assert_called_once_with("lex-1")
    review_storage.clear_lexicon_entries.assert_called_once_with()


def test_ui_settings_service_lexicon_methods_are_safe_without_storage():
    service = UISettingsService(
        config_service=Mock(),
        event_service=Mock(),
        history_service=Mock(),
    )

    assert service.list_lexicon_entries() == []
    assert service.remove_lexicon_entry("missing") is False
    assert service.clear_lexicon_entries() is False
    assert service.export_lexicon_entries()["success"] is False


def test_ui_settings_service_rejects_concurrent_review_runs():
    config_service = Mock()
    config_service.get_setting.return_value = True
    service = UISettingsService(
        config_service=config_service,
        event_service=Mock(),
        history_service=Mock(),
        container=object(),
    )

    service._review_run_lock.acquire()
    try:
        result = service.run_review_now()
    finally:
        service._review_run_lock.release()

    assert result["ran"] is False
    assert result["reason"] == "review_already_running"


def test_ui_model_service_updates_runtime_speech_service():
    original_speech_service = Mock(name="original_speech_service")
    replacement_speech_service = Mock(name="replacement_speech_service")
    replacement_speech_service.is_model_loaded = False

    service = UIModelService(original_speech_service)
    service.set_speech_service(replacement_speech_service)

    assert service.speech_service is replacement_speech_service
