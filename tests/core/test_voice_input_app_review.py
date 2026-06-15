from sonicinput.core.services.config import ConfigKeys
from sonicinput.core.services.review_scheduler_service import ReviewSchedulerRunResult
from sonicinput.core.voice_input_app import VoiceInputApp


class _Config:
    def __init__(self, enabled):
        self.enabled = enabled

    def get_setting(self, key, default=None):
        if key == ConfigKeys.REVIEW_ENABLED:
            return self.enabled
        return default


class _Scheduler:
    def __init__(self):
        self.idle_calls = 0
        self.manual_calls = 0

    def run_once_if_idle(self, review_service=None):
        self.idle_calls += 1
        return ReviewSchedulerRunResult(True, "completed", suggestion_count=0)

    def run_once_now(self, review_service=None):
        self.manual_calls += 1
        return ReviewSchedulerRunResult(True, "completed", suggestion_count=0)


def _app_with_review(enabled):
    app = VoiceInputApp.__new__(VoiceInputApp)
    app.config = _Config(enabled)
    app._review_scheduler = _Scheduler()
    return app


def test_voice_input_app_idle_review_is_disabled_by_default_gate():
    app = _app_with_review(enabled=False)

    result = app.run_idle_review_once()

    assert result.ran is False
    assert result.reason == "review_disabled"
    assert app._review_scheduler.idle_calls == 0
    assert app._review_scheduler.manual_calls == 0


def test_voice_input_app_idle_review_delegates_when_enabled():
    app = _app_with_review(enabled=True)

    result = app.run_idle_review_once()

    assert result.ran is True
    assert result.reason == "completed"
    assert app._review_scheduler.idle_calls == 0
    assert app._review_scheduler.manual_calls == 1
