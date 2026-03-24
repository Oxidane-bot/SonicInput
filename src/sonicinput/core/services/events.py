"""Event constants and metadata."""

from typing import Dict, List


class Events:
    """Event name constants."""

    # Recording
    RECORDING_STARTED = "recording_started"
    RECORDING_STOPPED = "recording_stopped"
    RECORDING_ERROR = "recording_error"
    AUDIO_LEVEL_UPDATE = "audio_level_update"
    RECORDING_STATE_CHANGED = "recording_state_changed"

    # Transcription
    TRANSCRIPTION_STARTED = "transcription_started"
    TRANSCRIPTION_COMPLETED = "transcription_completed"
    TRANSCRIPTION_ERROR = "transcription_error"
    TRANSCRIPTION_REQUEST = "transcription_request"
    TRANSCRIPTION_SERVICE_STARTED = "transcription_service_started"
    TRANSCRIPTION_SERVICE_STOPPED = "transcription_service_stopped"
    SPEECH_SERVICE_RELOADED = "speech_service_reloaded"

    # Model loading
    MODEL_LOADING_STARTED = "model_loading_started"
    MODEL_LOADING_COMPLETED = "model_loading_completed"
    MODEL_LOADED = "model_loaded"
    MODEL_LOADING_FAILED = "model_loading_failed"
    MODEL_LOADING_ERROR = "model_loading_error"
    MODEL_UNLOADED = "model_unloaded"

    # Streaming
    STREAMING_STARTED = "streaming_started"
    STREAMING_STOPPED = "streaming_stopped"
    STREAMING_CHUNK_COMPLETED = "streaming_chunk_completed"
    REALTIME_TEXT_UPDATED = "realtime_text_updated"

    # AI processing
    AI_PROCESSING_STARTED = "ai_processing_started"
    AI_PROCESSING_COMPLETED = "ai_processing_completed"
    AI_PROCESSING_ERROR = "ai_processing_error"
    AI_INCREMENTAL_TEXT_UPDATED = "ai_incremental_text_updated"
    AI_PROCESSED_TEXT = "ai_processed_text"
    AI_STREAMING_TOKEN_RECEIVED = "ai_streaming_token_received"  # token 级流式输出

    # Text input
    TEXT_INPUT_STARTED = "text_input_started"
    TEXT_INPUT_COMPLETED = "text_input_completed"
    TEXT_INPUT_ERROR = "text_input_error"

    # Hotkeys
    HOTKEY_TRIGGERED = "hotkey_triggered"
    HOTKEY_REGISTERED = "hotkey_registered"
    HOTKEY_UNREGISTERED = "hotkey_unregistered"
    HOTKEY_CONFLICT = "hotkey_conflict"
    HOTKEY_REGISTRATION_ERROR = "hotkey_registration_error"

    # Config
    CONFIG_CHANGED = "config_changed"
    CONFIG_CHANGED_DETAILED = "config_changed_detailed"
    CONFIG_LOADED = "config_loaded"
    CONFIG_SAVED = "config_saved"
    CONFIG_RESET = "config_reset"
    CONFIG_IMPORTED = "config_imported"

    # UI
    WINDOW_SHOWN = "window_shown"
    WINDOW_HIDDEN = "window_hidden"
    TRAY_CLICKED = "tray_clicked"
    OVERLAY_POSITION_CHANGED = "overlay_position_changed"
    UI_LANGUAGE_CHANGED = "ui_language_changed"

    # App lifecycle/state
    APP_STARTED = "app_started"
    APP_STARTUP_COMPLETED = "app_startup_completed"
    APP_STOPPING = "app_stopping"
    APP_ERROR = "app_error"
    APP_STATE_CHANGED = "app_state_changed"
    STATE_CHANGED = "state_changed"

    # Component lifecycle
    COMPONENT_REGISTERED = "component_registered"
    COMPONENT_UNREGISTERED = "component_unregistered"
    COMPONENT_INITIALIZED = "component_initialized"
    COMPONENT_STARTED = "component_started"
    COMPONENT_STOPPED = "component_stopped"
    COMPONENT_ERROR = "component_error"
    COMPONENT_STATE_CHANGED = "component_state_changed"

    # Network/API
    NETWORK_ERROR = "network_error"
    API_RATE_LIMITED = "api_rate_limited"

    # GPU
    GPU_STATUS_CHANGED = "gpu_status_changed"
    GPU_MEMORY_WARNING = "gpu_memory_warning"

    # Errors
    ERROR_OCCURRED = "error_occurred"
    ERROR_AUTO_RESOLVED = "error_auto_resolved"


def iter_event_names() -> List[str]:
    """Return canonical event names in definition order."""
    event_names: List[str] = []
    for name, value in Events.__dict__.items():
        if name.isupper() and isinstance(value, str):
            event_names.append(value)
    return event_names


EVENT_METADATA: Dict[str, Dict[str, object]] = {
    # Recording
    Events.RECORDING_STARTED: {
        "description": "Recording started",
        "namespace": "audio",
        "tags": ["audio", "recording"],
    },
    Events.RECORDING_STOPPED: {
        "description": "Recording stopped",
        "namespace": "audio",
        "tags": ["audio", "recording"],
    },
    Events.RECORDING_ERROR: {
        "description": "Recording error",
        "namespace": "audio",
        "tags": ["audio", "recording", "error"],
    },
    Events.AUDIO_LEVEL_UPDATE: {
        "description": "Audio level update",
        "namespace": "audio",
        "tags": ["audio", "level"],
    },
    Events.RECORDING_STATE_CHANGED: {
        "description": "Recording state changed",
        "namespace": "audio",
        "tags": ["audio", "recording", "state"],
    },
    # Transcription
    Events.TRANSCRIPTION_STARTED: {
        "description": "Transcription started",
        "namespace": "speech",
        "tags": ["speech", "transcription"],
    },
    Events.TRANSCRIPTION_COMPLETED: {
        "description": "Transcription completed",
        "namespace": "speech",
        "tags": ["speech", "transcription"],
    },
    Events.TRANSCRIPTION_ERROR: {
        "description": "Transcription error",
        "namespace": "speech",
        "tags": ["speech", "transcription", "error"],
    },
    Events.TRANSCRIPTION_REQUEST: {
        "description": "Transcription request",
        "namespace": "speech",
        "tags": ["speech", "transcription"],
    },
    Events.TRANSCRIPTION_SERVICE_STARTED: {
        "description": "Transcription service started",
        "namespace": "speech",
        "tags": ["speech", "service"],
    },
    Events.TRANSCRIPTION_SERVICE_STOPPED: {
        "description": "Transcription service stopped",
        "namespace": "speech",
        "tags": ["speech", "service"],
    },
    Events.SPEECH_SERVICE_RELOADED: {
        "description": "Speech service reloaded",
        "namespace": "speech",
        "tags": ["speech", "service", "reload"],
    },
    # Model loading
    Events.MODEL_LOADING_STARTED: {
        "description": "Model loading started",
        "namespace": "model",
        "tags": ["model", "loading"],
    },
    Events.MODEL_LOADING_COMPLETED: {
        "description": "Model loading completed",
        "namespace": "model",
        "tags": ["model", "loading"],
    },
    Events.MODEL_LOADED: {
        "description": "Model loaded",
        "namespace": "model",
        "tags": ["model", "loading"],
    },
    Events.MODEL_LOADING_FAILED: {
        "description": "Model loading failed",
        "namespace": "model",
        "tags": ["model", "loading", "error"],
    },
    Events.MODEL_LOADING_ERROR: {
        "description": "Model loading error",
        "namespace": "model",
        "tags": ["model", "loading", "error"],
    },
    Events.MODEL_UNLOADED: {
        "description": "Model unloaded",
        "namespace": "model",
        "tags": ["model", "loading"],
    },
    # Streaming
    Events.STREAMING_STARTED: {
        "description": "Streaming started",
        "namespace": "streaming",
        "tags": ["streaming"],
    },
    Events.STREAMING_STOPPED: {
        "description": "Streaming stopped",
        "namespace": "streaming",
        "tags": ["streaming"],
    },
    Events.STREAMING_CHUNK_COMPLETED: {
        "description": "Streaming chunk completed",
        "namespace": "streaming",
        "tags": ["streaming"],
    },
    Events.REALTIME_TEXT_UPDATED: {
        "description": "Realtime text updated",
        "namespace": "streaming",
        "tags": ["streaming", "realtime"],
    },
    # AI processing
    Events.AI_PROCESSING_STARTED: {
        "description": "AI processing started",
        "namespace": "ai",
        "tags": ["ai", "processing"],
    },
    Events.AI_PROCESSING_COMPLETED: {
        "description": "AI processing completed",
        "namespace": "ai",
        "tags": ["ai", "processing"],
    },
    Events.AI_PROCESSING_ERROR: {
        "description": "AI processing error",
        "namespace": "ai",
        "tags": ["ai", "processing", "error"],
    },
    Events.AI_INCREMENTAL_TEXT_UPDATED: {
        "description": "AI incremental text updated",
        "namespace": "ai",
        "tags": ["ai", "processing", "incremental"],
    },
    Events.AI_PROCESSED_TEXT: {
        "description": "AI processed text",
        "namespace": "ai",
        "tags": ["ai", "processing"],
    },
    Events.AI_STREAMING_TOKEN_RECEIVED: {
        "description": "AI streaming token received",
        "namespace": "ai",
        "tags": ["ai", "streaming", "token"],
    },
    # Text input
    Events.TEXT_INPUT_STARTED: {
        "description": "Text input started",
        "namespace": "input",
        "tags": ["input", "text"],
    },
    Events.TEXT_INPUT_COMPLETED: {
        "description": "Text input completed",
        "namespace": "input",
        "tags": ["input", "text"],
    },
    Events.TEXT_INPUT_ERROR: {
        "description": "Text input error",
        "namespace": "input",
        "tags": ["input", "text", "error"],
    },
    # Hotkeys
    Events.HOTKEY_TRIGGERED: {
        "description": "Hotkey triggered",
        "namespace": "hotkey",
        "tags": ["hotkey"],
    },
    Events.HOTKEY_REGISTERED: {
        "description": "Hotkey registered",
        "namespace": "hotkey",
        "tags": ["hotkey"],
    },
    Events.HOTKEY_UNREGISTERED: {
        "description": "Hotkey unregistered",
        "namespace": "hotkey",
        "tags": ["hotkey"],
    },
    Events.HOTKEY_CONFLICT: {
        "description": "Hotkey conflict",
        "namespace": "hotkey",
        "tags": ["hotkey", "error"],
    },
    Events.HOTKEY_REGISTRATION_ERROR: {
        "description": "Hotkey registration error",
        "namespace": "hotkey",
        "tags": ["hotkey", "error"],
    },
    # Config
    Events.CONFIG_CHANGED: {
        "description": "Config changed",
        "namespace": "config",
        "tags": ["config"],
    },
    Events.CONFIG_CHANGED_DETAILED: {
        "description": "Config changed (detailed)",
        "namespace": "config",
        "tags": ["config"],
    },
    Events.CONFIG_LOADED: {
        "description": "Config loaded",
        "namespace": "config",
        "tags": ["config"],
    },
    Events.CONFIG_SAVED: {
        "description": "Config saved",
        "namespace": "config",
        "tags": ["config"],
    },
    Events.CONFIG_RESET: {
        "description": "Config reset",
        "namespace": "config",
        "tags": ["config"],
    },
    Events.CONFIG_IMPORTED: {
        "description": "Config imported",
        "namespace": "config",
        "tags": ["config"],
    },
    # UI
    Events.WINDOW_SHOWN: {
        "description": "Window shown",
        "namespace": "ui",
        "tags": ["ui", "window"],
    },
    Events.WINDOW_HIDDEN: {
        "description": "Window hidden",
        "namespace": "ui",
        "tags": ["ui", "window"],
    },
    Events.TRAY_CLICKED: {
        "description": "Tray clicked",
        "namespace": "ui",
        "tags": ["ui", "tray"],
    },
    Events.OVERLAY_POSITION_CHANGED: {
        "description": "Overlay position changed",
        "namespace": "ui",
        "tags": ["ui", "overlay"],
    },
    Events.UI_LANGUAGE_CHANGED: {
        "description": "UI language changed",
        "namespace": "ui",
        "tags": ["ui", "i18n"],
    },
    # App lifecycle/state
    Events.APP_STARTED: {
        "description": "App started",
        "namespace": "app",
        "tags": ["app", "lifecycle"],
    },
    Events.APP_STARTUP_COMPLETED: {
        "description": "App startup completed",
        "namespace": "app",
        "tags": ["app", "lifecycle"],
    },
    Events.APP_STOPPING: {
        "description": "App stopping",
        "namespace": "app",
        "tags": ["app", "lifecycle"],
    },
    Events.APP_ERROR: {
        "description": "App error",
        "namespace": "app",
        "tags": ["app", "error"],
    },
    Events.APP_STATE_CHANGED: {
        "description": "App state changed",
        "namespace": "state",
        "tags": ["app", "state"],
    },
    Events.STATE_CHANGED: {
        "description": "State changed",
        "namespace": "state",
        "tags": ["state"],
    },
    # Component lifecycle
    Events.COMPONENT_REGISTERED: {
        "description": "Component registered",
        "namespace": "component",
        "tags": ["component"],
    },
    Events.COMPONENT_UNREGISTERED: {
        "description": "Component unregistered",
        "namespace": "component",
        "tags": ["component"],
    },
    Events.COMPONENT_INITIALIZED: {
        "description": "Component initialized",
        "namespace": "component",
        "tags": ["component"],
    },
    Events.COMPONENT_STARTED: {
        "description": "Component started",
        "namespace": "component",
        "tags": ["component"],
    },
    Events.COMPONENT_STOPPED: {
        "description": "Component stopped",
        "namespace": "component",
        "tags": ["component"],
    },
    Events.COMPONENT_ERROR: {
        "description": "Component error",
        "namespace": "component",
        "tags": ["component", "error"],
    },
    Events.COMPONENT_STATE_CHANGED: {
        "description": "Component state changed",
        "namespace": "component",
        "tags": ["component", "state"],
    },
    # Network/API
    Events.NETWORK_ERROR: {
        "description": "Network error",
        "namespace": "network",
        "tags": ["network", "error"],
    },
    Events.API_RATE_LIMITED: {
        "description": "API rate limited",
        "namespace": "network",
        "tags": ["network", "api"],
    },
    # GPU
    Events.GPU_STATUS_CHANGED: {
        "description": "GPU status changed",
        "namespace": "gpu",
        "tags": ["gpu"],
    },
    Events.GPU_MEMORY_WARNING: {
        "description": "GPU memory warning",
        "namespace": "gpu",
        "tags": ["gpu", "warning"],
    },
    # Errors
    Events.ERROR_OCCURRED: {
        "description": "Error occurred",
        "namespace": "error",
        "tags": ["error"],
    },
    Events.ERROR_AUTO_RESOLVED: {
        "description": "Error auto resolved",
        "namespace": "error",
        "tags": ["error", "recovery"],
    },
}


__all__ = ["Events", "EVENT_METADATA", "iter_event_names"]
