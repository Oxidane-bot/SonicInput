from pathlib import Path
from uuid import uuid4

from sonicinput.core.services.review_scheduler_service import (
    ReviewSchedulerConfig,
    ReviewSchedulerService,
)
from sonicinput.core.quality import ReviewSuggestion
from sonicinput.core.services.events import Events
from sonicinput.core.services.storage import ReviewStorageService


class _Clock:
    def __init__(self, value=0.0):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class _Config:
    def __init__(self, values):
        self.values = values

    def get_setting(self, key, default=None):
        return self.values.get(key, default)


class _Events:
    def __init__(self):
        self.listeners = {}

    def on(self, event_name, handler):
        listener_id = f"{event_name}-{len(self.listeners)}"
        self.listeners.setdefault(event_name, []).append((listener_id, handler))
        return listener_id

    def off(self, event_name, listener_id):
        self.listeners[event_name] = [
            item
            for item in self.listeners.get(event_name, [])
            if item[0] != listener_id
        ]

    def emit(self, event_name, data=None):
        for _listener_id, handler in list(self.listeners.get(event_name, [])):
            handler(data)


def _storage() -> ReviewStorageService:
    path = Path("quality_audit") / f"test_review_scheduler_{uuid4().hex}.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return ReviewStorageService(path)


class _ReviewServiceStub:
    def __init__(self, suggestions, source="llm", fallback_reason=None):
        self._suggestions = suggestions
        self._source = source
        self._fallback_reason = fallback_reason

    def review_records(self, records):
        from sonicinput.core.quality import ReviewRunOutcome

        return ReviewRunOutcome(
            review_source=self._source,
            suggestions=tuple(self._suggestions),
            provider="openrouter",
            model_id="demo-model",
            prompt_version="v1",
            fallback_reason=self._fallback_reason,
        )


def test_review_scheduler_waits_until_idle():
    clock = _Clock()
    scheduler = ReviewSchedulerService(
        load_recent_records=lambda limit: [],
        review_storage=_storage(),
        config=ReviewSchedulerConfig(idle_seconds=300),
        clock=clock,
    )

    assert scheduler.can_run().reason == "not_idle_long_enough"

    clock.advance(301)

    assert scheduler.can_run().can_run is True


def test_review_scheduler_run_now_ignores_idle_gate_but_keeps_busy_protection():
    clock = _Clock(1000)
    records = [{"id": "r1", "transcription_text": "hello"}]
    storage = _storage()
    scheduler = ReviewSchedulerService(
        load_recent_records=lambda limit: records[:limit],
        review_storage=storage,
        config=ReviewSchedulerConfig(idle_seconds=300, max_runs_per_session=1),
        clock=clock,
    )

    assert scheduler.run_once_if_idle().reason == "not_idle_long_enough"

    result = scheduler.run_once_now()

    assert result.ran is True
    assert result.reason == "completed"
    assert result.suggestion_count >= 0
    assert storage.list_review_jobs()[0]["id"] == result.job_id
    assert scheduler.run_once_now().ran is True

    scheduler.set_recording(True)
    assert scheduler.run_once_now().reason == "recording_active"


def test_review_scheduler_run_now_does_not_consume_session_budget():
    clock = _Clock(1000)
    scheduler = ReviewSchedulerService(
        load_recent_records=lambda limit: [],
        review_storage=_storage(),
        config=ReviewSchedulerConfig(idle_seconds=300, max_runs_per_session=1),
        clock=clock,
    )

    assert scheduler.run_once_now().ran is True
    assert scheduler.run_once_now().ran is True


def test_review_scheduler_blocks_while_recording():
    clock = _Clock(1000)
    scheduler = ReviewSchedulerService(
        load_recent_records=lambda limit: [],
        review_storage=_storage(),
        config=ReviewSchedulerConfig(idle_seconds=0),
        clock=clock,
    )

    scheduler.set_recording(True)

    assert scheduler.can_run().reason == "recording_active"
    assert scheduler.can_run_now().reason == "recording_active"


def test_review_scheduler_runs_and_persists_suggestions():
    clock = _Clock(1000)
    records = [
        {
            "id": "r1",
            "transcription_status": "success",
            "transcription_text": "搜索 SonicInput 的问题",
            "ai_status": "success",
            "ai_optimized_text": "以下是我为你找到的答案：SonicInput 有问题。",
            "final_text": "以下是我为你找到的答案：SonicInput 有问题。",
        }
    ]
    storage = _storage()
    scheduler = ReviewSchedulerService(
        load_recent_records=lambda limit: records[:limit],
        review_storage=storage,
        config=ReviewSchedulerConfig(
            idle_seconds=0,
            min_interval_seconds=60,
            max_records=20,
            max_runs_per_session=1,
        ),
        clock=clock,
    )

    result = scheduler.run_once_if_idle()

    assert result.ran is True
    assert result.suggestion_count == 1
    assert (
        storage.list_pending_suggestions()[0]["suggestion_type"]
        == "assistant_response_leak_alert"
    )
    assert scheduler.run_once_if_idle().reason == "min_interval_not_reached"


def test_review_scheduler_uses_llm_review_service_when_provided():
    clock = _Clock(1000)
    storage = _storage()
    suggestion = ReviewSuggestion(
        suggestion_id="review_llm_1",
        suggestion_type="bad_ai_output_alert",
        confidence=0.91,
        risk_level="high",
        source_record_ids=("r1",),
        title="AI 输出可能越界",
        detail="llm hit",
        evidence_count=1,
    )
    scheduler = ReviewSchedulerService(
        load_recent_records=lambda limit: [{"id": "r1"}],
        review_storage=storage,
        config=ReviewSchedulerConfig(idle_seconds=0, max_runs_per_session=1),
        clock=clock,
    )

    result = scheduler.run_once_now(review_service=_ReviewServiceStub([suggestion]))

    assert result.review_source == "llm"
    assert result.provider == "openrouter"
    assert result.model_id == "demo-model"
    jobs = storage.list_review_jobs()
    assert jobs[0]["review_source"] == "llm"
    assert jobs[0]["provider"] == "openrouter"
    assert jobs[0]["model_id"] == "demo-model"


def test_review_scheduler_respects_session_budget_after_interval():
    clock = _Clock(1000)
    scheduler = ReviewSchedulerService(
        load_recent_records=lambda limit: [],
        review_storage=_storage(),
        config=ReviewSchedulerConfig(
            idle_seconds=0,
            min_interval_seconds=10,
            max_runs_per_session=1,
        ),
        clock=clock,
    )

    assert scheduler.run_once_if_idle().ran is True
    clock.advance(11)

    assert scheduler.run_once_if_idle().reason == "session_budget_exhausted"


def test_review_scheduler_config_from_service():
    config = ReviewSchedulerService.config_from_service(
        _Config(
            {
                "review.idle_seconds": 10,
                "review.min_interval_seconds": 20,
                "review.max_records": 12,
                "review.max_runs_per_session": 2,
            }
        )
    )

    assert config.idle_seconds == 10
    assert config.min_interval_seconds == 20
    assert config.max_records == 12
    assert config.max_runs_per_session == 2


def test_review_scheduler_event_binding_tracks_busy_state():
    clock = _Clock(1000)
    events = _Events()
    scheduler = ReviewSchedulerService(
        load_recent_records=lambda limit: [],
        review_storage=_storage(),
        config=ReviewSchedulerConfig(idle_seconds=0),
        clock=clock,
    )
    scheduler.bind_events(events)

    events.emit(Events.RECORDING_STARTED)
    assert scheduler.can_run().reason == "recording_active"

    events.emit(Events.RECORDING_STOPPED)
    assert scheduler.can_run().can_run is True

    events.emit(Events.AI_PROCESSING_STARTED)
    assert scheduler.can_run().reason == "ai_processing_active"

    events.emit(Events.AI_PROCESSING_COMPLETED)
    assert scheduler.can_run().can_run is True

    scheduler.unbind_events(events)
    assert all(not listeners for listeners in events.listeners.values())
