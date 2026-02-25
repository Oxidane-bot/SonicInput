"""API连接测试 - 测试AI Tab和Transcription Tab的所有API提供商

测试策略:
- 使用真实的线程(不mock threading.Thread)
- Mock AI客户端的test_connection()方法
- 使用qtbot.waitUntil()等待线程完成
- 验证成功/失败对话框的显示
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from PySide6.QtWidgets import QMessageBox, QComboBox, QLineEdit, QPushButton
from PySide6.QtCore import Qt


class TestAITabAPIConnections:
    """AI Tab API连接测试"""

    def test_openrouter_api_connection_success(
        self, qtbot, settings_window, monkeypatch
    ):
        """测试OpenRouter API连接成功"""
        # Mock OpenRouter客户端
        mock_client = Mock()
        mock_client.test_connection = Mock(return_value=(True, ""))

        # 记录显示的对话框
        dialog_shown = []

        def mock_info(*args, **kwargs):
            dialog_shown.append(("success", args[2]))  # args[2] is message

        monkeypatch.setattr(QMessageBox, "information", mock_info)

        with patch(
            "sonicinput.ai.openrouter.OpenRouterClient", return_value=mock_client
        ):
            # 设置UI
            settings_window.show()
            qtbot.waitExposed(settings_window)
            settings_window.tab_widget.setCurrentIndex(3)  # AI tab
            qtbot.wait(50)

            ai_tab = settings_window.ai_tab

            # 切换到OpenRouter提供商
            ai_provider_combo = ai_tab.widget.findChild(QComboBox, "ai_provider_combo")
            ai_provider_combo.setCurrentText("OpenRouter")
            qtbot.wait(100)  # 等待provider切换完成

            # 设置API key
            api_key_input = ai_tab.widget.findChild(QLineEdit, "api_key_input")
            api_key_input.setText("test-openrouter-key-12345")
            qtbot.wait(50)

            # 点击测试按钮(启动真实线程)
            test_connection_btn = ai_tab.widget.findChild(
                QPushButton, "test_connection_btn"
            )
            test_connection_btn.click()
            qtbot.wait(100)  # 线程启动延迟

            # 等待线程完成并显示对话框
            qtbot.waitUntil(lambda: len(dialog_shown) > 0, timeout=5000)

            # 验证成功对话框显示
            assert len(dialog_shown) == 1
            assert "successful" in dialog_shown[0][1].lower()
            assert "OpenRouter" in dialog_shown[0][1]

            # 验证test_connection被调用
            mock_client.test_connection.assert_called_once()

    def test_groq_api_connection_success(self, qtbot, settings_window, monkeypatch):
        """测试Groq AI API连接成功"""
        # Mock Groq客户端
        mock_client = Mock()
        mock_client.test_connection = Mock(return_value=(True, ""))

        dialog_shown = []

        def mock_info(*args, **kwargs):
            dialog_shown.append(("success", args[2]))

        monkeypatch.setattr(QMessageBox, "information", mock_info)

        with patch("sonicinput.ai.groq.GroqClient", return_value=mock_client):
            # 设置UI
            settings_window.show()
            qtbot.waitExposed(settings_window)
            settings_window.tab_widget.setCurrentIndex(3)  # AI tab
            qtbot.wait(50)

            ai_tab = settings_window.ai_tab

            # 切换到Groq提供商
            ai_provider_combo = ai_tab.widget.findChild(QComboBox, "ai_provider_combo")
            ai_provider_combo.setCurrentText("Groq")
            qtbot.wait(100)  # 等待provider切换完成

            # 设置API key
            groq_api_key_input = ai_tab.widget.findChild(
                QLineEdit, "groq_api_key_input"
            )
            groq_api_key_input.setText("test-groq-key-67890")
            qtbot.wait(50)

            # 点击测试按钮
            test_connection_btn = ai_tab.widget.findChild(
                QPushButton, "test_connection_btn"
            )
            test_connection_btn.click()
            qtbot.wait(100)

            # 等待成功对话框
            qtbot.waitUntil(lambda: len(dialog_shown) > 0, timeout=5000)

            # 验证成功
            assert len(dialog_shown) == 1
            assert "successful" in dialog_shown[0][1].lower()
            assert "Groq" in dialog_shown[0][1]

    def test_groq_refresh_model_list_updates_combo(
        self, qtbot, settings_window, monkeypatch
    ):
        """测试Groq模型列表刷新会更新可编辑下拉框"""
        mock_client = Mock()
        mock_client.fetch_available_models = Mock(
            return_value=[
                "deepseek-r1-distill-llama-70b",
                "llama-3.3-70b-versatile",
            ]
        )

        dialog_shown = []

        def mock_info(*args, **kwargs):
            dialog_shown.append(("success", args[2]))

        monkeypatch.setattr(QMessageBox, "information", mock_info)

        with patch("sonicinput.ai.groq.GroqClient", return_value=mock_client):
            settings_window.show()
            qtbot.waitExposed(settings_window)
            settings_window.tab_widget.setCurrentIndex(3)  # AI tab
            qtbot.wait(50)

            ai_tab = settings_window.ai_tab
            ai_provider_combo = ai_tab.widget.findChild(QComboBox, "ai_provider_combo")
            ai_provider_combo.setCurrentText("Groq")
            qtbot.wait(100)

            groq_model_combo = ai_tab.widget.findChild(QComboBox, "groq_model_input")
            groq_model_combo.setCurrentText("")
            qtbot.wait(50)

            refresh_btn = ai_tab.widget.findChild(
                QPushButton, "refresh_groq_models_btn"
            )
            refresh_btn.click()

            qtbot.waitUntil(lambda: len(dialog_shown) > 0, timeout=5000)

            assert groq_model_combo.currentText() == "deepseek-r1-distill-llama-70b"
            mock_client.fetch_available_models.assert_called_once()

    def test_nvidia_api_connection_failure(self, qtbot, settings_window, monkeypatch):
        """测试NVIDIA API连接失败"""
        # Mock NVIDIA客户端返回失败
        mock_client = Mock()
        mock_client.test_connection = Mock(return_value=(False, "Invalid API key"))

        dialog_shown = []

        def mock_warning(*args, **kwargs):
            dialog_shown.append(("warning", args[2]))

        monkeypatch.setattr(QMessageBox, "warning", mock_warning)

        with patch("sonicinput.ai.nvidia.NvidiaClient", return_value=mock_client):
            # 设置UI
            settings_window.show()
            qtbot.waitExposed(settings_window)
            settings_window.tab_widget.setCurrentIndex(3)  # AI tab
            qtbot.wait(50)

            ai_tab = settings_window.ai_tab

            # 切换到NVIDIA提供商
            ai_provider_combo = ai_tab.widget.findChild(QComboBox, "ai_provider_combo")
            ai_provider_combo.setCurrentText("NVIDIA")
            qtbot.wait(100)

            # 设置API key
            nvidia_api_key_input = ai_tab.widget.findChild(
                QLineEdit, "nvidia_api_key_input"
            )
            nvidia_api_key_input.setText("invalid-nvidia-key")
            qtbot.wait(50)

            # 点击测试按钮
            test_connection_btn = ai_tab.widget.findChild(
                QPushButton, "test_connection_btn"
            )
            test_connection_btn.click()
            qtbot.wait(100)

            # 等待失败对话框
            qtbot.waitUntil(lambda: len(dialog_shown) > 0, timeout=5000)

            # 验证失败对话框显示
            assert len(dialog_shown) == 1
            assert "failed" in dialog_shown[0][1].lower()
            assert "Invalid API key" in dialog_shown[0][1]

    def test_nvidia_refresh_model_list_updates_combo(
        self, qtbot, settings_window, monkeypatch
    ):
        """测试NVIDIA模型列表刷新会更新可编辑下拉框"""
        mock_client = Mock()
        mock_client.fetch_available_models = Mock(
            return_value=[
                "meta/llama-3.1-8b-instruct",
                "nvidia/llama-3.1-nemotron-70b-instruct",
            ]
        )

        dialog_shown = []

        def mock_info(*args, **kwargs):
            dialog_shown.append(("success", args[2]))

        monkeypatch.setattr(QMessageBox, "information", mock_info)

        with patch("sonicinput.ai.nvidia.NvidiaClient", return_value=mock_client):
            settings_window.show()
            qtbot.waitExposed(settings_window)
            settings_window.tab_widget.setCurrentIndex(3)  # AI tab
            qtbot.wait(50)

            ai_tab = settings_window.ai_tab
            ai_provider_combo = ai_tab.widget.findChild(QComboBox, "ai_provider_combo")
            ai_provider_combo.setCurrentText("NVIDIA")
            qtbot.wait(100)

            nvidia_model_combo = ai_tab.widget.findChild(
                QComboBox, "nvidia_model_input"
            )
            nvidia_model_combo.setCurrentText("")
            qtbot.wait(50)

            refresh_btn = ai_tab.widget.findChild(
                QPushButton, "refresh_nvidia_models_btn"
            )
            refresh_btn.click()

            qtbot.waitUntil(lambda: len(dialog_shown) > 0, timeout=5000)

            assert nvidia_model_combo.currentText() == "meta/llama-3.1-8b-instruct"
            mock_client.fetch_available_models.assert_called_once()

    def test_openai_compatible_refresh_model_list_updates_combo(
        self, qtbot, settings_window, monkeypatch
    ):
        """测试OpenAI Compatible模型列表刷新会更新可编辑下拉框"""
        mock_client = Mock()
        mock_client.fetch_available_models = Mock(
            return_value=[
                "gpt-oss-20b",
                "qwen2.5-7b-instruct",
            ]
        )

        dialog_shown = []

        def mock_info(*args, **kwargs):
            dialog_shown.append(("success", args[2]))

        monkeypatch.setattr(QMessageBox, "information", mock_info)

        with patch(
            "sonicinput.ai.openai_compatible.OpenAICompatibleClient",
            return_value=mock_client,
        ):
            settings_window.show()
            qtbot.waitExposed(settings_window)
            settings_window.tab_widget.setCurrentIndex(3)  # AI tab
            qtbot.wait(50)

            ai_tab = settings_window.ai_tab
            ai_provider_combo = ai_tab.widget.findChild(QComboBox, "ai_provider_combo")
            ai_provider_combo.setCurrentText("OpenAI Compatible")
            qtbot.wait(100)

            openai_base_url = ai_tab.widget.findChild(
                QLineEdit, "openai_compatible_base_url_input"
            )
            openai_base_url.setText("http://localhost:1234/v1")
            qtbot.wait(50)

            openai_model_combo = ai_tab.widget.findChild(
                QComboBox, "openai_compatible_model_input"
            )
            openai_model_combo.setCurrentText("")
            qtbot.wait(50)

            refresh_btn = ai_tab.widget.findChild(
                QPushButton, "refresh_openai_compatible_models_btn"
            )
            refresh_btn.click()

            qtbot.waitUntil(lambda: len(dialog_shown) > 0, timeout=5000)

            assert openai_model_combo.currentText() == "gpt-oss-20b"
            mock_client.fetch_available_models.assert_called_once()

    def test_openai_compatible_api_connection_success(
        self, qtbot, settings_window, monkeypatch
    ):
        """测试OpenAI Compatible API连接成功"""
        # Mock OpenAI Compatible客户端
        mock_client = Mock()
        mock_client.test_connection = Mock(return_value=(True, ""))

        dialog_shown = []

        def mock_info(*args, **kwargs):
            dialog_shown.append(("success", args[2]))

        monkeypatch.setattr(QMessageBox, "information", mock_info)

        with patch(
            "sonicinput.ai.openai_compatible.OpenAICompatibleClient",
            return_value=mock_client,
        ):
            # 设置UI
            settings_window.show()
            qtbot.waitExposed(settings_window)
            settings_window.tab_widget.setCurrentIndex(3)  # AI tab
            qtbot.wait(50)

            ai_tab = settings_window.ai_tab

            # 切换到OpenAI Compatible提供商
            ai_provider_combo = ai_tab.widget.findChild(QComboBox, "ai_provider_combo")
            ai_provider_combo.setCurrentText("OpenAI Compatible")
            qtbot.wait(100)

            # 设置Base URL和API key
            openai_compatible_base_url_input = ai_tab.widget.findChild(
                QLineEdit, "openai_compatible_base_url_input"
            )
            openai_compatible_base_url_input.setText("https://api.example.com/v1")
            openai_compatible_api_key_input = ai_tab.widget.findChild(
                QLineEdit, "openai_compatible_api_key_input"
            )
            openai_compatible_api_key_input.setText("test-openai-compatible-key")
            qtbot.wait(50)

            # 点击测试按钮
            test_connection_btn = ai_tab.widget.findChild(
                QPushButton, "test_connection_btn"
            )
            test_connection_btn.click()
            qtbot.wait(100)

            # 等待成功对话框
            qtbot.waitUntil(lambda: len(dialog_shown) > 0, timeout=5000)

            # 验证成功
            assert len(dialog_shown) == 1
            assert "successful" in dialog_shown[0][1].lower()
            assert "OpenAI Compatible" in dialog_shown[0][1]


class TestTranscriptionTabAPIConnections:
    """Transcription Tab API连接测试"""

    def test_groq_transcription_api_success(self, qtbot, settings_window, monkeypatch):
        """测试Groq转录API连接成功"""
        # Mock GroqSpeechService
        mock_service = Mock()
        mock_service.load_model = Mock(return_value=True)

        dialog_shown = []

        def mock_info(*args, **kwargs):
            dialog_shown.append(("success", args[2]))

        monkeypatch.setattr(QMessageBox, "information", mock_info)

        with patch("sonicinput.speech.GroqSpeechService", return_value=mock_service):
            # 设置UI
            settings_window.show()
            qtbot.waitExposed(settings_window)
            settings_window.tab_widget.setCurrentIndex(1)  # Transcription tab
            qtbot.wait(50)

            transcription_tab = settings_window.transcription_tab

            # 切换到groq提供商
            transcription_provider_combo = transcription_tab.widget.findChild(
                QComboBox, "transcription_provider_combo"
            )
            transcription_provider_combo.setCurrentText("groq")
            qtbot.wait(100)  # 等待provider切换完成

            # 设置API key
            groq_api_key_edit = transcription_tab.widget.findChild(
                QLineEdit, "groq_api_key_edit"
            )
            groq_api_key_edit.setText("test-groq-transcription-key")
            qtbot.wait(50)

            # 点击测试按钮 (Groq uses test_model_button)
            test_model_btn = transcription_tab.widget.findChild(
                QPushButton, "test_model_btn"
            )
            test_model_btn.click()
            qtbot.wait(100)

            # 等待成功对话框
            qtbot.waitUntil(lambda: len(dialog_shown) > 0, timeout=5000)

            # 验证成功
            assert len(dialog_shown) == 1
            assert "successful" in dialog_shown[0][1].lower()
            assert "Groq" in dialog_shown[0][1]

    def test_siliconflow_api_success(self, qtbot, settings_window, monkeypatch):
        """测试SiliconFlow API连接成功"""
        # Mock SiliconFlowEngine
        mock_engine = Mock()
        mock_engine.test_connection = Mock(return_value=True)

        dialog_shown = []

        def mock_info(*args, **kwargs):
            dialog_shown.append(("success", args[2]))

        monkeypatch.setattr(QMessageBox, "information", mock_info)

        with patch(
            "sonicinput.speech.siliconflow_engine.SiliconFlowEngine",
            return_value=mock_engine,
        ):
            # 设置UI
            settings_window.show()
            qtbot.waitExposed(settings_window)
            settings_window.tab_widget.setCurrentIndex(1)  # Transcription tab
            qtbot.wait(50)

            transcription_tab = settings_window.transcription_tab

            # 切换到siliconflow提供商
            transcription_provider_combo = transcription_tab.widget.findChild(
                QComboBox, "transcription_provider_combo"
            )
            transcription_provider_combo.setCurrentText("siliconflow")
            qtbot.wait(100)

            # 设置API key
            siliconflow_api_key_edit = transcription_tab.widget.findChild(
                QLineEdit, "siliconflow_api_key_edit"
            )
            siliconflow_api_key_edit.setText("test-siliconflow-key")
            qtbot.wait(50)

            # 点击测试按钮 (SiliconFlow uses test_model_button)
            test_model_btn = transcription_tab.widget.findChild(
                QPushButton, "test_model_btn"
            )
            test_model_btn.click()
            qtbot.wait(100)

            # 等待成功对话框
            qtbot.waitUntil(lambda: len(dialog_shown) > 0, timeout=5000)

            # 验证成功
            assert len(dialog_shown) == 1
            assert "successful" in dialog_shown[0][1].lower()
            assert "SiliconFlow" in dialog_shown[0][1]

    def test_qwen_api_success(self, qtbot, settings_window, monkeypatch):
        """测试Qwen API连接成功"""
        # Mock SpeechServiceFactory.create_service
        mock_service = Mock()
        mock_service.test_connection = Mock(return_value=True)

        dialog_shown = []

        def mock_info(*args, **kwargs):
            dialog_shown.append(("success", args[2]))

        monkeypatch.setattr(QMessageBox, "information", mock_info)

        with patch(
            "sonicinput.speech.speech_service_factory.SpeechServiceFactory.create_service",
            return_value=mock_service,
        ):
            # 设置UI
            settings_window.show()
            qtbot.waitExposed(settings_window)
            settings_window.tab_widget.setCurrentIndex(1)  # Transcription tab
            qtbot.wait(50)

            transcription_tab = settings_window.transcription_tab

            # 切换到qwen提供商
            transcription_provider_combo = transcription_tab.widget.findChild(
                QComboBox, "transcription_provider_combo"
            )
            transcription_provider_combo.setCurrentText("qwen")
            qtbot.wait(100)

            # 设置API key
            qwen_api_key_edit = transcription_tab.widget.findChild(
                QLineEdit, "qwen_api_key_edit"
            )
            qwen_api_key_edit.setText("test-qwen-dashscope-key")
            qtbot.wait(50)

            # 点击测试按钮 (Qwen uses test_model_button)
            test_model_btn = transcription_tab.widget.findChild(
                QPushButton, "test_model_btn"
            )
            test_model_btn.click()
            qtbot.wait(100)

            # 等待成功对话框
            qtbot.waitUntil(lambda: len(dialog_shown) > 0, timeout=5000)

            # 验证成功
            assert len(dialog_shown) == 1
            assert "successful" in dialog_shown[0][1].lower()
            assert "Qwen" in dialog_shown[0][1]

    def test_api_test_with_threading(self, qtbot, settings_window, monkeypatch):
        """测试API测试使用后台线程(不阻塞UI)"""
        # Mock API客户端
        mock_client = Mock()
        test_called = []

        def mock_test_connection(*args, **kwargs):
            # 记录这个方法在线程中被调用
            import threading

            test_called.append(threading.current_thread().name)
            return True, ""

        mock_client.test_connection = mock_test_connection

        # Mock information dialog
        dialog_shown = []

        def mock_info(*args, **kwargs):
            dialog_shown.append(("success", args[2]))

        monkeypatch.setattr(QMessageBox, "information", mock_info)

        with patch(
            "sonicinput.ai.openrouter.OpenRouterClient", return_value=mock_client
        ):
            # 设置UI
            settings_window.show()
            qtbot.waitExposed(settings_window)
            settings_window.tab_widget.setCurrentIndex(3)  # AI tab
            qtbot.wait(50)

            ai_tab = settings_window.ai_tab

            # 切换到OpenRouter
            ai_provider_combo = ai_tab.widget.findChild(QComboBox, "ai_provider_combo")
            ai_provider_combo.setCurrentText("OpenRouter")
            qtbot.wait(100)

            # 设置API key
            api_key_input = ai_tab.widget.findChild(QLineEdit, "api_key_input")
            api_key_input.setText("test-key")
            qtbot.wait(50)

            # 点击测试按钮
            test_connection_btn = ai_tab.widget.findChild(
                QPushButton, "test_connection_btn"
            )
            test_connection_btn.click()
            qtbot.wait(100)

            # 等待线程完成
            qtbot.waitUntil(lambda: len(test_called) > 0, timeout=5000)

            # 验证test_connection在后台线程中被调用(不是主线程)
            assert len(test_called) == 1
            assert "Thread-" in test_called[0]  # 后台线程名包含"Thread-"

            # 等待成功对话框
            qtbot.waitUntil(lambda: len(dialog_shown) > 0, timeout=5000)

            # 验证成功对话框
            assert len(dialog_shown) == 1
            assert "successful" in dialog_shown[0][1].lower()
