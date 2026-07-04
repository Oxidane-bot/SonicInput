"""词汇库同音/近音预筛

把"注入哪些词条"从「全量塞进提示词」改为「程序化发音匹配」:
只有当词条的错误形式(或正确形式)与当前转写文本中的某段发音
相同或相近时,才把该词条作为纠错提示注入 AI 清理上下文。

匹配策略(由强到弱):
1. 字面命中 — 错误形式直接出现在文本中
2. 拼音精确命中 — 音节序列完全一致(同音字误写)
3. 拼音模糊命中 — 归一化后一致(平翘舌 z/zh c/ch s/sh、
   前后鼻音 an/ang en/eng in/ing、n/l 等 ASR 常见混淆)
英文词条走 token 精确匹配 + 编辑距离 ≤1 的模糊匹配。

纯本地计算,毫秒级;未命中的词条零注入。
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from pypinyin import lazy_pinyin

# ASR 常见声母混淆(平翘舌、n/l)
_FUZZY_INITIALS: Tuple[Tuple[str, str], ...] = (
    ("zh", "z"),
    ("ch", "c"),
    ("sh", "s"),
)
# ASR 常见韵母混淆(前后鼻音)
_FUZZY_FINALS: Tuple[Tuple[str, str], ...] = (
    ("iang", "ian"),
    ("uang", "uan"),
    ("ang", "an"),
    ("eng", "en"),
    ("ing", "in"),
)

_LITERAL_SCORE = 3
_EXACT_PINYIN_SCORE = 2
_FUZZY_PINYIN_SCORE = 1


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x4E00 <= code <= 0x9FFF or 0x3400 <= code <= 0x4DBF or 0xF900 <= code <= 0xFAFF
    )


def _normalize_syllable(syllable: str) -> str:
    """归一化单个拼音音节,吸收 ASR 常见发音混淆。"""
    normalized = syllable
    for wide, narrow in _FUZZY_INITIALS:
        if normalized.startswith(wide):
            normalized = narrow + normalized[len(wide) :]
            break
    if normalized.startswith("n") and not normalized.startswith("ng"):
        normalized = "l" + normalized[1:]
    for wide, narrow in _FUZZY_FINALS:
        if normalized.endswith(wide):
            normalized = normalized[: -len(wide)] + narrow
            break
    return normalized


def _edit_distance_leq_1(left: str, right: str) -> bool:
    """长度感知的编辑距离 ≤1 快速判定。"""
    if left == right:
        return True
    len_l, len_r = len(left), len(right)
    if abs(len_l - len_r) > 1:
        return False
    if len_l > len_r:
        left, right = right, left
        len_l, len_r = len_r, len_l
    # left 是较短者;逐位找第一处差异,跳过后须完全一致
    for i in range(len_l):
        if left[i] != right[i]:
            if len_l == len_r:
                return left[i + 1 :] == right[i + 1 :]
            return left[i:] == right[i + 1 :]
    return True  # left 是 right 的前缀且只差一位


def _contains_subsequence(haystack: Sequence[str], needle: Sequence[str]) -> bool:
    """needle 是否为 haystack 的连续子序列(不跨越 None 边界)。"""
    size = len(needle)
    if size == 0 or size > len(haystack):
        return False
    needle_tuple = tuple(needle)
    for start in range(len(haystack) - size + 1):
        window = tuple(haystack[start : start + size])
        if window == needle_tuple:
            return True
    return False


class LexiconMatcher:
    """对候选词条做发音相关性预筛。"""

    def __init__(self) -> None:
        self._form_syllable_cache: Dict[str, Tuple[str, ...]] = {}

    # ---- 文本侧 ----

    def _text_profile(self, text: str) -> Tuple[List[List[str]], List[str], str]:
        """把文本拆成 (CJK 连续段的音节序列列表, ASCII token 列表, 小写全文)。

        CJK 音节按连续段分组,避免 n-gram 跨越非中文字符边界。
        """
        segments: List[List[str]] = []
        current_chars: List[str] = []
        ascii_tokens: List[str] = []
        current_token: List[str] = []

        def _flush_cjk() -> None:
            if current_chars:
                segments.append(lazy_pinyin("".join(current_chars)))
                current_chars.clear()

        def _flush_token() -> None:
            if current_token:
                ascii_tokens.append("".join(current_token).lower())
                current_token.clear()

        for char in text:
            if _is_cjk(char):
                _flush_token()
                current_chars.append(char)
            elif char.isascii() and (char.isalnum() or char in "-_"):
                _flush_cjk()
                current_token.append(char)
            else:
                _flush_cjk()
                _flush_token()
        _flush_cjk()
        _flush_token()
        return segments, ascii_tokens, text.lower()

    # ---- 词条侧 ----

    def _form_syllables(self, form: str) -> Tuple[str, ...]:
        cached = self._form_syllable_cache.get(form)
        if cached is not None:
            return cached
        # 按连续 CJK 段转换,保留词组上下文(多音字)且不受混合字符干扰
        syllables: List[str] = []
        run: List[str] = []
        for char in form:
            if _is_cjk(char):
                run.append(char)
            elif run:
                syllables.extend(lazy_pinyin("".join(run)))
                run.clear()
        if run:
            syllables.extend(lazy_pinyin("".join(run)))
        result = tuple(syllables)
        self._form_syllable_cache[form] = result
        return result

    # ---- 匹配 ----

    def _score_form(
        self,
        form: str,
        segments: List[List[str]],
        ascii_tokens: List[str],
        lower_text: str,
    ) -> int:
        form = form.strip()
        if not form:
            return 0

        if form.lower() in lower_text:
            return _LITERAL_SCORE

        cjk_count = sum(1 for char in form if _is_cjk(char))
        if cjk_count >= 2:
            syllables = self._form_syllables(form)
            if syllables:
                for segment in segments:
                    if _contains_subsequence(segment, syllables):
                        return _EXACT_PINYIN_SCORE
                normalized_form = [_normalize_syllable(item) for item in syllables]
                for segment in segments:
                    normalized_segment = [_normalize_syllable(item) for item in segment]
                    if _contains_subsequence(normalized_segment, normalized_form):
                        return _FUZZY_PINYIN_SCORE
            return 0

        if cjk_count == 0 and len(form) >= 3:
            # 英文/数字词条:token 级模糊匹配(编辑距离 ≤1)
            lowered = form.lower()
            for token in ascii_tokens:
                if _edit_distance_leq_1(lowered, token):
                    return _FUZZY_PINYIN_SCORE
        # 单个 CJK 字或过短的 ASCII 词条只允许上面的字面命中,避免误注入
        return 0

    def select_relevant_entries(
        self,
        text: str,
        entries: Sequence[Dict[str, Any]],
        *,
        limit: int = 8,
    ) -> List[Dict[str, Any]]:
        """从词条列表中筛出与 text 发音相关的条目。

        Args:
            text: 当前待清理的转写文本
            entries: 词汇库条目(需含 term/old_form 字段)
            limit: 注入上限

        Returns:
            按 (匹配强度, evidence_count, confidence) 降序的命中词条
        """
        stripped = (text or "").strip()
        if not stripped or not entries:
            return []

        segments, ascii_tokens, lower_text = self._text_profile(stripped)
        scored: List[Tuple[int, int, float, Dict[str, Any]]] = []
        for entry in entries:
            term = str(entry.get("term") or "").strip()
            old_form = str(entry.get("old_form") or "").strip()
            if not term:
                continue
            # 错误形式命中(ASR 已写错)或正确形式发音命中(可能被写成别的同音词)
            score = max(
                self._score_form(old_form, segments, ascii_tokens, lower_text)
                if old_form
                else 0,
                self._score_form(term, segments, ascii_tokens, lower_text),
            )
            if score <= 0:
                continue
            evidence = self._coerce_int(entry.get("evidence_count"))
            confidence = self._coerce_float(entry.get("confidence"))
            scored.append((score, evidence, confidence, entry))

        scored.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        return [entry for _, _, _, entry in scored[: max(0, limit)]]

    @staticmethod
    def _coerce_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _coerce_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0


__all__ = ["LexiconMatcher"]
