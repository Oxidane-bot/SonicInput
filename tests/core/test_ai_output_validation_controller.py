from datetime import datetime

from sonicinput.core.controllers.ai_processing_controller import AIProcessingController
from sonicinput.core.interfaces import HistoryRecord
from sonicinput.core.services.events import Events


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
            "ai.groq.model_id": "demo-model",
            "ai.prompt": "prompt {text}",
            "ai.max_output_tokens": 4096,
            "ai.sentence_split.enabled": False,
            "ai.first_chunk_output.enabled": False,
            "ai.streaming_enabled": False,
        }

    def get_setting(self, key, default=None):
        return self.values.get(key, default)


class _State:
    def set_app_state(self, state):
        return None


class _History:
    def __init__(self, text):
        self.record = HistoryRecord(
            id="r1",
            timestamp=datetime(2026, 6, 9, 9, 0, 0),
            audio_file_path="C:/recording.wav",
            duration=1.0,
            transcription_text=text,
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
            final_text=text,
        )

    def get_record_by_id(self, record_id):
        return self.record if record_id == self.record.id else None

    def update_record(self, record):
        self.record = record
        return True


class _CountingAI:
    def __init__(self, output):
        self.output = output
        self.calls = 0
        self.prompt_templates = []
        self._last_tps = 10.0

    def refine_text(self, text, prompt_template, model, max_tokens=None):
        self.calls += 1
        self.prompt_templates.append(prompt_template)
        return self.output


class _ReviewStorage:
    def __init__(self, entries):
        self.entries = entries

    def list_active_lexicon_entries(self, limit=200):
        return self.entries[:limit]


def _controller(monkeypatch, original_text, ai_output):
    events = _Events()
    history = _History(original_text)
    ai_service = _CountingAI(ai_output)
    controller = AIProcessingController(
        config_service=_Config(),
        event_service=events,
        state_manager=_State(),
        history_service=history,
    )
    monkeypatch.setattr(controller, "_get_current_ai_service", lambda: ai_service)
    return controller, events, history, ai_service


def test_ai_controller_skips_low_information_input_without_calling_ai(monkeypatch):
    controller, events, history, ai_service = _controller(
        monkeypatch,
        original_text="嗯",
        ai_output="请提供需要优化的文本。",
    )

    controller._on_transcription_completed(
        {"record_id": "r1", "text": "嗯", "streaming_mode": "chunked"}
    )

    processed = [
        data for event, data in events.emitted if event == Events.AI_PROCESSED_TEXT
    ]

    assert ai_service.calls == 0
    assert processed[-1]["text"] == "嗯"
    assert history.record.ai_status == "skipped"
    assert history.record.ai_error == "low_information_input"
    assert history.record.final_text == "嗯"


def test_ai_controller_falls_back_when_refined_text_violates_contract(monkeypatch):
    original = "搜索一下 SonicInput 的历史记录里面 AI 优化经常失败的问题"
    controller, events, history, ai_service = _controller(
        monkeypatch,
        original_text=original,
        ai_output="以下是我为你找到的答案：SonicInput 的问题主要包括转写错误。",
    )

    controller._on_transcription_completed(
        {"record_id": "r1", "text": original, "streaming_mode": "chunked"}
    )

    processed = [
        data for event, data in events.emitted if event == Events.AI_PROCESSED_TEXT
    ]

    assert ai_service.calls == 1
    assert processed[-1]["text"] == original
    assert history.record.ai_status == "failed"
    assert history.record.ai_optimized_text is None
    assert history.record.ai_provider is None
    assert history.record.final_text == original
    assert "assistant_response_tone" in history.record.ai_error


def test_ai_controller_adds_rolling_context_within_recording(monkeypatch):
    controller, _events, _history, ai_service = _controller(
        monkeypatch,
        original_text="我们使用 PyTorch 做模型。",
        ai_output="我们使用 PyTorch 做模型。",
    )

    controller._on_recording_started()
    controller.process_with_ai("我们使用 PyTorch 做模型。", update_history=False)
    controller.process_with_ai("后面继续说这个模型。", update_history=False)

    assert len(ai_service.prompt_templates) == 2
    assert "Current recording context" not in ai_service.prompt_templates[0]
    assert "Current recording context" in ai_service.prompt_templates[1]
    assert "PyTorch" in ai_service.prompt_templates[1]


def test_ai_controller_adds_user_confirmed_lexicon_to_prompt(monkeypatch):
    config = _Config()
    events = _Events()
    history = _History("我们继续说拍套曲。")
    ai_service = _CountingAI("我们继续说 PyTorch。")
    controller = AIProcessingController(
        config_service=config,
        event_service=events,
        state_manager=_State(),
        history_service=history,
        review_storage_service=_ReviewStorage(
            [{"old_form": "拍套曲", "term": "PyTorch", "status": "active"}]
        ),
    )
    monkeypatch.setattr(controller, "_get_current_ai_service", lambda: ai_service)

    controller.process_with_ai("我们继续说拍套曲。", update_history=False)

    assert "User-confirmed local lexicon" in ai_service.prompt_templates[0]
    assert "Input: 拍套曲" in ai_service.prompt_templates[0]
    assert "Output: PyTorch" in ai_service.prompt_templates[0]


def test_ai_controller_can_disable_user_confirmed_lexicon(monkeypatch):
    config = _Config()
    config.values["review.use_lexicon_memory"] = False
    events = _Events()
    history = _History("我们继续说拍套曲。")
    ai_service = _CountingAI("我们继续说 PyTorch。")
    controller = AIProcessingController(
        config_service=config,
        event_service=events,
        state_manager=_State(),
        history_service=history,
        review_storage_service=_ReviewStorage(
            [{"old_form": "拍套曲", "term": "PyTorch"}]
        ),
    )
    monkeypatch.setattr(controller, "_get_current_ai_service", lambda: ai_service)

    controller.process_with_ai("我们继续说拍套曲。", update_history=False)

    assert "User-confirmed local lexicon" not in ai_service.prompt_templates[0]


def test_ai_controller_skips_phonetically_unrelated_lexicon_entries(monkeypatch):
    """与当前文本发音无关的词条不应注入(程序化预筛)。"""
    config = _Config()
    events = _Events()
    history = _History("今天天气不错。")
    ai_service = _CountingAI("今天天气不错。")
    controller = AIProcessingController(
        config_service=config,
        event_service=events,
        state_manager=_State(),
        history_service=history,
        review_storage_service=_ReviewStorage(
            [
                {"old_form": "拍套曲", "term": "PyTorch"},
                {"old_form": "词汇酷", "term": "词汇库"},
            ]
        ),
    )
    monkeypatch.setattr(controller, "_get_current_ai_service", lambda: ai_service)

    controller.process_with_ai("今天天气不错。", update_history=False)

    assert "User-confirmed local lexicon" not in ai_service.prompt_templates[0]
    assert "PyTorch" not in ai_service.prompt_templates[0]


def test_ai_controller_injects_only_phonetically_matched_lexicon_entries(monkeypatch):
    """同音异字命中该词条,其余无关词条被过滤。"""
    config = _Config()
    events = _Events()
    history = _History("这个慈会苦要更新了。")
    ai_service = _CountingAI("这个词汇库要更新了。")
    controller = AIProcessingController(
        config_service=config,
        event_service=events,
        state_manager=_State(),
        history_service=history,
        review_storage_service=_ReviewStorage(
            [
                {"old_form": "拍套曲", "term": "PyTorch"},
                {"old_form": "词汇酷", "term": "词汇库"},
            ]
        ),
    )
    monkeypatch.setattr(controller, "_get_current_ai_service", lambda: ai_service)

    # 慈会苦(ci hui ku)与 词汇库/词汇酷 同音 → 注入该词条
    controller.process_with_ai("这个慈会苦要更新了。", update_history=False)

    prompt = ai_service.prompt_templates[0]
    assert "User-confirmed local lexicon" in prompt
    assert "Output: 词汇库" in prompt
    assert "PyTorch" not in prompt
