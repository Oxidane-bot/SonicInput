"""SQLite persistence for lexicon review and local lexicon memory."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Iterable

from ...quality import ReviewSuggestion


class ReviewStorageService:
    """Persist lexicon-only review suggestions and accepted lexicon entries.

    Existing review tables are kept for compatibility, but this service only
    creates and lists ``lexicon_candidate`` suggestions. Old quality/debug review
    rows can remain in the database; they are not surfaced or accepted here.
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
        review_source: str = "local",
        provider: str | None = None,
        model_id: str | None = None,
        prompt_version: str | None = None,
        fallback_reason: str | None = None,
    ) -> str:
        job_id = f"review_job_{uuid.uuid4().hex[:16]}"
        created_at = datetime.now().isoformat(timespec="seconds")
        persisted_count = 0
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            self._create_tables(conn)
            conn.execute(
                """
                INSERT INTO review_jobs (
                    id, created_at, status, record_limit, reviewed_count,
                    suggestion_count, review_source, provider, model_id,
                    prompt_version, fallback_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    created_at,
                    "completed",
                    int(record_limit),
                    int(reviewed_count),
                    0,
                    review_source,
                    provider,
                    model_id,
                    prompt_version,
                    fallback_reason,
                ),
            )
            for suggestion in suggestions:
                if not self._is_persistable_lexicon_suggestion(suggestion):
                    continue
                if self._has_processed_similar_suggestion(conn, suggestion):
                    continue
                conn.execute(
                    """
                    INSERT OR REPLACE INTO review_suggestions (
                        suggestion_id, job_id, suggestion_type, confidence,
                        risk_level, source_record_ids, title, detail,
                        evidence_count, old_form, new_form, status,
                        created_at, reviewed_at
                    )
                    VALUES (?, ?, 'lexicon_candidate', ?, 'medium', ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        suggestion.suggestion_id,
                        job_id,
                        suggestion.confidence,
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
                persisted_count += 1
            conn.execute(
                "UPDATE review_jobs SET suggestion_count = ? WHERE id = ?",
                (persisted_count, job_id),
            )
            conn.commit()
        return job_id

    def load_review_cursor(
        self, *, cursor_name: str = "lexicon_review"
    ) -> dict[str, str] | None:
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            self._create_tables(conn)
            row = conn.execute(
                """
                SELECT cursor_timestamp, cursor_id
                FROM review_cursors
                WHERE cursor_name = ?
                """,
                (cursor_name,),
            ).fetchone()
        if row is None:
            return None
        return {
            "cursor_timestamp": str(row["cursor_timestamp"] or ""),
            "cursor_id": str(row["cursor_id"] or ""),
        }

    def save_review_cursor(
        self,
        *,
        cursor_timestamp: str | None,
        cursor_id: str | None,
        cursor_name: str = "lexicon_review",
    ) -> None:
        with sqlite3.connect(str(self._db_path)) as conn:
            self._create_tables(conn)
            conn.execute(
                """
                INSERT INTO review_cursors (cursor_name, cursor_timestamp, cursor_id)
                VALUES (?, ?, ?)
                ON CONFLICT(cursor_name) DO UPDATE SET
                    cursor_timestamp = excluded.cursor_timestamp,
                    cursor_id = excluded.cursor_id
                """,
                (cursor_name, cursor_timestamp, cursor_id),
            )
            conn.commit()

    def list_pending_suggestions(self, limit: int = 100) -> list[dict[str, object]]:
        safe_limit = max(0, int(limit or 0))
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            self._create_tables(conn)
            rows = conn.execute(
                """
                SELECT *
                FROM review_suggestions
                WHERE status = 'pending'
                  AND suggestion_type = 'lexicon_candidate'
                  AND COALESCE(old_form, '') != ''
                  AND COALESCE(new_form, '') != ''
                ORDER BY confidence DESC, evidence_count DESC, created_at DESC, suggestion_id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def list_review_jobs(self, limit: int = 20) -> list[dict[str, object]]:
        safe_limit = max(0, int(limit or 0))
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
                (safe_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_active_lexicon_entries(self, limit: int = 200) -> list[dict[str, object]]:
        safe_limit = max(0, int(limit or 0))
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
                (safe_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def clear_lexicon_entries(self) -> None:
        with sqlite3.connect(str(self._db_path)) as conn:
            self._create_tables(conn)
            conn.execute(
                """
                UPDATE local_lexicon_entries
                SET status = 'archived'
                WHERE status = 'active'
                """
            )
            conn.commit()

    def clear_learning_data(self) -> None:
        with sqlite3.connect(str(self._db_path)) as conn:
            self._create_tables(conn)
            conn.execute(
                "UPDATE local_lexicon_entries SET status = 'archived' WHERE status = 'active'"
            )
            conn.execute("DELETE FROM review_decisions")
            conn.execute(
                """
                UPDATE review_suggestions
                SET status = 'archived', reviewed_at = NULL
                WHERE suggestion_type = 'lexicon_candidate'
                  AND status IN ('pending', 'accepted', 'rejected', 'ignored')
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
                  AND suggestion_type = 'lexicon_candidate'
                  AND COALESCE(old_form, '') != ''
                  AND COALESCE(new_form, '') != ''
                """,
                (suggestion_id,),
            ).fetchone()
            if suggestion is None:
                return
            conn.execute(
                """
                INSERT INTO review_decisions (id, suggestion_id, decision, decided_at, note)
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
            if decision == "accepted":
                self._upsert_lexicon_entry_from_suggestion(
                    conn,
                    suggestion=suggestion,
                    decided_at=decided_at,
                )
            conn.commit()

    @staticmethod
    def _is_persistable_lexicon_suggestion(suggestion: ReviewSuggestion) -> bool:
        return (
            suggestion.suggestion_type == "lexicon_candidate"
            and bool(str(suggestion.old_form or "").strip())
            and bool(str(suggestion.new_form or "").strip())
        )

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
                suggestion_count INTEGER NOT NULL DEFAULT 0,
                review_source TEXT NOT NULL DEFAULT 'local',
                provider TEXT,
                model_id TEXT,
                prompt_version TEXT,
                fallback_reason TEXT
            )
            """
        )
        cls = ReviewStorageService
        cls._ensure_column(
            conn, "review_jobs", "review_source", "TEXT NOT NULL DEFAULT 'local'"
        )
        cls._ensure_column(conn, "review_jobs", "provider", "TEXT")
        cls._ensure_column(conn, "review_jobs", "model_id", "TEXT")
        cls._ensure_column(conn, "review_jobs", "prompt_version", "TEXT")
        cls._ensure_column(conn, "review_jobs", "fallback_reason", "TEXT")
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
            CREATE TABLE IF NOT EXISTS review_cursors (
                cursor_name TEXT PRIMARY KEY,
                cursor_timestamp TEXT,
                cursor_id TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS local_lexicon_entries (
                id TEXT PRIMARY KEY,
                term TEXT NOT NULL UNIQUE,
                old_form TEXT,
                source_suggestion_id TEXT,
                evidence_count INTEGER NOT NULL DEFAULT 0,
                confidence REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
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
    def _ensure_column(
        conn: sqlite3.Connection,
        table_name: str,
        column_name: str,
        column_definition: str,
    ) -> None:
        existing_columns = {
            row[1]
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in existing_columns:
            conn.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
            )

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, object]:
        item = dict(row)
        try:
            item["source_record_ids"] = json.loads(str(item["source_record_ids"]))
        except Exception:
            item["source_record_ids"] = []
        return item

    @classmethod
    def _has_processed_similar_suggestion(
        cls,
        conn: sqlite3.Connection,
        suggestion: ReviewSuggestion,
    ) -> bool:
        old_form = str(suggestion.old_form or "").strip().lower()
        new_form = str(suggestion.new_form or "").strip().lower()
        if not old_form or not new_form:
            return True
        row = conn.execute(
            """
            SELECT 1
            FROM review_suggestions
            WHERE suggestion_type = 'lexicon_candidate'
              AND LOWER(COALESCE(old_form, '')) = ?
              AND LOWER(COALESCE(new_form, '')) = ?
              AND status IN ('pending', 'accepted', 'rejected', 'ignored')
            LIMIT 1
            """,
            (old_form, new_form),
        ).fetchone()
        return row is not None

    @staticmethod
    def _upsert_lexicon_entry_from_suggestion(
        conn: sqlite3.Connection,
        *,
        suggestion: sqlite3.Row,
        decided_at: str,
    ) -> None:
        term = str(suggestion["new_form"] or "").strip()
        old_form = str(suggestion["old_form"] or "").strip()
        if not term or not old_form:
            return
        entry_id = f"lexicon_{uuid.uuid5(uuid.NAMESPACE_URL, term).hex[:16]}"
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
                evidence_count = MAX(local_lexicon_entries.evidence_count, excluded.evidence_count),
                confidence = MAX(local_lexicon_entries.confidence, excluded.confidence),
                status = 'active',
                updated_at = excluded.updated_at
            """,
            (
                entry_id,
                term,
                old_form,
                suggestion["suggestion_id"],
                int(suggestion["evidence_count"] or 0),
                float(suggestion["confidence"] or 0),
                decided_at,
                decided_at,
            ),
        )
