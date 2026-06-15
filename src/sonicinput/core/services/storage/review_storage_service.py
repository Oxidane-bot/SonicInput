"""SQLite persistence for local review suggestions."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Iterable

from ...quality import ReviewSuggestion


class ReviewStorageService:
    """Persist local review jobs, suggestions, and decisions.

    The service is intentionally small and can share the existing history DB.
    It does not alter history records.
    """

    def __init__(self, db_path: str | Path):
        self._db_path = Path(db_path)

    def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self._db_path)) as conn:
            self._create_tables(conn)

    def save_review_run(
        self,
        suggestions: Iterable[ReviewSuggestion],
        *,
        record_limit: int,
        reviewed_count: int,
    ) -> str:
        job_id = f"review_job_{uuid.uuid4().hex[:16]}"
        created_at = datetime.now().isoformat(timespec="seconds")
        exact_skip_statuses = {"accepted", "rejected", "ignored"}
        similar_skip_statuses = {"accepted", "rejected", "ignored"}
        persisted_suggestion_count = 0

        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            self._create_tables(conn)
            conn.execute(
                """
                INSERT INTO review_jobs (
                    id, created_at, status, record_limit,
                    reviewed_count, suggestion_count
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    created_at,
                    "completed",
                    record_limit,
                    reviewed_count,
                    0,
                ),
            )
            for suggestion in suggestions:
                existing = conn.execute(
                    """
                    SELECT status
                    FROM review_suggestions
                    WHERE suggestion_id = ?
                    """,
                    (suggestion.suggestion_id,),
                ).fetchone()
                if existing is not None and existing["status"] in exact_skip_statuses:
                    continue
                if self._has_processed_similar_suggestion(
                    conn,
                    suggestion,
                    similar_skip_statuses,
                ):
                    continue

                conn.execute(
                    """
                    INSERT OR REPLACE INTO review_suggestions (
                        suggestion_id, job_id, suggestion_type, confidence,
                        risk_level, source_record_ids, title, detail,
                        evidence_count, old_form, new_form, status,
                        created_at, reviewed_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        suggestion.suggestion_id,
                        job_id,
                        suggestion.suggestion_type,
                        suggestion.confidence,
                        suggestion.risk_level,
                        json.dumps(suggestion.source_record_ids, ensure_ascii=False),
                        suggestion.title,
                        suggestion.detail,
                        suggestion.evidence_count,
                        suggestion.old_form,
                        suggestion.new_form,
                        suggestion.status,
                        created_at,
                    ),
                )
                persisted_suggestion_count += 1
            conn.execute(
                """
                UPDATE review_jobs
                SET suggestion_count = ?
                WHERE id = ?
                """,
                (persisted_suggestion_count, job_id),
            )
            conn.commit()
        return job_id

    def list_pending_suggestions(self, limit: int = 100) -> list[dict[str, object]]:
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            self._create_tables(conn)
            rows = conn.execute(
                """
                SELECT *
                FROM review_suggestions
                WHERE status = 'pending'
                ORDER BY
                    CASE risk_level
                        WHEN 'high' THEN 0
                        WHEN 'medium' THEN 1
                        WHEN 'low' THEN 2
                        ELSE 3
                    END ASC,
                    CASE
                        WHEN suggestion_type = 'lexicon_candidate' THEN 1
                        ELSE 0
                    END ASC,
                    confidence DESC,
                    evidence_count DESC,
                    created_at DESC,
                    suggestion_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def list_review_jobs(self, limit: int = 20) -> list[dict[str, object]]:
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            self._create_tables(conn)
            rows = conn.execute(
                """
                SELECT *
                FROM review_jobs
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_active_lexicon_entries(self, limit: int = 200) -> list[dict[str, object]]:
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            self._create_tables(conn)
            rows = conn.execute(
                """
                SELECT *
                FROM local_lexicon_entries
                WHERE status = 'active'
                ORDER BY updated_at DESC, term COLLATE NOCASE ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def clear_lexicon_entries(self) -> None:
        with sqlite3.connect(str(self._db_path)) as conn:
            self._create_tables(conn)
            conn.execute("UPDATE local_lexicon_entries SET status = 'archived'")
            conn.commit()

    def clear_learning_data(self) -> None:
        """Clear local review-learning state without deleting audit/job history.

        This resets:
        - accepted lexicon memory entries
        - review decisions that influence future suggestion suppression
        - processed suggestion statuses that currently suppress exact/similar items
        """
        with sqlite3.connect(str(self._db_path)) as conn:
            self._create_tables(conn)
            conn.execute(
                """
                UPDATE local_lexicon_entries
                SET status = 'archived'
                WHERE status = 'active'
                """
            )
            conn.execute("DELETE FROM review_decisions")
            conn.execute(
                """
                UPDATE review_suggestions
                SET status = 'archived', reviewed_at = NULL
                WHERE status IN ('accepted', 'rejected', 'ignored')
                """
            )
            conn.commit()

    def record_decision(
        self,
        suggestion_id: str,
        decision: str,
        *,
        note: str | None = None,
    ) -> None:
        if decision not in {"accepted", "rejected", "ignored", "archived"}:
            raise ValueError(f"Unsupported review decision: {decision}")
        decided_at = datetime.now().isoformat(timespec="seconds")
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            self._create_tables(conn)
            suggestion = conn.execute(
                """
                SELECT *
                FROM review_suggestions
                WHERE suggestion_id = ?
                """,
                (suggestion_id,),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO review_decisions (
                    id, suggestion_id, decision, decided_at, note
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    f"review_decision_{uuid.uuid4().hex[:16]}",
                    suggestion_id,
                    decision,
                    decided_at,
                    note,
                ),
            )
            conn.execute(
                """
                UPDATE review_suggestions
                SET status = ?, reviewed_at = ?
                WHERE suggestion_id = ?
                """,
                (decision, decided_at, suggestion_id),
            )
            if decision == "accepted" and suggestion is not None:
                self._upsert_lexicon_entry_from_suggestion(
                    conn,
                    suggestion=suggestion,
                    decided_at=decided_at,
                )
            conn.commit()

    @staticmethod
    def _create_tables(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS review_jobs (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL,
                record_limit INTEGER NOT NULL,
                reviewed_count INTEGER NOT NULL,
                suggestion_count INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS review_suggestions (
                suggestion_id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                suggestion_type TEXT NOT NULL,
                confidence REAL NOT NULL,
                risk_level TEXT NOT NULL,
                source_record_ids TEXT NOT NULL,
                title TEXT NOT NULL,
                detail TEXT NOT NULL,
                evidence_count INTEGER NOT NULL,
                old_form TEXT,
                new_form TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                reviewed_at TEXT,
                FOREIGN KEY(job_id) REFERENCES review_jobs(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS review_decisions (
                id TEXT PRIMARY KEY,
                suggestion_id TEXT NOT NULL,
                decision TEXT NOT NULL,
                decided_at TEXT NOT NULL,
                note TEXT,
                FOREIGN KEY(suggestion_id) REFERENCES review_suggestions(suggestion_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS local_lexicon_entries (
                id TEXT PRIMARY KEY,
                term TEXT NOT NULL UNIQUE,
                old_form TEXT,
                source_suggestion_id TEXT NOT NULL,
                evidence_count INTEGER NOT NULL,
                confidence REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(source_suggestion_id)
                    REFERENCES review_suggestions(suggestion_id)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_review_suggestions_status_created
            ON review_suggestions(status, created_at DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_local_lexicon_entries_status
            ON local_lexicon_entries(status, updated_at DESC)
            """
        )

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, object]:
        item = dict(row)
        item["source_record_ids"] = json.loads(str(item["source_record_ids"]))
        return item

    @classmethod
    def _has_processed_similar_suggestion(
        cls,
        conn: sqlite3.Connection,
        suggestion: ReviewSuggestion,
        processed_statuses: set[str],
    ) -> bool:
        rows = conn.execute(
            """
            SELECT suggestion_type, source_record_ids, old_form, new_form, status
            FROM review_suggestions
            WHERE suggestion_type = ?
            """,
            (suggestion.suggestion_type,),
        ).fetchall()
        target = cls._suggestion_fingerprint(
            suggestion.suggestion_type,
            suggestion.source_record_ids,
            suggestion.old_form,
            suggestion.new_form,
        )
        for row in rows:
            if row["status"] not in processed_statuses:
                continue
            try:
                source_record_ids = tuple(json.loads(row["source_record_ids"]))
            except Exception:
                source_record_ids = ()
            existing = cls._suggestion_fingerprint(
                row["suggestion_type"],
                source_record_ids,
                row["old_form"],
                row["new_form"],
            )
            if existing == target:
                return True
        return False

    @staticmethod
    def _suggestion_fingerprint(
        suggestion_type: str,
        source_record_ids: tuple[str, ...],
        old_form: str | None,
        new_form: str | None,
    ) -> tuple[str, str, str, str]:
        normalized_old = str(old_form or "").strip().lower()
        normalized_new = str(new_form or "").strip().lower()
        if suggestion_type in {
            "lexicon_candidate",
            "prompt_failure_pattern",
        } and (normalized_old or normalized_new):
            source_key = ""
        else:
            source_key = ",".join(sorted(str(item) for item in source_record_ids))
        return (suggestion_type, source_key, normalized_old, normalized_new)

    @staticmethod
    def _upsert_lexicon_entry_from_suggestion(
        conn: sqlite3.Connection,
        *,
        suggestion: sqlite3.Row,
        decided_at: str,
    ) -> None:
        if suggestion["suggestion_type"] != "lexicon_candidate":
            return
        term = suggestion["new_form"]
        if not term:
            return

        entry_id = f"lexicon_{uuid.uuid5(uuid.NAMESPACE_URL, str(term)).hex[:16]}"
        conn.execute(
            """
            INSERT INTO local_lexicon_entries (
                id, term, old_form, source_suggestion_id, evidence_count,
                confidence, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)
            ON CONFLICT(term) DO UPDATE SET
                old_form = excluded.old_form,
                source_suggestion_id = excluded.source_suggestion_id,
                evidence_count = MAX(
                    local_lexicon_entries.evidence_count,
                    excluded.evidence_count
                ),
                confidence = MAX(
                    local_lexicon_entries.confidence,
                    excluded.confidence
                ),
                status = 'active',
                updated_at = excluded.updated_at
            """,
            (
                entry_id,
                term,
                suggestion["old_form"],
                suggestion["suggestion_id"],
                suggestion["evidence_count"],
                suggestion["confidence"],
                decided_at,
                decided_at,
            ),
        )
