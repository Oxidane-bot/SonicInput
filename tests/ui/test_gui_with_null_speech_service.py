from __future__ import annotations

from unittest.mock import MagicMock, Mock

import pytest

from sonicinput.core.services.ui_services import UIModelService, UISettingsService
from sonicinput.speech.null_speech_service import NullSpeechService
from sonicinput.ui.main_window import MainWindow


@pytest.mark.gui
def test_settings_window_opens_with_null_speech_service(
    qtbot, mock_config_service
) -> None:
    speech_service = NullSpeechService("local engine unavailable")

    event_service = MagicMock()
    event_service.on = Mock()
    event_service.emit = Mock()

    history_service = MagicMock()
    history_service.get_records = Mock(return_value=[])
    history_service.get_record_by_id = Mock(return_value=None)
    history_service.search_records = Mock(return_value=[])
    history_service.get_records_keyset = Mock(return_value=[])
    history_service.search_records_keyset = Mock(return_value=[])
    history_service.get_total_count = Mock(return_value=0)
    history_service.get_aggregate_stats = Mock(return_value=(0, 0.0, 0))

    ui_settings_service = UISettingsService(
        config_service=mock_config_service,
        event_service=event_service,
        history_service=history_service,
        transcription_service=speech_service,
        ai_processing_controller=None,
        localization_service=None,
        container=None,
    )
    ui_model_service = UIModelService(speech_service)

    window = MainWindow(
        ui_main_service=None,
        ui_settings_service=ui_settings_service,
        ui_model_service=ui_model_service,
    )
    qtbot.addWidget(window)

    window.show()
    qtbot.wait(50)

    window.show_settings()
    qtbot.wait(50)

    settings_window = getattr(window, "_settings_window", None)
    assert settings_window is not None
    assert settings_window.isVisible() is True
