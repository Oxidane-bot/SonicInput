"""用户界面模块初始化"""

from .fluent_recording_overlay import FluentRecordingOverlay
from .fluent_settings_window import FluentSettingsWindow
from .main_window import MainWindow

SettingsWindow = FluentSettingsWindow
RecordingOverlay = FluentRecordingOverlay

__all__ = ["SettingsWindow", "RecordingOverlay", "MainWindow"]
