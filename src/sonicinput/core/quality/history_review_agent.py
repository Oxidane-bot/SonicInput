"""Local rule reviewer for recent transcript history."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from .transcript_quality_validator import TranscriptQualityValidator


@dataclass(frozen=True)
class ReviewSuggestion:
    """A user-reviewable local quality suggestion."""

    suggestion_id: str
    suggestion_type: str
    confidence: float
    risk_level: str
    source_record_ids: tuple[str, ...]
    title: str
    detail: str
    evidence_count: int
    old_form: str | None = None
    new_form: str | None = None
    status: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HistoryReviewAgent:
    """Generate local rule-based review suggestions from recent history records.

    This reviewer does not mutate history and does not write lexicon memory. It
    only creates pending suggestions that a future UI can show for accept/reject.
    """

    _TERM_RE = re.compile(
        r"(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9_+#./\\:-]{1,40})(?![A-Za-z0-9_])"
    )
    _PLAIN_TITLECASE_MIN_EVIDENCE = 4
    _SHORT_UPPERCASE_ABBREVIATION_MIN_EVIDENCE = 3
    _LEXICON_EVIDENCE_BONUS_STEP = 0.04
    _LEXICON_EVIDENCE_BONUS_CAP = 0.24
    _LEXICON_UPPERCASE_EVIDENCE_BONUS_STEP = 0.03
    _LEXICON_UPPERCASE_EVIDENCE_BONUS_CAP = 0.21
    _LEXICON_PLAIN_TITLECASE_EVIDENCE_BONUS_STEP = 0.02
    _LEXICON_PLAIN_TITLECASE_EVIDENCE_BONUS_CAP = 0.16
    _PROMPT_FAILURE_MIN_EVIDENCE = 2
    _CHUNK_REPEAT_MIN_FRAGMENT_CHARS = 6
    _CHUNK_REPEAT_MAX_FRAGMENT_CHARS = 24
    _FALLBACK_CANDIDATE_MIN_DURATION_SECONDS = 8.0
    _FORMAT_POLLUTION_REASONS = frozenset(
        {"markdown_or_structured_format", "prompt_label_or_reasoning_leak"}
    )
    _OVER_COMPRESSED_SUPPRESSING_REASONS = frozenset(
        {
            "collapsed_to_fragment",
            "assistant_response_tone",
            "likely_executed_translation_command",
            "unexpected_language_shift",
            *_FORMAT_POLLUTION_REASONS,
        }
    )
    _SPECIFIC_VALIDATION_REASONS = frozenset(
        {
            "assistant_response_tone",
            "abnormal_repetition",
            "collapsed_to_fragment",
            "low_information_input_expanded",
            "over_expanded_short_input",
            "over_compressed_long_input",
            "likely_executed_translation_command",
            "unexpected_language_shift",
            *_FORMAT_POLLUTION_REASONS,
        }
    )

    def __init__(self, validator: TranscriptQualityValidator | None = None):
        self._validator = validator or TranscriptQualityValidator()

    def analyze_records(self, records: Iterable[Any]) -> list[ReviewSuggestion]:
        suggestions: list[ReviewSuggestion] = []
        term_sources: dict[str, dict[str, Any]] = {}
        prompt_failure_sources: dict[str, dict[str, Any]] = {}

        for record in records:
            record_id = str(self._field(record, "id", ""))
            raw_text = str(self._field(record, "transcription_text", "") or "")
            ai_text = str(self._field(record, "ai_optimized_text", "") or "")
            final_text = str(self._field(record, "final_text", "") or "")
            ai_status = str(self._field(record, "ai_status", "") or "")
            duration = float(self._field(record, "duration", 0.0) or 0.0)
            used_fallback = bool(self._field(record, "used_fallback", False))
            transcription_status = str(
                self._field(record, "transcription_status", "") or ""
            )

            if transcription_status != "success":
                suggestions.append(
                    self._suggestion(
                        "asr_failure_alert",
                        [record_id],
                        "转写失败记录",
                        "这条记录转写失败，可作为 ASR/fallback 调试样本。",
                        confidence=0.95,
                        risk_level="low",
                    )
                )
                continue

            if ai_status == "success" and ai_text:
                validation = self._validator.validate(raw_text, ai_text)
                if not validation.ok:
                    suggestions.extend(
                        self._suggestions_for_validation_reasons(
                            record_id,
                            validation.reasons,
                        )
                    )
                    self._collect_prompt_failure_patterns(
                        record_id,
                        validation.reasons,
                        prompt_failure_sources,
                    )
            else:
                validation = None

            if (
                self._validator.is_low_information_input(raw_text)
                and len(final_text) > 20
                and (
                    validation is None
                    or "low_information_input_expanded" not in validation.reasons
                )
            ):
                suggestions.append(
                    self._suggestion(
                        "low_information_expansion_alert",
                        [record_id],
                        "低信息输入疑似被扩写",
                        "原始 ASR 像短噪声或填充词，但最终文本明显变长。建议检查是否应回退。",
                        confidence=0.85,
                        risk_level="high",
                    )
                )

            chunk_repeat_fragment = self._detect_chunk_boundary_repeat(raw_text)
            if chunk_repeat_fragment:
                suggestions.append(
                    self._suggestion(
                        "chunk_boundary_repeat_alert",
                        [record_id],
                        "疑似 chunk 边界重复",
                        "原始转写里出现了相邻重复片段，像是分块重叠没有完全去重。"
                        "建议保留为 ASR/chunk 调试样本，必要时重新处理或检查边界去重策略。",
                        confidence=self._chunk_repeat_confidence(chunk_repeat_fragment),
                        risk_level="medium",
                        old_form=chunk_repeat_fragment,
                    )
                )

            if self._should_flag_fallback_candidate(
                raw_text=raw_text,
                final_text=final_text,
                duration=duration,
                used_fallback=used_fallback,
            ):
                suggestions.append(
                    self._suggestion(
                        "fallback_candidate_alert",
                        [record_id],
                        "长录音疑似需要 fallback",
                        "这条录音时长较长，但最终结果仍接近空白、静音或低信息噪声，"
                        "且当前没有使用 fallback。建议保留为 fallback 条件调试样本。",
                        confidence=0.84,
                        risk_level="medium",
                    )
                )

            for term, strong_shape, plain_titlecase in self._candidate_terms(
                self._lexicon_source_text(
                    ai_text=ai_text,
                    final_text=final_text,
                    validation_ok=validation.ok if validation is not None else None,
                )
            ):
                if term and term.lower() not in raw_text.lower():
                    stats = term_sources.setdefault(
                        term,
                        {
                            "source_ids": set(),
                            "strong_shape": False,
                            "plain_titlecase": True,
                        },
                    )
                    stats["source_ids"].add(record_id)
                    stats["strong_shape"] = bool(stats["strong_shape"] or strong_shape)
                    stats["plain_titlecase"] = bool(
                        stats["plain_titlecase"] and plain_titlecase
                    )

        for term, stats in sorted(term_sources.items()):
            source_ids = sorted(stats["source_ids"])
            evidence_count = len(source_ids)
            if evidence_count < 2:
                continue
            if not self._should_emit_lexicon_candidate(
                term=term,
                evidence_count=evidence_count,
                strong_shape=bool(stats["strong_shape"]),
                plain_titlecase=bool(stats["plain_titlecase"]),
            ):
                continue
            suggestions.append(
                self._suggestion(
                    "lexicon_candidate",
                    source_ids,
                    f"候选术语：{term}",
                    "同一术语多次出现在 AI 清理结果中，但不稳定出现在原始 ASR。"
                    "可在 Review UI 中确认是否加入本地词汇记忆。",
                    confidence=self._lexicon_confidence(
                        term=term,
                        evidence_count=evidence_count,
                        strong_shape=bool(stats["strong_shape"]),
                        plain_titlecase=bool(stats["plain_titlecase"]),
                    ),
                    risk_level="medium",
                    new_form=term,
                )
            )

        suggestions.extend(
            self._build_prompt_failure_suggestions(prompt_failure_sources)
        )
        return sorted(suggestions, key=self._suggestion_sort_key)

    @classmethod
    def _detect_chunk_boundary_repeat(cls, text: str) -> str:
        normalized = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(normalized) < cls._CHUNK_REPEAT_MIN_FRAGMENT_CHARS * 2:
            return ""

        max_fragment = min(
            cls._CHUNK_REPEAT_MAX_FRAGMENT_CHARS,
            len(normalized) // 2,
        )
        punctuation = " \t,，.。!！?？;；:："
        for fragment_len in range(
            max_fragment,
            cls._CHUNK_REPEAT_MIN_FRAGMENT_CHARS - 1,
            -1,
        ):
            for start in range(0, len(normalized) - fragment_len * 2 + 1):
                fragment = normalized[start : start + fragment_len]
                if TranscriptQualityValidator._meaningful_length(fragment) < 4:
                    continue
                fragment_core = fragment.strip(punctuation)
                if len(fragment_core) < cls._CHUNK_REPEAT_MIN_FRAGMENT_CHARS:
                    continue
                if len(set(fragment_core)) <= 2 and len(fragment_core) < 10:
                    continue

                for gap in range(0, 3):
                    right_start = start + fragment_len + gap
                    right_end = right_start + fragment_len
                    if right_end > len(normalized):
                        continue
                    if gap > 0 and any(
                        ch not in punctuation
                        for ch in normalized[start + fragment_len : right_start]
                    ):
                        continue
                    if normalized[right_start:right_end] == fragment:
                        return fragment_core
        return ""

    @classmethod
    def _chunk_repeat_confidence(cls, fragment: str) -> float:
        normalized = str(fragment or "").strip()
        meaningful_len = TranscriptQualityValidator._meaningful_length(normalized)
        return min(0.92, 0.76 + max(0, meaningful_len - 6) * 0.015)

    def _should_flag_fallback_candidate(
        self,
        *,
        raw_text: str,
        final_text: str,
        duration: float,
        used_fallback: bool,
    ) -> bool:
        if used_fallback or duration < self._FALLBACK_CANDIDATE_MIN_DURATION_SECONDS:
            return False
        if not self._validator.is_low_information_input(raw_text):
            return False
        candidate_text = final_text or raw_text
        return not TranscriptQualityValidator.has_meaningful_input(candidate_text)

    @classmethod
    def _collect_prompt_failure_patterns(
        cls,
        record_id: str,
        reasons: tuple[str, ...],
        prompt_failure_sources: dict[str, dict[str, Any]],
    ) -> None:
        for issue_key in cls._prompt_failure_issue_keys(reasons):
            stats = prompt_failure_sources.setdefault(issue_key, {"source_ids": set()})
            stats["source_ids"].add(record_id)

    @classmethod
    def _prompt_failure_issue_keys(cls, reasons: tuple[str, ...]) -> set[str]:
        reason_set = set(reasons)
        issue_keys: set[str] = set()
        if "assistant_response_tone" in reason_set:
            issue_keys.add("assistant_response_tone")
        if "likely_executed_translation_command" in reason_set:
            issue_keys.add("translation_command_leak")
        if "unexpected_language_shift" in reason_set:
            issue_keys.add("unexpected_language_shift")
        if reason_set & cls._FORMAT_POLLUTION_REASONS:
            issue_keys.add("format_pollution")
        return issue_keys

    def _build_prompt_failure_suggestions(
        self,
        prompt_failure_sources: dict[str, dict[str, Any]],
    ) -> list[ReviewSuggestion]:
        suggestions: list[ReviewSuggestion] = []
        for issue_key, stats in sorted(prompt_failure_sources.items()):
            source_ids = sorted(
                str(item) for item in stats.get("source_ids", set()) if str(item)
            )
            evidence_count = len(source_ids)
            if evidence_count < self._PROMPT_FAILURE_MIN_EVIDENCE:
                continue
            title, detail = self._prompt_failure_issue_text(issue_key, evidence_count)
            suggestions.append(
                self._suggestion(
                    "prompt_failure_pattern",
                    source_ids,
                    title,
                    detail,
                    confidence=self._prompt_failure_confidence(evidence_count),
                    risk_level="medium",
                    old_form=issue_key,
                )
            )
        return suggestions

    @staticmethod
    def _prompt_failure_issue_text(
        issue_key: str,
        evidence_count: int,
    ) -> tuple[str, str]:
        issue_titles = {
            "assistant_response_tone": "提示词失败模式：助手回复泄漏",
            "format_pollution": "提示词失败模式：格式污染反复出现",
            "translation_command_leak": "提示词失败模式：翻译命令越界",
            "unexpected_language_shift": "提示词失败模式：语言漂移反复出现",
        }
        issue_details = {
            "assistant_response_tone": "最近 {count} 条记录里，AI 把转写清理做成了回答、拒绝、占位提示或索取更多输入。建议把这类样本加入 prompt candidate / validator 回归。",
            "format_pollution": "最近 {count} 条记录里，AI 多次混入 markdown、列表、代码块或 Input/Output 标签。建议把这类样本沉淀到 prompt/validator 调试报告。",
            "translation_command_leak": "最近 {count} 条记录里，AI 像是在直接执行口述翻译命令。建议补充更严格的 prompt candidate 或 validator 规则。",
            "unexpected_language_shift": "最近 {count} 条记录里，AI 清理结果发生了意外语言切换。建议把该模式加入 prompt candidate / validator 回归。",
        }
        return (
            issue_titles.get(issue_key, "提示词失败模式"),
            issue_details.get(
                issue_key,
                "最近 {count} 条记录出现了相似的 prompt/validator 越界模式，建议纳入本地调试报告。",
            ).format(count=evidence_count),
        )

    @staticmethod
    def _prompt_failure_confidence(evidence_count: int) -> float:
        return min(0.92, 0.72 + max(0, evidence_count - 2) * 0.05)

    def _suggestions_for_validation_reasons(
        self,
        record_id: str,
        reasons: tuple[str, ...],
    ) -> list[ReviewSuggestion]:
        suggestions: list[ReviewSuggestion] = []
        reason_set = set(reasons)

        if "collapsed_to_fragment" in reason_set:
            suggestions.append(
                self._suggestion(
                    "collapsed_to_fragment_alert",
                    [record_id],
                    "长文本疑似塌缩成极短碎片",
                    "原始 ASR 很长，但 AI 清理结果只剩极短片段。"
                    "这通常比普通压缩更严重，建议优先回退或重新处理。",
                    confidence=0.96,
                    risk_level="high",
                )
            )

        if "over_compressed_long_input" in reason_set and not (
            reason_set & self._OVER_COMPRESSED_SUPPRESSING_REASONS
        ):
            suggestions.append(
                self._suggestion(
                    "over_compressed_long_input_alert",
                    [record_id],
                    "长文本疑似被过度压缩",
                    "原始 ASR 较长，但 AI 清理结果明显变短。"
                    "建议人工检查是否丢失关键从句或被总结。",
                    confidence=0.88,
                    risk_level="high",
                )
            )

        if "over_expanded_short_input" in reason_set:
            suggestions.append(
                self._suggestion(
                    "over_expanded_short_input_alert",
                    [record_id],
                    "短输入疑似被过度扩写",
                    "原始 ASR 很短，但 AI 清理结果变成了明显更长的解释、答案或改写。"
                    "建议检查是否应保留原片段或直接回退。",
                    confidence=0.89,
                    risk_level="high",
                )
            )

        if "low_information_input_expanded" in reason_set:
            suggestions.append(
                self._suggestion(
                    "low_information_expansion_alert",
                    [record_id],
                    "低信息输入疑似被扩写",
                    "原始 ASR 像短噪声或填充词，但 AI 清理结果明显变长。建议检查是否应回退。",
                    confidence=0.85,
                    risk_level="high",
                )
            )

        if "assistant_response_tone" in reason_set:
            suggestions.append(
                self._suggestion(
                    "assistant_response_leak_alert",
                    [record_id],
                    "AI 输出疑似变成助手回复",
                    "AI 清理结果像在回答、拒绝、道歉、索取更多输入，"
                    "或输出占位/提示语，而不是直接清理转写文本。",
                    confidence=0.91,
                    risk_level="high",
                )
            )

        if "abnormal_repetition" in reason_set:
            suggestions.append(
                self._suggestion(
                    "abnormal_repetition_alert",
                    [record_id],
                    "AI 输出疑似异常重复",
                    "AI 清理结果包含明显重复片段，像是卡住、循环生成或原样放大了重复噪声。",
                    confidence=0.87,
                    risk_level="high",
                )
            )

        if "likely_executed_translation_command" in reason_set:
            suggestions.append(
                self._suggestion(
                    "translation_command_leak_alert",
                    [record_id],
                    "翻译指令疑似被执行",
                    "原始 ASR 像是在口述翻译命令，但 AI 输出像直接给出了译文。"
                    "语音输入清理不应执行命令或翻译。",
                    confidence=0.9,
                    risk_level="high",
                )
            )

        if "unexpected_language_shift" in reason_set:
            suggestions.append(
                self._suggestion(
                    "unexpected_language_shift_alert",
                    [record_id],
                    "AI 输出疑似发生语言漂移",
                    "原始 ASR 与 AI 清理结果的主导语言/文字系统不一致，"
                    "像是被意外翻译或切换了语言。语音输入清理通常应保留原语言。",
                    confidence=0.89,
                    risk_level="high",
                )
            )

        if reason_set & self._FORMAT_POLLUTION_REASONS:
            suggestions.append(
                self._suggestion(
                    "format_pollution_alert",
                    [record_id],
                    "AI 输出疑似格式污染",
                    "AI 清理结果包含 markdown、列表、代码块或 Input/Output 等标签。"
                    "最终输入通常应保持为普通转写文本。",
                    confidence=0.87,
                    risk_level="medium",
                )
            )

        remaining_reasons = sorted(reason_set - self._SPECIFIC_VALIDATION_REASONS)
        if remaining_reasons:
            suggestions.append(
                self._suggestion(
                    "bad_ai_output_alert",
                    [record_id],
                    "AI 输出可能越界",
                    "Validator 命中："
                    + ", ".join(remaining_reasons)
                    + "。建议人工检查，必要时回退原始转写或重新处理。",
                    confidence=0.9,
                    risk_level="high",
                )
            )

        return suggestions

    @staticmethod
    def _field(record: Any, name: str, default: Any) -> Any:
        if isinstance(record, dict):
            return record.get(name, default)
        return getattr(record, name, default)

    def _candidate_terms(self, text: str) -> list[tuple[str, bool, bool]]:
        terms: dict[str, dict[str, Any]] = {}
        for match in self._TERM_RE.finditer(text or ""):
            term = match.group(1).strip(".,;:!?()[]{}<>\"'")
            if len(term) < 3:
                continue
            key = term.lower()
            strong_shape = self._has_strong_term_shape(term)
            plain_titlecase = self._is_plain_titlecase_term(term)

            if not strong_shape and not plain_titlecase:
                continue
            if plain_titlecase and self._is_sentence_start(text, match.start()):
                continue

            existing = terms.get(key)
            if existing is None:
                terms[key] = {
                    "term": term,
                    "strong_shape": strong_shape,
                    "plain_titlecase": plain_titlecase,
                }
                continue

            if len(term) > len(str(existing["term"])):
                existing["term"] = term
            existing["strong_shape"] = bool(existing["strong_shape"] or strong_shape)
            existing["plain_titlecase"] = bool(
                existing["plain_titlecase"] and plain_titlecase
            )

        return [
            (
                str(item["term"]),
                bool(item["strong_shape"]),
                bool(item["plain_titlecase"]),
            )
            for item in terms.values()
        ]

    @staticmethod
    def _has_strong_term_shape(term: str) -> bool:
        if any(char.isdigit() or char in "+#/\\_" for char in term):
            return True

        letters = [char for char in term if char.isalpha()]
        if letters and all(char.isupper() for char in letters):
            return True

        return any(char.isupper() for char in term[1:])

    @staticmethod
    def _is_plain_titlecase_term(term: str) -> bool:
        return term.isalpha() and term[:1].isupper() and term[1:].islower()

    @staticmethod
    def _is_sentence_start(text: str, index: int) -> bool:
        prefix = text[:index].rstrip()
        if not prefix:
            return True
        return prefix[-1] in ".!?。！？\n\r"

    @staticmethod
    def _lexicon_source_text(
        *,
        ai_text: str,
        final_text: str,
        validation_ok: bool | None,
    ) -> str:
        if validation_ok is True:
            return ai_text or final_text
        if validation_ok is False:
            if final_text and final_text != ai_text:
                return final_text
            return ""
        return final_text or ai_text

    @staticmethod
    def _is_short_uppercase_abbreviation(term: str) -> bool:
        return (
            term.isalpha() and len(term) <= 5 and all(char.isupper() for char in term)
        )

    @staticmethod
    def _is_all_uppercase_term(term: str) -> bool:
        letters = [char for char in term if char.isalpha()]
        return bool(letters) and all(char.isupper() for char in letters)

    @staticmethod
    def _has_mixed_case_shape(term: str) -> bool:
        return any(char.islower() for char in term) and any(
            char.isupper() for char in term[1:]
        )

    @staticmethod
    def _has_digit_or_operator_shape(term: str) -> bool:
        return any(char.isdigit() or char in "+#/\\_" for char in term)

    def _should_emit_lexicon_candidate(
        self,
        *,
        term: str,
        evidence_count: int,
        strong_shape: bool,
        plain_titlecase: bool,
    ) -> bool:
        if (
            self._is_short_uppercase_abbreviation(term)
            and evidence_count < self._SHORT_UPPERCASE_ABBREVIATION_MIN_EVIDENCE
        ):
            return False
        if strong_shape:
            return True
        if plain_titlecase:
            return evidence_count >= self._PLAIN_TITLECASE_MIN_EVIDENCE
        return False

    def _lexicon_confidence(
        self,
        *,
        term: str,
        evidence_count: int,
        strong_shape: bool,
        plain_titlecase: bool,
    ) -> float:
        del strong_shape
        if self._has_digit_or_operator_shape(term):
            base = 0.66
            evidence_bonus_step = self._LEXICON_EVIDENCE_BONUS_STEP
            evidence_bonus_cap = self._LEXICON_EVIDENCE_BONUS_CAP
        elif self._has_mixed_case_shape(term):
            base = 0.64
            evidence_bonus_step = self._LEXICON_EVIDENCE_BONUS_STEP
            evidence_bonus_cap = self._LEXICON_EVIDENCE_BONUS_CAP
        elif self._is_all_uppercase_term(term):
            base = 0.5
            evidence_bonus_step = self._LEXICON_UPPERCASE_EVIDENCE_BONUS_STEP
            evidence_bonus_cap = self._LEXICON_UPPERCASE_EVIDENCE_BONUS_CAP
        elif plain_titlecase:
            base = 0.52
            evidence_bonus_step = self._LEXICON_PLAIN_TITLECASE_EVIDENCE_BONUS_STEP
            evidence_bonus_cap = self._LEXICON_PLAIN_TITLECASE_EVIDENCE_BONUS_CAP
        else:
            base = 0.58
            evidence_bonus_step = self._LEXICON_UPPERCASE_EVIDENCE_BONUS_STEP
            evidence_bonus_cap = self._LEXICON_UPPERCASE_EVIDENCE_BONUS_CAP

        evidence_bonus = min(
            evidence_bonus_cap,
            max(0, evidence_count - 1) * evidence_bonus_step,
        )
        return min(0.95, base + evidence_bonus)

    @staticmethod
    def _suggestion_sort_key(suggestion: ReviewSuggestion) -> tuple[Any, ...]:
        risk_priority = {"high": 0, "medium": 1, "low": 2}.get(suggestion.risk_level, 3)
        type_priority = 1 if suggestion.suggestion_type == "lexicon_candidate" else 0
        return (
            risk_priority,
            type_priority,
            -suggestion.confidence,
            -suggestion.evidence_count,
            suggestion.title.lower(),
        )

    def _suggestion(
        self,
        suggestion_type: str,
        source_record_ids: list[str],
        title: str,
        detail: str,
        *,
        confidence: float,
        risk_level: str,
        old_form: str | None = None,
        new_form: str | None = None,
    ) -> ReviewSuggestion:
        stable_key = "|".join(
            [
                suggestion_type,
                ",".join(source_record_ids),
                old_form or "",
                new_form or "",
                title,
            ]
        )
        digest = hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:16]
        return ReviewSuggestion(
            suggestion_id=f"review_{digest}",
            suggestion_type=suggestion_type,
            confidence=round(confidence, 3),
            risk_level=risk_level,
            source_record_ids=tuple(source_record_ids),
            title=title,
            detail=detail,
            evidence_count=len(source_record_ids),
            old_form=old_form,
            new_form=new_form,
        )
