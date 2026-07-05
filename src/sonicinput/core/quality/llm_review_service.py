"""LLM-backed lexicon candidate generation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable


from ...ai.factory import AIClientFactory
from ..services.config import ConfigKeys
from .lexicon_review_agent import LexiconReviewAgent, ReviewSuggestion


@dataclass(frozen=True)
class ReviewRunOutcome:
    """Review run result with source metadata."""

    review_source: str
    suggestions: tuple[ReviewSuggestion, ...]
    provider: str | None = None
    model_id: str | None = None
    prompt_version: str = "lexicon-raw-v1"
    fallback_reason: str | None = None
    parser_error: str | None = None
    raw_response: str | None = None


class LLMReviewService:
    """Ask the configured AI provider to mine only lexicon candidates."""

    _PROMPT_VERSION = "lexicon-raw-v1"
    _MAX_OUTPUT_TOKENS = 2000
    _MAX_TEXT_EXCERPT_CHARS = 280
    _MAX_OLD_FORM_CHARS = 24
    _MAX_NEW_FORM_CHARS = 64
    _JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)

    def __init__(
        self,
        config_service: Any,
        *,
        fallback_agent: LexiconReviewAgent | None = None,
        client_factory: Callable[[], Any] | None = None,
    ):
        self._config_service = config_service
        self._fallback_agent = fallback_agent or LexiconReviewAgent()
        self._client_factory = client_factory or self._create_default_client

    def review_records(self, records: Iterable[Any]) -> ReviewRunOutcome:
        records_list = list(records)
        if not records_list:
            return ReviewRunOutcome("llm", tuple(), prompt_version=self._PROMPT_VERSION)

        provider = ""
        model_id = ""
        try:
            client = self._client_factory()
            provider = self._current_provider()
            model_id = self._current_model_id(provider)
        except Exception as exc:
            return self._fallback_result(records_list, str(exc), provider, model_id)

        if client is None:
            return self._fallback_result(
                records_list,
                "AI client unavailable",
                provider,
                model_id,
            )

        try:
            response = client.refine_text(
                self._build_payload(records_list),
                self._build_prompt(),
                model_id or None,
                max_tokens=self._MAX_OUTPUT_TOKENS,
            )
            suggestions = self._parse_suggestions(response, records_list)
            if suggestions is None:
                return self._fallback_result(
                    records_list,
                    "invalid_model_response",
                    provider,
                    model_id,
                    raw_response=response,
                    parser_error="invalid_json",
                )
            return ReviewRunOutcome(
                review_source="llm",
                suggestions=tuple(suggestions),
                provider=provider or None,
                model_id=model_id or None,
                prompt_version=self._PROMPT_VERSION,
                raw_response=response,
            )
        except Exception as exc:
            return self._fallback_result(records_list, str(exc), provider, model_id)

    def _fallback_result(
        self,
        records: list[Any],
        fallback_reason: str,
        provider: str,
        model_id: str,
        *,
        raw_response: str | None = None,
        parser_error: str | None = None,
    ) -> ReviewRunOutcome:
        return ReviewRunOutcome(
            review_source="fallback",
            suggestions=tuple(self._fallback_agent.analyze_records(records)),
            provider=provider or None,
            model_id=model_id or None,
            prompt_version=self._PROMPT_VERSION,
            fallback_reason=fallback_reason,
            parser_error=parser_error,
            raw_response=raw_response,
        )

    def _create_default_client(self) -> Any:
        return AIClientFactory.create_from_config(self._config_service)

    def _current_provider(self) -> str:
        return str(
            self._config_service.get_setting(ConfigKeys.AI_PROVIDER, "openrouter") or ""
        ).strip()

    def _current_model_id(self, provider: str) -> str:
        key_map = {
            "groq": ConfigKeys.AI_GROQ_MODEL_ID,
            "nvidia": ConfigKeys.AI_NVIDIA_MODEL_ID,
            "openai_compatible": ConfigKeys.AI_OPENAI_COMPATIBLE_MODEL_ID,
            "openrouter": ConfigKeys.AI_OPENROUTER_MODEL_ID,
        }
        default_map = {
            "groq": "llama-3.3-70b-versatile",
            "nvidia": "meta/llama-3.1-8b-instruct",
            "openai_compatible": "local-model",
            "openrouter": "anthropic/claude-3-sonnet",
        }
        key = key_map.get(provider, ConfigKeys.AI_OPENROUTER_MODEL_ID)
        return str(self._config_service.get_setting(key, default_map.get(provider, "")))

    def _build_prompt(self) -> str:
        return (
            "Return a single JSON object only. No markdown, prose, analysis, or "
            "extra keys. You only receive raw ASR transcript snippets; there is no "
            "AI-cleaned, corrected, or final text. Mine only candidates that could "
            "help the next AI cleanup pass before it runs. Before choosing any "
            "candidate, internally read the whole raw snippet and infer the topic, "
            "object being discussed, and local phrase role. Use that full-sentence "
            "context to distinguish homophones. Each old_form must be an exact short "
            "substring from raw. Each new_form is your conservative hypothesis for "
            "the intended domain term, proper noun, API/product name, or stable "
            "homophone correction. Only suggest when old_form is semantically odd in "
            "that context and new_form makes the raw sentence more coherent as a "
            "reusable lexicon term. Do not audit content, style, safety, prompt "
            "quality, transcript quality, punctuation, grammar, translation, or "
            "generic rewrites. If the raw phrase could be ordinary wording, if "
            "multiple homophones are plausible, or if you would need a corrected/final "
            "answer to know the target, return no suggestion. Prefer no suggestion "
            "over a guess. Return at most 6 suggestions. The detail must be one short "
            "context-evidence sentence based only on raw text; do not output a "
            "reasoning chain and never say it was corrected by AI. Use this exact "
            "JSON shape: "
            '{"suggestions":[{"suggestion_type":"lexicon_candidate",'
            '"old_form":"<substring from raw>",'
            '"new_form":"<intended term hypothesis>",'
            '"title":"<short label>",'
            '"detail":"<brief raw-context evidence>",'
            '"confidence":0.8,'
            '"source_record_ids":["<record id where old_form appears in raw>"]}]}. '
            'Return {"suggestions":[]} when there are no lexicon candidates.'
        )

    def _build_payload(self, records: list[Any]) -> str:
        payload = {"records": [self._serialize_record(record) for record in records]}
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def _serialize_record(cls, record: Any) -> dict[str, Any]:
        def _get(field: str, default: Any = None) -> Any:
            if isinstance(record, dict):
                return record.get(field, default)
            return getattr(record, field, default)

        def _clip(value: Any, limit: int) -> str | None:
            text = str(value or "").strip()
            if not text:
                return None
            if len(text) <= limit:
                return text
            return text[: limit - 1].rstrip() + "…"

        return {
            "id": str(_get("id", "") or ""),
            "raw": _clip(_get("transcription_text", ""), cls._MAX_TEXT_EXCERPT_CHARS),
        }

    def _parse_suggestions(
        self,
        response_text: str,
        records: list[Any],
    ) -> list[ReviewSuggestion] | None:
        raw_json = self._extract_json_blob(response_text)
        if not raw_json:
            return None
        try:
            parsed = json.loads(raw_json)
        except Exception:
            return None

        items = (
            parsed
            if isinstance(parsed, list)
            else parsed.get("suggestions", [])
            if isinstance(parsed, dict)
            else None
        )
        if not isinstance(items, list):
            return None

        valid: list[ReviewSuggestion] = []
        seen: set[tuple[str, str]] = set()
        for index, item in enumerate(items):
            suggestion = self._coerce_suggestion(item, records, index)
            if suggestion is None:
                continue
            key = (suggestion.old_form or "", suggestion.new_form or "")
            normalized_key = (key[0].strip().lower(), key[1].strip().lower())
            if normalized_key in seen:
                continue
            seen.add(normalized_key)
            valid.append(suggestion)
        return valid

    def _coerce_suggestion(
        self,
        item: Any,
        records: list[Any],
        index: int,
    ) -> ReviewSuggestion | None:
        if not isinstance(item, dict):
            return None
        suggestion_type = str(item.get("suggestion_type", "") or "").strip()
        old_form = self._optional_string(item.get("old_form"))
        new_form = self._optional_string(item.get("new_form"))
        if suggestion_type and suggestion_type != "lexicon_candidate":
            return None
        if not old_form or not new_form:
            return None
        if old_form.strip().lower() == new_form.strip().lower():
            return None

        source_record_ids = item.get("source_record_ids", [])
        if isinstance(source_record_ids, str):
            source_record_ids = [source_record_ids]
        if not isinstance(source_record_ids, list):
            source_record_ids = []
        normalized_ids = tuple(
            str(value).strip() for value in source_record_ids if str(value).strip()
        )
        if not normalized_ids and records:
            fallback_record = records[min(index, len(records) - 1)]
            record_id = str(
                fallback_record.get("id", "")
                if isinstance(fallback_record, dict)
                else getattr(fallback_record, "id", "")
            ).strip()
            if record_id:
                normalized_ids = (record_id,)
        if not normalized_ids:
            return None
        if not self._candidate_supported_by_records(
            old_form,
            new_form,
            normalized_ids,
            records,
        ):
            return None

        confidence = self._coerce_float(item.get("confidence"), default=0.75)
        title = (
            str(item.get("title", "") or "").strip() or f"Lexicon candidate: {new_form}"
        )
        detail = str(item.get("detail", "") or "").strip() or (
            f"Potential raw ASR lexicon candidate: {old_form} -> {new_form}"
        )
        return ReviewSuggestion(
            suggestion_id=self._stable_suggestion_id(
                "lexicon_candidate",
                normalized_ids,
                old_form,
                new_form,
                title,
            ),
            suggestion_type="lexicon_candidate",
            confidence=round(confidence, 3),
            risk_level="medium",
            source_record_ids=normalized_ids,
            title=title,
            detail=detail,
            evidence_count=len(normalized_ids),
            old_form=old_form,
            new_form=new_form,
        )

    @classmethod
    def _candidate_supported_by_records(
        cls,
        old_form: str,
        new_form: str,
        source_record_ids: tuple[str, ...],
        records: list[Any],
    ) -> bool:
        if not cls._forms_look_like_lexicon_pair(old_form, new_form):
            return False
        by_id = {
            str(
                record.get("id", "")
                if isinstance(record, dict)
                else getattr(record, "id", "")
            ).strip(): record
            for record in records
        }
        for record_id in source_record_ids:
            record = by_id.get(record_id)
            if record is None:
                continue
            serialized = cls._serialize_record(record)
            raw = str(serialized.get("raw") or "")
            if cls._contains_form(raw, old_form):
                return True
        return False

    @classmethod
    def _forms_look_like_lexicon_pair(cls, old_form: str, new_form: str) -> bool:
        old = old_form.strip()
        new = new_form.strip()
        if not old or not new:
            return False
        if old.lower() == new.lower():
            return False
        if len(old) > cls._MAX_OLD_FORM_CHARS or len(new) > cls._MAX_NEW_FORM_CHARS:
            return False
        if cls._has_ascii_letters(old) or cls._has_ascii_letters(new):
            return cls._has_ascii_term_shape(old) or cls._has_ascii_term_shape(new)
        return cls._cjk_count(old) >= 2 and cls._cjk_count(new) >= 2

    @staticmethod
    def _contains_form(text: str, form: str) -> bool:
        return form.strip().lower() in text.lower()

    @staticmethod
    def _has_ascii_letters(text: str) -> bool:
        return any(char.isascii() and char.isalpha() for char in text)

    @staticmethod
    def _has_ascii_term_shape(text: str) -> bool:
        token = "".join(
            char
            for char in text.strip()
            if char.isascii() and (char.isalnum() or char in "+#._-/")
        )
        if len(token) < 3:
            return False
        if any(char.isdigit() or char in "+#._-/" for char in token):
            return True
        if any(char.isupper() for char in token):
            return True
        return any(char.isascii() and char.isalpha() for char in token)

    @staticmethod
    def _cjk_count(text: str) -> int:
        return sum(1 for char in text if LLMReviewService._is_cjk(char))

    @staticmethod
    def _is_cjk(char: str) -> bool:
        code = ord(char)
        return (
            0x4E00 <= code <= 0x9FFF
            or 0x3400 <= code <= 0x4DBF
            or 0xF900 <= code <= 0xFAFF
        )

    @staticmethod
    def _coerce_float(value: Any, default: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        return min(0.99, max(0.0, number))

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _stable_suggestion_id(
        suggestion_type: str,
        source_record_ids: tuple[str, ...],
        old_form: str | None,
        new_form: str | None,
        title: str,
    ) -> str:
        from hashlib import sha256

        stable_key = "|".join(
            [
                suggestion_type,
                ",".join(source_record_ids),
                old_form or "",
                new_form or "",
                title,
            ]
        )
        digest = sha256(stable_key.encode("utf-8")).hexdigest()[:16]
        return f"lexicon_review_{digest}"

    def _extract_json_blob(self, response_text: str) -> str:
        text = str(response_text or "").strip()
        if not text:
            return ""
        fenced = self._JSON_FENCE_RE.search(text)
        if fenced:
            return fenced.group(1).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return text[start : end + 1].strip()
        return ""


__all__ = ["LLMReviewService", "ReviewRunOutcome"]
