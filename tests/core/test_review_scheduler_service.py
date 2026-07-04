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


class _CursorStorageStub:
    def __init__(self):
        self.cursor = None
        self.saved_cursors = []
        self.saved_jobs = []

    def load_review_cursor(self):
        return self.cursor

    def save_review_cursor(self, *, cursor_timestamp, cursor_id, cursor_name="llm_review"):
        self.cursor = {
            "cursor_timestamp": cursor_timestamp,
            "cursor_id": cursor_id,
            "cursor_name": cursor_name,
        }
        self.saved_cursors.append(self.cursor)

    def save_review_run(
        self,
        suggestions,
        *,
        record_limit,
        reviewed_count,
        review_source="local",
        provider=None,
        model_id=None,
        prompt_version=None,
        fallback_reason=None,
    ):
        job_id = f"job-{len(self.saved_jobs) + 1}"
        self.saved_jobs.append(
            {
                "id": job_id,
                "reviewed_count": reviewed_count,
                "record_limit": record_limit,
                "review_source": review_source,
                "provider": provider,
                "model_id": model_id,
                "prompt_version": prompt_version,
                "fallback_reason": fallback_reason,
                "suggestions": list(suggestions),
            }
        )
        return job_id


class _HistoryLoaderStub:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def __call__(self, limit, cursor):
        self.calls.append(cursor)
        key = None if cursor is None else cursor["cursor_id"]
        return self.pages.get(key, [])


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


def test_review_scheduler_rotates_through_history_windows():
    clock = _Clock(1000)
    storage = _CursorStorageStub()
    records = [
        {"id": "r5", "timestamp": "2026-06-16T00:05:00", "transcription_text": "5"},
        {"id": "r4", "timestamp": "2026-06-16T00:04:00", "transcription_text": "4"},
        {"id": "r3", "timestamp": "2026-06-16T00:03:00", "transcription_text": "3"},
        {"id": "r2", "timestamp": "2026-06-16T00:02:00", "transcription_text": "2"},
        {"id": "r1", "timestamp": "2026-06-16T00:01:00", "transcription_text": "1"},
    ]
    pages = []

    def load_review_records(limit, cursor):
        pages.append(cursor)
        if cursor is None:
            return records[:2]
        if cursor["cursor_id"] == "r4":
            return records[2:4]
        if cursor["cursor_id"] == "r2":
            return records[4:]
        return []

    scheduler = ReviewSchedulerService(
        load_review_records=load_review_records,
        review_storage=storage,
        config=ReviewSchedulerConfig(idle_seconds=0, max_records=2),
        clock=clock,
    )

    first = scheduler.run_once_now()
    second = scheduler.run_once_now()
    third = scheduler.run_once_now()

    assert first.reviewed_record_count == 2
    assert second.reviewed_record_count == 2
    assert third.reviewed_record_count == 1
    assert [page and page["cursor_id"] for page in pages] == [None, "r4", "r2"]
    assert storage.saved_cursors[-1]["cursor_id"] == "r1"


def test_review_scheduler_falls_back_to_recent_records_when_cursor_page_empty():
    clock = _Clock(1000)
    storage = _CursorStorageStub()
    storage.cursor = {"cursor_timestamp": "2026-06-16T00:00:00", "cursor_id": "missing"}
    loader = _HistoryLoaderStub({None: [{"id": "r1"}]})

    scheduler = ReviewSchedulerService(
        load_review_records=loader,
        review_storage=storage,
        config=ReviewSchedulerConfig(idle_seconds=0, max_records=1),
        clock=clock,
    )

    result = scheduler.run_once_now()

    assert result.reviewed_record_count == 1
    assert loader.calls == [
        {"cursor_timestamp": "2026-06-16T00:00:00", "cursor_id": "missing"},
        None,
    ]


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
