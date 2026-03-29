from sonicinput.ai.groq import GroqClient
from sonicinput.ai.nvidia import NvidiaClient
from sonicinput.ai.openai_compatible import OpenAICompatibleClient


class _FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_nvidia_fetch_available_models_returns_sorted_ids():
    client = NvidiaClient(api_key="")
    response = _FakeResponse(
        200,
        {
            "data": [
                {"id": "meta/llama-3.3-70b-instruct", "owned_by": "meta"},
                {"id": "01-ai/yi-large", "owned_by": "01-ai"},
                {"id": "nvidia/llama-3.1-nemotron-70b-instruct", "owned_by": "nvidia"},
            ]
        },
    )
    session = _FakeSession(response)
    client.session = session

    model_ids = client.fetch_available_models()

    assert model_ids == [
        "01-ai/yi-large",
        "meta/llama-3.3-70b-instruct",
        "nvidia/llama-3.1-nemotron-70b-instruct",
    ]
    assert len(session.calls) == 1
    url, kwargs = session.calls[0]
    assert url.endswith("/models")
    assert kwargs["timeout"] == client.timeout


def test_nvidia_get_available_models_returns_empty_on_http_error():
    client = NvidiaClient(api_key="")
    session = _FakeSession(_FakeResponse(500, text="upstream error"))
    client.session = session

    models = client.get_available_models()

    assert models == []
    assert len(session.calls) == 1


def test_groq_fetch_available_models_returns_sorted_ids():
    client = GroqClient(api_key="")
    response = _FakeResponse(
        200,
        {
            "data": [
                {"id": "llama-3.3-70b-versatile", "owned_by": "groq"},
                {"id": "deepseek-r1-distill-llama-70b", "owned_by": "groq"},
                {"id": "llama-3.1-8b-instant", "owned_by": "groq"},
            ]
        },
    )
    session = _FakeSession(response)
    client.session = session

    model_ids = client.fetch_available_models()

    assert model_ids == [
        "deepseek-r1-distill-llama-70b",
        "llama-3.1-8b-instant",
        "llama-3.3-70b-versatile",
    ]
    assert len(session.calls) == 1
    url, kwargs = session.calls[0]
    assert url.endswith("/models")
    assert kwargs["timeout"] == client.timeout


def test_groq_get_available_models_returns_empty_on_http_error():
    client = GroqClient(api_key="")
    session = _FakeSession(_FakeResponse(503, text="unavailable"))
    client.session = session

    models = client.get_available_models()

    assert models == []
    assert len(session.calls) == 1


def test_openai_compatible_fetch_available_models_returns_sorted_ids():
    client = OpenAICompatibleClient(api_key="", base_url="http://localhost:1234/v1")
    response = _FakeResponse(
        200,
        {
            "data": [
                {"id": "qwen2.5-7b-instruct"},
                {"id": "local-model"},
                {"id": "gpt-oss-20b"},
            ]
        },
    )
    session = _FakeSession(response)
    client.session = session

    model_ids = client.fetch_available_models()

    assert model_ids == ["gpt-oss-20b", "local-model", "qwen2.5-7b-instruct"]
    assert len(session.calls) == 1
    url, kwargs = session.calls[0]
    assert url.endswith("/models")
    assert kwargs["timeout"] == client.timeout


def test_openai_compatible_get_available_models_returns_empty_on_http_error():
    client = OpenAICompatibleClient(api_key="", base_url="http://localhost:1234/v1")
    session = _FakeSession(_FakeResponse(404, text="not found"))
    client.session = session

    models = client.get_available_models()

    assert models == []
    assert len(session.calls) == 1


def test_openai_compatible_is_model_available_checks_remote_list():
    client = OpenAICompatibleClient(api_key="", base_url="http://localhost:1234/v1")
    response = _FakeResponse(
        200,
        {
            "data": [
                {"id": "qwen-3-235b-a22b-instruct-2507"},
                {"id": "llama3.1-8b"},
            ]
        },
    )
    session = _FakeSession(response)
    client.session = session

    assert client.is_model_available("qwen-3-235b-a22b-instruct-2507") is True
    assert client.is_model_available("zai-glm-4.7") is False
    assert len(session.calls) == 2


def test_openai_compatible_test_connection_rejects_unknown_model_before_chat_call():
    client = OpenAICompatibleClient(
        api_key="test-key", base_url="http://localhost:1234/v1"
    )
    response = _FakeResponse(
        200,
        {
            "data": [
                {"id": "qwen-3-235b-a22b-instruct-2507"},
                {"id": "llama3.1-8b"},
            ]
        },
    )
    session = _FakeSession(response)
    client.session = session

    ok, message = client.test_connection(model="zai-glm-4.7")

    assert ok is False
    assert "not in the available model list" in message
    assert len(session.calls) == 1
