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
    """Persist lexicon review suggestions and accepted local memory."""

    def __init__(self, db_path: str | Path):
        self._db_path = Path(db_path)

    def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self._db_path)) as conn:
            self._create_tables(conn)
            self._normalize_legacy_context_wrapped_entries(conn)
            self._archive_pre_v3_pending_suggestions(conn)
            conn.commit()

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
            self._normalize_legacy_context_wrapped_entries(conn)
            self._archive_pre_v3_pending_suggestions(conn)
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
            self._normalize_legacy_context_wrapped_entries(conn)
            self._archive_pre_v3_pending_suggestions(conn)
            conn.commit()
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
            self._normalize_legacy_context_wrapped_entries(conn)
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
            self._normalize_legacy_context_wrapped_entries(conn)
            self._archive_pre_v3_pending_suggestions(conn)
            conn.commit()
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
            self._normalize_legacy_context_wrapped_entries(conn)
            self._archive_pre_v3_pending_suggestions(conn)
            conn.commit()
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

    def list_active_lexicon_entries(self) -> list[dict[str, object]]:
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            self._create_tables(conn)
            self._normalize_legacy_context_wrapped_entries(conn)
            conn.commit()
            rows = conn.execute(
                """
                SELECT *
                FROM local_lexicon_entries
                WHERE status = 'active'
                ORDER BY updated_at DESC, term COLLATE NOCASE ASC,
                         old_form COLLATE NOCASE ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def clear_lexicon_entries(self) -> None:
        with sqlite3.connect(str(self._db_path)) as conn:
            self._create_tables(conn)
            self._normalize_legacy_context_wrapped_entries(conn)
            conn.execute(
                """
                UPDATE local_lexicon_entries
                SET status = 'archived'
                WHERE status = 'active'
                """
            )
            conn.commit()

    def archive_lexicon_entry(self, entry_id: str) -> bool:
        normalized_entry_id = str(entry_id or "").strip()
        if not normalized_entry_id:
            return False
        archived_at = datetime.now().isoformat(timespec="seconds")
        with sqlite3.connect(str(self._db_path)) as conn:
            self._create_tables(conn)
            self._normalize_legacy_context_wrapped_entries(conn)
            cursor = conn.execute(
                """
                UPDATE local_lexicon_entries
                SET status = 'archived', updated_at = ?
                WHERE id = ? AND status = 'active'
                """,
                (archived_at, normalized_entry_id),
            )
            conn.commit()
        return cursor.rowcount > 0

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
            self._normalize_legacy_context_wrapped_entries(conn)
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
        conn.execute("BEGIN IMMEDIATE")
        try:
            if ReviewStorageService._review_schema_is_current(conn):
                conn.commit()
                return

            ReviewStorageService._drop_review_tables(conn)
            ReviewStorageService._create_current_review_tables(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    @staticmethod
    def _create_current_review_tables(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE review_jobs (
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
        conn.execute(
            """
            CREATE TABLE review_suggestions (
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
            CREATE TABLE review_decisions (
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
            CREATE TABLE review_cursors (
                cursor_name TEXT PRIMARY KEY,
                cursor_timestamp TEXT,
                cursor_id TEXT
            )
            """
        )
        ReviewStorageService._create_local_lexicon_entries_table(conn)
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

    @classmethod
    def _review_schema_is_current(cls, conn: sqlite3.Connection) -> bool:
        expected_columns = {
            "review_jobs": {
                "id",
                "created_at",
                "status",
                "record_limit",
                "reviewed_count",
                "suggestion_count",
                "review_source",
                "provider",
                "model_id",
                "prompt_version",
                "fallback_reason",
            },
            "review_suggestions": {
                "suggestion_id",
                "job_id",
                "suggestion_type",
                "confidence",
                "risk_level",
                "source_record_ids",
                "title",
                "detail",
                "evidence_count",
                "old_form",
                "new_form",
                "status",
                "created_at",
                "reviewed_at",
            },
            "review_decisions": {
                "id",
                "suggestion_id",
                "decision",
                "decided_at",
                "note",
            },
            "review_cursors": {
                "cursor_name",
                "cursor_timestamp",
                "cursor_id",
            },
        }
        for table_name, columns in expected_columns.items():
            actual_columns = {
                str(row[1])
                for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
            }
            if actual_columns != columns:
                return False
        return cls._local_lexicon_schema_is_current(conn)

    @staticmethod
    def _drop_review_tables(conn: sqlite3.Connection) -> None:
        for table_name in (
            "review_decisions",
            "review_suggestions",
            "review_jobs",
            "review_cursors",
            "local_lexicon_entries",
        ):
            conn.execute(f"DROP TABLE IF EXISTS {table_name}")

    @staticmethod
    def _create_local_lexicon_entries_table(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE local_lexicon_entries (
                id TEXT PRIMARY KEY,
                term TEXT NOT NULL COLLATE NOCASE,
                old_form TEXT NOT NULL COLLATE NOCASE,
                source_suggestion_id TEXT,
                evidence_count INTEGER NOT NULL DEFAULT 0,
                confidence REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (term, old_form)
            )
            """
        )

    @staticmethod
    def _normalize_legacy_context_wrapped_entries(conn: sqlite3.Connection) -> None:
        """Replace an unambiguous legacy shared context prefix with its core term."""
        prefixes = ("这个", "那个", "每个", "一个", "一些", "小")
        core_prefixes = ("梗", "段", "节", "点", "类", "版")
        rows = conn.execute(
            """
            SELECT id, term, old_form, source_suggestion_id, evidence_count,
                   confidence, status, created_at, updated_at
            FROM local_lexicon_entries
            WHERE status = 'active'
            """
        ).fetchall()
        for row in rows:
            old_form = str(row[2] or "").strip()
            term = str(row[1] or "").strip()
            core_old, core_term = ReviewStorageService._trim_legacy_context_prefix(
                old_form,
                term,
                prefixes=prefixes,
                core_prefixes=core_prefixes,
            )
            if (core_old, core_term) == (old_form, term):
                continue
            normalized_id = ReviewStorageService._lexicon_entry_id(core_term, core_old)
            conn.execute(
                """
                INSERT INTO local_lexicon_entries (
                    id, term, old_form, source_suggestion_id, evidence_count,
                    confidence, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)
                ON CONFLICT(term, old_form) DO UPDATE SET
                    evidence_count = MAX(
                        local_lexicon_entries.evidence_count,
                        excluded.evidence_count
                    ),
                    confidence = MAX(
                        local_lexicon_entries.confidence,
                        excluded.confidence
                    ),
                    updated_at = excluded.updated_at
                """,
                (
                    normalized_id,
                    core_term,
                    core_old,
                    row[3],
                    row[4],
                    row[5],
                    row[7],
                    row[8],
                ),
            )
            conn.execute(
                """
                UPDATE local_lexicon_entries
                SET status = 'archived', updated_at = ?
                WHERE id = ?
                """,
                (row[8], row[0]),
            )

    @staticmethod
    def _archive_pre_v3_pending_suggestions(conn: sqlite3.Connection) -> None:
        """Archive pending candidates that predate the strict provenance gate."""
        conn.execute(
            """
            UPDATE review_suggestions
            SET status = 'archived', reviewed_at = created_at
            WHERE status = 'pending'
              AND suggestion_type = 'lexicon_candidate'
              AND job_id IN (
                  SELECT id
                  FROM review_jobs
                  WHERE prompt_version IN ('lexicon-raw-v1', 'lexicon-core-term-v2')
              )
            """
        )

    @staticmethod
    def _trim_legacy_context_prefix(
        old_form: str,
        term: str,
        *,
        prefixes: tuple[str, ...],
        core_prefixes: tuple[str, ...],
    ) -> tuple[str, str]:
        current_old = old_form
        current_term = term
        for _ in range(3):
            matching_prefix = next(
                (
                    prefix
                    for prefix in sorted(prefixes, key=len, reverse=True)
                    if current_old.startswith(prefix)
                    and current_term.startswith(prefix)
                ),
                None,
            )
            if matching_prefix is None:
                break
            candidate_old = current_old[len(matching_prefix) :].strip()
            candidate_term = current_term[len(matching_prefix) :].strip()
            if (
                len(candidate_old) < 2
                or len(candidate_term) < 2
                or len(candidate_old) != len(candidate_term)
            ):
                break
            if (
                candidate_old[0] in core_prefixes
                and candidate_old[0] == candidate_term[0]
            ):
                current_old = candidate_old
                current_term = candidate_term
                continue
            if any(
                candidate_old.startswith(prefix) and candidate_term.startswith(prefix)
                for prefix in prefixes
            ):
                current_old = candidate_old
                current_term = candidate_term
                continue
            break
        return current_old, current_term

    @staticmethod
    def _local_lexicon_schema_is_current(conn: sqlite3.Connection) -> bool:
        columns = {
            str(row[1]): row
            for row in conn.execute(
                "PRAGMA table_info(local_lexicon_entries)"
            ).fetchall()
        }
        required_columns = {
            "id",
            "term",
            "old_form",
            "source_suggestion_id",
            "evidence_count",
            "confidence",
            "status",
            "created_at",
            "updated_at",
        }
        if not required_columns.issubset(columns):
            return False
        if not bool(columns["old_form"][3]):
            return False

        has_pair_constraint = False
        for index_row in conn.execute(
            "PRAGMA index_list(local_lexicon_entries)"
        ).fetchall():
            if not bool(index_row[2]):
                continue
            index_name = str(index_row[1]).replace('"', '""')
            key_rows = [
                row
                for row in conn.execute(
                    f'PRAGMA index_xinfo("{index_name}")'
                ).fetchall()
                if bool(row[5])
            ]
            columns = tuple(row[2] for row in key_rows)
            collations = tuple(str(row[4]).upper() for row in key_rows)
            if columns == ("term",):
                return False
            if bool(index_row[4]):
                continue
            if columns == ("term", "old_form") and collations == (
                "NOCASE",
                "NOCASE",
            ):
                has_pair_constraint = True
        return has_pair_constraint

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
    def _lexicon_entry_id(term: str, old_form: str) -> str:
        ascii_lowercase = str.maketrans(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"
        )
        pair_key = (
            f"{term.translate(ascii_lowercase)}\x1f"
            f"{old_form.translate(ascii_lowercase)}"
        )
        return f"lexicon_{uuid.uuid5(uuid.NAMESPACE_URL, pair_key).hex[:16]}"

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
        entry_id = ReviewStorageService._lexicon_entry_id(term, old_form)
        conn.execute(
            """
            INSERT INTO local_lexicon_entries (
                id, term, old_form, source_suggestion_id, evidence_count,
                confidence, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)
            ON CONFLICT(term, old_form) DO UPDATE SET
                term = excluded.term,
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
