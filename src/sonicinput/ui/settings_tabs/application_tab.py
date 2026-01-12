"""应用设置标签页 (合并 General + UI)"""

from typing import Any, Dict

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from .base_tab import BaseSettingsTab


class ApplicationTab(BaseSettingsTab):
    """应用设置标签页

    包含：
    - 应用设置（开机启动、最小化启动、托盘通知）
    - 日志设置（日志级别、控制台输出、日志大小限制）
    - 配置管理（导出、导入、重置）
    - 录音悬浮窗设置
    - 主题设置
    """

    def _setup_ui(self) -> None:
        """设置UI"""
        layout = QVBoxLayout(self.widget)

        # 应用设置组
        app_group = QGroupBox("Application Settings")
        app_layout = QFormLayout(app_group)
        self.app_group = app_group
        self.app_layout = app_layout

        # 最小化启动
        self.start_minimized_checkbox = QCheckBox("Start minimized to tray")
        app_layout.addRow("Startup:", self.start_minimized_checkbox)

        # 托盘通知
        self.tray_notifications_checkbox = QCheckBox("Show tray notifications")
        app_layout.addRow("Notifications:", self.tray_notifications_checkbox)

        # UI language
        self.language_combo = QComboBox()
        self.language_combo.addItem("System (Auto)", "auto")
        self.language_combo.addItem("English", "en-US")
        self.language_combo.addItem("Simplified Chinese", "zh-CN")
        app_layout.addRow("Language:", self.language_combo)

        layout.addWidget(app_group)

        # 悬浮窗设置组
        overlay_group = QGroupBox("Recording Overlay")
        overlay_layout = QFormLayout(overlay_group)
        self.overlay_group = overlay_group
        self.overlay_layout = overlay_layout

        # 显示悬浮窗
        self.show_overlay_checkbox = QCheckBox("Show recording overlay")
        overlay_layout.addRow("", self.show_overlay_checkbox)

        # 悬浮窗位置
        self.overlay_position_combo = QComboBox()
        self.overlay_position_combo.addItem("center", "center")
        self.overlay_position_combo.addItem("top_left", "top_left")
        self.overlay_position_combo.addItem("top_right", "top_right")
        self.overlay_position_combo.addItem("bottom_left", "bottom_left")
        self.overlay_position_combo.addItem("bottom_right", "bottom_right")
        overlay_layout.addRow("Position:", self.overlay_position_combo)

        # 始终置顶
        self.overlay_on_top_checkbox = QCheckBox("Always on top")
        overlay_layout.addRow("", self.overlay_on_top_checkbox)

        layout.addWidget(overlay_group)

        # 主题颜色设置组
        theme_group = QGroupBox("Theme Color")
        theme_layout = QFormLayout(theme_group)
        self.theme_group = theme_group
        self.theme_layout = theme_layout

        self.theme_color_combo = QComboBox()
        self.theme_color_combo.addItem("Cyan", "cyan")
        self.theme_color_combo.addItem("Blue", "blue")
        self.theme_color_combo.addItem("Teal", "teal")
        self.theme_color_combo.addItem("Purple", "purple")
        self.theme_color_combo.addItem("Red", "red")
        self.theme_color_combo.addItem("Pink", "pink")
        self.theme_color_combo.addItem("Amber", "amber")
        theme_layout.addRow("Color Theme:", self.theme_color_combo)

        # 添加提示
        self.theme_hint = QLabel("Changing theme requires application restart")
        self.theme_hint.setStyleSheet(
            "color: #888; font-size: 10px; font-style: italic;"
        )
        theme_layout.addRow("", self.theme_hint)

        layout.addWidget(theme_group)

        # 日志设置组
        log_group = QGroupBox("Logging Settings")
        log_layout = QFormLayout(log_group)
        self.log_group = log_group
        self.log_layout = log_layout

        # 日志级别
        self.log_level_combo = QComboBox()
        self.log_level_combo.setObjectName("log_level_combo")
        self.log_level_combo.addItem("DEBUG", "DEBUG")
        self.log_level_combo.addItem("INFO", "INFO")
        self.log_level_combo.addItem("WARNING", "WARNING")
        self.log_level_combo.addItem("ERROR", "ERROR")
        log_layout.addRow("Log Level:", self.log_level_combo)

        # 控制台输出
        self.console_output_checkbox = QCheckBox("Show console output (debug mode)")
        log_layout.addRow("", self.console_output_checkbox)

        # 日志大小限制
        self.max_log_size_spinbox = QSpinBox()
        self.max_log_size_spinbox.setRange(1, 100)
        self.max_log_size_spinbox.setSuffix(" MB")
        log_layout.addRow("Max log file size:", self.max_log_size_spinbox)

        layout.addWidget(log_group)

        # 配置管理组
        config_group = QGroupBox("Configuration Management")
        config_layout = QVBoxLayout(config_group)
        self.config_group = config_group

        config_buttons_layout = QHBoxLayout()

        self.export_config_button = QPushButton("Export Settings")
        self.export_config_button.setObjectName("export_config_btn")
        self.export_config_button.clicked.connect(self._export_config)
        config_buttons_layout.addWidget(self.export_config_button)

        self.import_config_button = QPushButton("Import Settings")
        self.import_config_button.setObjectName("import_config_btn")
        self.import_config_button.clicked.connect(self._import_config)
        config_buttons_layout.addWidget(self.import_config_button)

        self.reset_config_button = QPushButton("Reset to Defaults")
        self.reset_config_button.setObjectName("reset_config_btn")
        self.reset_config_button.clicked.connect(self._reset_config)
        config_buttons_layout.addWidget(self.reset_config_button)

        config_layout.addLayout(config_buttons_layout)

        layout.addWidget(config_group)

        layout.addStretch()

        self.retranslate_ui()

        # 保存控件引用
        self.controls = {
            "start_minimized": self.start_minimized_checkbox,
            "tray_notifications": self.tray_notifications_checkbox,
            "language": self.language_combo,
            "show_overlay": self.show_overlay_checkbox,
            "overlay_position": self.overlay_position_combo,
            "overlay_on_top": self.overlay_on_top_checkbox,
            "theme_color": self.theme_color_combo,
            "log_level": self.log_level_combo,
            "console_output": self.console_output_checkbox,
            "max_log_size": self.max_log_size_spinbox,
        }

        # 暴露控件到parent_window
        self.parent_window.start_minimized_checkbox = self.start_minimized_checkbox
        self.parent_window.tray_notifications_checkbox = (
            self.tray_notifications_checkbox
        )
        self.parent_window.language_combo = self.language_combo
        self.parent_window.show_overlay_checkbox = self.show_overlay_checkbox
        self.parent_window.overlay_position_combo = self.overlay_position_combo
        self.parent_window.overlay_on_top_checkbox = self.overlay_on_top_checkbox
        self.parent_window.theme_color_combo = self.theme_color_combo
        self.parent_window.log_level_combo = self.log_level_combo
        self.parent_window.console_output_checkbox = self.console_output_checkbox
        self.parent_window.max_log_size_spinbox = self.max_log_size_spinbox

    def retranslate_ui(self) -> None:
        """Update UI text for the current language."""

        def set_label(layout, field, value):
            label = layout.labelForField(field)
            if label:
                label.setText(value)

        self.app_group.setTitle(
            QCoreApplication.translate("ApplicationTab", "Application Settings")
        )
        set_label(
            self.app_layout,
            self.start_minimized_checkbox,
            QCoreApplication.translate("ApplicationTab", "Startup:"),
        )
        set_label(
            self.app_layout,
            self.tray_notifications_checkbox,
            QCoreApplication.translate("ApplicationTab", "Notifications:"),
        )
        set_label(
            self.app_layout,
            self.language_combo,
            QCoreApplication.translate("ApplicationTab", "Language:"),
        )
        self.start_minimized_checkbox.setText(
            QCoreApplication.translate("ApplicationTab", "Start minimized to tray")
        )
        self.tray_notifications_checkbox.setText(
            QCoreApplication.translate("ApplicationTab", "Show tray notifications")
        )

        self.overlay_group.setTitle(
            QCoreApplication.translate("ApplicationTab", "Recording Overlay")
        )
        set_label(
            self.overlay_layout,
            self.overlay_position_combo,
            QCoreApplication.translate("ApplicationTab", "Position:"),
        )
        self.show_overlay_checkbox.setText(
            QCoreApplication.translate("ApplicationTab", "Show recording overlay")
        )
        self.overlay_on_top_checkbox.setText(
            QCoreApplication.translate("ApplicationTab", "Always on top")
        )

        self.theme_group.setTitle(
            QCoreApplication.translate("ApplicationTab", "Theme Color")
        )
        set_label(
            self.theme_layout,
            self.theme_color_combo,
            QCoreApplication.translate("ApplicationTab", "Color Theme:"),
        )
        self.theme_hint.setText(
            QCoreApplication.translate(
                "ApplicationTab", "Changing theme requires application restart"
            )
        )

        self.log_group.setTitle(
            QCoreApplication.translate("ApplicationTab", "Logging Settings")
        )
        set_label(
            self.log_layout,
            self.log_level_combo,
            QCoreApplication.translate("ApplicationTab", "Log Level:"),
        )
        set_label(
            self.log_layout,
            self.max_log_size_spinbox,
            QCoreApplication.translate("ApplicationTab", "Max log file size:"),
        )
        self.max_log_size_spinbox.setSuffix(
            QCoreApplication.translate("ApplicationTab", " MB")
        )
        self.console_output_checkbox.setText(
            QCoreApplication.translate(
                "ApplicationTab", "Show console output (debug mode)"
            )
        )

        self.config_group.setTitle(
            QCoreApplication.translate("ApplicationTab", "Configuration Management")
        )
        self.export_config_button.setText(
            QCoreApplication.translate("ApplicationTab", "Export Settings")
        )
        self.import_config_button.setText(
            QCoreApplication.translate("ApplicationTab", "Import Settings")
        )
        self.reset_config_button.setText(
            QCoreApplication.translate("ApplicationTab", "Reset to Defaults")
        )

        # Combo box item text
        language_texts = [
            QCoreApplication.translate("ApplicationTab", "System (Auto)"),
            QCoreApplication.translate("ApplicationTab", "English"),
            QCoreApplication.translate("ApplicationTab", "Simplified Chinese"),
        ]
        for index, text_value in enumerate(language_texts):
            if index < self.language_combo.count():
                self.language_combo.setItemText(index, text_value)

        theme_texts = [
            QCoreApplication.translate("ApplicationTab", "Cyan"),
            QCoreApplication.translate("ApplicationTab", "Blue"),
            QCoreApplication.translate("ApplicationTab", "Teal"),
            QCoreApplication.translate("ApplicationTab", "Purple"),
            QCoreApplication.translate("ApplicationTab", "Red"),
            QCoreApplication.translate("ApplicationTab", "Pink"),
            QCoreApplication.translate("ApplicationTab", "Amber"),
        ]
        for index, text_value in enumerate(theme_texts):
            if index < self.theme_color_combo.count():
                self.theme_color_combo.setItemText(index, text_value)

        overlay_texts = [
            QCoreApplication.translate("ApplicationTab", "Center"),
            QCoreApplication.translate("ApplicationTab", "Top Left"),
            QCoreApplication.translate("ApplicationTab", "Top Right"),
            QCoreApplication.translate("ApplicationTab", "Bottom Left"),
            QCoreApplication.translate("ApplicationTab", "Bottom Right"),
        ]
        for index, text_value in enumerate(overlay_texts):
            if index < self.overlay_position_combo.count():
                self.overlay_position_combo.setItemText(index, text_value)

    def load_config(self, config: Dict[str, Any]) -> None:
        """从配置加载UI状态

        Args:
            config: 完整配置字典
        """
        ui_config = config.get("ui", {})

        # 加载应用设置
        self.start_minimized_checkbox.setChecked(ui_config.get("start_minimized", True))
        self.tray_notifications_checkbox.setChecked(
            ui_config.get("tray_notifications", True)
        )

        ui_language = ui_config.get("language", "auto")
        language_index = self.language_combo.findData(ui_language)
        if language_index >= 0:
            self.language_combo.setCurrentIndex(language_index)
        else:
            self.language_combo.setCurrentIndex(0)

        # 加载悬浮窗设置
        self.show_overlay_checkbox.setChecked(ui_config.get("show_overlay", True))
        self.overlay_on_top_checkbox.setChecked(
            ui_config.get("overlay_always_on_top", True)
        )

        # 加载overlay position (仅加载preset值，custom模式通过拖拽窗口设置)
        overlay_position = ui_config.get("overlay_position", {})
        position_mode = overlay_position.get("mode", "preset")
        if position_mode == "preset":
            preset_value = overlay_position.get("preset", "center")
            preset_index = self.overlay_position_combo.findData(preset_value)
            if preset_index >= 0:
                self.overlay_position_combo.setCurrentIndex(preset_index)
            else:
                self.overlay_position_combo.setCurrentIndex(0)
        else:
            # custom模式：显示默认值，用户可以通过拖拽窗口来改变位置
            preset_index = self.overlay_position_combo.findData("center")
            if preset_index >= 0:
                self.overlay_position_combo.setCurrentIndex(preset_index)

        # 加载主题颜色设置
        theme_color = ui_config.get("theme_color", "cyan")
        theme_index = self.theme_color_combo.findData(theme_color)
        if theme_index >= 0:
            self.theme_color_combo.setCurrentIndex(theme_index)
        else:
            self.theme_color_combo.setCurrentIndex(0)

        # 加载日志设置
        logging_config = config.get("logging", {})
        log_level = logging_config.get("level", "WARNING")
        log_level_index = self.log_level_combo.findData(log_level)
        if log_level_index >= 0:
            self.log_level_combo.setCurrentIndex(log_level_index)
        self.console_output_checkbox.setChecked(
            logging_config.get("console_output", False)
        )
        self.max_log_size_spinbox.setValue(logging_config.get("max_log_size_mb", 10))

    def save_config(self) -> Dict[str, Any]:
        """保存UI状态到配置

        Returns:
            Dict[str, Any]: 配置字典
        """
        # 映射显示文本到配置值
        theme_color = self.theme_color_combo.currentData() or "cyan"

        config = {
            "ui": {
                "start_minimized": self.start_minimized_checkbox.isChecked(),
                "tray_notifications": self.tray_notifications_checkbox.isChecked(),
                "show_overlay": self.show_overlay_checkbox.isChecked(),
                "overlay_always_on_top": self.overlay_on_top_checkbox.isChecked(),
                "language": self.language_combo.currentData() or "auto",
                "theme_color": theme_color,
            },
            "logging": {
                "level": self.log_level_combo.currentData() or "WARNING",
                "console_output": self.console_output_checkbox.isChecked(),
                "max_log_size_mb": self.max_log_size_spinbox.value(),
            },
        }

        # 处理overlay position preset设置
        # 注意：如果配置中已经存在custom模式的设置，需要保留它
        # position_manager会自动更新custom位置，这里只更新preset值
        overlay_position_text = self.overlay_position_combo.currentData() or "center"

        # 从当前配置中读取overlay_position（可能包含custom坐标）
        current_config = self.config_manager.get_all_settings()
        existing_overlay_position = current_config.get("ui", {}).get(
            "overlay_position", {}
        )

        # 如果现有配置是custom模式，保留custom数据；否则使用preset模式
        if existing_overlay_position.get("mode") == "custom":
            # 保留custom模式和坐标，但更新preset值（作为fallback）
            config["ui"]["overlay_position"] = {
                **existing_overlay_position,  # 保留所有现有字段（custom坐标等）
                "preset": overlay_position_text,  # 更新preset值
            }
        else:
            # preset模式或新配置，使用选中的preset
            config["ui"]["overlay_position"] = {
                "mode": "preset",
                "preset": overlay_position_text,
            }

        return config

    def _export_config(self) -> None:
        """????"""
        file_path, _ = QFileDialog.getSaveFileName(
            self.parent_window,
            QCoreApplication.translate("ApplicationTab", "Export Settings"),
            QCoreApplication.translate("ApplicationTab", "voice_input_settings.json"),
            QCoreApplication.translate("ApplicationTab", "JSON Files (*.json)"),
        )
        if file_path:
            try:
                self.config_manager.export_config(file_path)
                QMessageBox.information(
                    self.parent_window,
                    QCoreApplication.translate("ApplicationTab", "Export"),
                    QCoreApplication.translate(
                        "ApplicationTab", "Settings exported successfully!"
                    ),
                )
            except Exception as e:
                QMessageBox.critical(
                    self.parent_window,
                    QCoreApplication.translate("ApplicationTab", "Error"),
                    QCoreApplication.translate(
                        "ApplicationTab", "Failed to export settings: {error}"
                    ).format(error=e),
                )

    def _import_config(self) -> None:
        """????"""
        file_path, _ = QFileDialog.getOpenFileName(
            self.parent_window,
            QCoreApplication.translate("ApplicationTab", "Import Settings"),
            "",
            QCoreApplication.translate("ApplicationTab", "JSON Files (*.json)"),
        )
        if file_path:
            try:
                self.config_manager.import_config(file_path)
                # ???????????
                if hasattr(self.parent_window, "load_current_config"):
                    self.parent_window.load_current_config()
                QMessageBox.information(
                    self.parent_window,
                    QCoreApplication.translate("ApplicationTab", "Import"),
                    QCoreApplication.translate(
                        "ApplicationTab", "Settings imported successfully!"
                    ),
                )
            except Exception as e:
                QMessageBox.critical(
                    self.parent_window,
                    QCoreApplication.translate("ApplicationTab", "Error"),
                    QCoreApplication.translate(
                        "ApplicationTab", "Failed to import settings: {error}"
                    ).format(error=e),
                )

    def _reset_config(self) -> None:
        """????"""
        reply = QMessageBox.question(
            self.parent_window,
            QCoreApplication.translate("ApplicationTab", "Reset Settings"),
            QCoreApplication.translate(
                "ApplicationTab",
                "Are you sure you want to reset all settings to default values?",
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.config_manager.reset_to_defaults()
                # ???????????
                if hasattr(self.parent_window, "load_current_config"):
                    self.parent_window.load_current_config()
                QMessageBox.information(
                    self.parent_window,
                    QCoreApplication.translate("ApplicationTab", "Reset"),
                    QCoreApplication.translate(
                        "ApplicationTab", "Settings reset to defaults!"
                    ),
                )
            except Exception as e:
                QMessageBox.critical(
                    self.parent_window,
                    QCoreApplication.translate("ApplicationTab", "Error"),
                    QCoreApplication.translate(
                        "ApplicationTab", "Failed to reset settings: {error}"
                    ).format(error=e),
                )
