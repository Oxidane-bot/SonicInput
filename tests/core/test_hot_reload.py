"""Hot Reload System Tests

Tests for configuration hot reload functionality across all services.
This is a critical feature that allows users to change settings without restarting.
"""

import pytest
from unittest.mock import Mock
from typing import List, Dict, Any

from sonicinput.core.services.hot_reload_manager import HotReloadManager


class MockReloadableService:
    """Mock service implementing IHotReloadable for testing"""

    def __init__(self, name: str, config_deps: List[str]):
        self.name = name
        self.config_deps = config_deps
        self.reload_called = False
        self.reload_count = 0
        self.last_changed_keys = []
        self.last_new_config = {}
        self.should_succeed = True

    def get_config_dependencies(self) -> List[str]:
        return self.config_deps

    def on_config_changed(
        self, changed_keys: List[str], new_config: Dict[str, Any]
    ) -> bool:
        self.reload_called = True
        self.reload_count += 1
        self.last_changed_keys = changed_keys
        self.last_new_config = new_config
        return self.should_succeed


class TestHotReloadManager:
    """Test HotReloadManager basic functionality"""

    def test_manager_creation(self):
        """Test hot reload manager can be created"""
        manager = HotReloadManager()
        assert manager is not None
        assert manager._services == {}
        assert manager._config_to_services == {}

    def test_register_service(self):
        """Test registering a service for hot reload"""
        manager = HotReloadManager()
        service = MockReloadableService("test", ["hotkeys.keys"])

        manager.register_service("test", service)

        assert "test" in manager._services
        assert manager._services["test"] == service
        assert "hotkeys.keys" in manager._config_to_services
        assert "test" in manager._config_to_services["hotkeys.keys"]

    def test_register_multiple_services(self):
        """Test registering multiple services"""
        manager = HotReloadManager()
        service1 = MockReloadableService("audio", ["audio.device_id"])
        service2 = MockReloadableService("speech", ["transcription.provider"])

        manager.register_service("audio", service1)
        manager.register_service("speech", service2)

        assert len(manager._services) == 2
        assert "audio" in manager._services
        assert "speech" in manager._services

    def test_notify_config_changed_single_service(self):
        """Test notifying single service of config change"""
        manager = HotReloadManager()
        service = MockReloadableService("hotkey", ["hotkeys.keys"])
        manager.register_service("hotkey", service)

        new_config = {"hotkeys": {"keys": ["f9"]}}
        result = manager.notify_config_changed(["hotkeys.keys"], new_config)

        assert result is True
        assert service.reload_called is True
        assert service.reload_count == 1
        assert service.last_changed_keys == ["hotkeys.keys"]
        assert service.last_new_config == new_config

    def test_notify_config_changed_multiple_services(self):
        """Test notifying multiple services of config change"""
        manager = HotReloadManager()
        service1 = MockReloadableService("audio", ["audio.device_id"])
        service2 = MockReloadableService("speech", ["audio.device_id"])

        manager.register_service("audio", service1)
        manager.register_service("speech", service2)

        new_config = {"audio": {"device_id": 2}}
        result = manager.notify_config_changed(["audio.device_id"], new_config)

        assert result is True
        assert service1.reload_called is True
        assert service2.reload_called is True

    def test_reload_order_respected(self):
        """Test services are reloaded in correct order"""
        manager = HotReloadManager()
        reload_order = []

        # Create services that track reload order
        def make_tracking_service(name: str, deps: List[str]):
            service = MockReloadableService(name, deps)
            original_reload = service.on_config_changed

            def tracking_reload(changed_keys, new_config):
                reload_order.append(name)
                return original_reload(changed_keys, new_config)

            service.on_config_changed = tracking_reload
            return service

        # Register services in random order
        speech = make_tracking_service("speech", ["transcription.provider"])
        audio = make_tracking_service("audio", ["audio.device_id"])
        hotkey = make_tracking_service("hotkey", ["hotkeys.keys"])

        manager.register_service("speech", speech)
        manager.register_service("hotkey", hotkey)
        manager.register_service("audio", audio)

        # Trigger reload affecting all services
        new_config = {
            "audio": {"device_id": 2},
            "transcription": {"provider": "groq"},
            "hotkeys": {"keys": ["f9"]},
        }
        manager.notify_config_changed(
            ["audio.device_id", "transcription.provider", "hotkeys.keys"], new_config
        )

        # Verify reload order matches RELOAD_ORDER
        # Expected: audio -> speech -> hotkey (based on RELOAD_ORDER)
        assert reload_order == ["audio", "speech", "hotkey"]

    def test_notify_unaffected_config_change(self):
        """Test notifying of config change that doesn't affect any service"""
        manager = HotReloadManager()
        service = MockReloadableService("audio", ["audio.device_id"])
        manager.register_service("audio", service)

        # Change unrelated config
        new_config = {"logging": {"level": "DEBUG"}}
        result = manager.notify_config_changed(["logging.level"], new_config)

        assert result is True
        assert service.reload_called is False

    def test_reload_failure_stops_chain(self):
        """Test that reload failure stops the reload chain"""
        manager = HotReloadManager()
        service1 = MockReloadableService("audio", ["audio.device_id"])
        service2 = MockReloadableService("speech", ["audio.device_id"])

        # Make first service fail
        service1.should_succeed = False

        manager.register_service("audio", service1)
        manager.register_service("speech", service2)

        new_config = {"audio": {"device_id": 2}}
        result = manager.notify_config_changed(["audio.device_id"], new_config)

        assert result is False
        assert service1.reload_called is True
        # Speech should not be reloaded because audio failed
        assert service2.reload_called is False

    def test_reload_exception_handled(self):
        """Test that exceptions during reload are handled gracefully"""
        manager = HotReloadManager()
        service = MockReloadableService("audio", ["audio.device_id"])

        # Make service raise exception
        def raise_exception(changed_keys, new_config):
            raise RuntimeError("Reload failed")

        service.on_config_changed = raise_exception
        manager.register_service("audio", service)

        new_config = {"audio": {"device_id": 2}}
        result = manager.notify_config_changed(["audio.device_id"], new_config)

        assert result is False


class TestHotkeyHotReload:
    """Test hotkey configuration hot reload"""

    @pytest.fixture
    def mock_hotkey_service(self):
        """Create mock hotkey service"""
        service = Mock()
        service.get_config_dependencies.return_value = [
            "hotkeys.keys",
            "hotkeys.backend",
        ]
        service.on_config_changed.return_value = True
        return service

    def test_hotkey_change_triggers_reload(self, mock_hotkey_service):
        """Test changing hotkey triggers service reload"""
        manager = HotReloadManager()
        manager.register_service("hotkey", mock_hotkey_service)

        new_config = {"hotkeys": {"keys": ["f9", "ctrl+shift+v"]}}
        result = manager.notify_config_changed(["hotkeys.keys"], new_config)

        assert result is True
        mock_hotkey_service.on_config_changed.assert_called_once()
        call_args = mock_hotkey_service.on_config_changed.call_args
        assert call_args[0][0] == ["hotkeys.keys"]
        assert call_args[0][1] == new_config

    def test_hotkey_backend_change_triggers_reload(self, mock_hotkey_service):
        """Test changing hotkey backend triggers service reload"""
        manager = HotReloadManager()
        manager.register_service("hotkey", mock_hotkey_service)

        new_config = {"hotkeys": {"backend": "win32"}}
        result = manager.notify_config_changed(["hotkeys.backend"], new_config)

        assert result is True
        mock_hotkey_service.on_config_changed.assert_called_once()


class TestAudioDeviceHotReload:
    """Test audio device configuration hot reload"""

    @pytest.fixture
    def mock_audio_service(self):
        """Create mock audio service"""
        service = Mock()
        service.get_config_dependencies.return_value = [
            "audio.device_id",
            "audio.sample_rate",
        ]
        service.on_config_changed.return_value = True
        return service

    def test_audio_device_change_triggers_reload(self, mock_audio_service):
        """Test changing audio device triggers service reload"""
        manager = HotReloadManager()
        manager.register_service("audio", mock_audio_service)

        new_config = {"audio": {"device_id": 2}}
        result = manager.notify_config_changed(["audio.device_id"], new_config)

        assert result is True
        mock_audio_service.on_config_changed.assert_called_once()

    def test_audio_sample_rate_change_triggers_reload(self, mock_audio_service):
        """Test changing sample rate triggers service reload"""
        manager = HotReloadManager()
        manager.register_service("audio", mock_audio_service)

        new_config = {"audio": {"sample_rate": 48000}}
        result = manager.notify_config_changed(["audio.sample_rate"], new_config)

        assert result is True
        mock_audio_service.on_config_changed.assert_called_once()


class TestTranscriptionProviderHotReload:
    """Test transcription provider configuration hot reload"""

    @pytest.fixture
    def mock_speech_service(self):
        """Create mock speech service"""
        service = Mock()
        service.get_config_dependencies.return_value = [
            "transcription.provider",
            "transcription.local.model",
            "transcription.groq.api_key",
        ]
        service.on_config_changed.return_value = True
        return service

    def test_provider_change_triggers_reload(self, mock_speech_service):
        """Test changing transcription provider triggers service reload"""
        manager = HotReloadManager()
        manager.register_service("speech", mock_speech_service)

        new_config = {"transcription": {"provider": "groq"}}
        result = manager.notify_config_changed(["transcription.provider"], new_config)

        assert result is True
        mock_speech_service.on_config_changed.assert_called_once()

    def test_local_model_change_triggers_reload(self, mock_speech_service):
        """Test changing local model triggers service reload"""
        manager = HotReloadManager()
        manager.register_service("speech", mock_speech_service)

        new_config = {"transcription": {"local": {"model": "zipformer"}}}
        result = manager.notify_config_changed(
            ["transcription.local.model"], new_config
        )

        assert result is True
        mock_speech_service.on_config_changed.assert_called_once()

    def test_groq_api_key_change_triggers_reload(self, mock_speech_service):
        """Test changing Groq API key triggers service reload"""
        manager = HotReloadManager()
        manager.register_service("speech", mock_speech_service)

        new_config = {"transcription": {"groq": {"api_key": "new-key"}}}
        result = manager.notify_config_changed(
            ["transcription.groq.api_key"], new_config
        )

        assert result is True
        mock_speech_service.on_config_changed.assert_called_once()


class TestAIProviderHotReload:
    """Test AI provider configuration hot reload"""

    @pytest.fixture
    def mock_ai_service(self):
        """Create mock AI service"""
        service = Mock()
        service.get_config_dependencies.return_value = [
            "ai.enabled",
            "ai.provider",
            "ai.openrouter.api_key",
        ]
        service.on_config_changed.return_value = True
        return service

    def test_ai_enabled_change_triggers_reload(self, mock_ai_service):
        """Test toggling AI enabled triggers service reload"""
        manager = HotReloadManager()
        manager.register_service("ai", mock_ai_service)

        new_config = {"ai": {"enabled": False}}
        result = manager.notify_config_changed(["ai.enabled"], new_config)

        assert result is True
        mock_ai_service.on_config_changed.assert_called_once()

    def test_ai_provider_change_triggers_reload(self, mock_ai_service):
        """Test changing AI provider triggers service reload"""
        manager = HotReloadManager()
        manager.register_service("ai", mock_ai_service)

        new_config = {"ai": {"provider": "groq"}}
        result = manager.notify_config_changed(["ai.provider"], new_config)

        assert result is True
        mock_ai_service.on_config_changed.assert_called_once()


class TestMultiServiceHotReload:
    """Test hot reload scenarios affecting multiple services"""

    def test_audio_device_affects_audio_and_speech(self):
        """Test audio device change affects both audio and speech services"""
        manager = HotReloadManager()

        audio_service = MockReloadableService("audio", ["audio.device_id"])
        speech_service = MockReloadableService("speech", ["audio.device_id"])

        manager.register_service("audio", audio_service)
        manager.register_service("speech", speech_service)

        new_config = {"audio": {"device_id": 2}}
        result = manager.notify_config_changed(["audio.device_id"], new_config)

        assert result is True
        assert audio_service.reload_called is True
        assert speech_service.reload_called is True
        # Audio should reload before speech (based on RELOAD_ORDER)
        assert audio_service.reload_count == 1
        assert speech_service.reload_count == 1

    def test_multiple_config_changes_at_once(self):
        """Test multiple config changes trigger correct services"""
        manager = HotReloadManager()

        audio_service = MockReloadableService("audio", ["audio.device_id"])
        speech_service = MockReloadableService("speech", ["transcription.provider"])
        hotkey_service = MockReloadableService("hotkey", ["hotkeys.keys"])

        manager.register_service("audio", audio_service)
        manager.register_service("speech", speech_service)
        manager.register_service("hotkey", hotkey_service)

        new_config = {
            "audio": {"device_id": 2},
            "transcription": {"provider": "groq"},
            "hotkeys": {"keys": ["f9"]},
        }
        result = manager.notify_config_changed(
            ["audio.device_id", "transcription.provider", "hotkeys.keys"], new_config
        )

        assert result is True
        assert audio_service.reload_called is True
        assert speech_service.reload_called is True
        assert hotkey_service.reload_called is True
