import time

from sonicinput.core.controllers.ai_processing_controller import AIProcessingController
from sonicinput.core.controllers.input_controller import InputController
from sonicinput.core.services.events import Events


class DummyEventService:
    def __init__(self):
        self.emitted = []
        self._listeners = {}

    def emit(self, event_name, data=None):
        self.emitted.append((event_name, data))

    def on(self, event_name, handler):
        listeners = self._listeners.setdefault(event_name, [])
        listener_id = f"{event_name}-{len(listeners)}"
        listeners.append((listener_id, handler))
        return listener_id

    def off(self, event_name, listener_id):
        listeners = self._listeners.get(event_name, [])
        self._listeners[event_name] = [
            (lid, handler) for lid, handler in listeners if lid != listener_id
        ]


class DummyConfigService:
    def __init__(self, values):
        self.values = values

    def get_setting(self, key, default=None):
        return self.values.get(key, default)


class DummyStateManager:
    def __init__(self):
        self.app_state = None

    def set_app_state(self, state):
        self.app_state = state


class DummyHistoryService:
    def get_record_by_id(self, record_id):
        return None

    def update_record(self, record):
        return True


class FakeAIService:
    def __init__(self):
        self._last_tps = 123.0

    def refine_text(self, text, prompt_template, model):
        return f"<{text}>"


class DummyInputService:
    def __init__(self):
        self.inputs = []
        self.stop_calls = 0
        self.start_calls = 0

    def input_text(self, text):
        self.inputs.append(text)
        return True

    def stop_recording_mode(self):
        self.stop_calls += 1

    def start_recording_mode(self):
        self.start_calls += 1


def test_ai_processing_emits_incremental_updates_for_multiple_groups(monkeypatch):
    config = DummyConfigService(
        {
            "ai.enabled": True,
            "ai.provider": "openrouter",
            "ai.openrouter.model_id": "demo-model",
            "ai.prompt": "prompt {text}",
            "ai.sentence_split.enabled": True,
        }
    )
    events = DummyEventService()
    controller = AIProcessingController(
        config_service=config,
        event_service=events,
        state_manager=DummyStateManager(),
        history_service=DummyHistoryService(),
    )
    monkeypatch.setattr(controller, "_get_current_ai_service", lambda: FakeAIService())

    final_text = controller.process_with_ai(
        "第一句。第二句。第三句。第四句。第五句。第六句。",
        incremental_event_data={"streaming_mode": "chunked"},
    )

    incremental_events = [
        data for event_name, data in events.emitted if event_name == Events.AI_INCREMENTAL_TEXT_UPDATED
    ]

    assert len(incremental_events) == 2
    assert incremental_events[0]["text"] == "<第一句。第二句。第三句。>"
    assert incremental_events[1]["text"] == "<第一句。第二句。第三句。><第四句。第五句。第六句。>"
    assert final_text == incremental_events[-1]["text"]


def test_input_controller_does_not_duplicate_final_incremental_ai_text():
    input_service = DummyInputService()
    events = DummyEventService()
    controller = InputController(
        input_service=input_service,
        config_service=DummyConfigService({}),
        event_service=events,
        state_manager=DummyStateManager(),
    )

    controller._on_recording_started()
    controller._on_ai_incremental_text_updated({"text": "第一段"})
    controller._on_text_ready_for_input(
        {
            "text": "第一段",
            "streaming_mode": "chunked",
            "incremental_output_used": True,
            "recording_stop_time": time.time(),
            "audio_duration": 1.0,
            "transcribe_duration": 0.5,
        }
    )

    assert input_service.inputs == ["第一段"]
    assert input_service.stop_calls == 1
    assert events.emitted[-1][0] == Events.TEXT_INPUT_COMPLETED


def test_first_chunk_output_emits_incremental_text_before_final(monkeypatch):
    config = DummyConfigService(
        {
            "ai.enabled": True,
            "ai.provider": "openrouter",
            "ai.openrouter.model_id": "demo-model",
            "ai.prompt": "prompt {text}",
            "ai.sentence_split.enabled": True,
            "ai.first_chunk_output.enabled": True,
        }
    )
    events = DummyEventService()
    controller = AIProcessingController(
        config_service=config,
        event_service=events,
        state_manager=DummyStateManager(),
        history_service=DummyHistoryService(),
    )
    monkeypatch.setattr(controller, "_get_current_ai_service", lambda: FakeAIService())

    controller._on_transcription_request(
        {
            "record_id": "r1",
            "audio_duration": 12.0,
            "recording_stop_time": time.time(),
        }
    )
    controller._on_streaming_chunk_completed(
        {
            "chunk_id": 0,
            "result": {
                "success": True,
                "text": "第一句。第二句。第三句。第四",
            },
        }
    )

    incremental_events = [
        data
        for event_name, data in events.emitted
        if event_name == Events.AI_INCREMENTAL_TEXT_UPDATED
    ]
    assert len(incremental_events) == 1
    assert incremental_events[0]["text"] == "<第一句。第二句。>"

    controller._on_transcription_completed(
        {
            "record_id": "r1",
            "text": "第一句。第二句。第三句。第四句。",
            "streaming_mode": "chunked",
            "audio_duration": 12.0,
            "recording_stop_time": time.time(),
        }
    )

    final_events = [
        data for event_name, data in events.emitted if event_name == Events.AI_PROCESSED_TEXT
    ]
    assert final_events[-1]["incremental_output_used"] is True
    assert final_events[-1]["text"] == "<第一句。第二句。><第三句。第四句。>"


def test_first_chunk_output_waits_for_contiguous_chunks(monkeypatch):
    config = DummyConfigService(
        {
            "ai.enabled": True,
            "ai.provider": "openrouter",
            "ai.openrouter.model_id": "demo-model",
            "ai.prompt": "prompt {text}",
            "ai.sentence_split.enabled": True,
            "ai.first_chunk_output.enabled": True,
        }
    )
    events = DummyEventService()
    controller = AIProcessingController(
        config_service=config,
        event_service=events,
        state_manager=DummyStateManager(),
        history_service=DummyHistoryService(),
    )
    monkeypatch.setattr(controller, "_get_current_ai_service", lambda: FakeAIService())

    controller._on_transcription_request({"record_id": "r2"})
    controller._on_streaming_chunk_completed(
        {
            "chunk_id": 1,
            "result": {"success": True, "text": "第四句。第五句。第六句。"},
        }
    )

    incremental_events = [
        data
        for event_name, data in events.emitted
        if event_name == Events.AI_INCREMENTAL_TEXT_UPDATED
    ]
    assert incremental_events == []

    controller._on_streaming_chunk_completed(
        {
            "chunk_id": 0,
            "result": {"success": True, "text": "第一句。第二句。第三句。"},
        }
    )

    incremental_events = [
        data
        for event_name, data in events.emitted
        if event_name == Events.AI_INCREMENTAL_TEXT_UPDATED
    ]
    assert len(incremental_events) == 1
    assert incremental_events[0]["text"] == "<第一句。第二句。第三句。第四句。第五句。>"


def test_first_chunk_output_uses_two_sentence_threshold(monkeypatch):
    config = DummyConfigService(
        {
            "ai.enabled": True,
            "ai.provider": "openrouter",
            "ai.openrouter.model_id": "demo-model",
            "ai.prompt": "prompt {text}",
            "ai.sentence_split.enabled": True,
            "ai.first_chunk_output.enabled": True,
        }
    )
    events = DummyEventService()
    controller = AIProcessingController(
        config_service=config,
        event_service=events,
        state_manager=DummyStateManager(),
        history_service=DummyHistoryService(),
    )
    monkeypatch.setattr(controller, "_get_current_ai_service", lambda: FakeAIService())

    controller._on_transcription_request({"record_id": "r3"})
    controller._on_streaming_chunk_completed(
        {
            "chunk_id": 0,
            "result": {"success": True, "text": "第一句。第二句。第三"},
        }
    )

    incremental_events = [
        data
        for event_name, data in events.emitted
        if event_name == Events.AI_INCREMENTAL_TEXT_UPDATED
    ]
    assert len(incremental_events) == 1
    assert incremental_events[0]["text"] == "<第一句。第二句。>"
