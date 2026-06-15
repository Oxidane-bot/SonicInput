from unittest.mock import Mock

from sonicinput.core.quality import LLMReviewService


class _Config:
    def __init__(self, values):
        self.values = values

    def get_setting(self, key, default=None):
        return self.values.get(key, default)


class _Client:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def refine_text(self, text, prompt_template, model, max_tokens=1000):
        self.calls.append(
            {
                "text": text,
                "prompt_template": prompt_template,
                "model": model,
                "max_tokens": max_tokens,
            }
        )
        return self.response


def test_llm_review_service_parses_model_suggestions():
    client = _Client(
        """
        {
          "suggestions": [
            {
              "suggestion_type": "bad_ai_output_alert",
              "confidence": 0.91,
              "risk_level": "high",
              "source_record_ids": ["r1"],
              "title": "AI 输出可能越界",
              "detail": "Model detected a boundary violation."
            }
          ]
        }
        """
    )
    service = LLMReviewService(
        _Config(
            {
                "ai.provider": "openrouter",
                "ai.openrouter.model_id": "demo-model",
            }
        ),
        client_factory=lambda: client,
    )

    outcome = service.review_records([{"id": "r1", "transcription_text": "hello"}])

    assert outcome.review_source == "llm"
    assert outcome.provider == "openrouter"
    assert outcome.model_id == "demo-model"
    assert len(outcome.suggestions) == 1
    assert outcome.suggestions[0].suggestion_type == "bad_ai_output_alert"
    assert client.calls[0]["model"] == "demo-model"


def test_llm_review_service_falls_back_on_invalid_json():
    client = _Client("not json")
    service = LLMReviewService(
        _Config(
            {
                "ai.provider": "openrouter",
                "ai.openrouter.model_id": "demo-model",
            }
        ),
        client_factory=lambda: client,
    )

    outcome = service.review_records([{"id": "r1", "transcription_text": "hello"}])

    assert outcome.review_source == "fallback"
    assert outcome.fallback_reason == "invalid_model_response"
    assert outcome.suggestions


def test_llm_review_service_uses_provider_specific_model_defaults():
    service = LLMReviewService(
        _Config({"ai.provider": "groq", "ai.groq.model_id": "groq-model"}),
        client_factory=lambda: _Client('{"suggestions": []}'),
    )

    outcome = service.review_records([{"id": "r1"}])

    assert outcome.provider == "groq"
    assert outcome.model_id == "groq-model"
