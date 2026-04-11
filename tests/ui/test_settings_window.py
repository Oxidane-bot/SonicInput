"""SettingsWindow UI测试套件

测试SettingsWindow的功能,确保使用临时配置文件,不修改真实配置。
"""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QPushButton, QComboBox
from pathlib import Path
import os
import json


@pytest.mark.gui
class TestSettingsWindowCreation:
    """SettingsWindow创建和初始化测试"""

    def test_settings_window_creation(
        self, qtbot, settings_window, verify_real_config_untouched
    ):
        """测试设置窗口可以被创建(不修改真实配置)"""
        assert settings_window is not None
        assert not settings_window.isVisible()

    def test_window_title(self, qtbot, settings_window):
        """测试窗口标题"""
        assert "Sonic Input" in settings_window.windowTitle()

    def test_window_size(self, qtbot, settings_window):
        """测试窗口最小尺寸"""
        min_size = settings_window.minimumSize()
        assert min_size.width() >= 800
        assert min_size.height() >= 600

    def test_tabs_exist(self, qtbot, settings_window):
        """测试所有标签页存在"""
        assert hasattr(settings_window, "tab_widget")
        assert settings_window.tab_widget is not None
        assert settings_window.tab_widget.count() > 0


@pytest.mark.gui
class TestSettingsWindowTabs:
    """SettingsWindow标签页测试"""

    def test_application_tab_exists(self, qtbot, settings_window):
        """测试应用程序标签页存在"""
        assert hasattr(settings_window, "application_tab")
        assert settings_window.application_tab is not None

    def test_hotkey_tab_exists(self, qtbot, settings_window):
        """测试热键标签页存在"""
        assert hasattr(settings_window, "hotkey_tab")
        assert settings_window.hotkey_tab is not None

    def test_transcription_tab_exists(self, qtbot, settings_window):
        """测试转录标签页存在"""
        assert hasattr(settings_window, "transcription_tab")
        assert settings_window.transcription_tab is not None

    def test_ai_tab_exists(self, qtbot, settings_window):
        """测试AI标签页存在"""
        assert hasattr(settings_window, "ai_tab")
        assert settings_window.ai_tab is not None

    def test_audio_input_tab_exists(self, qtbot, settings_window):
        """测试音频输入标签页存在"""
        assert hasattr(settings_window, "audio_input_tab")
        assert settings_window.audio_input_tab is not None

    def test_audio_input_tab_hides_advanced_audio_parameters(
        self, qtbot, settings_window
    ):
        """AudioInputTab 不应在 UI 层暴露采样率/声道/Chunk Size 等高级参数。"""
        controls = settings_window.audio_input_tab.controls
        assert "sample_rate" not in controls
        assert "channels" not in controls
        assert "chunk_size" not in controls

    def test_history_tab_exists(self, qtbot, settings_window):
        """测试历史记录标签页存在"""
        assert hasattr(settings_window, "history_tab")
        assert settings_window.history_tab is not None

    def test_tab_switching(self, qtbot, settings_window, verify_real_config_untouched):
        """测试标签页切换(不修改真实配置)"""
        tab_widget = settings_window.tab_widget

        # 切换到每个标签页
        for i in range(tab_widget.count()):
            tab_widget.setCurrentIndex(i)
            qtbot.wait(100)
            assert tab_widget.currentIndex() == i


@pytest.mark.gui
class TestSettingsWindowButtons:
    """SettingsWindow按钮测试"""

    def test_apply_button_exists(self, qtbot, settings_window):
        """测试应用按钮存在"""
        apply_btn = settings_window.findChild(QPushButton, "apply_btn")
        assert apply_btn is not None
        assert apply_btn.text() in ["Apply", "应用"]

    def test_cancel_button_exists(self, qtbot, settings_window):
        """测试取消按钮存在"""
        cancel_btn = settings_window.findChild(QPushButton, "cancel_btn")
        assert cancel_btn is not None
        assert cancel_btn.text() in ["Cancel", "取消"]

    def test_cancel_button_closes_window(
        self, qtbot, settings_window, verify_real_config_untouched
    ):
        """测试取消按钮关闭窗口(不修改真实配置)"""
        # 显示窗口
        settings_window.show()
        qtbot.waitExposed(settings_window, timeout=1000)

        # 点击取消按钮
        cancel_btn = settings_window.findChild(QPushButton, "cancel_btn")
        cancel_btn.click()

        # 验证窗口隐藏
        qtbot.waitUntil(lambda: not settings_window.isVisible(), timeout=2000)
        assert not settings_window.isVisible()


@pytest.mark.gui
class TestSettingsWindowConfigIsolation:
    """SettingsWindow配置隔离测试 - 确保不修改真实配置"""

    def test_uses_isolated_config(self, qtbot, settings_window, isolated_config):
        """验证SettingsWindow使用隔离的配置文件"""
        # 检查配置服务使用的是临时路径
        config_path = settings_window.ui_settings_service.config_path

        # 验证不是真实配置路径
        real_config_path = (
            Path(os.getenv("APPDATA", ".")) / "SonicInput" / "config.json"
        )
        assert str(config_path) != str(real_config_path)

        # 验证是临时路径
        assert str(config_path) == str(isolated_config)

    def test_apply_writes_to_temp_config(
        self,
        qtbot,
        settings_window,
        isolated_config,
        verify_real_config_untouched,
        monkeypatch,
    ):
        """测试应用设置写入临时配置文件,不修改真实配置"""
        # Mock QMessageBox to avoid blocking
        monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

        # 显示窗口
        settings_window.show()
        qtbot.waitExposed(settings_window, timeout=1000)

        # 记录临时配置的初始修改时间

        # 修改一个设置(例如日志级别)
        # 这里需要根据实际的UI结构修改
        settings_window.application_tab.log_level_combo.setCurrentText("DEBUG")

        # 点击应用按钮
        settings_window.findChild(QPushButton, "apply_btn").click()
        qtbot.wait(200)

        after = json.loads(isolated_config.read_text(encoding="utf-8"))
        assert after["logging"]["level"] == "DEBUG"

        # 验证临时配置被修改
        # (可能需要调整,取决于实际的保存机制)

        # verify_real_config_untouched fixture会自动验证真实配置未被修改

    def test_real_config_never_touched(
        self, qtbot, settings_window, verify_real_config_untouched, monkeypatch
    ):
        """显式测试:真实配置文件永远不被触碰"""
        # Mock QMessageBox to avoid blocking
        monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

        real_config_path = (
            Path(os.getenv("APPDATA", ".")) / "SonicInput" / "config.json"
        )

        if real_config_path.exists():
            original_mtime = real_config_path.stat().st_mtime
            original_content = real_config_path.read_text(encoding="utf-8")

            # 显示窗口
            settings_window.show()
            qtbot.waitExposed(settings_window, timeout=1000)

            # 执行各种操作
            settings_window.tab_widget.setCurrentIndex(0)
            qtbot.wait(100)
            settings_window.tab_widget.setCurrentIndex(1)
            qtbot.wait(100)

            # 点击应用按钮
            settings_window.findChild(QPushButton, "apply_btn").click()
            qtbot.wait(200)

            # 关闭窗口
            settings_window.cancel_button.click()
            qtbot.wait(100)

            # 验证真实配置未被修改
            assert real_config_path.stat().st_mtime == original_mtime
            assert real_config_path.read_text(encoding="utf-8") == original_content


@pytest.mark.gui
class TestSettingsWindowSignals:
    """SettingsWindow信号测试"""

    def test_settings_changed_signal(self, qtbot, settings_window):
        """测试设置变更信号"""
        with qtbot.waitSignal(
            settings_window.settings_changed, timeout=1000
        ) as blocker:
            settings_window.settings_changed.emit("test_key", "test_value")

        assert blocker.args == ["test_key", "test_value"]

    def test_hotkey_test_signal(self, qtbot, settings_window):
        """测试热键测试信号"""
        with qtbot.waitSignal(
            settings_window.hotkey_test_requested, timeout=1000
        ) as blocker:
            settings_window.hotkey_test_requested.emit("f12")

        assert blocker.args == ["f12"]

    def test_api_test_signal(self, qtbot, settings_window):
        """测试API测试信号"""
        with qtbot.waitSignal(settings_window.api_test_requested, timeout=1000):
            settings_window.api_test_requested.emit()

    def test_model_load_signal(self, qtbot, settings_window):
        """测试模型加载信号"""
        with qtbot.waitSignal(
            settings_window.model_load_requested, timeout=1000
        ) as blocker:
            settings_window.model_load_requested.emit("base")

        assert blocker.args == ["base"]


@pytest.mark.gui
class TestSettingsWindowDialogs:
    """SettingsWindow对话框测试 - 使用mock避免阻塞"""

    def test_reset_settings_confirmation(
        self, qtbot, settings_window, monkeypatch, verify_real_config_untouched
    ):
        """测试重置设置确认对话框(mock)"""
        question_calls = []

        def mock_question(*args, **kwargs):
            question_calls.append((args, kwargs))
            return QMessageBox.StandardButton.Yes

        monkeypatch.setattr(QMessageBox, "question", mock_question)

        # 显示窗口
        settings_window.show()
        qtbot.waitExposed(settings_window, timeout=1000)

        # 触发重置(如果有这个功能)
        settings_window.tab_widget.setCurrentIndex(0)  # Application tab
        settings_window.application_tab.log_level_combo.setCurrentText("DEBUG")

        settings_window.findChild(QPushButton, "reset_btn").click()
        qtbot.wait(200)

        assert len(question_calls) == 1
        assert (
            settings_window.application_tab.log_level_combo.currentText() == "WARNING"
        )

        # verify_real_config_untouched会自动验证真实配置未被修改


@pytest.mark.gui
@pytest.mark.slow
class TestSettingsWindowLoadSave:
    """SettingsWindow加载/保存测试"""

    def test_load_config_from_temp(self, qtbot, settings_window, isolated_config):
        """测试从临时配置加载设置"""
        # 加载配置
        settings_window.load_current_config()
        qtbot.wait(100)

        # 验证配置被加载(检查内部状态)
        assert hasattr(settings_window, "current_config")

    def test_multiple_save_operations(
        self,
        qtbot,
        settings_window,
        isolated_config,
        verify_real_config_untouched,
        monkeypatch,
    ):
        """测试多次保存操作只修改临时配置"""
        # Mock QMessageBox to avoid blocking
        monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

        settings_window.show()
        qtbot.waitExposed(settings_window, timeout=1000)

        # 多次点击应用按钮
        for level in ["DEBUG", "INFO", "ERROR"]:
            settings_window.application_tab.log_level_combo.setCurrentText(level)
            settings_window.findChild(QPushButton, "apply_btn").click()
            qtbot.wait(200)

            saved = json.loads(isolated_config.read_text(encoding="utf-8"))
            assert saved["logging"]["level"] == level

        # verify_real_config_untouched会验证真实配置未被修改


@pytest.mark.gui
class TestSettingsWindowCoreButtons:
    """SettingsWindow核心按钮功能测试"""

    def test_apply_button_saves_config_and_keeps_open(
        self, qtbot, settings_window, isolated_config, monkeypatch
    ):
        """测试Apply按钮保存配置且窗口保持打开"""
        # Mock QMessageBox to avoid blocking
        monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

        # 显示窗口
        settings_window.show()
        qtbot.waitExposed(settings_window, timeout=1000)

        # 修改一个配置(日志级别)
        settings_window.application_tab.log_level_combo.setCurrentText("DEBUG")

        # 点击Apply按钮
        settings_window.findChild(QPushButton, "apply_btn").click()
        qtbot.wait(200)

        # 验证配置被保存
        saved_config = settings_window.ui_settings_service.get_all_settings()
        assert saved_config["logging"]["level"] == "DEBUG"

        # 验证窗口仍然可见
        assert settings_window.isVisible()

    def test_ok_button_saves_and_closes(
        self, qtbot, settings_window, isolated_config, monkeypatch
    ):
        """测试OK按钮保存配置并关闭窗口"""
        # Mock QMessageBox to avoid blocking
        monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

        # 显示窗口
        settings_window.show()
        qtbot.waitExposed(settings_window, timeout=1000)

        # 修改一个配置
        settings_window.application_tab.log_level_combo.setCurrentText("INFO")

        # 点击OK按钮
        settings_window.findChild(QPushButton, "ok_btn").click()
        qtbot.wait(200)

        # 验证配置被保存
        saved_config = settings_window.ui_settings_service.get_all_settings()
        assert saved_config["logging"]["level"] == "INFO"

        # 验证窗口已隐藏
        qtbot.waitUntil(lambda: not settings_window.isVisible(), timeout=2000)
        assert not settings_window.isVisible()

    def test_ok_button_does_not_close_when_apply_fails(
        self, qtbot, settings_window, monkeypatch
    ):
        """保存失败时，OK 不应关闭设置窗口。"""
        monkeypatch.setattr(settings_window, "apply_settings", lambda: False)

        settings_window.show()
        qtbot.waitExposed(settings_window, timeout=1000)

        settings_window.findChild(QPushButton, "ok_btn").click()
        qtbot.wait(200)

        assert settings_window.isVisible()

    def test_unload_model_does_not_emit_when_user_cancels(
        self, qtbot, settings_window, monkeypatch
    ):
        """用户取消卸载时，不应发出卸载请求。"""
        unload_requests = []

        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *args, **kwargs: QMessageBox.StandardButton.No,
        )
        monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

        settings_window.model_unload_requested.connect(
            lambda: unload_requests.append(True)
        )

        settings_window.unload_model()

        assert unload_requests == []

    def test_reset_tab_button_resets_config(
        self, qtbot, settings_window, isolated_config, monkeypatch
    ):
        """测试Reset Tab按钮实际重置配置"""
        # Mock get_default_config to return plain dict (avoid pickle issue)
        plain_default_config = {
            "ui": {
                "launch_at_login": False,
                "start_minimized": True,
                "tray_notifications": False,
                "show_overlay": True,
            },
            "logging": {
                "level": "WARNING",
                "console_output": False,
            },
            "hotkeys": ["f12"],
        }

        monkeypatch.setattr(
            settings_window.ui_settings_service,
            "get_default_config",
            lambda: plain_default_config,
        )

        # Mock confirmation dialog - return Yes
        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
        )
        monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

        settings_window.show()
        qtbot.waitExposed(settings_window, timeout=1000)

        # Go to Application tab and change a setting
        settings_window.tab_widget.setCurrentIndex(0)
        settings_window.application_tab.log_level_combo.setCurrentText("DEBUG")

        # Click reset tab button
        settings_window.findChild(QPushButton, "reset_btn").click()
        qtbot.wait(200)

        # Verify setting was reset to default
        assert (
            settings_window.application_tab.log_level_combo.currentText() == "WARNING"
        )

    def test_reset_tab_button_cancel(
        self, qtbot, settings_window, isolated_config, monkeypatch
    ):
        """测试取消Reset Tab操作"""
        # Mock QMessageBox.question to return No (cancel)
        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *args, **kwargs: QMessageBox.StandardButton.No,
        )

        # 显示窗口
        settings_window.show()
        qtbot.waitExposed(settings_window, timeout=1000)
        settings_window.tab_widget.setCurrentIndex(0)  # Application tab

        # 修改配置
        settings_window.application_tab.log_level_combo.setCurrentText("DEBUG")
        original_value = settings_window.application_tab.log_level_combo.currentText()

        # 点击Reset Tab按钮(但会取消)
        settings_window.findChild(QPushButton, "reset_btn").click()
        qtbot.wait(200)

        # 验证配置未被重置
        current_value = settings_window.application_tab.log_level_combo.currentText()
        assert current_value == original_value


@pytest.mark.gui
class TestConfigManagementIntegration:
    """配置管理集成测试 - 使用真实文件I/O"""

    def test_export_config_creates_json_with_envelope(
        self, qtbot, settings_window, isolated_config, tmp_path, monkeypatch
    ):
        """测试导出配置创建带envelope的JSON"""
        import json
        from PySide6.QtWidgets import QFileDialog

        export_file = tmp_path / "test_export.json"

        # Track any errors
        errors = []

        def mock_critical(*args, **kwargs):
            errors.append(str(args))

        # Mock ALL QMessageBox dialogs to prevent blocking
        monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
        monkeypatch.setattr(QMessageBox, "critical", mock_critical)

        # Mock file dialog
        monkeypatch.setattr(
            QFileDialog,
            "getSaveFileName",
            lambda *args, **kwargs: (str(export_file), "JSON Files (*.json)"),
        )

        settings_window.show()
        qtbot.waitExposed(settings_window)

        # Click export button (real file I/O!)
        settings_window.application_tab.export_config_button.click()
        qtbot.wait(200)

        # Check if there were errors
        if errors:
            pytest.fail(f"Export failed with error: {errors}")

        # Verify file was created
        assert export_file.exists()

        # Verify JSON structure
        with open(export_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert "version" in data
        assert data["version"] == "1.0"
        assert "exported_at" in data
        assert "config" in data
        assert isinstance(data["config"], dict)

        # Verify exported_at is ISO format
        from datetime import datetime

        datetime.fromisoformat(data["exported_at"])  # Should not raise

    def test_export_config_writes_utf8_correctly(
        self, qtbot, settings_window, isolated_config, tmp_path, monkeypatch
    ):
        """测试导出配置正确写入UTF-8编码"""
        import json
        from PySide6.QtWidgets import QFileDialog

        export_file = tmp_path / "test_utf8.json"

        # Mock ALL QMessageBox dialogs to prevent blocking
        monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

        monkeypatch.setattr(
            QFileDialog,
            "getSaveFileName",
            lambda *args, **kwargs: (str(export_file), ""),
        )

        # Set some config with Chinese characters
        settings_window.ui_settings_service.set_setting("test_chinese", "测试中文")

        settings_window.show()
        qtbot.waitExposed(settings_window)
        settings_window.application_tab.export_config_button.click()
        qtbot.wait(200)

        # Read and verify UTF-8
        with open(export_file, "r", encoding="utf-8") as f:
            content = f.read()
            assert "测试中文" in content  # Should be readable

        # Verify ensure_ascii=False (Chinese chars not escaped)
        with open(export_file, "rb") as f:
            raw = f.read()
            # UTF-8 encoded Chinese should be multi-byte, not \\uXXXX
            assert b"\\u6d4b" not in raw  # Should NOT be Unicode-escaped

    def test_import_config_merges_with_existing(
        self, qtbot, settings_window, isolated_config, tmp_path, monkeypatch
    ):
        """测试导入配置深度合并(不是替换)"""
        import json
        from PySide6.QtWidgets import QFileDialog

        # Create import file with partial config
        import_file = tmp_path / "import.json"
        import_data = {
            "version": "1.0",
            "exported_at": "2025-11-12T10:00:00",
            "config": {"logging": {"level": "DEBUG"}, "new_key": "new_value"},
        }
        with open(import_file, "w", encoding="utf-8") as f:
            json.dump(import_data, f)

        # Get current config state
        original_hotkeys = settings_window.ui_settings_service.get_setting("hotkeys")

        # Mock ALL QMessageBox dialogs to prevent blocking
        monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

        monkeypatch.setattr(
            QFileDialog,
            "getOpenFileName",
            lambda *args, **kwargs: (str(import_file), ""),
        )

        settings_window.show()
        qtbot.waitExposed(settings_window)
        settings_window.application_tab.import_config_button.click()
        qtbot.wait(200)

        # Verify merge: new key added, existing keys preserved
        assert (
            settings_window.ui_settings_service.get_setting("logging.level") == "DEBUG"
        )
        assert settings_window.ui_settings_service.get_setting("new_key") == "new_value"
        assert (
            settings_window.ui_settings_service.get_setting("hotkeys")
            == original_hotkeys
        )

    def test_import_config_updates_ui(
        self, qtbot, settings_window, isolated_config, tmp_path, monkeypatch
    ):
        """测试导入配置后更新UI"""
        import json
        from PySide6.QtWidgets import QFileDialog

        import_file = tmp_path / "import_ui_test.json"
        import_data = {
            "version": "1.0",
            "exported_at": "2025-11-12T10:00:00",
            "config": {"logging": {"level": "ERROR"}},
        }
        with open(import_file, "w", encoding="utf-8") as f:
            json.dump(import_data, f)

        # Mock ALL QMessageBox dialogs to prevent blocking
        monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

        monkeypatch.setattr(
            QFileDialog,
            "getOpenFileName",
            lambda *args, **kwargs: (str(import_file), ""),
        )

        # Track if load_current_config was called
        load_called = []
        original_load = settings_window.load_current_config
        settings_window.load_current_config = lambda: (
            load_called.append(True),
            original_load(),
        )[1]

        settings_window.show()
        qtbot.waitExposed(settings_window)
        settings_window.application_tab.import_config_button.click()
        qtbot.wait(200)

        # Verify UI was updated
        assert len(load_called) == 1  # load_current_config called
        assert settings_window.application_tab.log_level_combo.currentText() == "ERROR"

    def test_reset_to_defaults_resets_all_keys(
        self, qtbot, settings_window, isolated_config, monkeypatch
    ):
        """测试重置默认配置重置所有键"""
        from sonicinput.core.services.config.config_defaults import get_default_config

        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
        )
        monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

        settings_window.show()
        qtbot.waitExposed(settings_window)

        # Change multiple settings
        settings_window.application_tab.log_level_combo.setCurrentText("DEBUG")
        settings_window.findChild(
            QPushButton, "apply_btn"
        ).click()  # Use window-level apply button
        qtbot.wait(100)

        # Reset to defaults
        settings_window.application_tab.reset_config_button.click()
        qtbot.wait(200)

        # Verify all settings match defaults
        defaults = get_default_config()
        current_config = settings_window.ui_settings_service.get_all_settings()

        assert current_config["logging"]["level"] == defaults["logging"]["level"]

    def test_reset_to_defaults_saves_to_disk(
        self, qtbot, settings_window, isolated_config, monkeypatch
    ):
        """测试重置默认配置保存到磁盘"""
        import json

        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
        )
        monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

        settings_window.show()
        qtbot.waitExposed(settings_window)

        config_path = settings_window.ui_settings_service.config_service.config_path

        # Reset to defaults
        settings_window.application_tab.reset_config_button.click()
        qtbot.wait(500)  # Wait for save

        # Verify file exists and contains default config
        assert config_path.exists()
        with open(config_path, "r", encoding="utf-8") as f:
            saved_config = json.load(f)

        from sonicinput.core.services.config.config_defaults import get_default_config

        defaults = get_default_config()

        # Key configs should match defaults
        assert saved_config["logging"] == defaults["logging"]

    def test_reset_to_defaults_shows_confirmation(
        self, qtbot, settings_window, monkeypatch
    ):
        """测试重置默认配置显示确认对话框"""
        dialog_called = []

        def mock_question(*args, **kwargs):
            dialog_called.append(True)
            return QMessageBox.StandardButton.No  # Cancel

        monkeypatch.setattr(QMessageBox, "question", mock_question)

        settings_window.show()
        qtbot.waitExposed(settings_window)

        settings_window.application_tab.reset_config_button.click()
        qtbot.wait(100)

        # Verify confirmation dialog was shown
        assert len(dialog_called) == 1


@pytest.mark.gui
class TestLaunchAtLoginSetting:
    """开机自启设置相关 UI 行为测试。"""

    def test_launch_at_login_checkbox_exists(self, qtbot, settings_window):
        """ApplicationTab 应暴露开机自启勾选框。"""
        assert hasattr(settings_window.application_tab, "launch_at_login_checkbox")
        assert settings_window.application_tab.launch_at_login_checkbox is not None

    def test_application_tab_save_includes_launch_at_login(
        self, qtbot, settings_window
    ):
        """保存配置时应包含 ui.launch_at_login。"""
        settings_window.application_tab.launch_at_login_checkbox.setChecked(True)
        saved = settings_window.application_tab.save_config()
        assert saved["ui"]["launch_at_login"] is True

    def test_apply_enforces_minimized_when_launch_at_login_enabled(
        self, qtbot, settings_window, monkeypatch
    ):
        """启用开机自启时，apply 应强制 start_minimized 为 True。"""
        import sonicinput.ui.settings_window as settings_window_module

        captured = {"changes": None}

        class FakeTransaction:
            def __init__(self, *_args, **_kwargs):
                pass

            def begin(self):
                return None

            def apply_model_change(self, _model_name):
                return None

            def apply_config_changes(self, changes):
                captured["changes"] = dict(changes)

            def apply_launch_at_login_change(self, _changes):
                return None

            def commit(self):
                return None

        monkeypatch.setattr(settings_window_module, "ApplyTransaction", FakeTransaction)

        # 避免误触发模型重载分支
        settings_window.ui_model_service.get_model_info = lambda: {
            "model_name": "paraformer"
        }

        settings_window.show()
        qtbot.waitExposed(settings_window, timeout=1000)

        settings_window.application_tab.launch_at_login_checkbox.setChecked(True)
        settings_window.application_tab.start_minimized_checkbox.setChecked(False)

        settings_window.apply_settings()

        assert captured["changes"] is not None
        assert captured["changes"]["ui.launch_at_login"] is True
        assert captured["changes"]["ui.start_minimized"] is True


@pytest.mark.gui
class TestAIStreamingSetting:
    def test_ai_tab_exposes_streaming_checkbox(self, qtbot, settings_window):
        assert hasattr(settings_window.ai_tab, "ai_streaming_checkbox")
        assert settings_window.ai_tab.ai_streaming_checkbox is not None

    def test_ai_tab_save_includes_streaming_enabled(self, qtbot, settings_window):
        settings_window.ai_tab.ai_streaming_checkbox.setChecked(True)
        saved = settings_window.ai_tab.save_config()
        assert saved["ai"]["streaming_enabled"] is True

    def test_ai_tab_load_reads_streaming_enabled(self, qtbot, settings_window):
        settings_window.ai_tab.load_config({"ai": {"streaming_enabled": True}})
        assert settings_window.ai_tab.ai_streaming_checkbox.isChecked() is True


class TestModelUnloadConfirmation:
    def test_unload_model_decline_does_not_emit_request(self, monkeypatch):
        from sonicinput.ui.settings_window import SettingsWindow

        class _SignalStub:
            def __init__(self):
                self.calls = 0

            def emit(self):
                self.calls += 1

        settings_window = SettingsWindow.__new__(SettingsWindow)
        settings_window.model_unload_requested = _SignalStub()

        emitted = []
        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *args, **kwargs: QMessageBox.StandardButton.No,
        )
        monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
        monkeypatch.setattr(
            QMessageBox,
            "critical",
            lambda *args, **kwargs: emitted.append(("critical", args, kwargs)),
        )

        settings_window.unload_model()

        assert emitted == []
        assert settings_window.model_unload_requested.calls == 0
