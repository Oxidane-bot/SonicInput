def test_event_bus_re_exports_events_for_smoke_test_compatibility():
    from sonicinput.core.services.event_bus import EventBus, Events

    bus = EventBus()
    calls = []
    bus.on(Events.RECORDING_STARTED, lambda data=None: calls.append(data))

    bus.emit(Events.RECORDING_STARTED)

    assert calls == [None]
