import numpy as np

from sonicinput.core.services.events import Events
from sonicinput.core.services.streaming_coordinator import StreamingCoordinator


class _DummyEventService:
    def __init__(self) -> None:
        self.emitted = []

    def emit(self, event_name, data=None):
        self.emitted.append((event_name, data))


class _FakeRealtimeSession:
    def __init__(self, partial_results):
        self.partial_results = list(partial_results)
        self.calls = 0
        self.added_samples = []

    def add_samples(self, audio_data):
        self.added_samples.append(audio_data.copy())

    def get_partial_result(self):
        result = self.partial_results[self.calls]
        self.calls += 1
        return result


def test_realtime_text_accumulates_across_endpoint_resets():
    events = _DummyEventService()
    coordinator = StreamingCoordinator(event_service=events, streaming_mode="realtime")
    session = _FakeRealtimeSession(["第一句", "第二句"])
    coordinator.start_streaming(session)

    coordinator.add_realtime_audio(np.array([0.1], dtype=np.float32))
    coordinator.add_realtime_audio(np.array([0.2], dtype=np.float32))

    assert coordinator.get_realtime_text() == "第一句第二句"
    realtime_events = [
        data for event_name, data in events.emitted if event_name == Events.REALTIME_TEXT_UPDATED
    ]
    assert [event["text"] for event in realtime_events] == ["第一句", "第一句第二句"]


def test_realtime_text_treats_non_prefix_corrections_as_revisions():
    coordinator = StreamingCoordinator(event_service=_DummyEventService(), streaming_mode="realtime")
    session = _FakeRealtimeSession(["hello wrold", "hello world"])
    coordinator.start_streaming(session)

    coordinator.add_realtime_audio(np.array([0.1], dtype=np.float32))
    coordinator.add_realtime_audio(np.array([0.2], dtype=np.float32))

    assert coordinator.get_realtime_text() == "hello world"
