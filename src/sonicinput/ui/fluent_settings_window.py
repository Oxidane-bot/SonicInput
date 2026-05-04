"""Fluent QML settings host."""

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from ..utils import app_logger
from .qml_bridge import FluentSettingsViewModel, qml_path


class FluentSettingsWindow(QObject):
    """Host object for the Fluent QML settings window."""

    model_load_requested = Signal(str)
    model_unload_requested = Signal()
    model_test_requested = Signal()

    def __init__(self, ui_settings_service, ui_model_service=None):
        super().__init__()
        self.ui_settings_service = ui_settings_service
        self.ui_model_service = ui_model_service
        self.view_model = FluentSettingsViewModel(ui_settings_service)
        self.engine = QQmlApplicationEngine()
        self.engine.rootContext().setContextProperty(
            "settingsViewModel", self.view_model
        )
        self.engine.rootContext().setContextProperty("settingsHost", self)
        if QQuickStyle.name() != "FluentWinUI3":
            QQuickStyle.setStyle("FluentWinUI3")
        self.engine.load(QUrl.fromLocalFile(str(qml_path("FluentSettingsWindow.qml"))))
        roots = self.engine.rootObjects()
        if not roots:
            raise RuntimeError("Failed to load FluentSettingsWindow.qml")
        self.root = roots[0]

    @Slot(str)
    def requestModelLoad(self, model_name: str) -> None:
        self.model_load_requested.emit(model_name)

    @Slot()
    def requestModelUnload(self) -> None:
        self.model_unload_requested.emit()

    @Slot()
    def requestModelTest(self) -> None:
        self.model_test_requested.emit()

    def refresh_model_status(self) -> None:
        self.view_model.changed.emit()

    def show(self) -> None:
        self.root.show()

    def raise_(self) -> None:
        try:
            self.root.raise_()
        except AttributeError:
            pass

    def activateWindow(self) -> None:
        try:
            self.root.requestActivate()
        except Exception as e:
            app_logger.log_error(e, "fluent_settings_activate")

    def close(self) -> None:
        self.root.close()

    def isVisible(self) -> bool:
        return bool(self.root.isVisible())
