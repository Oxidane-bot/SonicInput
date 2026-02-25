from sonicinput.core.services.config.config_validator import ConfigValidator
from sonicinput.speech.groq_speech_service import GroqSpeechService
from sonicinput.speech.siliconflow_engine import SiliconFlowEngine


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def _base_config(provider: str, provider_config: dict) -> dict:
    return {
        "hotkeys": {"keys": ["Ctrl+Shift+V"], "backend": "auto"},
        "transcription": {provider: provider_config, "provider": provider},
        "audio": {"sample_rate": 16000},
        "ui": {"theme_color": "cyan", "language": "auto"},
        "ai": {"enabled": False},
    }


def test_groq_fetch_available_models_filters_to_whisper(monkeypatch):
    service = GroqSpeechService(api_key="test-key")
    response = _FakeResponse(
        {
            "data": [
                {"id": "whisper-large-v3-turbo"},
                {"id": "whisper-large-v3"},
                {"id": "llama-3.3-70b-versatile"},
            ]
        }
    )
    session = _FakeSession(response)
    monkeypatch.setattr(service, "_get_session", lambda: session)

    models = service.fetch_available_models(timeout=5)

    assert models == ["whisper-large-v3", "whisper-large-v3-turbo"]
    assert len(session.calls) == 1
    url, kwargs = session.calls[0]
    assert url.endswith("/models")
    assert kwargs["timeout"] == 5


def test_siliconflow_fetch_available_models_uses_audio_filter(monkeypatch):
    service = SiliconFlowEngine(api_key="test-key")
    response = _FakeResponse(
        {
            "data": [
                {"id": "TeleAI/TeleSpeechASR"},
                {"id": "FunAudioLLM/SenseVoiceSmall"},
            ]
        }
    )
    session = _FakeSession(response)
    monkeypatch.setattr(service, "_get_session", lambda: session)

    models = service.fetch_available_models(timeout=3)

    assert models == ["FunAudioLLM/SenseVoiceSmall", "TeleAI/TeleSpeechASR"]
    assert len(session.calls) == 1
    _, kwargs = session.calls[0]
    assert kwargs["timeout"] == 3
    assert kwargs["params"] == {"type": "audio", "sub_type": "speech-to-text"}


def test_groq_and_siliconflow_model_validation_is_not_hardcoded():
    validator = ConfigValidator()

    groq_config = _base_config(
        "groq",
        {"api_key": "test-key", "model": "whisper-next-preview-2026"},
    )
    groq_result = validator.validate_config(groq_config)
    assert (
        "Unknown Groq model: whisper-next-preview-2026" not in groq_result["warnings"]
    )

    siliconflow_config = _base_config(
        "siliconflow",
        {"api_key": "test-key", "model": "Vendor/New-ASR-Model"},
    )
    siliconflow_result = validator.validate_config(siliconflow_config)
    assert (
        "Unknown SiliconFlow model: Vendor/New-ASR-Model"
        not in siliconflow_result["warnings"]
    )


def test_qwen_model_validation_remains_static():
    validator = ConfigValidator()
    qwen_config = _base_config(
        "qwen",
        {"api_key": "test-key", "model": "qwen-unknown-model"},
    )

    result = validator.validate_config(qwen_config)

    assert "Unknown Qwen ASR model: qwen-unknown-model" in result["warnings"]
