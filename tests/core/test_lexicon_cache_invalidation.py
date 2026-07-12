from datetime import datetime

from sonicinput.core.controllers.ai_processing_controller import AIProcessingController
from sonicinput.core.interfaces import HistoryRecord
from sonicinput.core.services.ui_services import UISettingsService


class _Config:
    def __init__(self):
        self.values = {
            "ai.enabled": True,
            "ai.provider": "test",
            "ai.test.model_id": "test-model",
            "ai.prompt": "Improve this text: {text}",
            "ai.max_output_tokens": 4096,
            "ai.sentence_split.enabled": False,
            "ai.first_chunk_output.enabled": False,
            "ai.streaming_enabled": False,
            "review.use_lexicon_memory": True,
        }

    def get_setting(self, key, default=None):
        return self.values.get(key, default)


class _Events:
    def emit(self, _event_name, _data=None):
        return None

    def on(self, event_name, _handler):
        return f"{event_name}-listener"

    def off(self, _event_name, _listener_id):
        return None


class _State:
    def set_app_state(self, _state):
        return None


class _History:
    def __init__(self):
        self.record = HistoryRecord(
            id="record-1",
            timestamp=datetime(2026, 7, 12, 9, 0),
            audio_file_path="C:/recording.wav",
            duration=1.0,
            transcription_text="我们继续说拍套曲。",
            transcription_provider="test",
            transcription_status="success",
            streaming_mode="chunked",
            transcription_duration=0.1,
            used_fallback=False,
            fallback_type="none",
            fallback_reason=None,
            diagnostics_collected=True,
            transcription_error=None,
            ai_optimized_text=None,
            ai_provider=None,
            ai_status="pending",
            ai_error=None,
            final_text="我们继续说拍套曲。",
        )

    def get_record_by_id(self, record_id):
        return self.record if record_id == self.record.id else None

    def update_record(self, record):
        self.record = record
        return True


class _PromptCapturingAI:
    def __init__(self):
        self.prompt_templates = []
        self._last_tps = 0.0

    def refine_text(self, text, prompt_template, _model, max_tokens=None):
        del max_tokens
        self.prompt_templates.append(prompt_template)
        return text


class _MutableLexiconStorage:
    def __init__(self, entries):
        self.entries = list(entries)
        self.pending_entries = {
            "suggestion-1": {
                "id": "lex-1",
                "term": "PyTorch",
                "old_form": "拍套曲",
            }
        }
        self.list_calls = 0

    def list_active_lexicon_entries(self):
        self.list_calls += 1
        return list(self.entries)

    def record_decision(self, suggestion_id, decision, *, note=None):
        del note
        if decision == "accepted":
            self.entries.append(dict(self.pending_entries[suggestion_id]))

    def archive_lexicon_entry(self, entry_id):
        previous_count = len(self.entries)
        self.entries = [entry for entry in self.entries if entry["id"] != entry_id]
        return len(self.entries) != previous_count

    def clear_lexicon_entries(self):
        self.entries = []


def _lexicon_entry() -> dict[str, str]:
    return {
        "id": "lex-1",
        "term": "PyTorch",
        "old_form": "拍套曲",
    }


def _build_services(monkeypatch, entries):
    config = _Config()
    storage = _MutableLexiconStorage(entries)
    ai_service = _PromptCapturingAI()
    controller = AIProcessingController(
        config_service=config,
        event_service=_Events(),
        state_manager=_State(),
        history_service=_History(),
        review_storage_service=storage,
    )
    monkeypatch.setattr(controller, "_get_current_ai_service", lambda: ai_service)
    settings = UISettingsService(
        config_service=config,
        event_service=_Events(),
        history_service=_History(),
        ai_processing_controller=controller,
        review_storage_service=storage,
    )
    return controller, settings, storage, ai_service


def _process_prompt(controller, ai_service) -> str:
    controller.process_with_ai(
        "我们继续说拍套曲。", update_history=False, emit_events=False
    )
    return ai_service.prompt_templates[-1]


def test_accepting_lexicon_candidate_invalidates_cached_prompt_entries(monkeypatch):
    controller, settings, storage, ai_service = _build_services(monkeypatch, [])

    assert "Input: 拍套曲" not in _process_prompt(controller, ai_service)
    assert storage.list_calls == 1

    assert settings.decide_review_suggestion("suggestion-1", "accepted") is True

    refreshed_prompt = _process_prompt(controller, ai_service)
    assert storage.list_calls == 2
    assert "Input: 拍套曲" in refreshed_prompt
    assert "Output: PyTorch" in refreshed_prompt


def test_removing_lexicon_entry_invalidates_cached_prompt_entries(monkeypatch):
    controller, settings, storage, ai_service = _build_services(
        monkeypatch, [_lexicon_entry()]
    )

    assert "Input: 拍套曲" in _process_prompt(controller, ai_service)
    assert storage.list_calls == 1

    assert settings.remove_lexicon_entry("lex-1") is True

    refreshed_prompt = _process_prompt(controller, ai_service)
    assert storage.list_calls == 2
    assert "User-confirmed local lexicon" not in refreshed_prompt
    assert "Input: 拍套曲" not in refreshed_prompt


def test_clearing_lexicon_entries_invalidates_cached_prompt_entries(monkeypatch):
    controller, settings, storage, ai_service = _build_services(
        monkeypatch, [_lexicon_entry()]
    )

    assert "Input: 拍套曲" in _process_prompt(controller, ai_service)
    assert storage.list_calls == 1

    assert settings.clear_lexicon_entries() is True

    refreshed_prompt = _process_prompt(controller, ai_service)
    assert storage.list_calls == 2
    assert "User-confirmed local lexicon" not in refreshed_prompt
    assert "Input: 拍套曲" not in refreshed_prompt
