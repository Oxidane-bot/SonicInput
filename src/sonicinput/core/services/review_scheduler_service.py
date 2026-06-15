"""Conservative idle scheduler for local transcript review."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from ..quality import HistoryReviewAgent, LLMReviewService, ReviewRunOutcome
from .config import ConfigKeys
from .events import Events
from .storage import ReviewStorageService


@dataclass(frozen=True)
class ReviewSchedulerConfig:
    idle_seconds: float = 5 * 60
    min_interval_seconds: float = 30 * 60
    max_records: int = 20
    max_runs_per_session: int = 3


@dataclass(frozen=True)
class ReviewSchedulerDecision:
    can_run: bool
    reason: str


@dataclass(frozen=True)
class ReviewSchedulerRunResult:
    ran: bool
    reason: str
    job_id: str | None = None
    reviewed_record_count: int = 0
    suggestion_count: int = 0
    review_source: str = "local"
    provider: str | None = None
    model_id: str | None = None
    prompt_version: str | None = None
    fallback_reason: str | None = None


class ReviewSchedulerService:
    """Run review only when the app is idle and within budget.

    This service deliberately has no background thread. The app can call
    ``run_once_if_idle`` from an existing timer after updating busy/activity
    state from events.
    """

    def __init__(
        self,
        *,
        load_recent_records: Callable[[int], Sequence[Any]],
        review_storage: ReviewStorageService,
        review_agent: HistoryReviewAgent | None = None,
        config: ReviewSchedulerConfig | None = None,
        clock: Callable[[], float] | None = None,
    ):
        self._load_recent_records = load_recent_records
        self._review_storage = review_storage
        self._review_agent = review_agent or HistoryReviewAgent()
        self._config = config or ReviewSchedulerConfig()
        self._clock = clock or time.time
        self._last_activity_at = self._clock()
        self._last_run_at: float | None = None
        self._runs_this_session = 0
        self._recording = False
        self._transcribing = False
        self._ai_processing = False
        self._ui_busy = False
        self._event_bindings: list[tuple[str, str]] = []

    @classmethod
    def config_from_service(cls, config_service: Any) -> ReviewSchedulerConfig:
        return ReviewSchedulerConfig(
            idle_seconds=float(
                config_service.get_setting(ConfigKeys.REVIEW_IDLE_SECONDS, 600)
            ),
            min_interval_seconds=float(
                config_service.get_setting(
                    ConfigKeys.REVIEW_MIN_INTERVAL_SECONDS,
                    1800,
                )
            ),
            max_records=int(
                config_service.get_setting(ConfigKeys.REVIEW_MAX_RECORDS, 20)
            ),
            max_runs_per_session=int(
                config_service.get_setting(ConfigKeys.REVIEW_MAX_RUNS_PER_SESSION, 3)
            ),
        )

    def mark_activity(self) -> None:
        self._last_activity_at = self._clock()

    def set_recording(self, active: bool) -> None:
        self._recording = active
        self.mark_activity()

    def set_transcribing(self, active: bool) -> None:
        self._transcribing = active
        self.mark_activity()

    def set_ai_processing(self, active: bool) -> None:
        self._ai_processing = active
        self.mark_activity()

    def set_ui_busy(self, active: bool) -> None:
        self._ui_busy = active
        self.mark_activity()

    def bind_events(self, event_service: Any) -> None:
        """Bind app events so scheduler can maintain busy/idle state."""

        if self._event_bindings:
            return

        bindings = [
            (Events.RECORDING_STARTED, lambda _data=None: self.set_recording(True)),
            (Events.RECORDING_STOPPED, lambda _data=None: self.set_recording(False)),
            (Events.RECORDING_ERROR, lambda _data=None: self.set_recording(False)),
            (
                Events.TRANSCRIPTION_REQUEST,
                lambda _data=None: self.set_transcribing(True),
            ),
            (
                Events.TRANSCRIPTION_STARTED,
                lambda _data=None: self.set_transcribing(True),
            ),
            (
                Events.TRANSCRIPTION_COMPLETED,
                lambda _data=None: self.set_transcribing(False),
            ),
            (
                Events.TRANSCRIPTION_ERROR,
                lambda _data=None: self.set_transcribing(False),
            ),
            (
                Events.AI_PROCESSING_STARTED,
                lambda _data=None: self.set_ai_processing(True),
            ),
            (
                Events.AI_PROCESSING_COMPLETED,
                lambda _data=None: self.set_ai_processing(False),
            ),
            (
                Events.AI_PROCESSING_ERROR,
                lambda _data=None: self.set_ai_processing(False),
            ),
            (
                Events.AI_PROCESSED_TEXT,
                lambda _data=None: self.set_ai_processing(False),
            ),
        ]

        for event_name, handler in bindings:
            listener_id = event_service.on(event_name, handler)
            self._event_bindings.append((event_name, listener_id))

    def unbind_events(self, event_service: Any) -> None:
        for event_name, listener_id in self._event_bindings:
            event_service.off(event_name, listener_id)
        self._event_bindings.clear()

    def can_run(
        self,
        *,
        quota_available: bool = True,
        network_available: bool = True,
    ) -> ReviewSchedulerDecision:
        now = self._clock()
        if self._recording:
            return ReviewSchedulerDecision(False, "recording_active")
        if self._transcribing:
            return ReviewSchedulerDecision(False, "transcription_active")
        if self._ai_processing:
            return ReviewSchedulerDecision(False, "ai_processing_active")
        if self._ui_busy:
            return ReviewSchedulerDecision(False, "ui_busy")
        if not quota_available:
            return ReviewSchedulerDecision(False, "quota_unavailable")
        if not network_available:
            return ReviewSchedulerDecision(False, "network_unavailable")
        if now - self._last_activity_at < self._config.idle_seconds:
            return ReviewSchedulerDecision(False, "not_idle_long_enough")
        return self._can_run_after_idle_checks(now)

    def _can_run_after_idle_checks(self, now: float) -> ReviewSchedulerDecision:
        if (
            self._last_run_at is not None
            and now - self._last_run_at < self._config.min_interval_seconds
        ):
            return ReviewSchedulerDecision(False, "min_interval_not_reached")
        if self._runs_this_session >= self._config.max_runs_per_session:
            return ReviewSchedulerDecision(False, "session_budget_exhausted")
        return ReviewSchedulerDecision(True, "idle")

    def can_run_now(
        self,
        *,
        quota_available: bool = True,
        network_available: bool = True,
    ) -> ReviewSchedulerDecision:
        if self._recording:
            return ReviewSchedulerDecision(False, "recording_active")
        if self._transcribing:
            return ReviewSchedulerDecision(False, "transcription_active")
        if self._ai_processing:
            return ReviewSchedulerDecision(False, "ai_processing_active")
        if self._ui_busy:
            return ReviewSchedulerDecision(False, "ui_busy")
        if not quota_available:
            return ReviewSchedulerDecision(False, "quota_unavailable")
        if not network_available:
            return ReviewSchedulerDecision(False, "network_unavailable")
        return ReviewSchedulerDecision(True, "manual")

    def _run_review_pass(
        self,
        *,
        count_run: bool,
        review_service: LLMReviewService | None = None,
    ) -> ReviewSchedulerRunResult:
        records = list(self._load_recent_records(self._config.max_records))
        if review_service is None:
            outcome = ReviewRunOutcome(
                review_source="local",
                suggestions=tuple(self._review_agent.analyze_records(records)),
            )
        else:
            outcome = review_service.review_records(records)
        job_id = self._review_storage.save_review_run(
            outcome.suggestions,
            record_limit=self._config.max_records,
            reviewed_count=len(records),
            review_source=outcome.review_source,
            provider=outcome.provider,
            model_id=outcome.model_id,
            prompt_version=outcome.prompt_version,
            fallback_reason=outcome.fallback_reason,
        )
        self._last_run_at = self._clock()
        if count_run:
            self._runs_this_session += 1
        return ReviewSchedulerRunResult(
            True,
            "completed",
            job_id=job_id,
            reviewed_record_count=len(records),
            suggestion_count=len(outcome.suggestions),
            review_source=outcome.review_source,
            provider=outcome.provider,
            model_id=outcome.model_id,
            prompt_version=outcome.prompt_version,
            fallback_reason=outcome.fallback_reason,
        )

    def run_once_if_idle(
        self,
        *,
        quota_available: bool = True,
        network_available: bool = True,
        review_service: LLMReviewService | None = None,
    ) -> ReviewSchedulerRunResult:
        decision = self.can_run(
            quota_available=quota_available,
            network_available=network_available,
        )
        if not decision.can_run:
            return ReviewSchedulerRunResult(False, decision.reason)
        return self._run_review_pass(count_run=True, review_service=review_service)

    def run_once_now(
        self,
        *,
        quota_available: bool = True,
        network_available: bool = True,
        review_service: LLMReviewService | None = None,
    ) -> ReviewSchedulerRunResult:
        decision = self.can_run_now(
            quota_available=quota_available,
            network_available=network_available,
        )
        if not decision.can_run:
            return ReviewSchedulerRunResult(False, decision.reason)
        return self._run_review_pass(count_run=False, review_service=review_service)
