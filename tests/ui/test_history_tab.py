from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QDialog

import sonicinput.ui.settings_tabs.history_tab as history_tab_module
from sonicinput.ui.settings_tabs.history_tab import HistoryTab


@pytest.mark.gui
def test_history_tab_refreshes_after_detail_dialog_accepts(qtbot, monkeypatch):
    config_manager = MagicMock()
    config_manager.get_history_service.return_value = MagicMock()

    tab = HistoryTab(config_manager, None)
    qtbot.addWidget(tab.create())
    tab.current_records = [SimpleNamespace(id="record-1")]

    class FakeDialog:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

    reload_calls = []
    monkeypatch.setattr(history_tab_module, "HistoryDetailDialog", FakeDialog)
    monkeypatch.setattr(tab, "_load_history", lambda: reload_calls.append(True))

    tab._show_detail_dialog(tab.current_records[0])

    assert reload_calls == [True]
