"""Lexicon-only review data types and local fallback."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class ReviewSuggestion:
    """A user-reviewable lexicon candidate."""

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


class LexiconReviewAgent:
    """Local fallback for lexicon review.

    It intentionally returns no suggestions. New lexicon memory needs an
    intended target term, and raw ASR text alone is not enough for a deterministic
    local rule to infer that target without inventing corrections.
    """

    def analyze_records(self, records: Iterable[Any]) -> list[ReviewSuggestion]:
        del records
        return []


__all__ = ["LexiconReviewAgent", "ReviewSuggestion"]
