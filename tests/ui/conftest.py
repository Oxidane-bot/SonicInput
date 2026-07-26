"""UI测试的配置和fixtures - 确保配置文件完全隔离"""

import pytest
import os
import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, Mock
from PySide6.QtWidgets import QMessageBox, QProgressDialog, QWidget


def _assert_valid_parent(method_name: str, parent) -> None:
    """Mimic PySide6's C++ parent-type contract.

    PySide6 dialogs require a QWidget subclass (or None) as parent. Passing a bare
    QObject (e.g. FluentSettingsWindow, which hosts a QML window) raises TypeError
    at runtime — but monkeypatched dialogs in tests would silently accept it,
    hiding the bug. This guard makes the contract explicit in tests.
    """
    assert parent is None or isinstance(parent, QWidget), (
        f"{method_name} parent must be QWidget or None, got "
        f"{type(parent).__name__} ({parent!r})"
    )


@pytest.fixture(autouse=True)
def qmessagebox_guard(monkeypatch):
    """Prevent blocking dialogs and fail on unexpected warning/critical popups."""

    def _information(*args, **_kwargs):
        _assert_valid_parent("QMessageBox.information", args[0] if args else None)
        return QMessageBox.StandardButton.Ok

    def _warning(*args, **_kwargs):
        _assert_valid_parent("QMessageBox.warning", args[0] if args else None)
        title = args[1] if len(args) > 1 else ""
        text = args[2] if len(args) > 2 else ""
        raise AssertionError(f"Unexpected QMessageBox.warning: {title} | {text}")

    def _critical(*args, **_kwargs):
        _assert_valid_parent("QMessageBox.critical", args[0] if args else None)
        title = args[1] if len(args) > 1 else ""
        text = args[2] if len(args) > 2 else ""
        raise AssertionError(f"Unexpected QMessageBox.critical: {title} | {text}")

    def _question(*args, **_kwargs):
        _assert_valid_parent("QMessageBox.question", args[0] if args else None)
        # Default to "No" to avoid destructive actions in tests unless explicitly mocked.
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "information", _information)
    monkeypatch.setattr(QMessageBox, "warning", _warning)
    monkeypatch.setattr(QMessageBox, "critical", _critical)
    monkeypatch.setattr(QMessageBox, "question", _question)


@pytest.fixture(autouse=True)
def qprogressdialog_guard(monkeypatch):
    """Validate QProgressDialog construction signatures at test time.

    PySide6 has two QProgressDialog overloads:
      (labelText: str, cancelButtonText: str, minimum: int, maximum: int, /,
          parent: QWidget|None = None, ...)
      (parent: QWidget|None = None, flags: ...)
    Disambiguate by inspecting args[0] type — matches PySide6's runtime dispatch.
    Both `cancelButtonText` must be str (not None) on the first overload.
    """
    original_init = QProgressDialog.__init__

    def _qpd_init(self, *args, **kwargs):
        if args and isinstance(args[0], str):
            # label-first overload
            if len(args) >= 2:
                assert isinstance(args[1], str), (
                    f"QProgressDialog cancelButtonText must be str, got "
                    f"{type(args[1]).__name__} ({args[1]!r})"
                )
            parent = args[4] if len(args) >= 5 else kwargs.get("parent")
        elif args:
            # parent-first overload
            parent = args[0]
        else:
            parent = kwargs.get("parent")
        _assert_valid_parent("QProgressDialog.__init__", parent)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(QProgressDialog, "__init__", _qpd_init)


# ============= 配置隔离 Fixtures =============


@pytest.fixture
def isolated_config(monkeypatch, tmp_path):
    """创建隔离的临时配置文件

    这个fixture确保测试永远不会修改真实的用户配置文件。
    每个测试都会得到一个独立的临时配置文件。

    配置会从真实用户配置复制API keys和model IDs,避免测试时弹出错误窗口。
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=False)
    monkeypatch.setenv("TMP", str(config_dir))
    monkeypatch.setenv("TEMP", str(config_dir))
    config_file = config_dir / "test_config.json"

    # 尝试读取真实用户配置以获取API keys
    real_config_path = Path(os.getenv("APPDATA", ".")) / "SonicInput" / "config.json"
    real_config = {}
    if real_config_path.exists():
        try:
            with open(real_config_path, "r", encoding="utf-8") as f:
                real_config = json.load(f)
        except Exception:
            pass

    # 创建默认测试配置,但使用真实的API keys
    default_config = {
        "hotkeys": ["f12"],
        "transcription": {
            "provider": "local",
            "local": real_config.get("transcription", {}).get(
                "local",
                {
                    "model": "paraformer",
                    "language": "zh",
                    "auto_load": False,
                    "streaming_mode": "chunked",
                },
            ),
            "groq": real_config.get("transcription", {}).get(
                "groq", {"api_key": "", "model": "whisper-large-v3-turbo"}
            ),
            "siliconflow": real_config.get("transcription", {}).get(
                "siliconflow", {"api_key": "", "model": "FunAudioLLM/SenseVoiceSmall"}
            ),
            "qwen": real_config.get("transcription", {}).get(
                "qwen", {"api_key": "", "model": "qwen3-asr-flash"}
            ),
        },
        "ai": {
            "enabled": False,
            "provider": "openrouter",
            "openrouter": real_config.get("ai", {}).get(
                "openrouter", {"api_key": "", "model_id": "anthropic/claude-3-sonnet"}
            ),
            "groq": real_config.get("ai", {}).get(
                "groq", {"api_key": "", "model_id": "llama3-70b-8192"}
            ),
            "nvidia": real_config.get("ai", {}).get(
                "nvidia",
                {"api_key": "", "model_id": "nvidia/llama-3.1-nemotron-70b-instruct"},
            ),
            "openai_compatible": real_config.get("ai", {}).get(
                "openai_compatible", {"api_key": "", "base_url": "", "model_id": ""}
            ),
        },
        "audio": {
            "sample_rate": 16000,
            "channels": 1,
            "auto_stop_enabled": True,
            "max_recording_duration": 60,
        },
        "ui": {
            "launch_at_login": False,
            "start_minimized": False,
            "tray_notifications": True,
            "show_overlay": True,
        },
        "logging": {"level": "WARNING", "console_output": False},
    }

    # 写入配置文件
    config_file.write_text(json.dumps(default_config, indent=2, ensure_ascii=False))

    yield config_file

    shutil.rmtree(config_dir, ignore_errors=True)


@pytest.fixture
def mock_config_service(isolated_config):
    """使用临时配置的 Mock ConfigService

    这个mock确保UI组件使用隔离的配置,不会触碰真实配置。
    """
    from sonicinput.core.services.config import RefactoredConfigService

    # 创建使用临时配置文件的ConfigService
    config_service = RefactoredConfigService(
        config_path=str(isolated_config),
        event_service=None,  # UI测试不需要事件服务
    )

    # 必须调用 load_config() 或 start() 来加载配置
    config_service.load_config()

    return config_service


@pytest.fixture
def verify_real_config_untouched():
    """验证真实配置文件未被修改的辅助fixture"""
    real_config_path = Path(os.getenv("APPDATA", ".")) / "SonicInput" / "config.json"

    # 记录初始状态
    initial_state = {
        "exists": real_config_path.exists(),
        "mtime": real_config_path.stat().st_mtime
        if real_config_path.exists()
        else None,
        "content": real_config_path.read_text(encoding="utf-8")
        if real_config_path.exists()
        else None,
    }

    yield

    # 验证配置文件未被修改
    if initial_state["exists"]:
        assert real_config_path.exists(), "Real config file was deleted during test!"
        assert real_config_path.stat().st_mtime == initial_state["mtime"], (
            "Real config file was modified during test!"
        )
        assert (
            real_config_path.read_text(encoding="utf-8") == initial_state["content"]
        ), "Real config file content was changed during test!"


# ============= UI组件 Mock Services =============


@pytest.fixture
def mock_ui_services():
    """创建UI组件需要的Mock服务集合"""
    services = {
        "settings": MagicMock(),
        "model": MagicMock(),
        "event_service": MagicMock(),
        "audio_service": MagicMock(),
        "speech_service": MagicMock(),
        "input_service": MagicMock(),
    }

    # 配置常用的返回值
    services["settings"].get_setting = Mock(return_value=None)
    services["settings"].set_setting = Mock()
    services["model"].get_state = Mock(return_value={"recording": False})

    return services


# ============= Fluent Recording Overlay Fixtures =============


@pytest.fixture
def recording_overlay(qtbot, mock_config_service):
    """创建 FluentRecordingOverlay 实例。"""
    from sonicinput.ui.fluent_recording_overlay import FluentRecordingOverlay

    overlay = FluentRecordingOverlay()
    overlay.set_config_service(mock_config_service)

    yield overlay

    # 清理:确保overlay被隐藏和删除
    if overlay.isVisible():
        overlay.hide()
    overlay.deleteLater()


# ============= Fluent Settings Window Fixtures =============


@pytest.fixture
def settings_window(qtbot, mock_config_service):
    """创建 FluentSettingsWindow 实例(使用隔离配置)。"""
    from sonicinput.ui.fluent_settings_window import FluentSettingsWindow

    # 创建mock UI服务,但使用真实的配置服务方法
    mock_ui_settings_service = MagicMock()
    mock_ui_settings_service.config_path = mock_config_service.config_path
    mock_ui_settings_service.config_service = (
        mock_config_service  # Expose config_service for tests
    )

    # 使用真实配置服务的方法
    mock_ui_settings_service.get_setting = mock_config_service.get_setting
    mock_ui_settings_service.set_setting = mock_config_service.set_setting
    mock_ui_settings_service.get_all_settings = mock_config_service.get_all_settings
    mock_ui_settings_service.save_config = mock_config_service.save_config
    mock_ui_settings_service.export_config = mock_config_service.export_config
    mock_ui_settings_service.import_config = mock_config_service.import_config
    mock_ui_settings_service.reset_to_defaults = (
        mock_config_service.reset_to_default
    )  # Note: method is reset_to_default not reset_to_defaults

    # Mock其他方法
    mock_event_service = MagicMock()
    mock_event_service.on = Mock()
    mock_event_service.emit = Mock()

    mock_ui_settings_service.get_event_service = Mock(return_value=mock_event_service)
    mock_ui_settings_service.get_config_service = Mock(return_value=mock_config_service)
    mock_ui_settings_service.get_transcription_service = Mock(return_value=None)
    mock_ui_settings_service.get_ai_processing_controller = Mock(return_value=None)
    mock_ui_settings_service.get_launch_at_login_service = Mock(return_value=None)
    mock_ui_settings_service.get_localization_service = Mock(return_value=None)
    mock_history_service = MagicMock()
    mock_history_service.get_records = Mock(return_value=[])
    mock_history_service.search_records = Mock(return_value=[])
    mock_history_service.get_records_keyset = Mock(return_value=[])
    mock_history_service.search_records_keyset = Mock(return_value=[])
    mock_history_service.get_total_count = Mock(return_value=0)
    mock_history_service.get_aggregate_stats = Mock(return_value=(0, 0.0, 0))
    mock_ui_settings_service.get_history_service = Mock(
        return_value=mock_history_service
    )
    mock_ui_settings_service.get_default_config = Mock(return_value={})

    mock_ui_model_service = MagicMock()
    mock_ui_model_service.get_state = Mock(return_value={"recording": False})

    # 创建设置窗口
    window = FluentSettingsWindow(
        ui_settings_service=mock_ui_settings_service,
        ui_model_service=mock_ui_model_service,
    )

    yield window

    # 清理
    window.close()


# ============= SystemTray Fixtures =============


@pytest.fixture
def system_tray_widget(qtbot, mock_config_service):
    """创建 SystemTray 组件(使用隔离配置)"""
    from sonicinput.ui.components.system_tray.tray_widget import TrayWidget

    tray = TrayWidget(config_service=mock_config_service)
    qtbot.addWidget(tray)

    yield tray

    # 清理
    tray.hide()
    tray.deleteLater()


# ============= pytest-qt 配置 =============


@pytest.fixture(scope="session")
def qapp_args():
    """配置QApplication参数用于测试"""
    return ["--platform", "offscreen"]  # 无头模式,不显示窗口


@pytest.fixture
def qtbot_wait_time():
    """配置qtbot的等待超时时间"""
    return 1000  # 1秒,适合快速测试
