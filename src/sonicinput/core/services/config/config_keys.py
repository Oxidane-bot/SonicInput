"""配置键常量定义 - 类型安全的配置访问

提供所有配置路径的类型化常量,支持IDE自动完成和编译时检查。

使用示例:
    config.get(ConfigKeys.HOTKEYS_KEYS)  # IDE会提示所有可用的配置键
    config.get(ConfigKeys.TRANSCRIPTION_PROVIDER)
"""


class ConfigKeys:
    """配置键常量类 - 所有配置路径的中央定义"""

    # ==================== Hotkeys (热键配置) ====================
    HOTKEYS_KEYS = "hotkeys.keys"
    """热键组合列表 (List[str]): 例如 ["ctrl+shift+v", "f12"]"""

    HOTKEYS_BACKEND = "hotkeys.backend"
    """热键后端 (str): "auto" | "win32" | "pynput" """

    # ==================== Transcription (转录配置) ====================
    TRANSCRIPTION_PROVIDER = "transcription.provider"
    """转录提供商 (str): "local" | "groq" | "siliconflow" | "qwen" """

    # Local sherpa-onnx
    TRANSCRIPTION_LOCAL_MODEL = "transcription.local.model"
    """本地模型名称 (str): "paraformer" | "zipformer-small" """

    TRANSCRIPTION_LOCAL_LANGUAGE = "transcription.local.language"
    """本地模型语言 (str): "zh" | "en" """

    TRANSCRIPTION_LOCAL_AUTO_LOAD = "transcription.local.auto_load"
    """启动时自动加载模型 (bool)"""

    TRANSCRIPTION_LOCAL_STREAMING_MODE = "transcription.local.streaming_mode"
    """流式转录模式 (str): "chunked" | "realtime" """

    TRANSCRIPTION_LONG_RECORDING_FILE_THRESHOLD_SECONDS = (
        "transcription.long_recording.file_threshold_seconds"
    )
    """长录音切换到文件转录路径的阈值秒数 (float)。"""

    TRANSCRIPTION_LONG_RECORDING_PREFER_FILE_FOR_CLOUD = (
        "transcription.long_recording.prefer_file_for_cloud"
    )
    """长录音时云提供商优先走文件转录路径 (bool)。"""

    # Groq
    TRANSCRIPTION_GROQ_API_KEY = "transcription.groq.api_key"
    """Groq API密钥 (str)"""

    TRANSCRIPTION_GROQ_MODEL = "transcription.groq.model"
    """Groq模型 (str): 例如 "whisper-large-v3-turbo" """

    TRANSCRIPTION_GROQ_BASE_URL = "transcription.groq.base_url"
    """Groq API基础URL (str)"""

    TRANSCRIPTION_GROQ_TIMEOUT = "transcription.groq.timeout"
    """Groq请求超时 (int): 秒"""

    TRANSCRIPTION_GROQ_MAX_RETRIES = "transcription.groq.max_retries"
    """Groq最大重试次数 (int)"""

    # SiliconFlow
    TRANSCRIPTION_SILICONFLOW_API_KEY = "transcription.siliconflow.api_key"
    """SiliconFlow API密钥 (str)"""

    TRANSCRIPTION_SILICONFLOW_MODEL = "transcription.siliconflow.model"
    """SiliconFlow模型 (str)"""

    TRANSCRIPTION_SILICONFLOW_BASE_URL = "transcription.siliconflow.base_url"
    """SiliconFlow API基础URL (str)"""

    TRANSCRIPTION_SILICONFLOW_TIMEOUT = "transcription.siliconflow.timeout"
    """SiliconFlow请求超时 (int): 秒"""

    TRANSCRIPTION_SILICONFLOW_MAX_RETRIES = "transcription.siliconflow.max_retries"
    """SiliconFlow最大重试次数 (int)"""

    # Qwen
    TRANSCRIPTION_QWEN_API_KEY = "transcription.qwen.api_key"
    """Qwen API密钥 (str)"""

    TRANSCRIPTION_QWEN_MODEL = "transcription.qwen.model"
    """Qwen模型 (str)"""

    TRANSCRIPTION_QWEN_BASE_URL = "transcription.qwen.base_url"
    """Qwen API基础URL (str)"""

    TRANSCRIPTION_QWEN_TIMEOUT = "transcription.qwen.timeout"
    """Qwen请求超时 (int): 秒"""

    TRANSCRIPTION_QWEN_MAX_RETRIES = "transcription.qwen.max_retries"
    """Qwen最大重试次数 (int)"""

    TRANSCRIPTION_QWEN_ENABLE_ITN = "transcription.qwen.enable_itn"
    """Qwen启用ITN (bool): Inverse Text Normalization"""

    # ==================== AI (AI文本优化配置) ====================
    AI_PROVIDER = "ai.provider"
    """AI提供商 (str): "openrouter" | "groq" | "nvidia" | "openai_compatible" """

    AI_ENABLED = "ai.enabled"
    """启用AI文本优化 (bool)"""

    AI_FILTER_THINKING = "ai.filter_thinking"
    """过滤思考过程 (bool): 移除<think>标签内容"""

    AI_PROMPT = "ai.prompt"
    """AI系统提示词 (str)"""

    AI_MAX_OUTPUT_TOKENS = "ai.max_output_tokens"
    """AI最大输出 token 数 (int)"""

    AI_SENTENCE_SPLIT_ENABLED = "ai.sentence_split.enabled"
    """AI分句与分组开关 (bool): 启用3-5句分组的分句处理"""

    AI_FIRST_CHUNK_OUTPUT_ENABLED = "ai.first_chunk_output.enabled"
    """首块ASR完成即触发AI输出 (bool): chunked模式下按分块尽早启动AI"""

    AI_STREAMING_ENABLED = "ai.streaming_enabled"
    """AI流式输出开关 (bool): 启用后AI响应以token级实时显示（默认关闭）"""

    AI_TIMEOUT = "ai.timeout"
    """AI请求超时 (int): 秒"""

    AI_RETRIES = "ai.retries"
    """AI请求重试次数 (int)"""

    # OpenRouter
    AI_OPENROUTER_API_KEY = "ai.openrouter.api_key"
    """OpenRouter API密钥 (str)"""

    AI_OPENROUTER_MODEL_ID = "ai.openrouter.model_id"
    """OpenRouter模型ID (str)"""

    # Groq
    AI_GROQ_API_KEY = "ai.groq.api_key"
    """Groq API密钥 (str)"""

    AI_GROQ_MODEL_ID = "ai.groq.model_id"
    """Groq模型ID (str)"""

    # NVIDIA
    AI_NVIDIA_API_KEY = "ai.nvidia.api_key"
    """NVIDIA API密钥 (str)"""

    AI_NVIDIA_MODEL_ID = "ai.nvidia.model_id"
    """NVIDIA模型ID (str)"""

    # OpenAI Compatible
    AI_OPENAI_COMPATIBLE_API_KEY = "ai.openai_compatible.api_key"
    """OpenAI兼容API密钥 (str)"""

    AI_OPENAI_COMPATIBLE_BASE_URL = "ai.openai_compatible.base_url"
    """OpenAI兼容API基础URL (str)"""

    AI_OPENAI_COMPATIBLE_MODEL_ID = "ai.openai_compatible.model_id"
    """OpenAI兼容模型ID (str)"""

    # ==================== Audio (音频配置) ====================
    AUDIO_SAMPLE_RATE = "audio.sample_rate"
    """音频采样率 (int): 例如 16000"""

    AUDIO_CHANNELS = "audio.channels"
    """音频通道数 (int): 1=单声道, 2=立体声"""

    AUDIO_DEVICE_ID = "audio.device_id"
    """音频设备ID (int | None): None表示默认设备"""

    AUDIO_CHUNK_SIZE = "audio.chunk_size"
    """音频分块大小 (int)"""

    AUDIO_STREAMING_CHUNK_DURATION = "audio.streaming.chunk_duration"
    """流式转录分块时长 (float): 默认15秒"""

    # ==================== UI (界面配置) ====================
    UI_SHOW_OVERLAY = "ui.show_overlay"
    """显示录音悬浮窗 (bool)"""

    UI_OVERLAY_POSITION = "ui.overlay_position"
    """悬浮窗位置配置对象 (Dict)"""

    UI_OVERLAY_POSITION_MODE = "ui.overlay_position.mode"
    """悬浮窗位置模式 (str): "preset" | "custom" """

    UI_OVERLAY_POSITION_PRESET = "ui.overlay_position.preset"
    """悬浮窗预设位置 (str): "center" | "top_left" | etc."""

    UI_OVERLAY_POSITION_CUSTOM = "ui.overlay_position.custom"
    """悬浮窗自定义位置 (Dict): {"x": int, "y": int}"""

    UI_OVERLAY_POSITION_CUSTOM_X = "ui.overlay_position.custom.x"
    """悬浮窗自定义位置X坐标 (int)"""

    UI_OVERLAY_POSITION_CUSTOM_Y = "ui.overlay_position.custom.y"
    """悬浮窗自定义位置Y坐标 (int)"""

    UI_OVERLAY_POSITION_LAST_SCREEN = "ui.overlay_position.last_screen"
    """上次使用的屏幕信息 (Dict)"""

    UI_OVERLAY_POSITION_LAST_SCREEN_GEOMETRY = (
        "ui.overlay_position.last_screen.geometry"
    )
    """上次使用的屏幕几何信息 (str): 例如 "1920x1080" """

    UI_OVERLAY_POSITION_LAST_SCREEN_DEVICE_PIXEL_RATIO = (
        "ui.overlay_position.last_screen.device_pixel_ratio"
    )
    """上次使用的屏幕设备像素比 (float)"""

    UI_OVERLAY_POSITION_AUTO_SAVE = "ui.overlay_position.auto_save"
    """自动保存悬浮窗位置 (bool)"""

    UI_OVERLAY_ALWAYS_ON_TOP = "ui.overlay_always_on_top"
    """悬浮窗始终置顶 (bool)"""

    UI_TRAY_NOTIFICATIONS = "ui.tray_notifications"
    """系统托盘通知 (bool)"""

    UI_LAUNCH_AT_LOGIN = "ui.launch_at_login"
    """Windows 登录后自动启动应用 (bool)"""

    UI_START_MINIMIZED = "ui.start_minimized"
    """启动时最小化 (bool)"""

    UI_LANGUAGE = "ui.language"
    """UI language (str): "auto" | "en-US" | "zh-CN" """

    UI_THEME_COLOR = "ui.theme_color"
    """主题颜色 (str): "cyan" | "blue" | "green" | etc."""

    # ==================== Input (输入方式配置) ====================
    INPUT_PREFERRED_METHOD = "input.preferred_method"
    """首选输入方法 (str): "clipboard" | "sendinput" """

    INPUT_FALLBACK_ENABLED = "input.fallback_enabled"
    """启用输入方法回退 (bool)"""

    INPUT_AUTO_DETECT_TERMINAL = "input.auto_detect_terminal"
    """自动检测终端 (bool)"""

    INPUT_CLIPBOARD_RESTORE_DELAY = "input.clipboard_restore_delay"
    """剪贴板恢复延迟 (float): 秒"""

    INPUT_TYPING_DELAY = "input.typing_delay"
    """键入延迟 (float): 秒"""

    # ==================== History (历史记录配置) ====================
    HISTORY_STORAGE_PATH = "history.storage_path"
    """历史记录存储路径 (str): "auto"表示自动选择"""

    # ==================== Lexicon Review / Memory (本地词汇审查与记忆配置) ====================
    REVIEW_ENABLED = "review.enabled"
    """启用空闲词汇候选审查调度 (bool)"""

    REVIEW_IDLE_SECONDS = "review.idle_seconds"
    """空闲多久后允许运行词汇审查 (float): 秒"""

    REVIEW_MIN_INTERVAL_SECONDS = "review.min_interval_seconds"
    """两次词汇审查之间的最小间隔 (float): 秒"""

    REVIEW_MAX_RECORDS = "review.max_records"
    """每次最多扫描的历史记录数 (int)"""

    REVIEW_MAX_RUNS_PER_SESSION = "review.max_runs_per_session"
    """每个 App session 最多运行词汇审查的次数 (int)"""

    REVIEW_USE_LEXICON_MEMORY = "review.use_lexicon_memory"
    """是否在 AI 清理时使用用户已接受的本地词汇记忆 (bool)"""

    # ==================== Logging (日志配置) ====================
    LOGGING_LEVEL = "logging.level"
    """日志级别 (str): "DEBUG" | "INFO" | "WARNING" | "ERROR" """

    LOGGING_CONSOLE_OUTPUT = "logging.console_output"
    """控制台输出 (bool)"""

    LOGGING_MAX_LOG_SIZE_MB = "logging.max_log_size_mb"
    """最大日志文件大小 (int): MB"""

    LOGGING_KEEP_LOGS_DAYS = "logging.keep_logs_days"
    """日志保留天数 (int)"""

    LOGGING_ENABLED_CATEGORIES = "logging.enabled_categories"
    """启用的日志类别 (List[str])"""

    # ==================== Advanced (高级配置) ====================
    ADVANCED_AUDIO_PROCESSING_NORMALIZE = "advanced.audio_processing.normalize_audio"
    """音频标准化 (bool)"""

    ADVANCED_AUDIO_PROCESSING_REMOVE_SILENCE = (
        "advanced.audio_processing.remove_silence"
    )
    """移除静音 (bool)"""

    ADVANCED_AUDIO_PROCESSING_NOISE_REDUCTION = (
        "advanced.audio_processing.noise_reduction"
    )
    """降噪 (bool)"""

    ADVANCED_PERFORMANCE_PRELOAD_MODEL = "advanced.performance.preload_model"
    """预加载模型 (bool)"""

    ADVANCED_PERFORMANCE_CACHE_AUDIO = "advanced.performance.cache_audio"
    """缓存音频 (bool)"""

    ADVANCED_PERFORMANCE_PARALLEL_PROCESSING = (
        "advanced.performance.parallel_processing"
    )
    """并行处理 (bool)"""

    # 配置键分组 - 用于批量操作和验证

    # ==================== Legacy (Deprecated Flat Keys) ====================
    HOTKEY = "hotkey"
    """Legacy hotkey key (str)."""

    WHISPER_MODEL = "whisper.model"
    """Legacy Whisper model key (str)."""

    WHISPER_LANGUAGE = "whisper.language"
    """Legacy Whisper language key (str)."""

    WHISPER_USE_GPU = "whisper.use_gpu"
    """Legacy Whisper GPU toggle key (bool)."""

    WHISPER_AUTO_LOAD = "whisper.auto_load"
    """Legacy Whisper auto-load key (bool)."""

    WHISPER_TEMPERATURE = "whisper.temperature"
    """Legacy Whisper temperature key (float)."""

    WHISPER_DEVICE = "whisper.device"
    """Legacy Whisper device key (str)."""

    WHISPER_COMPUTE_TYPE = "whisper.compute_type"
    """Legacy Whisper compute type key (str)."""

    OPENROUTER_API_KEY = "openrouter.api_key"
    """Legacy OpenRouter API key (str)."""

    OPENROUTER_MODEL = "openrouter.model"
    """Legacy OpenRouter model key (str)."""

    OPENROUTER_SIMPLE_MODEL_ID = "openrouter.simple_model_id"
    """Legacy OpenRouter simple model id (str)."""

    OPENROUTER_SIMPLE_PROMPT = "openrouter.simple_prompt"
    """Legacy OpenRouter simple prompt (str)."""

    OPENROUTER_ENABLED = "openrouter.enabled"
    """Legacy OpenRouter enabled flag (bool)."""

    OPENROUTER_TIMEOUT = "openrouter.timeout"
    """Legacy OpenRouter timeout (int)."""

    OPENROUTER_MAX_RETRIES = "openrouter.max_retries"
    """Legacy OpenRouter retries (int)."""

    UI_AUTO_START = "ui.auto_start"
    """Legacy UI autostart key (bool)."""

    UI_THEME = "ui.theme"
    """Legacy UI theme key (str)."""

    NOTIFICATIONS_ENABLED = "ui.notifications_enabled"
    """Legacy UI notifications key (bool)."""

    AUTO_START = "ui.auto_start"
    """Legacy UI autostart key (bool)."""

    LOG_LEVEL = "logging.level"
    """Legacy logging level key (str)."""

    RECORDING_TIMEOUT = "recording.timeout"
    """Legacy recording timeout key (int)."""

    AUDIO_INPUT_DEVICE = "audio.input_device"
    """Legacy audio input device key (str | int)."""

    NOISE_REDUCTION_ENABLED = "audio.noise_reduction_enabled"
    """Legacy noise reduction toggle key (bool)."""

    VOLUME_THRESHOLD = "audio.volume_threshold"
    """Legacy volume threshold key (float)."""

    SPEECH_LANGUAGE = "speech.language"
    """Legacy speech language key (str)."""

    HOTKEYS_ENABLED = "hotkeys.enabled"
    """Legacy hotkeys enabled key (bool)."""

    RECORDING_HOTKEY = "hotkeys.recording"
    """Legacy recording hotkey key (str)."""

    TEXT_OPTIMIZATION_ENABLED = "text.optimization_enabled"
    """Legacy text optimization toggle key (bool)."""

    OVERLAY_ENABLED = "ui.overlay.enabled"
    """Legacy overlay enabled key (bool)."""

    OVERLAY_POSITION = "ui.overlay.position"
    """Legacy overlay position key (str)."""

    OVERLAY_OPACITY = "ui.overlay.opacity"
    """Legacy overlay opacity key (float)."""

    ADVANCED_AUDIO_NORMALIZE = "advanced.audio_processing.normalize_audio"
    """Legacy audio normalize key (bool)."""

    ADVANCED_AUDIO_REMOVE_SILENCE = "advanced.audio_processing.remove_silence"
    """Legacy audio remove silence key (bool)."""

    ADVANCED_AUDIO_NOISE_REDUCTION = "advanced.audio_processing.noise_reduction"
    """Legacy audio noise reduction key (bool)."""


class ConfigKeyGroups:
    """配置键分组 - 便于批量操作"""

    HOTKEYS = [
        ConfigKeys.HOTKEYS_KEYS,
        ConfigKeys.HOTKEYS_BACKEND,
    ]

    TRANSCRIPTION_LOCAL = [
        ConfigKeys.TRANSCRIPTION_LOCAL_MODEL,
        ConfigKeys.TRANSCRIPTION_LOCAL_LANGUAGE,
        ConfigKeys.TRANSCRIPTION_LOCAL_AUTO_LOAD,
        ConfigKeys.TRANSCRIPTION_LOCAL_STREAMING_MODE,
    ]

    TRANSCRIPTION_CLOUD = [
        ConfigKeys.TRANSCRIPTION_GROQ_API_KEY,
        ConfigKeys.TRANSCRIPTION_SILICONFLOW_API_KEY,
        ConfigKeys.TRANSCRIPTION_QWEN_API_KEY,
    ]

    AI = [
        ConfigKeys.AI_PROVIDER,
        ConfigKeys.AI_ENABLED,
        ConfigKeys.AI_FILTER_THINKING,
        ConfigKeys.AI_PROMPT,
        ConfigKeys.AI_MAX_OUTPUT_TOKENS,
        ConfigKeys.AI_SENTENCE_SPLIT_ENABLED,
        ConfigKeys.AI_FIRST_CHUNK_OUTPUT_ENABLED,
        ConfigKeys.AI_STREAMING_ENABLED,
    ]

    AUDIO = [
        ConfigKeys.AUDIO_SAMPLE_RATE,
        ConfigKeys.AUDIO_CHANNELS,
        ConfigKeys.AUDIO_DEVICE_ID,
        ConfigKeys.AUDIO_CHUNK_SIZE,
    ]

    UI = [
        ConfigKeys.UI_SHOW_OVERLAY,
        ConfigKeys.UI_OVERLAY_ALWAYS_ON_TOP,
        ConfigKeys.UI_TRAY_NOTIFICATIONS,
        ConfigKeys.UI_LAUNCH_AT_LOGIN,
        ConfigKeys.UI_START_MINIMIZED,
        ConfigKeys.UI_LANGUAGE,
        ConfigKeys.UI_THEME_COLOR,
    ]

    INPUT = [
        ConfigKeys.INPUT_PREFERRED_METHOD,
        ConfigKeys.INPUT_FALLBACK_ENABLED,
        ConfigKeys.INPUT_AUTO_DETECT_TERMINAL,
    ]

    REVIEW = [
        ConfigKeys.REVIEW_ENABLED,
        ConfigKeys.REVIEW_IDLE_SECONDS,
        ConfigKeys.REVIEW_MIN_INTERVAL_SECONDS,
        ConfigKeys.REVIEW_MAX_RECORDS,
        ConfigKeys.REVIEW_MAX_RUNS_PER_SESSION,
        ConfigKeys.REVIEW_USE_LEXICON_MEMORY,
    ]
