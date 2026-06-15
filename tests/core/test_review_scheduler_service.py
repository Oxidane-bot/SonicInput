from pathlib import Path
from uuid import uuid4

from sonicinput.core.services.review_scheduler_service import (
    ReviewSchedulerConfig,
    ReviewSchedulerService,
)
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
            item for item in self.listeners.get(event_name, []) if item[0] != listener_id
        ]

    def emit(self, event_name, data=None):
        for _listener_id, handler in list(self.listeners.get(event_name, [])):
            handler(data)


def _storage() -> ReviewStorageService:
    path = Path("quality_audit") / f"test_review_scheduler_{uuid4().hex}.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return ReviewStorageService(path)


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
    assert storage.list_pending_suggestions()[0]["suggestion_type"] == "assistant_response_leak_alert"
    assert scheduler.run_once_if_idle().reason == "min_interval_not_reached"


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
