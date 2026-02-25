"""Transcription设置标签页"""

from typing import Any, Dict

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from .base_tab import BaseSettingsTab


class DataAwareComboBox(QComboBox):
    def setCurrentText(self, text: str) -> None:
        index = self.findText(text)
        if index != -1:
            super().setCurrentText(text)
            return
        data_index = self.findData(text)
        if data_index != -1:
            self.setCurrentIndex(data_index)
            return
        super().setCurrentText(text)


class TranscriptionTab(BaseSettingsTab):
    """Transcription设置标签页

    包含：
    - 转录提供商选择（sherpa-onnx / Groq / SiliconFlow / Qwen）
    - sherpa-onnx 本地模型配置
    - 云服务 API 配置（Groq / SiliconFlow / Qwen）
    - 模型管理（加载/卸载/测试）
    """

    def _setup_ui(self) -> None:
        """设置UI"""
        layout = QVBoxLayout(self.widget)

        # 转录提供商选择组
        provider_group = QGroupBox("Transcription Provider")
        provider_layout = QFormLayout(provider_group)
        self.provider_group = provider_group
        self.provider_layout = provider_layout

        self.transcription_provider_combo = DataAwareComboBox()
        self.transcription_provider_combo.setObjectName("transcription_provider_combo")
        self.transcription_provider_combo.addItem("Local (sherpa-onnx)", "local")
        self.transcription_provider_combo.addItem("Groq Cloud", "groq")
        self.transcription_provider_combo.addItem("SiliconFlow Cloud", "siliconflow")
        self.transcription_provider_combo.addItem("Qwen ASR (Alibaba Cloud)", "qwen")
        self.transcription_provider_combo.currentIndexChanged.connect(
            self._on_provider_changed
        )
        provider_layout.addRow("Provider:", self.transcription_provider_combo)

        layout.addWidget(provider_group)

        # sherpa-onnx 本地模型设置组
        model_group = QGroupBox("sherpa-onnx Configuration")
        model_layout = QFormLayout(model_group)
        self.model_group = model_group
        self.model_layout = model_layout

        # 模型选择
        self.whisper_model_combo = QComboBox()
        self.whisper_model_combo.addItems(["paraformer", "zipformer-small"])
        model_layout.addRow("Model:", self.whisper_model_combo)

        # 语言设置
        self.whisper_language_combo = QComboBox()
        self.whisper_language_combo.addItem("Auto", "auto")
        self.whisper_language_combo.addItem("English", "en")
        self.whisper_language_combo.addItem("Chinese", "zh")
        self.whisper_language_combo.addItem("Japanese", "ja")
        self.whisper_language_combo.addItem("Korean", "ko")
        self.whisper_language_combo.addItem("Spanish", "es")
        self.whisper_language_combo.addItem("French", "fr")
        self.whisper_language_combo.addItem("German", "de")
        self.whisper_language_combo.addItem("Italian", "it")
        self.whisper_language_combo.addItem("Portuguese", "pt")
        self.whisper_language_combo.addItem("Russian", "ru")
        model_layout.addRow("Language:", self.whisper_language_combo)

        # 流式模式选择
        self.streaming_mode_combo = QComboBox()
        self.streaming_mode_combo.addItem("Chunked (recommended)", "chunked")
        self.streaming_mode_combo.addItem("Realtime", "realtime")
        self.streaming_mode_combo.setToolTip(
            "chunked: 30s segments with AI optimization (recommended)\n"
            "realtime: Edge-to-edge streaming with lowest latency"
        )
        model_layout.addRow("Streaming Mode:", self.streaming_mode_combo)

        # 自动加载
        self.auto_load_model_checkbox = QCheckBox("Load model on startup")
        model_layout.addRow("", self.auto_load_model_checkbox)

        layout.addWidget(model_group)

        # 模型管理组
        management_group = QGroupBox("Model Management")
        management_layout = QVBoxLayout(management_group)
        self.management_group = management_group

        # 当前状态
        self.model_status_label = QLabel("Model not loaded")
        management_layout.addWidget(self.model_status_label)

        # 操作按钮
        model_buttons_layout = QHBoxLayout()

        self.load_model_button = QPushButton("Load Model")
        self.load_model_button.clicked.connect(self._load_model)
        model_buttons_layout.addWidget(self.load_model_button)

        self.unload_model_button = QPushButton("Unload Model")
        self.unload_model_button.clicked.connect(self._unload_model)
        model_buttons_layout.addWidget(self.unload_model_button)

        self.test_model_button = QPushButton("Test Model")
        self.test_model_button.setObjectName("test_model_btn")
        self.test_model_button.clicked.connect(self._test_model)
        model_buttons_layout.addWidget(self.test_model_button)

        management_layout.addLayout(model_buttons_layout)

        # 进度条
        self.model_progress = QProgressBar()
        self.model_progress.hide()
        management_layout.addWidget(self.model_progress)

        layout.addWidget(management_group)

        # Groq API 配置组
        groq_group = QGroupBox("Groq Cloud API Configuration")
        groq_layout = QFormLayout(groq_group)
        self.groq_group = groq_group
        self.groq_layout = groq_layout

        # API Key
        self.groq_api_key_edit = QLineEdit()
        self.groq_api_key_edit.setObjectName("groq_api_key_edit")
        self.groq_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.groq_api_key_edit.setPlaceholderText("Enter Groq API key")
        self.groq_api_key_edit.textChanged.connect(self._on_groq_api_key_changed)
        groq_layout.addRow("API Key:", self.groq_api_key_edit)

        # Base URL
        self.groq_base_url_edit = QLineEdit()
        self.groq_base_url_edit.setPlaceholderText("Leave empty to restore default")
        groq_layout.addRow("Base URL:", self.groq_base_url_edit)

        # 模型选择（支持自定义输入）
        self.groq_model_combo = QComboBox()
        self.groq_model_combo.setEditable(True)  # 允许用户自定义输入
        self.groq_model_combo.addItems(["whisper-large-v3-turbo", "whisper-large-v3"])
        groq_layout.addRow("Model:", self.groq_model_combo)
        self.refresh_groq_models_button = QPushButton("Refresh Model List")
        self.refresh_groq_models_button.setObjectName("refresh_groq_models_btn")
        self.refresh_groq_models_button.clicked.connect(self._refresh_groq_models)
        groq_layout.addRow("", self.refresh_groq_models_button)

        # 超时设置
        self.groq_timeout_spinbox = QSpinBox()
        self.groq_timeout_spinbox.setRange(5, 120)
        self.groq_timeout_spinbox.setValue(30)
        self.groq_timeout_spinbox.setSuffix("s")
        groq_layout.addRow("Timeout:", self.groq_timeout_spinbox)

        # 重试设置
        self.groq_max_retries_spinbox = QSpinBox()
        self.groq_max_retries_spinbox.setRange(0, 10)
        self.groq_max_retries_spinbox.setValue(3)
        groq_layout.addRow("Max Retries:", self.groq_max_retries_spinbox)

        layout.addWidget(groq_group)

        # SiliconFlow API 配置组
        siliconflow_group = QGroupBox("SiliconFlow Cloud API Configuration")
        siliconflow_layout = QFormLayout(siliconflow_group)
        self.siliconflow_group = siliconflow_group
        self.siliconflow_layout = siliconflow_layout

        # API Key
        self.siliconflow_api_key_edit = QLineEdit()
        self.siliconflow_api_key_edit.setObjectName("siliconflow_api_key_edit")
        self.siliconflow_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.siliconflow_api_key_edit.setPlaceholderText("Enter SiliconFlow API key")
        self.siliconflow_api_key_edit.textChanged.connect(
            self._on_siliconflow_api_key_changed
        )
        siliconflow_layout.addRow("API Key:", self.siliconflow_api_key_edit)

        # Base URL
        self.siliconflow_base_url_edit = QLineEdit()
        self.siliconflow_base_url_edit.setPlaceholderText(
            "Leave empty to restore default"
        )
        siliconflow_layout.addRow("Base URL:", self.siliconflow_base_url_edit)

        # 模型选择（支持自定义输入）
        self.siliconflow_model_combo = QComboBox()
        self.siliconflow_model_combo.setEditable(True)  # 允许用户自定义输入
        self.siliconflow_model_combo.addItems(
            ["FunAudioLLM/SenseVoiceSmall", "TeleAI/TeleSpeechASR"]
        )
        self.siliconflow_model_combo.setCurrentText("FunAudioLLM/SenseVoiceSmall")
        siliconflow_layout.addRow("Model:", self.siliconflow_model_combo)
        self.refresh_siliconflow_models_button = QPushButton("Refresh Model List")
        self.refresh_siliconflow_models_button.setObjectName(
            "refresh_siliconflow_models_btn"
        )
        self.refresh_siliconflow_models_button.clicked.connect(
            self._refresh_siliconflow_models
        )
        siliconflow_layout.addRow("", self.refresh_siliconflow_models_button)

        # 超时设置
        self.siliconflow_timeout_spinbox = QSpinBox()
        self.siliconflow_timeout_spinbox.setRange(5, 120)
        self.siliconflow_timeout_spinbox.setValue(30)
        self.siliconflow_timeout_spinbox.setSuffix("s")
        siliconflow_layout.addRow("Timeout:", self.siliconflow_timeout_spinbox)

        # 重试设置
        self.siliconflow_max_retries_spinbox = QSpinBox()
        self.siliconflow_max_retries_spinbox.setRange(0, 10)
        self.siliconflow_max_retries_spinbox.setValue(3)
        siliconflow_layout.addRow("Max Retries:", self.siliconflow_max_retries_spinbox)

        layout.addWidget(siliconflow_group)

        # Qwen API 配置组
        qwen_group = QGroupBox("Qwen ASR (Alibaba Cloud) API Configuration")
        qwen_layout = QFormLayout(qwen_group)
        self.qwen_group = qwen_group
        self.qwen_layout = qwen_layout

        # API Key
        self.qwen_api_key_edit = QLineEdit()
        self.qwen_api_key_edit.setObjectName("qwen_api_key_edit")
        self.qwen_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.qwen_api_key_edit.setPlaceholderText("Enter DashScope API key")
        self.qwen_api_key_edit.textChanged.connect(self._on_qwen_api_key_changed)
        qwen_layout.addRow("API Key:", self.qwen_api_key_edit)

        # Model
        self.qwen_model_combo = QComboBox()
        self.qwen_model_combo.addItems(["qwen3-asr-flash"])
        self.qwen_model_combo.setToolTip(
            "Qwen ASR model with emotion and language detection"
        )
        qwen_layout.addRow("Model:", self.qwen_model_combo)

        # Base URL
        self.qwen_base_url_edit = QLineEdit()
        self.qwen_base_url_edit.setPlaceholderText(
            "Leave empty to use default (https://dashscope.aliyuncs.com)"
        )
        qwen_layout.addRow("Base URL:", self.qwen_base_url_edit)

        # Enable ITN (Inverse Text Normalization)
        self.qwen_enable_itn_checkbox = QCheckBox("Enable Inverse Text Normalization")
        self.qwen_enable_itn_checkbox.setToolTip(
            "Convert spoken numbers to digits (e.g., '一千' -> '1000')"
        )
        self.qwen_enable_itn_checkbox.setChecked(True)
        qwen_layout.addRow("ITN:", self.qwen_enable_itn_checkbox)

        # Timeout
        self.qwen_timeout_spinbox = QSpinBox()
        self.qwen_timeout_spinbox.setRange(10, 180)
        self.qwen_timeout_spinbox.setValue(30)
        self.qwen_timeout_spinbox.setSuffix("s")
        qwen_layout.addRow("Timeout:", self.qwen_timeout_spinbox)

        # Max Retries
        self.qwen_max_retries_spinbox = QSpinBox()
        self.qwen_max_retries_spinbox.setRange(0, 10)
        self.qwen_max_retries_spinbox.setValue(3)
        qwen_layout.addRow("Max Retries:", self.qwen_max_retries_spinbox)

        layout.addWidget(qwen_group)

        layout.addStretch()

        # 保存控件引用
        self.retranslate_ui()

        self.controls = {
            "transcription_provider": self.transcription_provider_combo,
            "whisper_model": self.whisper_model_combo,
            "whisper_language": self.whisper_language_combo,
            "streaming_mode": self.streaming_mode_combo,
            "auto_load_model": self.auto_load_model_checkbox,
            "groq_api_key": self.groq_api_key_edit,
            "groq_base_url": self.groq_base_url_edit,
            "groq_model": self.groq_model_combo,
            "refresh_groq_models_btn": self.refresh_groq_models_button,
            "groq_timeout": self.groq_timeout_spinbox,
            "groq_max_retries": self.groq_max_retries_spinbox,
            "siliconflow_api_key": self.siliconflow_api_key_edit,
            "siliconflow_base_url": self.siliconflow_base_url_edit,
            "siliconflow_model": self.siliconflow_model_combo,
            "refresh_siliconflow_models_btn": self.refresh_siliconflow_models_button,
            "siliconflow_timeout": self.siliconflow_timeout_spinbox,
            "siliconflow_max_retries": self.siliconflow_max_retries_spinbox,
            "qwen_api_key": self.qwen_api_key_edit,
            "qwen_model": self.qwen_model_combo,
            "qwen_base_url": self.qwen_base_url_edit,
            "qwen_enable_itn": self.qwen_enable_itn_checkbox,
            "qwen_timeout": self.qwen_timeout_spinbox,
            "qwen_max_retries": self.qwen_max_retries_spinbox,
            "model_status": self.model_status_label,
        }

        # 暴露控件到parent_window
        self.parent_window.whisper_model_combo = self.whisper_model_combo
        self.parent_window.whisper_language_combo = self.whisper_language_combo
        self.parent_window.streaming_mode_combo = self.streaming_mode_combo
        self.parent_window.auto_load_model_checkbox = self.auto_load_model_checkbox
        self.parent_window.model_status_label = self.model_status_label

    def retranslate_ui(self) -> None:
        """Update UI text for the current language."""

        def set_label(layout, field, value):
            label = layout.labelForField(field)
            if label:
                label.setText(value)

        self.provider_group.setTitle(
            QCoreApplication.translate("TranscriptionTab", "Transcription Provider")
        )
        set_label(
            self.provider_layout,
            self.transcription_provider_combo,
            QCoreApplication.translate("TranscriptionTab", "Provider:"),
        )
        provider_texts = [
            QCoreApplication.translate("TranscriptionTab", "Local (sherpa-onnx)"),
            QCoreApplication.translate("TranscriptionTab", "Groq Cloud"),
            QCoreApplication.translate("TranscriptionTab", "SiliconFlow Cloud"),
            QCoreApplication.translate("TranscriptionTab", "Qwen ASR (Alibaba Cloud)"),
        ]
        for index, text_value in enumerate(provider_texts):
            if index < self.transcription_provider_combo.count():
                self.transcription_provider_combo.setItemText(index, text_value)

        self.model_group.setTitle(
            QCoreApplication.translate("TranscriptionTab", "sherpa-onnx Configuration")
        )
        set_label(
            self.model_layout,
            self.whisper_model_combo,
            QCoreApplication.translate("TranscriptionTab", "Model:"),
        )
        set_label(
            self.model_layout,
            self.whisper_language_combo,
            QCoreApplication.translate("TranscriptionTab", "Language:"),
        )
        set_label(
            self.model_layout,
            self.streaming_mode_combo,
            QCoreApplication.translate("TranscriptionTab", "Streaming Mode:"),
        )

        language_texts = [
            QCoreApplication.translate("TranscriptionTab", "Auto"),
            QCoreApplication.translate("TranscriptionTab", "English"),
            QCoreApplication.translate("TranscriptionTab", "Chinese"),
            QCoreApplication.translate("TranscriptionTab", "Japanese"),
            QCoreApplication.translate("TranscriptionTab", "Korean"),
            QCoreApplication.translate("TranscriptionTab", "Spanish"),
            QCoreApplication.translate("TranscriptionTab", "French"),
            QCoreApplication.translate("TranscriptionTab", "German"),
            QCoreApplication.translate("TranscriptionTab", "Italian"),
            QCoreApplication.translate("TranscriptionTab", "Portuguese"),
            QCoreApplication.translate("TranscriptionTab", "Russian"),
        ]
        for index, text_value in enumerate(language_texts):
            if index < self.whisper_language_combo.count():
                self.whisper_language_combo.setItemText(index, text_value)

        streaming_texts = [
            QCoreApplication.translate("TranscriptionTab", "Chunked (recommended)"),
            QCoreApplication.translate("TranscriptionTab", "Realtime"),
        ]
        for index, text_value in enumerate(streaming_texts):
            if index < self.streaming_mode_combo.count():
                self.streaming_mode_combo.setItemText(index, text_value)

        self.streaming_mode_combo.setToolTip(
            QCoreApplication.translate(
                "TranscriptionTab",
                "chunked: 30s segments with AI optimization (recommended)\n"
                "realtime: Edge-to-edge streaming with lowest latency",
            )
        )
        self.auto_load_model_checkbox.setText(
            QCoreApplication.translate("TranscriptionTab", "Load model on startup")
        )

        self.groq_group.setTitle(
            QCoreApplication.translate(
                "TranscriptionTab", "Groq Cloud API Configuration"
            )
        )
        set_label(
            self.groq_layout,
            self.groq_api_key_edit,
            QCoreApplication.translate("TranscriptionTab", "API Key:"),
        )
        set_label(
            self.groq_layout,
            self.groq_base_url_edit,
            QCoreApplication.translate("TranscriptionTab", "Base URL:"),
        )
        set_label(
            self.groq_layout,
            self.groq_model_combo,
            QCoreApplication.translate("TranscriptionTab", "Model:"),
        )
        self.refresh_groq_models_button.setText(
            QCoreApplication.translate("TranscriptionTab", "Refresh Model List")
        )
        set_label(
            self.groq_layout,
            self.groq_timeout_spinbox,
            QCoreApplication.translate("TranscriptionTab", "Timeout:"),
        )
        set_label(
            self.groq_layout,
            self.groq_max_retries_spinbox,
            QCoreApplication.translate("TranscriptionTab", "Max Retries:"),
        )
        self.groq_api_key_edit.setPlaceholderText(
            QCoreApplication.translate("TranscriptionTab", "Enter Groq API key")
        )
        self.groq_base_url_edit.setPlaceholderText(
            QCoreApplication.translate(
                "TranscriptionTab", "Leave empty to restore default"
            )
        )
        self.groq_timeout_spinbox.setSuffix(
            QCoreApplication.translate("TranscriptionTab", "s")
        )

        self.siliconflow_group.setTitle(
            QCoreApplication.translate(
                "TranscriptionTab", "SiliconFlow Cloud API Configuration"
            )
        )
        set_label(
            self.siliconflow_layout,
            self.siliconflow_api_key_edit,
            QCoreApplication.translate("TranscriptionTab", "API Key:"),
        )
        set_label(
            self.siliconflow_layout,
            self.siliconflow_base_url_edit,
            QCoreApplication.translate("TranscriptionTab", "Base URL:"),
        )
        set_label(
            self.siliconflow_layout,
            self.siliconflow_model_combo,
            QCoreApplication.translate("TranscriptionTab", "Model:"),
        )
        self.refresh_siliconflow_models_button.setText(
            QCoreApplication.translate("TranscriptionTab", "Refresh Model List")
        )
        set_label(
            self.siliconflow_layout,
            self.siliconflow_timeout_spinbox,
            QCoreApplication.translate("TranscriptionTab", "Timeout:"),
        )
        set_label(
            self.siliconflow_layout,
            self.siliconflow_max_retries_spinbox,
            QCoreApplication.translate("TranscriptionTab", "Max Retries:"),
        )
        self.siliconflow_api_key_edit.setPlaceholderText(
            QCoreApplication.translate("TranscriptionTab", "Enter SiliconFlow API key")
        )
        self.siliconflow_base_url_edit.setPlaceholderText(
            QCoreApplication.translate(
                "TranscriptionTab", "Leave empty to restore default"
            )
        )
        self.siliconflow_timeout_spinbox.setSuffix(
            QCoreApplication.translate("TranscriptionTab", "s")
        )

        self.qwen_group.setTitle(
            QCoreApplication.translate(
                "TranscriptionTab", "Qwen ASR (Alibaba Cloud) API Configuration"
            )
        )
        set_label(
            self.qwen_layout,
            self.qwen_api_key_edit,
            QCoreApplication.translate("TranscriptionTab", "API Key:"),
        )
        set_label(
            self.qwen_layout,
            self.qwen_model_combo,
            QCoreApplication.translate("TranscriptionTab", "Model:"),
        )
        set_label(
            self.qwen_layout,
            self.qwen_base_url_edit,
            QCoreApplication.translate("TranscriptionTab", "Base URL:"),
        )
        set_label(
            self.qwen_layout,
            self.qwen_enable_itn_checkbox,
            QCoreApplication.translate("TranscriptionTab", "ITN:"),
        )
        set_label(
            self.qwen_layout,
            self.qwen_timeout_spinbox,
            QCoreApplication.translate("TranscriptionTab", "Timeout:"),
        )
        set_label(
            self.qwen_layout,
            self.qwen_max_retries_spinbox,
            QCoreApplication.translate("TranscriptionTab", "Max Retries:"),
        )
        self.qwen_api_key_edit.setPlaceholderText(
            QCoreApplication.translate("TranscriptionTab", "Enter DashScope API key")
        )
        self.qwen_model_combo.setToolTip(
            QCoreApplication.translate(
                "TranscriptionTab",
                "Qwen ASR model with emotion and language detection",
            )
        )
        self.qwen_base_url_edit.setPlaceholderText(
            QCoreApplication.translate(
                "TranscriptionTab",
                "Leave empty to use default (https://dashscope.aliyuncs.com)",
            )
        )
        self.qwen_enable_itn_checkbox.setText(
            QCoreApplication.translate(
                "TranscriptionTab", "Enable Inverse Text Normalization"
            )
        )
        self.qwen_enable_itn_checkbox.setToolTip(
            QCoreApplication.translate(
                "TranscriptionTab",
                "Convert spoken numbers to digits (e.g., '1000' for one thousand)",
            )
        )
        self.qwen_timeout_spinbox.setSuffix(
            QCoreApplication.translate("TranscriptionTab", "s")
        )

        # Refresh provider-dependent labels after translation update.
        self._on_provider_changed(self.transcription_provider_combo.currentData())

    def load_config(self, config: Dict[str, Any]) -> None:
        """从配置加载UI状态

        Args:
            config: 完整配置字典
        """
        # 转录配置（新）
        transcription_config = config.get("transcription", {})
        provider = transcription_config.get("provider", "local")
        provider_index = self.transcription_provider_combo.findData(provider)
        if provider_index >= 0:
            self.transcription_provider_combo.setCurrentIndex(provider_index)
        else:
            self.transcription_provider_combo.setCurrentIndex(0)

        # sherpa-onnx local settings
        local_config = transcription_config.get("local", {})
        # Fallback to old whisper config for backward compatibility
        whisper_config = config.get("whisper", {})

        self.whisper_model_combo.setCurrentText(
            local_config.get("model", whisper_config.get("model", "paraformer"))
        )
        language_value = local_config.get(
            "language", whisper_config.get("language", "auto")
        )
        language_index = self.whisper_language_combo.findData(language_value)
        if language_index >= 0:
            self.whisper_language_combo.setCurrentIndex(language_index)
        else:
            self.whisper_language_combo.setCurrentIndex(0)
        # streaming_mode只在local provider下有效
        if provider == "local":
            streaming_mode = local_config.get("streaming_mode", "chunked")
            streaming_index = self.streaming_mode_combo.findData(streaming_mode)
            if streaming_index >= 0:
                self.streaming_mode_combo.setCurrentIndex(streaming_index)
            else:
                self.streaming_mode_combo.setCurrentIndex(0)
        self.auto_load_model_checkbox.setChecked(
            local_config.get("auto_load", whisper_config.get("auto_load", True))
        )

        # Groq settings
        groq_config = transcription_config.get("groq", {})
        self.groq_api_key_edit.setText(groq_config.get("api_key", ""))
        self.groq_base_url_edit.setText(
            groq_config.get("base_url", "https://api.groq.com/openai/v1")
        )
        self.groq_model_combo.setCurrentText(
            groq_config.get("model", "whisper-large-v3-turbo")
        )
        self.groq_timeout_spinbox.setValue(groq_config.get("timeout", 30))
        self.groq_max_retries_spinbox.setValue(groq_config.get("max_retries", 3))

        # SiliconFlow settings
        siliconflow_config = transcription_config.get("siliconflow", {})
        self.siliconflow_api_key_edit.setText(siliconflow_config.get("api_key", ""))
        self.siliconflow_base_url_edit.setText(
            siliconflow_config.get("base_url", "https://api.siliconflow.cn/v1")
        )
        self.siliconflow_model_combo.setCurrentText(
            siliconflow_config.get("model", "FunAudioLLM/SenseVoiceSmall")
        )
        self.siliconflow_timeout_spinbox.setValue(siliconflow_config.get("timeout", 30))
        self.siliconflow_max_retries_spinbox.setValue(
            siliconflow_config.get("max_retries", 3)
        )

        # Qwen settings
        qwen_config = transcription_config.get("qwen", {})
        self.qwen_api_key_edit.setText(qwen_config.get("api_key", ""))
        self.qwen_model_combo.setCurrentText(
            qwen_config.get("model", "qwen3-asr-flash")
        )
        self.qwen_base_url_edit.setText(
            qwen_config.get("base_url", "https://dashscope.aliyuncs.com")
        )
        self.qwen_enable_itn_checkbox.setChecked(qwen_config.get("enable_itn", True))
        self.qwen_timeout_spinbox.setValue(qwen_config.get("timeout", 30))
        self.qwen_max_retries_spinbox.setValue(qwen_config.get("max_retries", 3))

        # Update visibility based on provider
        self._on_provider_changed(provider)

    def save_config(self) -> Dict[str, Any]:
        """保存UI状态到配置

        Returns:
            Dict[str, Any]: 配置字典
        """
        # 获取当前provider
        current_provider = self.transcription_provider_combo.currentData() or "local"

        # 构建完整配置（保存所有provider）
        config = {
            "transcription": {
                "provider": current_provider,
                "local": {
                    "model": self.whisper_model_combo.currentText(),
                    "language": self.whisper_language_combo.currentData() or "auto",
                    "auto_load": self.auto_load_model_checkbox.isChecked(),
                },
                "groq": {
                    "api_key": self.groq_api_key_edit.text(),
                    "base_url": self.groq_base_url_edit.text().strip()
                    or "https://api.groq.com/openai/v1",
                    "model": self.groq_model_combo.currentText(),
                    "timeout": self.groq_timeout_spinbox.value(),
                    "max_retries": self.groq_max_retries_spinbox.value(),
                },
                "siliconflow": {
                    "api_key": self.siliconflow_api_key_edit.text(),
                    "base_url": self.siliconflow_base_url_edit.text().strip()
                    or "https://api.siliconflow.cn/v1",
                    "model": self.siliconflow_model_combo.currentText(),
                    "timeout": self.siliconflow_timeout_spinbox.value(),
                    "max_retries": self.siliconflow_max_retries_spinbox.value(),
                },
                "qwen": {
                    "api_key": self.qwen_api_key_edit.text(),
                    "model": self.qwen_model_combo.currentText(),
                    "base_url": self.qwen_base_url_edit.text().strip()
                    or "https://dashscope.aliyuncs.com",
                    "enable_itn": self.qwen_enable_itn_checkbox.isChecked(),
                    "timeout": self.qwen_timeout_spinbox.value(),
                    "max_retries": self.qwen_max_retries_spinbox.value(),
                },
            },
        }

        # streaming_mode只在local provider下才从UI读取并保存
        if current_provider == "local":
            config["transcription"]["local"]["streaming_mode"] = (
                self.streaming_mode_combo.currentData() or "chunked"
            )
        # 否则不添加streaming_mode字段（保持config文件中的原值）

        return config

    def _load_model(self) -> None:
        """加载模型 - 发送信号到父窗口"""
        model_name = self.whisper_model_combo.currentText()
        if hasattr(self.parent_window, "model_load_requested"):
            self.parent_window.model_load_requested.emit(model_name)

    def _unload_model(self) -> None:
        """卸载模型 - 发送信号到父窗口"""
        if hasattr(self.parent_window, "unload_model"):
            self.parent_window.unload_model()

    def _test_model(self) -> None:
        """测试模型或 API 连接 - 根据提供商类型"""
        provider = self.transcription_provider_combo.currentData() or "local"

        if provider == "local":
            # Local 模式：测试本地模型
            if hasattr(self.parent_window, "model_test_requested"):
                self.parent_window.model_test_requested.emit()
        elif provider == "groq":
            # Groq 模式：测试 API 连接
            self._test_groq_api()
        elif provider == "siliconflow":
            # SiliconFlow 模式：测试 API 连接
            self._test_siliconflow_api()
        elif provider == "qwen":
            # Qwen 模式：测试 API 连接
            self._test_qwen_api()

    def _test_groq_api(self) -> None:
        """Test Groq API connection."""
        import threading
        import time

        from PySide6.QtCore import QTimer

        api_key = self.groq_api_key_edit.text().strip()
        if not api_key:
            QMessageBox.warning(
                self.parent_window,
                QCoreApplication.translate("TranscriptionTab", "API Key Missing"),
                QCoreApplication.translate(
                    "TranscriptionTab", "Please enter your Groq API key first."
                ),
            )
            return

        model = self.groq_model_combo.currentText()
        progress_dialog = QMessageBox(self.parent_window)
        progress_dialog.setWindowTitle(
            QCoreApplication.translate("TranscriptionTab", "Testing Groq API")
        )
        progress_dialog.setText(
            QCoreApplication.translate(
                "TranscriptionTab",
                "Testing Groq API connection...\n\n"
                "Model: {model}\n\n"
                "This may take a few seconds.",
            ).format(model=model)
        )
        progress_dialog.setStandardButtons(QMessageBox.StandardButton.Cancel)
        progress_dialog.show()

        QApplication.processEvents()

        result_container = {"success": False, "error": ""}

        def test_connection_thread():
            try:
                from sonicinput.speech import GroqSpeechService

                service = GroqSpeechService(api_key=api_key, model=model)
                success = service.load_model()
                result_container["success"] = success

                if not success:
                    result_container["error"] = QCoreApplication.translate(
                        "TranscriptionTab", "Failed to initialize Groq client"
                    )

            except Exception as e:
                result_container["success"] = False
                result_container["error"] = str(e)

        test_thread = threading.Thread(target=test_connection_thread, daemon=True)
        test_thread.start()

        self._groq_test_thread = test_thread
        self._groq_test_result = result_container
        self._groq_progress_dialog = progress_dialog
        self._groq_test_start_time = time.time()
        self._groq_test_model = model

        self._groq_test_timer = QTimer()
        self._groq_test_timer.timeout.connect(self._check_groq_test_status)
        self._groq_test_timer.start(100)

    def _check_groq_test_status(self) -> None:
        """Check Groq API test status."""
        import time

        try:
            thread_alive = self._groq_test_thread.is_alive()
            elapsed_time = time.time() - self._groq_test_start_time

            if not thread_alive or elapsed_time > 30:
                self._groq_test_timer.stop()

                if (
                    self._groq_progress_dialog
                    and self._groq_progress_dialog.result()
                    == QMessageBox.StandardButton.Cancel
                ):
                    self.model_status_label.setText(
                        QCoreApplication.translate(
                            "TranscriptionTab", "API test cancelled"
                        )
                    )
                    return

                if self._groq_test_result["success"]:
                    self.model_status_label.setText(
                        QCoreApplication.translate(
                            "TranscriptionTab", "API connection successful"
                        )
                    )
                    QMessageBox.information(
                        self.parent_window,
                        QCoreApplication.translate(
                            "TranscriptionTab", "API Test Successful"
                        ),
                        QCoreApplication.translate(
                            "TranscriptionTab",
                            "Successfully connected to Groq API!\n\n"
                            "Model: {model}\n\n"
                            "You can now use cloud transcription.",
                        ).format(model=self._groq_test_model),
                    )
                else:
                    error_msg = self._groq_test_result[
                        "error"
                    ] or QCoreApplication.translate("TranscriptionTab", "Unknown error")
                    self.model_status_label.setText(
                        QCoreApplication.translate(
                            "TranscriptionTab", "API connection failed"
                        )
                    )
                    QMessageBox.critical(
                        self.parent_window,
                        QCoreApplication.translate(
                            "TranscriptionTab", "API Test Failed"
                        ),
                        QCoreApplication.translate(
                            "TranscriptionTab",
                            "Failed to connect to Groq API.\n\n"
                            "Error: {error}\n\n"
                            "Please check:\n"
                            "- API key is valid\n"
                            "- Internet connection\n"
                            "- Groq service status",
                        ).format(error=error_msg),
                    )

                if self._groq_progress_dialog:
                    self._groq_progress_dialog.hide()

                if thread_alive and elapsed_time > 30:
                    self.model_status_label.setText(
                        QCoreApplication.translate(
                            "TranscriptionTab", "API test cancelled"
                        )
                    )

        except Exception as e:
            self.model_status_label.setText(
                QCoreApplication.translate("TranscriptionTab", "API test error")
            )
            QMessageBox.critical(
                self.parent_window,
                QCoreApplication.translate("TranscriptionTab", "API Test Error"),
                QCoreApplication.translate(
                    "TranscriptionTab", "Error during API test: {error}"
                ).format(error=e),
            )

    def _test_siliconflow_api(self) -> None:
        """Test SiliconFlow API connection."""
        import threading
        import time

        from PySide6.QtCore import QTimer

        api_key = self.siliconflow_api_key_edit.text().strip()
        if not api_key:
            QMessageBox.warning(
                self.parent_window,
                QCoreApplication.translate("TranscriptionTab", "API Key Missing"),
                QCoreApplication.translate(
                    "TranscriptionTab", "Please enter your SiliconFlow API key first."
                ),
            )
            return

        model = self.siliconflow_model_combo.currentText()
        progress_dialog = QMessageBox(self.parent_window)
        progress_dialog.setWindowTitle(
            QCoreApplication.translate("TranscriptionTab", "Testing SiliconFlow API")
        )
        progress_dialog.setText(
            QCoreApplication.translate(
                "TranscriptionTab",
                "Testing SiliconFlow API connection...\n\n"
                "Model: {model}\n\n"
                "This may take up to 30 seconds.",
            ).format(model=model)
        )
        progress_dialog.setStandardButtons(QMessageBox.StandardButton.Cancel)
        progress_dialog.show()

        QApplication.processEvents()

        result_container = {"success": False, "error": ""}

        def test_connection_thread():
            try:
                from sonicinput.speech.speech_service_factory import (
                    SpeechServiceFactory,
                )

                service = SpeechServiceFactory.create_service(
                    provider="siliconflow",
                    api_key=api_key,
                    model=model,
                    base_url=self.siliconflow_base_url_edit.text().strip() or None,
                )
                result = service.test_connection()
                if isinstance(result, dict):
                    success = bool(result.get("success"))
                    error_message = result.get("message") or result.get("error", "")
                else:
                    success = bool(result)
                    error_message = ""

                result_container["success"] = success
                if not success:
                    result_container["error"] = (
                        error_message
                        or QCoreApplication.translate(
                            "TranscriptionTab", "Connection test failed"
                        )
                    )

            except Exception as e:
                result_container["success"] = False
                result_container["error"] = str(e)

        test_thread = threading.Thread(target=test_connection_thread, daemon=True)
        test_thread.start()

        self._siliconflow_test_thread = test_thread
        self._siliconflow_test_result = result_container
        self._siliconflow_progress_dialog = progress_dialog
        self._siliconflow_test_start_time = time.time()
        self._siliconflow_test_model = model

        self._siliconflow_test_timer = QTimer()
        self._siliconflow_test_timer.timeout.connect(
            self._check_siliconflow_test_status
        )
        self._siliconflow_test_timer.start(100)

    def _check_siliconflow_test_status(self) -> None:
        """Check SiliconFlow API test status."""
        import time

        try:
            thread_alive = self._siliconflow_test_thread.is_alive()
            elapsed_time = time.time() - self._siliconflow_test_start_time

            if not thread_alive or elapsed_time > 40:
                self._siliconflow_test_timer.stop()

                if (
                    self._siliconflow_progress_dialog
                    and self._siliconflow_progress_dialog.result()
                    == QMessageBox.StandardButton.Cancel
                ):
                    self.model_status_label.setText(
                        QCoreApplication.translate(
                            "TranscriptionTab", "API test cancelled"
                        )
                    )
                    return

                if self._siliconflow_test_result["success"]:
                    self.model_status_label.setText(
                        QCoreApplication.translate(
                            "TranscriptionTab", "API connection successful"
                        )
                    )
                    QMessageBox.information(
                        self.parent_window,
                        QCoreApplication.translate(
                            "TranscriptionTab", "API Test Successful"
                        ),
                        QCoreApplication.translate(
                            "TranscriptionTab",
                            "Successfully connected to SiliconFlow API!\n\n"
                            "Model: {model}\n\n"
                            "You can now use cloud transcription.",
                        ).format(model=self._siliconflow_test_model),
                    )
                else:
                    error_msg = self._siliconflow_test_result[
                        "error"
                    ] or QCoreApplication.translate("TranscriptionTab", "Unknown error")
                    self.model_status_label.setText(
                        QCoreApplication.translate(
                            "TranscriptionTab", "API connection failed"
                        )
                    )
                    QMessageBox.critical(
                        self.parent_window,
                        QCoreApplication.translate(
                            "TranscriptionTab", "API Test Failed"
                        ),
                        QCoreApplication.translate(
                            "TranscriptionTab",
                            "Failed to connect to SiliconFlow API.\n\n"
                            "Error: {error}\n\n"
                            "Please check:\n"
                            "- API key is valid\n"
                            "- Internet connection\n"
                            "- SiliconFlow service status",
                        ).format(error=error_msg),
                    )

                if self._siliconflow_progress_dialog:
                    self._siliconflow_progress_dialog.hide()

                if thread_alive and elapsed_time > 40:
                    self.model_status_label.setText(
                        QCoreApplication.translate(
                            "TranscriptionTab", "API test cancelled"
                        )
                    )

        except Exception as e:
            self.model_status_label.setText(
                QCoreApplication.translate("TranscriptionTab", "API test error")
            )
            QMessageBox.critical(
                self.parent_window,
                QCoreApplication.translate("TranscriptionTab", "API Test Error"),
                QCoreApplication.translate(
                    "TranscriptionTab", "Error during API test: {error}"
                ).format(error=e),
            )

    def _replace_combo_items(self, combo: QComboBox, models: list[str]) -> None:
        """Replace combo options while preserving current text."""
        current_text = combo.currentText().strip()
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(models)
        if current_text and current_text not in models:
            combo.addItem(current_text)
        if current_text:
            combo.setCurrentText(current_text)
        combo.blockSignals(False)

    def _refresh_groq_models(self) -> None:
        """Fetch Groq model IDs from provider endpoint."""
        import threading
        import time

        from PySide6.QtCore import QTimer

        api_key = self.groq_api_key_edit.text().strip()
        if not api_key:
            QMessageBox.warning(
                self.parent_window,
                QCoreApplication.translate("TranscriptionTab", "API Key Missing"),
                QCoreApplication.translate(
                    "TranscriptionTab",
                    "Please enter your Groq API key before refreshing model list.",
                ),
            )
            return

        base_url = self.groq_base_url_edit.text().strip() or "https://api.groq.com/openai/v1"
        progress_dialog = QMessageBox(self.parent_window)
        progress_dialog.setWindowTitle(
            QCoreApplication.translate("TranscriptionTab", "Refreshing Groq Models")
        )
        progress_dialog.setText(
            QCoreApplication.translate(
                "TranscriptionTab",
                "Refreshing Groq model list...\n\nThis may take a few seconds.",
            )
        )
        progress_dialog.setStandardButtons(QMessageBox.StandardButton.Cancel)
        progress_dialog.show()

        QApplication.processEvents()

        result_container = {"success": False, "error": "", "models": []}

        def refresh_models_thread():
            try:
                from sonicinput.speech import GroqSpeechService

                service = GroqSpeechService(
                    api_key=api_key,
                    model=self.groq_model_combo.currentText(),
                    base_url=base_url,
                )
                models = service.fetch_available_models()
                result_container["models"] = models
                result_container["success"] = bool(models)
                if not models:
                    result_container["error"] = QCoreApplication.translate(
                        "TranscriptionTab", "No Groq models returned from API"
                    )
            except Exception as e:
                result_container["success"] = False
                result_container["error"] = str(e)

        refresh_thread = threading.Thread(target=refresh_models_thread, daemon=True)
        refresh_thread.start()

        self._groq_models_refresh_thread = refresh_thread
        self._groq_models_refresh_result = result_container
        self._groq_models_refresh_dialog = progress_dialog
        self._groq_models_refresh_start_time = time.time()

        self._groq_models_refresh_timer = QTimer()
        self._groq_models_refresh_timer.timeout.connect(
            self._check_groq_models_refresh_status
        )
        self._groq_models_refresh_timer.start(100)

    def _check_groq_models_refresh_status(self) -> None:
        """Check Groq model refresh status."""
        import time

        try:
            thread_alive = self._groq_models_refresh_thread.is_alive()
            elapsed_time = time.time() - self._groq_models_refresh_start_time

            if not thread_alive or elapsed_time > 20:
                self._groq_models_refresh_timer.stop()

                if (
                    self._groq_models_refresh_dialog
                    and self._groq_models_refresh_dialog.result()
                    == QMessageBox.StandardButton.Cancel
                ):
                    self.model_status_label.setText(
                        QCoreApplication.translate(
                            "TranscriptionTab", "Model refresh cancelled"
                        )
                    )
                    return

                if self._groq_models_refresh_result["success"]:
                    models = self._groq_models_refresh_result["models"]
                    self._replace_combo_items(self.groq_model_combo, models)
                    self.model_status_label.setText(
                        QCoreApplication.translate(
                            "TranscriptionTab", "Model list updated"
                        )
                    )
                    QMessageBox.information(
                        self.parent_window,
                        QCoreApplication.translate(
                            "TranscriptionTab", "Model List Updated"
                        ),
                        QCoreApplication.translate(
                            "TranscriptionTab",
                            "Groq model list refreshed successfully.\n\nFound {count} models.",
                        ).format(count=len(models)),
                    )
                else:
                    error_msg = self._groq_models_refresh_result[
                        "error"
                    ] or QCoreApplication.translate("TranscriptionTab", "Unknown error")
                    self.model_status_label.setText(
                        QCoreApplication.translate(
                            "TranscriptionTab", "Model refresh failed"
                        )
                    )
                    QMessageBox.critical(
                        self.parent_window,
                        QCoreApplication.translate(
                            "TranscriptionTab", "Model Refresh Failed"
                        ),
                        QCoreApplication.translate(
                            "TranscriptionTab",
                            "Failed to refresh Groq model list.\n\nError: {error}",
                        ).format(error=error_msg),
                    )

                if self._groq_models_refresh_dialog:
                    self._groq_models_refresh_dialog.hide()

        except Exception as e:
            self.model_status_label.setText(
                QCoreApplication.translate("TranscriptionTab", "Model refresh error")
            )
            QMessageBox.critical(
                self.parent_window,
                QCoreApplication.translate("TranscriptionTab", "Model Refresh Error"),
                QCoreApplication.translate(
                    "TranscriptionTab", "Error during model refresh: {error}"
                ).format(error=e),
            )

    def _refresh_siliconflow_models(self) -> None:
        """Fetch SiliconFlow model IDs from provider endpoint."""
        import threading
        import time

        from PySide6.QtCore import QTimer

        api_key = self.siliconflow_api_key_edit.text().strip()
        if not api_key:
            QMessageBox.warning(
                self.parent_window,
                QCoreApplication.translate("TranscriptionTab", "API Key Missing"),
                QCoreApplication.translate(
                    "TranscriptionTab",
                    "Please enter your SiliconFlow API key before refreshing model list.",
                ),
            )
            return

        base_url = (
            self.siliconflow_base_url_edit.text().strip() or "https://api.siliconflow.cn/v1"
        )
        progress_dialog = QMessageBox(self.parent_window)
        progress_dialog.setWindowTitle(
            QCoreApplication.translate(
                "TranscriptionTab", "Refreshing SiliconFlow Models"
            )
        )
        progress_dialog.setText(
            QCoreApplication.translate(
                "TranscriptionTab",
                "Refreshing SiliconFlow model list...\n\nThis may take a few seconds.",
            )
        )
        progress_dialog.setStandardButtons(QMessageBox.StandardButton.Cancel)
        progress_dialog.show()

        QApplication.processEvents()

        result_container = {"success": False, "error": "", "models": []}

        def refresh_models_thread():
            try:
                from sonicinput.speech.siliconflow_engine import SiliconFlowEngine

                service = SiliconFlowEngine(
                    api_key=api_key,
                    model_name=self.siliconflow_model_combo.currentText(),
                    base_url=base_url,
                )
                models = service.fetch_available_models()
                result_container["models"] = models
                result_container["success"] = bool(models)
                if not models:
                    result_container["error"] = QCoreApplication.translate(
                        "TranscriptionTab", "No SiliconFlow models returned from API"
                    )
            except Exception as e:
                result_container["success"] = False
                result_container["error"] = str(e)

        refresh_thread = threading.Thread(target=refresh_models_thread, daemon=True)
        refresh_thread.start()

        self._siliconflow_models_refresh_thread = refresh_thread
        self._siliconflow_models_refresh_result = result_container
        self._siliconflow_models_refresh_dialog = progress_dialog
        self._siliconflow_models_refresh_start_time = time.time()

        self._siliconflow_models_refresh_timer = QTimer()
        self._siliconflow_models_refresh_timer.timeout.connect(
            self._check_siliconflow_models_refresh_status
        )
        self._siliconflow_models_refresh_timer.start(100)

    def _check_siliconflow_models_refresh_status(self) -> None:
        """Check SiliconFlow model refresh status."""
        import time

        try:
            thread_alive = self._siliconflow_models_refresh_thread.is_alive()
            elapsed_time = time.time() - self._siliconflow_models_refresh_start_time

            if not thread_alive or elapsed_time > 20:
                self._siliconflow_models_refresh_timer.stop()

                if (
                    self._siliconflow_models_refresh_dialog
                    and self._siliconflow_models_refresh_dialog.result()
                    == QMessageBox.StandardButton.Cancel
                ):
                    self.model_status_label.setText(
                        QCoreApplication.translate(
                            "TranscriptionTab", "Model refresh cancelled"
                        )
                    )
                    return

                if self._siliconflow_models_refresh_result["success"]:
                    models = self._siliconflow_models_refresh_result["models"]
                    self._replace_combo_items(self.siliconflow_model_combo, models)
                    self.model_status_label.setText(
                        QCoreApplication.translate(
                            "TranscriptionTab", "Model list updated"
                        )
                    )
                    QMessageBox.information(
                        self.parent_window,
                        QCoreApplication.translate(
                            "TranscriptionTab", "Model List Updated"
                        ),
                        QCoreApplication.translate(
                            "TranscriptionTab",
                            "SiliconFlow model list refreshed successfully.\n\nFound {count} models.",
                        ).format(count=len(models)),
                    )
                else:
                    error_msg = self._siliconflow_models_refresh_result[
                        "error"
                    ] or QCoreApplication.translate("TranscriptionTab", "Unknown error")
                    self.model_status_label.setText(
                        QCoreApplication.translate(
                            "TranscriptionTab", "Model refresh failed"
                        )
                    )
                    QMessageBox.critical(
                        self.parent_window,
                        QCoreApplication.translate(
                            "TranscriptionTab", "Model Refresh Failed"
                        ),
                        QCoreApplication.translate(
                            "TranscriptionTab",
                            "Failed to refresh SiliconFlow model list.\n\nError: {error}",
                        ).format(error=error_msg),
                    )

                if self._siliconflow_models_refresh_dialog:
                    self._siliconflow_models_refresh_dialog.hide()

        except Exception as e:
            self.model_status_label.setText(
                QCoreApplication.translate("TranscriptionTab", "Model refresh error")
            )
            QMessageBox.critical(
                self.parent_window,
                QCoreApplication.translate("TranscriptionTab", "Model Refresh Error"),
                QCoreApplication.translate(
                    "TranscriptionTab", "Error during model refresh: {error}"
                ).format(error=e),
            )

    def _on_provider_changed(self, provider: str) -> None:
        """Update UI visibility based on provider selection."""
        provider_value = provider if isinstance(provider, str) else None
        provider_value = (
            provider_value or self.transcription_provider_combo.currentData() or "local"
        )

        is_local = provider_value == "local"
        is_groq = provider_value == "groq"
        is_siliconflow = provider_value == "siliconflow"
        is_qwen = provider_value == "qwen"

        # Show/hide sherpa-onnx settings
        self.model_group.setVisible(is_local)

        # Show/hide Groq settings
        self.groq_group.setVisible(is_groq)

        # Show/hide SiliconFlow settings
        self.siliconflow_group.setVisible(is_siliconflow)

        # Show/hide Qwen settings
        self.qwen_group.setVisible(is_qwen)

        # Update Model Management / API Test section
        if is_local:
            self.management_group.setTitle(
                QCoreApplication.translate("TranscriptionTab", "Model Management")
            )
            self.model_status_label.setText(
                QCoreApplication.translate(
                    "TranscriptionTab", "Checking model status..."
                )
            )
            self.model_status_label.setStyleSheet("QLabel { color: #757575; }")

            self.load_model_button.setVisible(True)
            self.unload_model_button.setVisible(True)
            self.test_model_button.setText(
                QCoreApplication.translate("TranscriptionTab", "Test Model")
            )
        elif is_groq:
            self.management_group.setTitle(
                QCoreApplication.translate("TranscriptionTab", "API Connection Test")
            )
            self.model_status_label.setText(
                QCoreApplication.translate("TranscriptionTab", "API key configured")
                if self.groq_api_key_edit.text().strip()
                else QCoreApplication.translate(
                    "TranscriptionTab", "API key not configured"
                )
            )
            self.load_model_button.setVisible(False)
            self.unload_model_button.setVisible(False)
            self.test_model_button.setText(
                QCoreApplication.translate("TranscriptionTab", "Test API Connection")
            )
        elif is_siliconflow:
            self.management_group.setTitle(
                QCoreApplication.translate("TranscriptionTab", "API Connection Test")
            )
            self.model_status_label.setText(
                QCoreApplication.translate("TranscriptionTab", "API key configured")
                if self.siliconflow_api_key_edit.text().strip()
                else QCoreApplication.translate(
                    "TranscriptionTab", "API key not configured"
                )
            )
            self.load_model_button.setVisible(False)
            self.unload_model_button.setVisible(False)
            self.test_model_button.setText(
                QCoreApplication.translate("TranscriptionTab", "Test API Connection")
            )
        elif is_qwen:
            self.management_group.setTitle(
                QCoreApplication.translate("TranscriptionTab", "API Connection Test")
            )
            self.model_status_label.setText(
                QCoreApplication.translate("TranscriptionTab", "API key configured")
                if self.qwen_api_key_edit.text().strip()
                else QCoreApplication.translate(
                    "TranscriptionTab", "API key not configured"
                )
            )
            self.load_model_button.setVisible(False)
            self.unload_model_button.setVisible(False)
            self.test_model_button.setText(
                QCoreApplication.translate("TranscriptionTab", "Test API Connection")
            )

    def _on_groq_api_key_changed(self, text: str) -> None:
        """Handle Groq API key changes."""
        provider = self.transcription_provider_combo.currentData() or "local"
        if provider == "groq":
            if text.strip():
                self.model_status_label.setText(
                    QCoreApplication.translate("TranscriptionTab", "API key configured")
                )
            else:
                self.model_status_label.setText(
                    QCoreApplication.translate(
                        "TranscriptionTab", "API key not configured"
                    )
                )

    def _on_siliconflow_api_key_changed(self, text: str) -> None:
        """Handle SiliconFlow API key changes."""
        provider = self.transcription_provider_combo.currentData() or "local"
        if provider == "siliconflow":
            if text.strip():
                self.model_status_label.setText(
                    QCoreApplication.translate("TranscriptionTab", "API key configured")
                )
            else:
                self.model_status_label.setText(
                    QCoreApplication.translate(
                        "TranscriptionTab", "API key not configured"
                    )
                )

    # ==================== Qwen API Methods ====================

    def _on_qwen_api_key_changed(self, text: str) -> None:
        """Handle Qwen API key changes."""
        provider = self.transcription_provider_combo.currentData() or "local"
        if provider == "qwen":
            if text.strip():
                self.model_status_label.setText(
                    QCoreApplication.translate("TranscriptionTab", "API key configured")
                )
            else:
                self.model_status_label.setText(
                    QCoreApplication.translate(
                        "TranscriptionTab", "API key not configured"
                    )
                )

    def _test_qwen_api(self) -> None:
        """Test Qwen API connection."""
        import threading
        import time

        from PySide6.QtCore import QTimer

        api_key = self.qwen_api_key_edit.text().strip()
        if not api_key:
            QMessageBox.warning(
                self.parent_window,
                QCoreApplication.translate("TranscriptionTab", "API Key Missing"),
                QCoreApplication.translate(
                    "TranscriptionTab",
                    "Please enter your Qwen (DashScope) API key first.",
                ),
            )
            return

        model = self.qwen_model_combo.currentText()
        progress_dialog = QMessageBox(self.parent_window)
        progress_dialog.setWindowTitle(
            QCoreApplication.translate("TranscriptionTab", "Testing Qwen API")
        )
        progress_dialog.setText(
            QCoreApplication.translate(
                "TranscriptionTab",
                "Testing Qwen ASR API connection...\n\n"
                "Model: {model}\n\n"
                "This may take a few seconds.",
            ).format(model=model)
        )
        progress_dialog.setStandardButtons(QMessageBox.StandardButton.Cancel)
        progress_dialog.show()

        QApplication.processEvents()

        result_container = {"success": False, "error": ""}

        def test_connection_thread():
            try:
                from sonicinput.speech.speech_service_factory import (
                    SpeechServiceFactory,
                )

                service = SpeechServiceFactory.create_service(
                    provider="qwen",
                    api_key=api_key,
                    model=model,
                    base_url=self.qwen_base_url_edit.text().strip()
                    or "https://dashscope.aliyuncs.com",
                    enable_itn=self.qwen_enable_itn_checkbox.isChecked(),
                )
                result = service.test_connection()
                if isinstance(result, dict):
                    success = bool(result.get("success"))
                    error_message = result.get("message") or result.get("error", "")
                else:
                    success = bool(result)
                    error_message = ""

                result_container["success"] = success
                if not success:
                    result_container["error"] = (
                        error_message
                        or QCoreApplication.translate(
                            "TranscriptionTab", "Connection test failed"
                        )
                    )

            except Exception as e:
                result_container["success"] = False
                result_container["error"] = str(e)

        test_thread = threading.Thread(target=test_connection_thread, daemon=True)
        test_thread.start()

        self._qwen_test_thread = test_thread
        self._qwen_test_result = result_container
        self._qwen_progress_dialog = progress_dialog
        self._qwen_test_start_time = time.time()
        self._qwen_test_model = model

        self._qwen_test_timer = QTimer()
        self._qwen_test_timer.timeout.connect(self._check_qwen_test_status)
        self._qwen_test_timer.start(100)

    def _check_qwen_test_status(self) -> None:
        """Check Qwen API test status."""
        import time

        try:
            thread_alive = self._qwen_test_thread.is_alive()
            elapsed_time = time.time() - self._qwen_test_start_time

            if not thread_alive or elapsed_time > 30:
                self._qwen_test_timer.stop()

                if (
                    self._qwen_progress_dialog
                    and self._qwen_progress_dialog.result()
                    == QMessageBox.StandardButton.Cancel
                ):
                    self.model_status_label.setText(
                        QCoreApplication.translate(
                            "TranscriptionTab", "API test cancelled"
                        )
                    )
                    return

                if self._qwen_test_result["success"]:
                    self.model_status_label.setText(
                        QCoreApplication.translate(
                            "TranscriptionTab", "API connection successful"
                        )
                    )
                    QMessageBox.information(
                        self.parent_window,
                        QCoreApplication.translate(
                            "TranscriptionTab", "API Test Successful"
                        ),
                        QCoreApplication.translate(
                            "TranscriptionTab",
                            "Successfully connected to Qwen ASR API!\n\n"
                            "Model: {model}\n\n"
                            "You can now use cloud transcription.",
                        ).format(model=self._qwen_test_model),
                    )
                else:
                    error_msg = self._qwen_test_result[
                        "error"
                    ] or QCoreApplication.translate("TranscriptionTab", "Unknown error")
                    self.model_status_label.setText(
                        QCoreApplication.translate(
                            "TranscriptionTab", "API connection failed"
                        )
                    )
                    QMessageBox.critical(
                        self.parent_window,
                        QCoreApplication.translate(
                            "TranscriptionTab", "API Test Failed"
                        ),
                        QCoreApplication.translate(
                            "TranscriptionTab",
                            "Failed to connect to Qwen ASR API.\n\n"
                            "Error: {error}\n\n"
                            "Please check:\n"
                            "- DashScope API key is valid\n"
                            "- Internet connection\n"
                            "- Qwen service status",
                        ).format(error=error_msg),
                    )

                if self._qwen_progress_dialog:
                    self._qwen_progress_dialog.hide()

                if thread_alive and elapsed_time > 30:
                    self.model_status_label.setText(
                        QCoreApplication.translate(
                            "TranscriptionTab", "API test cancelled"
                        )
                    )

        except Exception as e:
            self.model_status_label.setText(
                QCoreApplication.translate("TranscriptionTab", "API test error")
            )
            QMessageBox.critical(
                self.parent_window,
                QCoreApplication.translate("TranscriptionTab", "API Test Error"),
                QCoreApplication.translate(
                    "TranscriptionTab", "Error during API test: {error}"
                ).format(error=e),
            )
