from datetime import datetime

import pytest

from sonicinput.ai.base_client import BaseAIClient
from sonicinput.core.controllers.ai_processing_controller import AIProcessingController
from sonicinput.core.interfaces import HistoryRecord
from sonicinput.core.services.events import Events
from sonicinput.utils.exceptions import AIOutputTruncatedError


class _Response:
    status_code = 200
    text = "{}"

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _Session:
    def __init__(self, payload):
        self.headers = {}
        self.payload = payload
        self.requests = []

    def post(self, url, json, timeout, stream=False):
        self.requests.append(
            {"url": url, "json": json, "timeout": timeout, "stream": stream}
        )
        return _Response(self.payload)


class _Client(BaseAIClient):
    def get_base_url(self) -> str:
        return "https://example.invalid/v1"

    def get_provider_name(self) -> str:
        return "TestAI"

    def get_default_model(self) -> str:
        return "test-model"

    def _create_api_error(self, message: str) -> Exception:
        return RuntimeError(message)


def test_base_ai_client_rejects_length_finished_response():
    session = _Session(
        {
            "choices": [
                {
                    "finish_reason": "length",
                    "message": {"content": "只有前半段"},
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 1000,
                "total_tokens": 1010,
            },
        }
    )
    client = _Client(api_key="key")
    client.session = session

    with pytest.raises(AIOutputTruncatedError):
        client.refine_text(
            "完整原文",
            "prompt {text}",
            "test-model",
            max_tokens=1000,
        )

    assert session.requests[0]["json"]["max_tokens"] == 1000


class _Events:
    def __init__(self):
        self.emitted = []

    def emit(self, event_name, data=None):
        self.emitted.append((event_name, data))

    def on(self, event_name, handler):
        return f"{event_name}-listener"

    def off(self, event_name, listener_id):
        return None


class _Config:
    def __init__(self):
        self.values = {
            "ai.enabled": True,
            "ai.provider": "groq",
            "ai.groq.model_id": "openai/gpt-oss-120b",
            "ai.prompt": "prompt {text}",
            "ai.max_output_tokens": 4096,
            "ai.sentence_split.enabled": False,
            "ai.streaming_enabled": False,
        }

    def get_setting(self, key, default=None):
        return self.values.get(key, default)


class _State:
    def set_app_state(self, state):
        return None


class _History:
    def __init__(self):
        self.record = HistoryRecord(
            id="r1",
            timestamp=datetime(2026, 5, 15, 2, 46, 0),
            audio_file_path="C:/recording.wav",
            duration=1.0,
            transcription_text="完整转写文本",
            transcription_provider="groq",
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
            final_text="完整转写文本",
        )
        self.updated = []

    def get_record_by_id(self, record_id):
        return self.record if record_id == self.record.id else None

    def update_record(self, record):
        self.updated.append(record)
        return True


class _TruncatedAI:
    def __init__(self):
        self._last_tps = 123.0
        self.max_tokens_seen = None

    def refine_text(self, text, prompt_template, model, max_tokens=None):
        self.max_tokens_seen = max_tokens
        raise AIOutputTruncatedError(
            "AI output reached max_tokens before completion",
            context={"finish_reason": "length", "max_tokens": max_tokens},
        )


def test_ai_processing_falls_back_to_transcription_when_ai_output_is_truncated(
    monkeypatch,
):
    config = _Config()
    events = _Events()
    history = _History()
    ai_service = _TruncatedAI()
    controller = AIProcessingController(
        config_service=config,
        event_service=events,
        state_manager=_State(),
        history_service=history,
    )
    monkeypatch.setattr(controller, "_get_current_ai_service", lambda: ai_service)

    controller._on_transcription_completed(
        {
            "record_id": "r1",
            "text": "完整转写文本",
            "streaming_mode": "chunked",
        }
    )

    processed = [
        data for event, data in events.emitted if event == Events.AI_PROCESSED_TEXT
    ]

    assert ai_service.max_tokens_seen == 4096
    assert processed[-1]["text"] == "完整转写文本"
    assert history.record.final_text == "完整转写文本"
    assert history.record.ai_optimized_text is None
    assert history.record.ai_provider is None
    assert history.record.ai_status == "failed"
    assert "max_tokens" in history.record.ai_error
