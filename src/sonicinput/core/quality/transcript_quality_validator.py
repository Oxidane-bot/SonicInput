"""Heuristic quality guard for AI-refined voice transcripts.

The validator is intentionally conservative: it does not try to judge writing
quality. It only catches high-confidence contract violations where the AI
appears to answer, translate, format, summarize, or expand noise instead of
cleaning the transcript.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class TranscriptValidationResult:
    """Result returned by :class:`TranscriptQualityValidator`."""

    ok: bool
    reasons: tuple[str, ...] = ()

    @property
    def reason_text(self) -> str:
        return "; ".join(self.reasons)


class AIOutputValidationError(RuntimeError):
    """Raised when an AI refinement violates the transcript-cleaning contract."""

    def __init__(self, reasons: Iterable[str]):
        self.reasons = tuple(reasons)
        super().__init__("AI output validation failed: " + "; ".join(self.reasons))


class TranscriptQualityValidator:
    """Detect unsafe AI transcript-cleaning outputs.

    The rules are generic and product-level. They avoid user-specific spelling
    fixes or hardcoded personal terms.
    """

    _LABEL_RE = re.compile(
        r"(?im)^\s*(input|output|analysis|reasoning|original|refined|"
        r"translation|answer|result|原文|优化后|润色后|输出|分析|推理|译文|翻译)\s*[:：]"
    )
    _MARKDOWN_HEADING_RE = re.compile(r"(?m)^\s{0,3}#{1,6}\s+\S")
    _MARKDOWN_LIST_RE = re.compile(r"(?m)^\s*(?:[-*+]|\d+[.)、])\s+\S")
    _PARENTHESIZED_META_RESPONSE_RE = re.compile(
        r"^\s*[（(].{0,240}[）)]\s*$", re.DOTALL
    )
    _REPEATED_SEGMENT_RE = re.compile(r"(.{4,40}?)\1{2,}", re.DOTALL)
    _CJK_RE = re.compile(r"[\u4e00-\u9fff]")
    _LATIN_RE = re.compile(r"[A-Za-z]")
    _MEANINGFUL_CHAR_RE = re.compile(r"[\w\u4e00-\u9fff]", re.UNICODE)

    _PUNCTUATION_CHARS = set(
        "，。！？!?、,.…·~`'\"“”‘’()（）[]【】{}<>《》:：;；-—_ \t\r\n"
    )

    _FILLER_PHRASES = {
        "嗯",
        "嗯嗯",
        "呃",
        "额",
        "啊",
        "哦",
        "喔",
        "唉",
        "这个",
        "那个",
        "就是",
        "然后",
        "呃呃",
        "嗯哼",
        "uh",
        "um",
        "umm",
        "hmm",
        "ah",
        "er",
    }

    _ASSISTANT_TONE_PATTERNS = (
        "我是ai",
        "作为ai",
        "作为一个ai",
        "我不能",
        "我无法",
        "抱歉",
        "请提供",
        "请告诉我",
        "以下是",
        "下面是",
        "已经为你",
        "我可以帮",
        "sure,",
        "here is",
        "here's",
        "i'm sorry",
        "i’m sorry",
        "i cannot",
        "i can't",
        "can't help with that",
        "cannot help with that",
        "as an ai",
        "please provide",
        "please share",
    )
    _META_RESPONSE_PATTERNS = (
        "等待用户输入",
        "请提供需要清理",
        "请提供需要优化",
        "请把需要清理",
        "待清理的asr文本",
        "原始asr文本",
        "原始语音转写文本",
        "语音转写文本后",
        "按规则处理",
        "只返回整理后的结果",
        "waiting for user input",
        "please provide the raw",
        "raw asr text",
        "process it according to the rules",
        "return only the cleaned result",
    )

    _TRANSLATION_COMMAND_PATTERNS = (
        "翻译成",
        "翻译成英文",
        "翻译成英语",
        "翻译成中文",
        "翻译成汉语",
        "翻成英文",
        "翻成英语",
        "翻成中文",
        "翻成汉语",
        "译成英文",
        "译成英语",
        "译成中文",
        "译成汉语",
        "翻译为",
        "译为",
        "翻译一下",
        "翻译一下这句",
        "translate this",
        "translate it",
        "translate to",
        "translate to english",
        "translate to chinese",
        "translate into",
        "translate into english",
        "translate into chinese",
    )
    _OVER_COMPRESSED_RATIO_THRESHOLD = 0.45
    _SEVERE_OVER_COMPRESSED_RATIO_THRESHOLD = 0.33
    _OVER_COMPRESSED_ABSOLUTE_LOSS_THRESHOLD = 120
    _COLLAPSED_TO_FRAGMENT_MIN_ORIGINAL_LEN = 60
    _COLLAPSED_TO_FRAGMENT_MAX_LEN = 3
    _DOMINANT_SCRIPT_MIN_CHARS = 6
    _DOMINANT_SCRIPT_MIN_SHARE = 0.7

    def validate(
        self, original_text: str, refined_text: str
    ) -> TranscriptValidationResult:
        """Validate a refined transcript against the original ASR text."""

        original = self._normalize(original_text)
        refined = self._normalize(refined_text)
        reasons: list[str] = []

        if not refined and self.has_meaningful_input(original):
            reasons.append("output_emptied_meaningful_input")

        if self.is_low_information_input(original) and self._meaningful_length(
            refined
        ) > max(8, self._meaningful_length(original) * 3):
            reasons.append("low_information_input_expanded")

        if self._looks_like_markdown(refined):
            reasons.append("markdown_or_structured_format")

        if self._LABEL_RE.search(refined):
            reasons.append("prompt_label_or_reasoning_leak")

        if self._looks_like_assistant_response(refined):
            reasons.append("assistant_response_tone")

        if self._likely_executed_translation_command(original, refined):
            reasons.append("likely_executed_translation_command")

        if self._unexpected_language_shift(original, refined):
            reasons.append("unexpected_language_shift")

        if self._collapsed_to_fragment(original, refined):
            reasons.append("collapsed_to_fragment")

        if self._over_compressed(original, refined):
            reasons.append("over_compressed_long_input")

        if self._over_expanded(original, refined):
            reasons.append("over_expanded_short_input")

        if self._has_abnormal_repetition(refined):
            reasons.append("abnormal_repetition")

        return TranscriptValidationResult(ok=not reasons, reasons=tuple(reasons))

    def validate_or_raise(self, original_text: str, refined_text: str) -> None:
        result = self.validate(original_text, refined_text)
        if not result.ok:
            raise AIOutputValidationError(result.reasons)

    @classmethod
    def has_meaningful_input(cls, text: str) -> bool:
        return cls._meaningful_length(text) >= 2 and not cls.is_low_information_input(
            text
        )

    @classmethod
    def is_low_information_input(cls, text: str) -> bool:
        normalized = cls._normalize(text)
        compact = cls._strip_punctuation_and_spaces(normalized).lower()
        if not compact:
            return True
        if compact in cls._FILLER_PHRASES:
            return True
        return cls._meaningful_length(compact) <= 1

    @classmethod
    def _normalize(cls, text: str) -> str:
        normalized = unicodedata.normalize("NFKC", str(text or ""))
        return normalized.strip()

    @classmethod
    def _strip_punctuation_and_spaces(cls, text: str) -> str:
        return "".join(
            ch for ch in text if ch not in cls._PUNCTUATION_CHARS and not ch.isspace()
        )

    @classmethod
    def _meaningful_length(cls, text: str) -> int:
        return len(cls._MEANINGFUL_CHAR_RE.findall(text or ""))

    @classmethod
    def _looks_like_markdown(cls, text: str) -> bool:
        if "```" in text:
            return True
        if cls._MARKDOWN_HEADING_RE.search(text):
            return True
        # One dictated bullet can be legitimate; several list lines usually mean
        # the model formatted or answered instead of cleaning the transcript.
        return len(cls._MARKDOWN_LIST_RE.findall(text)) >= 2

    @classmethod
    def _looks_like_assistant_response(cls, text: str) -> bool:
        lowered = text.lower().strip()
        return any(pattern in lowered for pattern in cls._ASSISTANT_TONE_PATTERNS) or (
            cls._looks_like_placeholder_meta_response(text)
        )

    @classmethod
    def _looks_like_placeholder_meta_response(cls, text: str) -> bool:
        normalized = cls._normalize(text)
        lowered = normalized.lower()
        return bool(cls._PARENTHESIZED_META_RESPONSE_RE.match(normalized)) and any(
            pattern in lowered for pattern in cls._META_RESPONSE_PATTERNS
        )

    @classmethod
    def _has_translation_intent(cls, text: str) -> bool:
        lowered = text.lower()
        return any(pattern in lowered for pattern in cls._TRANSLATION_COMMAND_PATTERNS)

    @classmethod
    def _dominant_script(cls, text: str) -> str | None:
        cjk_count = len(cls._CJK_RE.findall(text))
        latin_count = len(cls._LATIN_RE.findall(text))
        total = cjk_count + latin_count
        if total <= 0:
            return None

        if (
            cjk_count >= cls._DOMINANT_SCRIPT_MIN_CHARS
            and (cjk_count / total) >= cls._DOMINANT_SCRIPT_MIN_SHARE
        ):
            return "cjk"
        if (
            latin_count >= cls._DOMINANT_SCRIPT_MIN_CHARS
            and (latin_count / total) >= cls._DOMINANT_SCRIPT_MIN_SHARE
        ):
            return "latin"
        return None

    @classmethod
    def _likely_executed_translation_command(cls, original: str, refined: str) -> bool:
        if not cls._has_translation_intent(original):
            return False
        if "翻译" in refined or "translate" in refined.lower():
            return False
        refined_meaningful = cls._meaningful_length(refined)
        if refined_meaningful < 8:
            return False

        original_script = cls._dominant_script(original)
        refined_script = cls._dominant_script(refined)
        return (
            original_script is not None
            and refined_script is not None
            and original_script != refined_script
        )

    @classmethod
    def _unexpected_language_shift(cls, original: str, refined: str) -> bool:
        if cls._has_translation_intent(original):
            return False
        if not cls.has_meaningful_input(original):
            return False
        if cls._looks_like_assistant_response(refined):
            return False
        if cls._meaningful_length(refined) < 8:
            return False

        original_script = cls._dominant_script(original)
        refined_script = cls._dominant_script(refined)
        return (
            original_script is not None
            and refined_script is not None
            and original_script != refined_script
        )

    @classmethod
    def _over_compressed(cls, original: str, refined: str) -> bool:
        original_len = cls._meaningful_length(original)
        refined_len = cls._meaningful_length(refined)
        if original_len < 80 or refined_len <= 0:
            return False

        if refined_len >= original_len * cls._OVER_COMPRESSED_RATIO_THRESHOLD:
            return False

        return (
            refined_len < original_len * cls._SEVERE_OVER_COMPRESSED_RATIO_THRESHOLD
            or (original_len - refined_len)
            >= cls._OVER_COMPRESSED_ABSOLUTE_LOSS_THRESHOLD
        )

    @classmethod
    def _collapsed_to_fragment(cls, original: str, refined: str) -> bool:
        original_len = cls._meaningful_length(original)
        refined_len = cls._meaningful_length(refined)
        if (
            original_len < cls._COLLAPSED_TO_FRAGMENT_MIN_ORIGINAL_LEN
            or refined_len <= 0
        ):
            return False
        return refined_len <= cls._COLLAPSED_TO_FRAGMENT_MAX_LEN

    @classmethod
    def _over_expanded(cls, original: str, refined: str) -> bool:
        original_len = cls._meaningful_length(original)
        refined_len = cls._meaningful_length(refined)
        return (
            1 <= original_len <= 20
            and refined_len >= 60
            and refined_len > original_len * 4
        )

    @classmethod
    def _has_abnormal_repetition(cls, text: str) -> bool:
        return bool(cls._REPEATED_SEGMENT_RE.search(text))
