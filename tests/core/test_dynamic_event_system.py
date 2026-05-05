from sonicinput.core.services.dynamic_event_system import DynamicEventSystem


def test_listener_failures_are_counted_without_stopping_other_listeners():
    events = DynamicEventSystem()
    called = []

    def bad_listener(_data):
        called.append("bad")
        raise RuntimeError("listener failed")

    def good_listener(_data):
        called.append("good")

    bad_id = events.subscribe("test_event", bad_listener)
    events.subscribe("test_event", good_listener)

    events.emit("test_event", None)

    assert called == ["bad", "good"]
    bad_listener_record = next(
        listener for listener in events._listeners["test_event"] if listener.id == bad_id
    )
    assert bad_listener_record.failure_count == 1
    assert "listener failed" in bad_listener_record.last_error
    assert events.get_event_stats()["listener_failures"] == 1


def test_listener_cache_uses_new_listener_after_same_count_replacement():
    events = DynamicEventSystem()

    def first(_data):
        raise AssertionError("stale listener should not be called")

    def second(data):
        data.append("second")

    first_id = events.subscribe("cache_event", first)
    assert events._get_sorted_listeners("cache_event")[0].callback is first

    assert events.unsubscribe("cache_event", first_id) is True
    events.subscribe("cache_event", second)

    listeners = events._get_sorted_listeners("cache_event")
    called = []
    listeners[0].callback(called)

    assert called == ["second"]
