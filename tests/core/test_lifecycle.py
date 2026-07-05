"""Lifecycle Management Tests

Tests for LifecycleComponent base class that manages component start/stop lifecycle.
This is a critical foundation for all stateful services in the application.
"""

import pytest

from sonicinput.core.base.lifecycle_component import LifecycleComponent, ComponentState


class MockLifecycleComponent(LifecycleComponent):
    """Mock component for testing lifecycle behavior"""

    def __init__(self, name: str = "TestComponent"):
        super().__init__(name)
        self.start_called = False
        self.stop_called = False
        self.start_count = 0
        self.stop_count = 0
        self.should_start_succeed = True
        self.should_stop_succeed = True
        self.start_exception = None
        self.stop_exception = None

    def _do_start(self) -> bool:
        self.start_called = True
        self.start_count += 1

        if self.start_exception:
            raise self.start_exception

        return self.should_start_succeed

    def _do_stop(self) -> bool:
        self.stop_called = True
        self.stop_count += 1

        if self.stop_exception:
            raise self.stop_exception

        return self.should_stop_succeed


class TestLifecycleComponentBasics:
    """Test basic lifecycle component functionality"""

    def test_component_creation(self):
        """Test component can be created"""
        component = MockLifecycleComponent("TestComponent")

        assert component is not None
        assert component.component_name == "TestComponent"
        assert component.state == ComponentState.STOPPED
        assert component.is_running is False

    def test_initial_state_is_stopped(self):
        """Test component starts in STOPPED state"""
        component = MockLifecycleComponent()

        assert component.state == ComponentState.STOPPED
        assert component.is_running is False

    def test_component_name_property(self):
        """Test component name property"""
        component = MockLifecycleComponent("MyService")

        assert component.component_name == "MyService"


class TestLifecycleStartStop:
    """Test start and stop operations"""

    def test_start_component(self):
        """Test starting a component"""
        component = MockLifecycleComponent()

        result = component.start()

        assert result is True
        assert component.start_called is True
        assert component.start_count == 1
        assert component.state == ComponentState.RUNNING
        assert component.is_running is True

    def test_stop_component(self):
        """Test stopping a component"""
        component = MockLifecycleComponent()
        component.start()

        result = component.stop()

        assert result is True
        assert component.stop_called is True
        assert component.stop_count == 1
        assert component.state == ComponentState.STOPPED
        assert component.is_running is False

    def test_start_stop_cycle(self):
        """Test complete start-stop cycle"""
        component = MockLifecycleComponent()

        # Start
        assert component.start() is True
        assert component.state == ComponentState.RUNNING

        # Stop
        assert component.stop() is True
        assert component.state == ComponentState.STOPPED

        # Verify counts
        assert component.start_count == 1
        assert component.stop_count == 1

    def test_multiple_start_stop_cycles(self):
        """Test multiple start-stop cycles"""
        component = MockLifecycleComponent()

        # Cycle 1
        component.start()
        component.stop()

        # Cycle 2
        component.start()
        component.stop()

        # Cycle 3
        component.start()
        component.stop()

        assert component.start_count == 3
        assert component.stop_count == 3
        assert component.state == ComponentState.STOPPED


class TestLifecycleIdempotency:
    """Test idempotent start/stop operations"""

    def test_start_when_already_running(self):
        """Test starting an already running component is idempotent"""
        component = MockLifecycleComponent()
        component.start()

        # Start again
        result = component.start()

        assert result is True
        assert component.start_count == 1  # Should not call _do_start again
        assert component.state == ComponentState.RUNNING

    def test_stop_when_already_stopped(self):
        """Test stopping an already stopped component is idempotent"""
        component = MockLifecycleComponent()

        # Stop without starting
        result = component.stop()

        assert result is True
        assert component.stop_count == 0  # Should not call _do_stop
        assert component.state == ComponentState.STOPPED

    def test_multiple_starts_without_stop(self):
        """Test multiple start calls without stop"""
        component = MockLifecycleComponent()

        component.start()
        component.start()
        component.start()

        assert component.start_count == 1  # Only first start should execute
        assert component.state == ComponentState.RUNNING

    def test_multiple_stops_without_start(self):
        """Test multiple stop calls without start"""
        component = MockLifecycleComponent()

        component.stop()
        component.stop()
        component.stop()

        assert component.stop_count == 0  # No stops should execute
        assert component.state == ComponentState.STOPPED


class TestLifecycleStateTransitions:
    """Test state transitions"""

    def test_stopped_to_running_transition(self):
        """Test STOPPED -> RUNNING transition"""
        component = MockLifecycleComponent()

        assert component.state == ComponentState.STOPPED
        component.start()
        assert component.state == ComponentState.RUNNING

    def test_running_to_stopped_transition(self):
        """Test RUNNING -> STOPPED transition"""
        component = MockLifecycleComponent()
        component.start()

        assert component.state == ComponentState.RUNNING
        component.stop()
        assert component.state == ComponentState.STOPPED

    def test_stopped_to_error_on_start_failure(self):
        """Test STOPPED -> ERROR transition on start failure"""
        component = MockLifecycleComponent()
        component.should_start_succeed = False

        result = component.start()

        assert result is False
        assert component.state == ComponentState.ERROR

    def test_running_to_error_on_stop_failure(self):
        """Test RUNNING -> ERROR transition on stop failure"""
        component = MockLifecycleComponent()
        component.start()
        component.should_stop_succeed = False

        result = component.stop()

        assert result is False
        assert component.state == ComponentState.ERROR

    def test_error_state_persists(self):
        """Test ERROR state persists until successful operation"""
        component = MockLifecycleComponent()
        component.should_start_succeed = False

        # First start fails
        component.start()
        assert component.state == ComponentState.ERROR

        # Try to start again (should still fail)
        component.start()
        assert component.state == ComponentState.ERROR


class TestLifecycleErrorHandling:
    """Test error handling in lifecycle operations"""

    def test_start_failure_returns_false(self):
        """Test start failure returns False"""
        component = MockLifecycleComponent()
        component.should_start_succeed = False

        result = component.start()

        assert result is False
        assert component.state == ComponentState.ERROR

    def test_stop_failure_returns_false(self):
        """Test stop failure returns False"""
        component = MockLifecycleComponent()
        component.start()
        component.should_stop_succeed = False

        result = component.stop()

        assert result is False
        assert component.state == ComponentState.ERROR

    def test_start_exception_handled(self):
        """Test exception during start is handled gracefully"""
        component = MockLifecycleComponent()
        component.start_exception = RuntimeError("Start failed")

        result = component.start()

        assert result is False
        assert component.state == ComponentState.ERROR

    def test_stop_exception_handled(self):
        """Test exception during stop is handled gracefully"""
        component = MockLifecycleComponent()
        component.start()
        component.stop_exception = RuntimeError("Stop failed")

        result = component.stop()

        assert result is False
        assert component.state == ComponentState.ERROR

    def test_start_exception_does_not_crash(self):
        """Test start exception doesn't crash the application"""
        component = MockLifecycleComponent()
        component.start_exception = Exception("Critical error")

        # Should not raise exception
        try:
            result = component.start()
            assert result is False
        except Exception:
            pytest.fail("Start should not raise exception")

    def test_stop_exception_does_not_crash(self):
        """Test stop exception doesn't crash the application"""
        component = MockLifecycleComponent()
        component.start()
        component.stop_exception = Exception("Critical error")

        # Should not raise exception
        try:
            result = component.stop()
            assert result is False
        except Exception:
            pytest.fail("Stop should not raise exception")


class TestLifecycleWithResources:
    """Test lifecycle with resource management"""

    def test_resource_acquisition_on_start(self):
        """Test resources are acquired on start"""

        class ResourceComponent(LifecycleComponent):
            def __init__(self):
                super().__init__("ResourceComponent")
                self.resource = None

            def _do_start(self) -> bool:
                self.resource = "acquired_resource"
                return True

            def _do_stop(self) -> bool:
                self.resource = None
                return True

        component = ResourceComponent()
        component.start()

        assert component.resource == "acquired_resource"

    def test_resource_release_on_stop(self):
        """Test resources are released on stop"""

        class ResourceComponent(LifecycleComponent):
            def __init__(self):
                super().__init__("ResourceComponent")
                self.resource = None

            def _do_start(self) -> bool:
                self.resource = "acquired_resource"
                return True

            def _do_stop(self) -> bool:
                self.resource = None
                return True

        component = ResourceComponent()
        component.start()
        component.stop()

        assert component.resource is None

    def test_resource_cleanup_on_failed_start(self):
        """Test resources are cleaned up on failed start"""

        class ResourceComponent(LifecycleComponent):
            def __init__(self):
                super().__init__("ResourceComponent")
                self.resource = None
                self.cleanup_called = False

            def _do_start(self) -> bool:
                self.resource = "acquired_resource"
                # Simulate failure after acquiring resource
                self.cleanup_called = True
                self.resource = None
                return False

            def _do_stop(self) -> bool:
                return True

        component = ResourceComponent()
        result = component.start()

        assert result is False
        assert component.cleanup_called is True
        assert component.resource is None


class TestLifecycleComponentIntegration:
    """Test lifecycle component integration scenarios"""

    def test_multiple_components_start_stop(self):
        """Test multiple components can be started and stopped"""
        component1 = MockLifecycleComponent("Component1")
        component2 = MockLifecycleComponent("Component2")
        component3 = MockLifecycleComponent("Component3")

        # Start all
        assert component1.start() is True
        assert component2.start() is True
        assert component3.start() is True

        # All should be running
        assert component1.is_running is True
        assert component2.is_running is True
        assert component3.is_running is True

        # Stop all
        assert component1.stop() is True
        assert component2.stop() is True
        assert component3.stop() is True

        # All should be stopped
        assert component1.is_running is False
        assert component2.is_running is False
        assert component3.is_running is False

    def test_dependent_components_start_order(self):
        """Test dependent components can be started in order"""
        start_order = []

        class OrderedComponent(LifecycleComponent):
            def __init__(self, name: str):
                super().__init__(name)

            def _do_start(self) -> bool:
                start_order.append(self.component_name)
                return True

            def _do_stop(self) -> bool:
                return True

        comp1 = OrderedComponent("First")
        comp2 = OrderedComponent("Second")
        comp3 = OrderedComponent("Third")

        # Start in order
        comp1.start()
        comp2.start()
        comp3.start()

        assert start_order == ["First", "Second", "Third"]

    def test_component_failure_does_not_affect_others(self):
        """Test one component failure doesn't affect others"""
        component1 = MockLifecycleComponent("Component1")
        component2 = MockLifecycleComponent("Component2")
        component2.should_start_succeed = False
        component3 = MockLifecycleComponent("Component3")

        # Start all
        result1 = component1.start()
        result2 = component2.start()
        result3 = component3.start()

        # Component 2 should fail, others succeed
        assert result1 is True
        assert result2 is False
        assert result3 is True

        assert component1.state == ComponentState.RUNNING
        assert component2.state == ComponentState.ERROR
        assert component3.state == ComponentState.RUNNING


class TestLifecycleComponentProperties:
    """Test lifecycle component properties"""

    def test_is_running_property(self):
        """Test is_running property reflects state correctly"""
        component = MockLifecycleComponent()

        assert component.is_running is False

        component.start()
        assert component.is_running is True

        component.stop()
        assert component.is_running is False

    def test_state_property(self):
        """Test state property returns correct state"""
        component = MockLifecycleComponent()

        assert component.state == ComponentState.STOPPED

        component.start()
        assert component.state == ComponentState.RUNNING

        component.stop()
        assert component.state == ComponentState.STOPPED

    def test_component_name_property(self):
        """Test component_name property returns correct name"""
        component = MockLifecycleComponent("MyComponent")

        assert component.component_name == "MyComponent"

    def test_state_enum_values(self):
        """Test ComponentState enum has correct values"""
        assert ComponentState.STOPPED.value == "stopped"
        assert ComponentState.RUNNING.value == "running"
        assert ComponentState.ERROR.value == "error"
