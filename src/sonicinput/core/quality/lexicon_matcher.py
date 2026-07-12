"""Local phonetic pre-filtering for accepted lexicon entries.

Confirmed ASR forms are the primary retrieval key. A correct term is used only
as a conservative fallback for an unseen homophone or a one-edit ASCII variant;
an already-correct literal term does not cause prompt injection.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

from pypinyin import lazy_pinyin


_FUZZY_INITIALS: Tuple[Tuple[str, str], ...] = (
    ("zh", "z"),
    ("ch", "c"),
    ("sh", "s"),
)
_FUZZY_FINALS: Tuple[Tuple[str, str], ...] = (
    ("iang", "ian"),
    ("uang", "uan"),
    ("ang", "an"),
    ("eng", "en"),
    ("ing", "in"),
)
_ASCII_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
_FLEXIBLE_ASCII_FORM_RE = re.compile(r"^[A-Za-z0-9]+(?:[ _-]+[A-Za-z0-9]+)*$")

_CONFIRMED_LITERAL_SCORE = 5
_CONFIRMED_EXACT_SCORE = 4
_TERM_VARIANT_SCORE = 3
_CONFIRMED_FUZZY_SCORE = 2


@dataclass(frozen=True)
class _IndexedEntry:
    index: int
    entry: Dict[str, Any]
    term: str
    old_form: str


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x4E00 <= code <= 0x9FFF or 0x3400 <= code <= 0x4DBF or 0xF900 <= code <= 0xFAFF
    )


def _edit_distance_leq_1(left: str, right: str) -> bool:
    """Return whether two strings have Levenshtein distance at most one."""
    if left == right:
        return True
    len_l, len_r = len(left), len(right)
    if abs(len_l - len_r) > 1:
        return False
    if len_l > len_r:
        left, right = right, left
        len_l, len_r = len_r, len_l
    for index in range(len_l):
        if left[index] != right[index]:
            if len_l == len_r:
                return left[index + 1 :] == right[index + 1 :]
            return left[index:] == right[index + 1 :]
    return True


def _contains_subsequence(haystack: Sequence[str], needle: Sequence[str]) -> bool:
    size = len(needle)
    if size == 0 or size > len(haystack):
        return False
    needle_tuple = tuple(needle)
    return any(
        tuple(haystack[start : start + size]) == needle_tuple
        for start in range(len(haystack) - size + 1)
    )


def _count_subsequences(haystack: Sequence[str], needle: Sequence[str]) -> int:
    size = len(needle)
    if size == 0 or size > len(haystack):
        return 0
    needle_tuple = tuple(needle)
    return sum(
        tuple(haystack[start : start + size]) == needle_tuple
        for start in range(len(haystack) - size + 1)
    )


def _one_phonetic_confusion(left: str, right: str) -> bool:
    """Return whether one known ASR pronunciation confusion relates two syllables."""
    if left == right:
        return False

    for wide, narrow in _FUZZY_INITIALS:
        if left.startswith(wide) and narrow + left[len(wide) :] == right:
            return True
        if right.startswith(wide) and narrow + right[len(wide) :] == left:
            return True

    if left.startswith("n") and not left.startswith("ng"):
        if "l" + left[1:] == right:
            return True
    if right.startswith("n") and not right.startswith("ng"):
        if "l" + right[1:] == left:
            return True

    for wide, narrow in _FUZZY_FINALS:
        if left.endswith(wide) and left[: -len(wide)] + narrow == right:
            return True
        if right.endswith(wide) and right[: -len(wide)] + narrow == left:
            return True
    return False


def is_conservative_phonetic_confusion(left: str, right: str) -> bool:
    """Expose the narrow ASR near-sound rule for candidate validation."""
    return _one_phonetic_confusion(left, right)


def _contains_single_confusion_subsequence(
    haystack: Sequence[str], needle: Sequence[str]
) -> bool:
    """Match a same-length window with exactly one conservative pinyin confusion."""
    size = len(needle)
    if size == 0 or size > len(haystack):
        return False
    for start in range(len(haystack) - size + 1):
        confusion_count = 0
        for actual, expected in zip(haystack[start : start + size], needle):
            if actual == expected:
                continue
            if not _one_phonetic_confusion(actual, expected):
                break
            confusion_count += 1
            if confusion_count > 1:
                break
        else:
            if confusion_count == 1:
                return True
    return False


def _count_single_confusion_subsequences(
    haystack: Sequence[str], needle: Sequence[str]
) -> int:
    size = len(needle)
    if size == 0 or size > len(haystack):
        return 0
    count = 0
    for start in range(len(haystack) - size + 1):
        confusion_count = 0
        for actual, expected in zip(haystack[start : start + size], needle):
            if actual == expected:
                continue
            if not _one_phonetic_confusion(actual, expected):
                break
            confusion_count += 1
            if confusion_count > 1:
                break
        else:
            count += confusion_count == 1
    return count


class LexiconMatcher:
    """Select accepted lexicon entries relevant to the current transcript."""

    def __init__(self) -> None:
        self._form_syllable_cache: Dict[str, Tuple[str, ...]] = {}
        self._entries_identity: int | None = None
        self._entries_length = -1
        self._indexed_entries: Tuple[_IndexedEntry, ...] = ()
        self._ascii_entries_by_token: Dict[str, Tuple[_IndexedEntry, ...]] = {}
        self._ascii_entries_by_deleted_token: Dict[str, Tuple[_IndexedEntry, ...]] = {}
        self._cjk_entries_by_syllable: Dict[str, Tuple[_IndexedEntry, ...]] = {}
        self._other_entries: Tuple[_IndexedEntry, ...] = ()

    def invalidate_entry_index(self) -> None:
        """Discard cached candidates after the local lexicon changes."""
        self._entries_identity = None
        self._entries_length = -1
        self._indexed_entries = ()
        self._ascii_entries_by_token = {}
        self._ascii_entries_by_deleted_token = {}
        self._cjk_entries_by_syllable = {}
        self._other_entries = ()

    @staticmethod
    def _deleted_token_variants(token: str) -> Tuple[str, ...]:
        return tuple(
            {token[:index] + token[index + 1 :] for index in range(len(token))}
        )

    def _index_entries(self, entries: Sequence[Dict[str, Any]]) -> None:
        if self._entries_identity == id(entries) and self._entries_length == len(
            entries
        ):
            return

        ascii_by_token: Dict[str, List[_IndexedEntry]] = defaultdict(list)
        ascii_by_deleted_token: Dict[str, List[_IndexedEntry]] = defaultdict(list)
        cjk_by_syllable: Dict[str, List[_IndexedEntry]] = defaultdict(list)
        other_entries: List[_IndexedEntry] = []
        indexed_entries: List[_IndexedEntry] = []
        for index, entry in enumerate(entries):
            term = str(entry.get("term") or "").strip()
            old_form = str(entry.get("old_form") or "").strip()
            if not term or not old_form:
                continue
            indexed = _IndexedEntry(
                index=index,
                entry=entry,
                term=term,
                old_form=old_form,
            )
            indexed_entries.append(indexed)
            index_forms = (old_form, term)
            index_ascii_tokens = {
                token for form in index_forms for token in self._ascii_form_tokens(form)
            }
            index_cjk_syllables = {
                syllable
                for form in index_forms
                for syllable in self._form_syllables(form)
            }
            if index_ascii_tokens:
                for token in index_ascii_tokens:
                    ascii_by_token[token].append(indexed)
                    if len(token) >= 3:
                        for variant in self._deleted_token_variants(token):
                            ascii_by_deleted_token[variant].append(indexed)
            if index_cjk_syllables:
                for syllable in index_cjk_syllables:
                    cjk_by_syllable[syllable].append(indexed)
            if not index_ascii_tokens and not index_cjk_syllables:
                other_entries.append(indexed)

        self._entries_identity = id(entries)
        self._entries_length = len(entries)
        self._indexed_entries = tuple(indexed_entries)
        self._ascii_entries_by_token = {
            token: tuple(matches) for token, matches in ascii_by_token.items()
        }
        self._ascii_entries_by_deleted_token = {
            token: tuple(matches) for token, matches in ascii_by_deleted_token.items()
        }
        self._cjk_entries_by_syllable = {
            syllable: tuple(matches) for syllable, matches in cjk_by_syllable.items()
        }
        self._other_entries = tuple(other_entries)

    def _candidate_entries(
        self,
        entries: Sequence[Dict[str, Any]],
        cjk_segments: Sequence[Sequence[str]],
        ascii_segments: Sequence[Sequence[str]],
    ) -> Sequence[_IndexedEntry]:
        self._index_entries(entries)
        if len(self._indexed_entries) <= 512:
            return self._indexed_entries

        candidates: dict[int, _IndexedEntry] = {
            indexed.index: indexed for indexed in self._other_entries
        }
        for ascii_segment in ascii_segments:
            for token in ascii_segment:
                for indexed in self._ascii_entries_by_token.get(token, ()):
                    candidates[indexed.index] = indexed
                for indexed in self._ascii_entries_by_deleted_token.get(token, ()):
                    candidates[indexed.index] = indexed
                for variant in self._deleted_token_variants(token):
                    for indexed in self._ascii_entries_by_token.get(variant, ()):
                        candidates[indexed.index] = indexed
                    for indexed in self._ascii_entries_by_deleted_token.get(
                        variant, ()
                    ):
                        candidates[indexed.index] = indexed
        for cjk_segment in cjk_segments:
            for syllable in cjk_segment:
                for indexed in self._cjk_entries_by_syllable.get(syllable, ()):
                    candidates[indexed.index] = indexed
        return tuple(candidates.values())

    def _text_profile(self, text: str) -> Tuple[List[List[str]], List[List[str]], str]:
        """Build CJK pronunciation segments and boundary-safe ASCII token runs."""
        cjk_segments: List[List[str]] = []
        ascii_segments: List[List[str]] = []
        current_chars: List[str] = []
        current_ascii_tokens: List[str] = []
        current_ascii_token: List[str] = []

        def _flush_cjk() -> None:
            if current_chars:
                cjk_segments.append(lazy_pinyin("".join(current_chars)))
                current_chars.clear()

        def _flush_ascii_token() -> None:
            if current_ascii_token:
                current_ascii_tokens.append("".join(current_ascii_token).casefold())
                current_ascii_token.clear()

        def _flush_ascii_segment() -> None:
            _flush_ascii_token()
            if current_ascii_tokens:
                ascii_segments.append(list(current_ascii_tokens))
                current_ascii_tokens.clear()

        for char in text:
            if _is_cjk(char):
                _flush_ascii_segment()
                current_chars.append(char)
            elif char.isascii() and char.isalnum():
                _flush_cjk()
                current_ascii_token.append(char)
            elif char.isspace() or char in "-_":
                _flush_cjk()
                _flush_ascii_token()
            else:
                _flush_cjk()
                _flush_ascii_segment()
        _flush_cjk()
        _flush_ascii_segment()
        return cjk_segments, ascii_segments, text.casefold()

    def _form_syllables(self, form: str) -> Tuple[str, ...]:
        cached = self._form_syllable_cache.get(form)
        if cached is not None:
            return cached
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

    @staticmethod
    def _form_kind(form: str) -> str:
        has_cjk = any(_is_cjk(char) for char in form)
        has_ascii_alnum = any(char.isascii() and char.isalnum() for char in form)
        if has_cjk and has_ascii_alnum:
            return "mixed"
        if has_cjk:
            return "cjk"
        if has_ascii_alnum:
            return "ascii"
        return "other"

    @staticmethod
    def _ascii_form_tokens(form: str) -> List[str]:
        return [match.group(0).casefold() for match in _ASCII_TOKEN_RE.finditer(form)]

    @classmethod
    def _ascii_window_match(
        cls,
        form: str,
        text_segments: Sequence[Sequence[str]],
        *,
        fuzzy: bool,
    ) -> bool:
        return cls._count_ascii_window_matches(form, text_segments, fuzzy=fuzzy) > 0

    @classmethod
    def _count_ascii_window_matches(
        cls,
        form: str,
        text_segments: Sequence[Sequence[str]],
        *,
        fuzzy: bool,
    ) -> int:
        form_tokens = cls._ascii_form_tokens(form)
        if (
            not form_tokens
            or not text_segments
            or not _FLEXIBLE_ASCII_FORM_RE.fullmatch(form)
        ):
            return 0
        target = "".join(form_tokens)
        if fuzzy and len(target) < 3:
            return 0

        min_size = max(1, len(form_tokens) - 1)
        max_size = len(form_tokens) + 1
        match_count = 0
        for text_tokens in text_segments:
            for start in range(len(text_tokens)):
                for size in range(min_size, max_size + 1):
                    end = start + size
                    if end > len(text_tokens):
                        break
                    candidate = "".join(text_tokens[start:end])
                    if fuzzy:
                        if candidate != target and _edit_distance_leq_1(
                            candidate, target
                        ):
                            match_count += 1
                    elif candidate == target:
                        match_count += 1
        return match_count

    @staticmethod
    def _bounded_literal_match(form: str, folded_text: str) -> bool:
        return bool(LexiconMatcher._literal_ranges(form, folded_text))

    @staticmethod
    def _literal_ranges(form: str, folded_text: str) -> List[Tuple[int, int]]:
        folded_form = form.casefold()
        ranges: List[Tuple[int, int]] = []
        start = folded_text.find(folded_form)
        while start >= 0:
            end = start + len(folded_form)
            left_ok = (
                not form[0].isascii()
                or not form[0].isalnum()
                or start == 0
                or not (
                    folded_text[start - 1].isascii()
                    and folded_text[start - 1].isalnum()
                )
            )
            right_ok = (
                not form[-1].isascii()
                or not form[-1].isalnum()
                or end == len(folded_text)
                or not (folded_text[end].isascii() and folded_text[end].isalnum())
            )
            if left_ok and right_ok:
                ranges.append((start, end))
            start = folded_text.find(folded_form, start + 1)
        return ranges

    @classmethod
    def _old_literal_is_covered_by_term(
        cls,
        old_form: str,
        term: str,
        folded_text: str,
    ) -> bool:
        old_ranges = cls._literal_ranges(old_form, folded_text)
        term_ranges = cls._literal_ranges(term, folded_text)
        return bool(old_ranges and term_ranges) and all(
            any(
                term_start <= old_start and old_end <= term_end
                for term_start, term_end in term_ranges
            )
            for old_start, old_end in old_ranges
        )

    @classmethod
    def _cjk_literals_are_only_term_boundary_artifacts(
        cls,
        old_form: str,
        term: str,
        folded_text: str,
    ) -> bool:
        if cls._form_kind(old_form) != "cjk" or cls._form_kind(term) != "cjk":
            return False
        if len(old_form) < 2:
            return False

        term_ranges = cls._literal_ranges(term, folded_text)
        old_ranges = cls._literal_ranges(old_form, folded_text)
        return bool(term_ranges and old_ranges) and all(
            sum(
                term_start < old_end and old_start < term_end
                for term_start, term_end in term_ranges
            )
            >= 2
            for old_start, old_end in old_ranges
        )

    @classmethod
    def _ascii_old_is_covered_by_correct_term(
        cls,
        old_form: str,
        term: str,
        ascii_segments: Sequence[Sequence[str]],
        folded_text: str,
    ) -> bool:
        if cls._form_kind(old_form) != "ascii" or cls._form_kind(term) != "ascii":
            return False
        if cls._literal_ranges(old_form, folded_text):
            return False
        if not cls._literal_ranges(term, folded_text):
            return False
        old_compact = "".join(cls._ascii_form_tokens(old_form))
        term_compact = "".join(cls._ascii_form_tokens(term))
        if not (
            old_compact
            and term_compact
            and _edit_distance_leq_1(old_compact, term_compact)
        ):
            return False
        confirmed_match_count = cls._count_ascii_window_matches(
            old_form, ascii_segments, fuzzy=False
        )
        confirmed_match_count += cls._count_ascii_window_matches(
            old_form, ascii_segments, fuzzy=True
        )
        correct_term_match_count = len(cls._literal_ranges(term, folded_text))
        return confirmed_match_count <= correct_term_match_count

    def _confirmed_match_is_only_correct_term(
        self,
        old_form: str,
        term: str,
        segments: Sequence[Sequence[str]],
        folded_text: str,
    ) -> bool:
        if self._form_kind(old_form) != "cjk" or self._form_kind(term) != "cjk":
            return False
        old_syllables = self._form_syllables(old_form)
        term_syllables = self._form_syllables(term)
        if not old_syllables or not term_syllables:
            return False
        matches_per_term = _count_subsequences(term_syllables, old_syllables)
        matches_per_term += _count_single_confusion_subsequences(
            term_syllables, old_syllables
        )
        if matches_per_term == 0:
            return False
        confirmed_match_count = sum(
            _count_subsequences(segment, old_syllables)
            + _count_single_confusion_subsequences(segment, old_syllables)
            for segment in segments
        )
        correct_term_match_count = (
            len(self._literal_ranges(term, folded_text)) * matches_per_term
        )
        return confirmed_match_count <= correct_term_match_count

    @classmethod
    def _literal_match(
        cls,
        form: str,
        ascii_segments: Sequence[Sequence[str]],
        folded_text: str,
    ) -> bool:
        kind = cls._form_kind(form)
        if kind == "ascii":
            return cls._bounded_literal_match(
                form, folded_text
            ) or cls._ascii_window_match(form, ascii_segments, fuzzy=False)
        if kind == "mixed":
            return cls._bounded_literal_match(form, folded_text)
        if kind == "cjk":
            return form.casefold() in folded_text
        return False

    def _score_confirmed_form(
        self,
        form: str,
        segments: List[List[str]],
        ascii_segments: List[List[str]],
        folded_text: str,
    ) -> int:
        form = form.strip()
        if not form:
            return 0
        if self._literal_match(form, ascii_segments, folded_text):
            return _CONFIRMED_LITERAL_SCORE

        kind = self._form_kind(form)
        if kind == "mixed":
            return 0
        if kind == "ascii":
            return (
                _CONFIRMED_FUZZY_SCORE
                if self._ascii_window_match(form, ascii_segments, fuzzy=True)
                else 0
            )
        if kind != "cjk":
            return 0

        syllables = self._form_syllables(form)
        if len(syllables) < 2:
            return 0
        if any(_contains_subsequence(segment, syllables) for segment in segments):
            return _CONFIRMED_EXACT_SCORE
        if any(
            _contains_single_confusion_subsequence(segment, syllables)
            for segment in segments
        ):
            return _CONFIRMED_FUZZY_SCORE
        return 0

    def _score_unseen_term_variant(
        self,
        term: str,
        segments: List[List[str]],
        ascii_segments: List[List[str]],
        folded_text: str,
    ) -> int:
        """Score only a non-literal variant of the intended term."""
        kind = self._form_kind(term)
        if kind == "ascii":
            target_length = sum(len(token) for token in self._ascii_form_tokens(term))
            if target_length < 5:
                return 0
            return (
                _TERM_VARIANT_SCORE
                if self._ascii_window_match(term, ascii_segments, fuzzy=True)
                else 0
            )
        if kind != "cjk":
            return 0
        syllables = self._form_syllables(term)
        if len(syllables) < 2:
            return 0
        term_ranges = self._literal_ranges(term, folded_text)
        if term_ranges:
            return 0
        phonetic_count = sum(
            _count_subsequences(segment, syllables) for segment in segments
        )
        if phonetic_count:
            return _TERM_VARIANT_SCORE
        return 0

    def select_relevant_entries(
        self,
        text: str,
        entries: Sequence[Dict[str, Any]],
        *,
        limit: int = 8,
    ) -> List[Dict[str, Any]]:
        """Return the highest-quality distinct terms relevant to text."""
        stripped = (text or "").strip()
        safe_limit = max(0, limit)
        if not stripped or not entries or safe_limit == 0:
            return []

        segments, ascii_segments, folded_text = self._text_profile(stripped)
        scored: List[Tuple[int, int, float, bool, int, Dict[str, Any]]] = []
        for indexed in self._candidate_entries(entries, segments, ascii_segments):
            index = indexed.index
            entry = indexed.entry
            term = indexed.term
            old_form = indexed.old_form

            old_literal = self._literal_match(old_form, ascii_segments, folded_text)
            term_literal = self._literal_match(term, ascii_segments, folded_text)
            old_is_covered = (
                (
                    old_literal
                    and term_literal
                    and self._old_literal_is_covered_by_term(
                        old_form, term, folded_text
                    )
                )
                or (
                    term_literal
                    and self._ascii_old_is_covered_by_correct_term(
                        old_form, term, ascii_segments, folded_text
                    )
                )
                or (
                    term_literal
                    and self._cjk_literals_are_only_term_boundary_artifacts(
                        old_form, term, folded_text
                    )
                )
            )
            confirmed_score = (
                0
                if old_is_covered
                or (
                    term_literal
                    and not old_literal
                    and self._confirmed_match_is_only_correct_term(
                        old_form, term, segments, folded_text
                    )
                )
                else self._score_confirmed_form(
                    old_form, segments, ascii_segments, folded_text
                )
            )
            term_score = self._score_unseen_term_variant(
                term, segments, ascii_segments, folded_text
            )
            score = max(confirmed_score, term_score)
            if score <= 0:
                continue
            evidence = self._coerce_int(entry.get("evidence_count"))
            confidence = self._coerce_float(entry.get("confidence"))
            scored.append(
                (score, evidence, confidence, confirmed_score > 0, index, entry)
            )

        scored.sort(
            key=lambda item: (item[0], item[1], item[2], item[3], -item[4]),
            reverse=True,
        )
        selected: List[Dict[str, Any]] = []
        seen_matches: set[Tuple[str, str]] = set()
        terms_with_confirmed_matches = {
            str(entry.get("term") or "").strip().casefold()
            for _, _, _, confirmed, _, entry in scored
            if confirmed
        }
        for _, _, _, confirmed, _, entry in scored:
            term_key = str(entry.get("term") or "").strip().casefold()
            if not confirmed and term_key in terms_with_confirmed_matches:
                continue
            old_form_key = (
                str(entry.get("old_form") or "").strip().casefold() if confirmed else ""
            )
            match_key = (term_key, old_form_key)
            if match_key in seen_matches:
                continue
            selected.append(entry)
            seen_matches.add(match_key)
            if len(selected) >= safe_limit:
                break
        return selected

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


__all__ = ["LexiconMatcher", "is_conservative_phonetic_confusion"]
