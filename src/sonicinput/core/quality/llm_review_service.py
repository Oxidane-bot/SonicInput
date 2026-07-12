"""LLM-backed lexicon candidate generation."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from pypinyin import lazy_pinyin

from ...ai.factory import AIClientFactory
from ..services.config import ConfigKeys
from .lexicon_matcher import is_conservative_phonetic_confusion
from .lexicon_review_agent import LexiconReviewAgent, ReviewSuggestion


@dataclass(frozen=True)
class ReviewRunOutcome:
    """Review run result with source metadata."""

    review_source: str
    suggestions: tuple[ReviewSuggestion, ...]
    provider: str | None = None
    model_id: str | None = None
    prompt_version: str = "lexicon-core-term-v3"
    fallback_reason: str | None = None
    parser_error: str | None = None
    raw_response: str | None = None


class LLMReviewService:
    """Ask the configured AI provider to mine only lexicon candidates."""

    _PROMPT_VERSION = "lexicon-core-term-v3"
    _MAX_OUTPUT_TOKENS = 1200
    _MAX_TEXT_EXCERPT_CHARS = 280
    _MAX_CORE_TERM_CHARS = 12
    _MIN_CJK_CORE_CHARS = 2
    _GENERIC_PREFIXES = ("这个", "那个", "每个", "一个", "一些")
    _GENERIC_SINGLE_CHAR_PREFIXES = ("小",)
    _GENERIC_PREFIX_SUFFIXES = ("梗", "段", "节", "点", "类", "版")
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
            "help the next AI cleanup pass before it runs. Read the whole raw snippet "
            "and use full-sentence context only to reject uncertain candidates. Never "
            "infer a target from the topic, "
            "a nearby word, or a corrected/final answer. Each old_form and new_form "
            "must be the smallest reusable complete term containing the ASR error, "
            "normally a 2-6 character same-sound or conservatively near-sound "
            "replacement. A near-sound pair may differ in only one syllable through "
            "a common ASR confusion such as zh/z, ch/c, sh/s, n/l, or a nearby nasal "
            "final. Do not output a single changed character. Strip only clearly "
            "generic shared prefixes, "
            "classifier words, verbs, particles, and surrounding noun phrases; never "
            "strip a meaningful shared stem. Example: raw '每一级的一个小梗盖' must yield "
            "old_form '梗盖' and new_form '梗概', never '小梗盖' -> '小梗概' and never "
            "'盖' -> '概'. Only suggest a pair when the raw form is an exact substring "
            "and the replacement is a high-confidence same-sound intended domain "
            "term, proper noun, API/product name, or stable homophone correction. The "
            "two forms must be a local substitution for the same term, not a rewrite "
            "to another word elsewhere in the sentence. Do not use semantic topic "
            "guesses to replace an ordinary phrase with an unrelated word. Example: "
            "do not infer '张话' -> '过滤' merely because the nearby topic mentions "
            "filtering. Do not replace a natural ordinary phrase with a merely "
            "same-sounding word. Example: do not infer '预览' -> '玉兰'. Do not output "
            "equal or formatting-only pairs. Do not audit "
            "content, style, safety, prompt "
            "quality, transcript quality, punctuation, grammar, translation, or "
            "generic rewrites. If the raw phrase could be ordinary wording, if "
            "multiple homophones are plausible, if the changed portion cannot be "
            "isolated, or if a source record cannot be named, return no suggestion. "
            "Prefer no suggestion over a guess. Return "
            "at most 4 suggestions. The detail must be one short context-evidence "
            "sentence based only on raw text; do not output a reasoning chain and "
            "never say it was corrected by AI. Use this exact "
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
        for item in items:
            suggestion = self._coerce_suggestion(item, records)
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
        old_form, new_form = self._trim_generic_shared_prefix(old_form, new_form)
        if self._canonical_form(old_form) == self._canonical_form(new_form):
            return None
        if (
            len(old_form) > self._MAX_CORE_TERM_CHARS
            or len(new_form) > self._MAX_CORE_TERM_CHARS
        ):
            return None

        source_record_ids = item.get("source_record_ids", [])
        if isinstance(source_record_ids, str):
            source_record_ids = [source_record_ids]
        if not isinstance(source_record_ids, list):
            source_record_ids = []
        normalized_ids = tuple(
            dict.fromkeys(
                str(value).strip() for value in source_record_ids if str(value).strip()
            )
        )
        if not normalized_ids:
            return None
        supporting_ids = self._supporting_record_ids(
            old_form,
            new_form,
            normalized_ids,
            records,
        )
        if not supporting_ids:
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
                supporting_ids,
                old_form,
                new_form,
                title,
            ),
            suggestion_type="lexicon_candidate",
            confidence=round(confidence, 3),
            risk_level="medium",
            source_record_ids=supporting_ids,
            title=title,
            detail=detail,
            evidence_count=len(supporting_ids),
            old_form=old_form,
            new_form=new_form,
        )

    @classmethod
    def _supporting_record_ids(
        cls,
        old_form: str,
        new_form: str,
        source_record_ids: tuple[str, ...],
        records: list[Any],
    ) -> tuple[str, ...]:
        if not cls._forms_look_like_lexicon_pair(old_form, new_form):
            return ()
        by_id = {
            str(
                record.get("id", "")
                if isinstance(record, dict)
                else getattr(record, "id", "")
            ).strip(): record
            for record in records
        }
        supported: list[str] = []
        for record_id in source_record_ids:
            record = by_id.get(record_id)
            if record is None:
                return ()
            serialized = cls._serialize_record(record)
            raw = str(serialized.get("raw") or "")
            if not cls._contains_form(raw, old_form):
                return ()
            supported.append(record_id)
        return tuple(supported)

    @classmethod
    def _forms_look_like_lexicon_pair(cls, old_form: str, new_form: str) -> bool:
        old = old_form.strip()
        new = new_form.strip()
        if not old or not new:
            return False
        if cls._canonical_form(old) == cls._canonical_form(new):
            return False
        if len(old) > cls._MAX_CORE_TERM_CHARS or len(new) > cls._MAX_CORE_TERM_CHARS:
            return False
        old_has_ascii = cls._has_ascii_letters(old)
        new_has_ascii = cls._has_ascii_letters(new)
        if old_has_ascii != new_has_ascii:
            return False
        if old_has_ascii:
            return cls._ascii_forms_are_locally_related(old, new)
        return cls._cjk_forms_are_locally_related(old, new)

    @classmethod
    def _trim_generic_shared_prefix(
        cls, old_form: str, new_form: str
    ) -> tuple[str, str]:
        trimmed_old = old_form
        trimmed_new = new_form
        prefixes = sorted(
            (*cls._GENERIC_PREFIXES, *cls._GENERIC_SINGLE_CHAR_PREFIXES),
            key=len,
            reverse=True,
        )
        while True:
            for prefix in prefixes:
                if not (
                    trimmed_old.startswith(prefix) and trimmed_new.startswith(prefix)
                ):
                    continue
                next_old = trimmed_old[len(prefix) :].strip()
                next_new = trimmed_new[len(prefix) :].strip()
                if cls._can_trim_generic_prefix(next_old, next_new):
                    trimmed_old = next_old
                    trimmed_new = next_new
                    break
            else:
                return trimmed_old, trimmed_new

    @classmethod
    def _can_trim_generic_prefix(cls, old_form: str, new_form: str) -> bool:
        if (
            cls._cjk_count(old_form) < cls._MIN_CJK_CORE_CHARS
            or cls._cjk_count(new_form) < cls._MIN_CJK_CORE_CHARS
        ):
            return False
        if cls._has_generic_core_prefix(old_form, new_form):
            return True
        return any(
            old_form.startswith(prefix) and new_form.startswith(prefix)
            for prefix in (*cls._GENERIC_PREFIXES, *cls._GENERIC_SINGLE_CHAR_PREFIXES)
        )

    @classmethod
    def _has_generic_core_prefix(cls, old_form: str, new_form: str) -> bool:
        if len(old_form) != len(new_form) or len(old_form) < 2:
            return False
        return (
            old_form[0] == new_form[0] and old_form[0] in cls._GENERIC_PREFIX_SUFFIXES
        )

    @classmethod
    def _cjk_forms_are_locally_related(cls, old_form: str, new_form: str) -> bool:
        if (
            cls._cjk_count(old_form) < cls._MIN_CJK_CORE_CHARS
            or cls._cjk_count(new_form) < cls._MIN_CJK_CORE_CHARS
        ):
            return False
        old_syllables = tuple(lazy_pinyin(old_form))
        new_syllables = tuple(lazy_pinyin(new_form))
        if len(old_syllables) != len(new_syllables):
            return False
        if not any(
            old_char == new_char
            for old_char, new_char in zip(old_form, new_form)
            if cls._is_cjk(old_char) and cls._is_cjk(new_char)
        ):
            return False
        near_sound_count = 0
        for old_syllable, new_syllable in zip(old_syllables, new_syllables):
            if old_syllable == new_syllable:
                continue
            if not is_conservative_phonetic_confusion(old_syllable, new_syllable):
                return False
            near_sound_count += 1
        return near_sound_count <= 1

    @classmethod
    def _ascii_forms_are_locally_related(cls, old_form: str, new_form: str) -> bool:
        if not (
            cls._has_ascii_term_shape(old_form) or cls._has_ascii_term_shape(new_form)
        ):
            return False
        old_tokens = cls._ascii_tokens(old_form)
        new_tokens = cls._ascii_tokens(new_form)
        if not old_tokens or not new_tokens:
            return False
        if set(old_tokens) & set(new_tokens):
            return True
        return any(
            cls._is_subsequence(left, right) or cls._is_subsequence(right, left)
            for left in old_tokens
            for right in new_tokens
        )

    @staticmethod
    def _is_subsequence(left: str, right: str) -> bool:
        if len(left) < 3 or len(left) >= len(right):
            return False
        iterator = iter(right)
        return all(char in iterator for char in left)

    @staticmethod
    def _ascii_tokens(text: str) -> tuple[str, ...]:
        return tuple(token.casefold() for token in re.findall(r"[A-Za-z0-9]+", text))

    @staticmethod
    def _contains_form(text: str, form: str) -> bool:
        return LLMReviewService._canonical_form(
            form
        ) in LLMReviewService._canonical_form(text)

    @staticmethod
    def _canonical_form(text: str) -> str:
        normalized = unicodedata.normalize("NFKC", str(text or ""))
        return re.sub(r"[\s\u200b-\u200d\ufeff]+", "", normalized).casefold()

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
