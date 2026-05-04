"""Fluent QML about window host."""

from PySide6.QtCore import QObject, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from .. import __version__
from ..utils import app_logger
from .qml_bridge import qml_path


class FluentAboutWindow(QObject):
    """Host object for the Fluent QML about window."""

    def __init__(self):
        super().__init__()
        self.engine = QQmlApplicationEngine()
        self.engine.rootContext().setContextProperty("appVersion", __version__)
        if QQuickStyle.name() != "FluentWinUI3":
            QQuickStyle.setStyle("FluentWinUI3")
        self.engine.load(QUrl.fromLocalFile(str(qml_path("FluentAboutWindow.qml"))))
        roots = self.engine.rootObjects()
        if not roots:
            raise RuntimeError("Failed to load FluentAboutWindow.qml")
        self.root = roots[0]

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
            app_logger.log_error(e, "fluent_about_activate")

    def close(self) -> None:
        self.root.close()

    def isVisible(self) -> bool:
        return bool(self.root.isVisible())
