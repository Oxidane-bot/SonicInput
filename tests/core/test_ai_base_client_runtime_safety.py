import json

import pytest

from sonicinput.ai.base_client import BaseAIClient


class FakeResponse:
    status_code = 200
    text = ""

    def __init__(self, payload=None, lines=None):
        self._payload = payload or {
            "choices": [{"message": {"content": "refined"}}],
            "usage": {},
        }
        self._lines = lines or []

    def json(self):
        return self._payload

    def iter_lines(self):
        return iter(self._lines)


class RecordingSession:
    def __init__(self):
        self.headers = {}
        self.post_calls = []

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        if kwargs.get("stream"):
            line = json.dumps({"choices": [{"delta": {"content": "token"}}]})
            return FakeResponse(lines=[f"data: {line}".encode(), b"data: [DONE]"])
        return FakeResponse()

    def get(self, url, **kwargs):
        return FakeResponse()


class FakeAIClient(BaseAIClient):
    def get_base_url(self) -> str:
        return "https://example.test/v1"

    def get_provider_name(self) -> str:
        return "TestAI"

    def get_default_model(self) -> str:
        return "test-model"

    def _create_api_error(self, message: str) -> Exception:
        return RuntimeError(message)


def test_ai_client_uses_per_request_headers_not_shared_session_headers():
    client = FakeAIClient(api_key="initial-key")
    session = RecordingSession()
    client.session = session

    client.refine_text("hello", "{text}")

    assert "Authorization" not in session.headers
    assert session.post_calls[0][1]["headers"]["Authorization"] == "Bearer initial-key"

    client.set_api_key("updated-key")
    client.refine_text("hello", "{text}")

    assert "Authorization" not in session.headers
    assert session.post_calls[1][1]["headers"]["Authorization"] == "Bearer updated-key"


def test_streaming_token_callback_failure_is_observable():
    client = FakeAIClient(api_key="key", max_retries=1)
    client.session = RecordingSession()

    def failing_callback(_token):
        raise ValueError("callback failed")

    with pytest.raises(RuntimeError, match="callback failed"):
        client.refine_text_streaming("hello", "{text}", on_token=failing_callback)
