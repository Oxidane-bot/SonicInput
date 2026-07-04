"""LLM-backed review suggestion generation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from ...ai.factory import AIClientFactory
from ..services.config import ConfigKeys
from .history_review_agent import HistoryReviewAgent, ReviewSuggestion


@dataclass(frozen=True)
class ReviewRunOutcome:
    """Review run result with source metadata."""

    review_source: str
    suggestions: tuple[ReviewSuggestion, ...]
    provider: str | None = None
    model_id: str | None = None
    prompt_version: str = "v1"
    fallback_reason: str | None = None
    parser_error: str | None = None
    raw_response: str | None = None


class LLMReviewService:
    """Generate review suggestions from the configured AI provider.

    The LLM path is primary. Local heuristics remain available as fallback safety
    validation when the configured provider is unavailable or returns invalid
    output.
    """

    _PROMPT_VERSION = "v2"
    _MAX_OUTPUT_TOKENS = 1400
    _MAX_TEXT_EXCERPT_CHARS = 200
    _MAX_ERROR_EXCERPT_CHARS = 80
    _JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)

    def __init__(
        self,
        config_service: Any,
        *,
        fallback_agent: HistoryReviewAgent | None = None,
        client_factory: Callable[[], Any] | None = None,
    ):
        self._config_service = config_service
        self._fallback_agent = fallback_agent or HistoryReviewAgent()
        self._client_factory = client_factory or self._create_default_client

    def review_records(self, records: Iterable[Any]) -> ReviewRunOutcome:
        records_list = list(records)
        if not records_list:
            return ReviewRunOutcome("llm", tuple(), prompt_version=self._PROMPT_VERSION)

        client = None
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
            prompt = self._build_prompt()
            payload = self._build_payload(records_list)
            response = client.refine_text(
                payload,
                prompt,
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
            return self._fallback_result(
                records_list,
                str(exc),
                provider,
                model_id,
            )

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
        suggestions = self._fallback_agent.analyze_records(records)
        return ReviewRunOutcome(
            review_source="fallback",
            suggestions=tuple(suggestions),
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
        provider = self._config_service.get_setting(
            ConfigKeys.AI_PROVIDER, "openrouter"
        )
        return str(provider or "").strip()

    def _current_model_id(self, provider: str) -> str:
        key_map = {
            "groq": ConfigKeys.AI_GROQ_MODEL_ID,
            "nvidia": ConfigKeys.AI_NVIDIA_MODEL_ID,
            "openai_compatible": ConfigKeys.AI_OPENAI_COMPATIBLE_MODEL_ID,
            "openrouter": ConfigKeys.AI_OPENROUTER_MODEL_ID,
        }
        key = key_map.get(provider, ConfigKeys.AI_OPENROUTER_MODEL_ID)
        default_map = {
            "groq": "llama-3.3-70b-versatile",
            "nvidia": "meta/llama-3.1-8b-instruct",
            "openai_compatible": "local-model",
            "openrouter": "anthropic/claude-3-sonnet",
        }
        return str(self._config_service.get_setting(key, default_map.get(provider, "")))

    def _build_prompt(self) -> str:
        # v2: 词条挖掘优先 — 审查的产出是「错误形式 → 正确形式」的词汇库
        # 候选,而不是泛化的质量警报。用户确认后词条才会注入后续转写。
        return (
            "You mine ASR dictation history for recurring word-level "
            "recognition errors: proper nouns, technical terms, names, and "
            "homophone mistakes the ASR keeps getting wrong. "
            'Return only JSON: {"suggestions":[{'
            '"suggestion_type":"lexicon_candidate",'
            '"old_form":"<misrecognized text as ASR wrote it>",'
            '"new_form":"<what the user actually meant>",'
            '"title":"<short summary>",'
            '"detail":"<evidence: where and why>",'
            '"confidence":0.8,'
            '"source_record_ids":["<record id>"]}]}. '
            "Compare the raw/ai/out fields of each record to spot both "
            "corrections the AI already made (confirm them as lexicon pairs) "
            "and errors that survived to the final output. "
            "Only report concrete word or short-phrase pairs that a user "
            "would want auto-corrected in future dictation. "
            "No sentence rewrites, no style feedback, no generic quality "
            'alerts, no markdown. Return {"suggestions":[]} if nothing '
            "qualifies. Prompt v2."
        )

    def _build_payload(self, records: list[Any]) -> str:
        payload = {
            "records": [self._serialize_record(record) for record in records],
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _serialize_record(record: Any) -> dict[str, Any]:
        def _get(field: str, default: Any = None) -> Any:
            return (
                record.get(field)
                if isinstance(record, dict)
                else getattr(record, field, default)
            )

        def _clip(value: Any, limit: int) -> str | None:
            text = str(value or "").strip()
            if not text:
                return None
            if len(text) <= limit:
                return text
            return text[: limit - 1].rstrip() + "…"

        timestamp = _get("timestamp")
        if timestamp is not None:
            try:
                timestamp = timestamp.isoformat()
            except Exception:
                timestamp = str(timestamp)

        return {
            "id": str(_get("id", "") or ""),
            "timestamp": timestamp,
            "duration": round(float(_get("duration", 0.0) or 0.0), 1),
            "transcription_status": str(_get("transcription_status", "") or ""),
            "transcription_provider": str(_get("transcription_provider", "") or ""),
            "used_fallback": bool(_get("used_fallback", False)),
            "fallback_type": str(_get("fallback_type", "") or ""),
            "fallback_reason": _clip(
                _get("fallback_reason", ""),
                LLMReviewService._MAX_ERROR_EXCERPT_CHARS,
            ),
            "transcription_error": _clip(
                _get("transcription_error", ""),
                LLMReviewService._MAX_ERROR_EXCERPT_CHARS,
            ),
            "ai_status": str(_get("ai_status", "") or ""),
            "ai_provider": str(_get("ai_provider", "") or ""),
            "ai_error": _clip(
                _get("ai_error", ""),
                LLMReviewService._MAX_ERROR_EXCERPT_CHARS,
            ),
            "raw": _clip(
                _get("transcription_text", ""),
                LLMReviewService._MAX_TEXT_EXCERPT_CHARS,
            ),
            "ai": _clip(
                _get("ai_optimized_text", ""),
                LLMReviewService._MAX_TEXT_EXCERPT_CHARS,
            ),
            "out": _clip(
                _get("final_text", ""),
                LLMReviewService._MAX_TEXT_EXCERPT_CHARS,
            ),
            "dr": _clip(
                _get("transcription_decision_reason", ""),
                LLMReviewService._MAX_ERROR_EXCERPT_CHARS,
            ),
            "dc": bool(_get("diagnostics_collected", False)),
            "rp": str(_get("reprocess_parent_id", "") or ""),
            "sm": str(_get("streaming_mode", "") or ""),
            "pt": str(_get("transcription_path", "") or ""),
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

        if isinstance(parsed, list):
            items = parsed
        elif isinstance(parsed, dict):
            items = parsed.get("suggestions", [])
        else:
            return None

        if not isinstance(items, list):
            return None

        valid = []
        for index, item in enumerate(items):
            suggestion = self._coerce_suggestion(item, records, index)
            if suggestion is not None:
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

        issue = str(item.get("issue", "") or "").strip()
        suggestion_type = str(item.get("suggestion_type", "") or "").strip()
        if not suggestion_type:
            # v2 提示词只要求词条候选:带成对形式的条目默认按词条处理
            if self._optional_string(item.get("old_form")) and self._optional_string(
                item.get("new_form")
            ):
                suggestion_type = "lexicon_candidate"
            else:
                suggestion_type = self._infer_suggestion_type(issue)

        title = str(item.get("title", "") or "").strip()
        detail = str(item.get("detail", "") or "").strip()
        if not title:
            title = self._derive_title(issue, suggestion_type)
        if not detail:
            detail = issue or title
        if not suggestion_type or not title or not detail:
            return None

        source_record_ids = item.get("source_record_ids", [])
        singular_source_record_id = item.get("source_record_id", "")
        if singular_source_record_id and not source_record_ids:
            source_record_ids = [singular_source_record_id]
        if isinstance(source_record_ids, str):
            source_record_ids = [source_record_ids]
        if not isinstance(source_record_ids, list):
            source_record_ids = []
        normalized_ids = tuple(
            str(value).strip() for value in source_record_ids if str(value).strip()
        )
        if not normalized_ids and records:
            first_record = records[min(index, len(records) - 1)]
            record_id = str(
                first_record.get("id", "")
                if isinstance(first_record, dict)
                else getattr(first_record, "id", "")
            ).strip()
            if record_id:
                normalized_ids = (record_id,)
        if not normalized_ids:
            return None

        confidence = self._coerce_float(item.get("confidence"), default=0.75)
        risk_level = str(item.get("risk_level", "medium") or "medium").strip().lower()
        if risk_level not in {"high", "medium", "low"}:
            risk_level = "medium"

        old_form = self._optional_string(item.get("old_form"))
        new_form = self._optional_string(item.get("new_form"))
        # 词条候选缺少任一形式就无法入库/注入,直接丢弃
        if suggestion_type == "lexicon_candidate" and not (old_form and new_form):
            return None
        evidence_count = len(normalized_ids)
        return ReviewSuggestion(
            suggestion_id=self._stable_suggestion_id(
                suggestion_type,
                normalized_ids,
                old_form,
                new_form,
                title,
            ),
            suggestion_type=suggestion_type,
            confidence=round(confidence, 3),
            risk_level=risk_level,
            source_record_ids=normalized_ids,
            title=title,
            detail=detail,
            evidence_count=evidence_count,
            old_form=old_form,
            new_form=new_form,
        )

    @staticmethod
    def _infer_suggestion_type(issue: str) -> str:
        normalized_issue = issue.lower()
        if "assistant_response_tone" in normalized_issue:
            return "assistant_response_leak_alert"
        if "format" in normalized_issue and "pollution" in normalized_issue:
            return "format_pollution_alert"
        if "translation" in normalized_issue and "command" in normalized_issue:
            return "translation_command_leak_alert"
        if "language" in normalized_issue and "shift" in normalized_issue:
            return "unexpected_language_shift_alert"
        if "repetition" in normalized_issue:
            return "abnormal_repetition_alert"
        if "collapse" in normalized_issue or "fragment" in normalized_issue:
            return "collapsed_to_fragment_alert"
        if "compressed" in normalized_issue:
            return "over_compressed_long_input_alert"
        if "expanded" in normalized_issue:
            return "over_expanded_short_input_alert"
        if "fallback" in normalized_issue:
            return "fallback_candidate_alert"
        if "ai output validation failed" in normalized_issue:
            return "bad_ai_output_alert"
        return "bad_ai_output_alert"

    @staticmethod
    def _derive_title(issue: str, suggestion_type: str) -> str:
        if issue:
            return issue[:80]
        return suggestion_type.replace("_", " ").strip().title() or "Review finding"

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
        return f"review_{digest}"

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
