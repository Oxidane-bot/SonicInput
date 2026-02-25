from sonicinput.ai.groq import GroqClient
from sonicinput.ai.nvidia import NvidiaClient


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
