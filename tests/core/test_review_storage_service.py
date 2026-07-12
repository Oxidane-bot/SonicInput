import json
import sqlite3
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest

from sonicinput.core.quality import ReviewSuggestion
from sonicinput.core.services.storage import ReviewStorageService
from sonicinput.core.services.ui_services import UISettingsService


def _db_path(tmp_path: Path) -> Path:
    return tmp_path / f"test_review_storage_{uuid4().hex}.db"


def _insert_lexicon_entry(
    db_path: Path,
    *,
    entry_id: str,
    term: str,
    old_form: str = "",
    status: str = "active",
    evidence_count: int = 1,
    confidence: float = 0.8,
    updated_at: str = "2026-06-09T03:00:00",
) -> None:
    service = ReviewStorageService(db_path)
    service.initialize()
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO local_lexicon_entries (
                id, term, old_form, source_suggestion_id, evidence_count,
                confidence, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry_id,
                term,
                old_form,
                "test-suggestion",
                evidence_count,
                confidence,
                status,
                "2026-06-09T02:00:00",
                updated_at,
            ),
        )
        conn.commit()


def _seed_review_state(service: ReviewStorageService) -> None:
    suggestion = ReviewSuggestion(
        suggestion_id="stale-suggestion",
        suggestion_type="lexicon_candidate",
        confidence=0.9,
        risk_level="medium",
        source_record_ids=("record-1",),
        title="wrong -> Correct",
        detail="Repeated correction",
        evidence_count=2,
        old_form="wrong",
        new_form="Correct",
    )
    service.save_review_run([suggestion], record_limit=20, reviewed_count=1)
    service.record_decision(suggestion.suggestion_id, "accepted")
    service.save_review_cursor(
        cursor_timestamp="2026-06-10T03:00:00",
        cursor_id="record-1",
    )


def test_review_storage_service_initializes_empty_lexicon_table(tmp_path):
    service = ReviewStorageService(_db_path(tmp_path))

    assert service.list_active_lexicon_entries() == []


def test_review_storage_service_lists_only_active_lexicon_entries(tmp_path):
    db_path = _db_path(tmp_path)
    _insert_lexicon_entry(
        db_path,
        entry_id="lex-old",
        term="OldTerm",
        old_form="欧德特姆",
        status="archived",
    )
    _insert_lexicon_entry(
        db_path,
        entry_id="lex-new",
        term="PyTorch",
        old_form="拍套曲",
        status="active",
        evidence_count=3,
        confidence=0.91,
        updated_at="2026-06-09T04:00:00",
    )

    entries = ReviewStorageService(db_path).list_active_lexicon_entries()

    assert len(entries) == 1
    assert entries[0]["term"] == "PyTorch"
    assert entries[0]["old_form"] == "拍套曲"
    assert entries[0]["evidence_count"] == 3


def test_review_storage_normalizes_legacy_context_wrapped_entry(tmp_path):
    db_path = _db_path(tmp_path)
    _insert_lexicon_entry(
        db_path,
        entry_id="legacy-context",
        term="小梗概",
        old_form="小梗盖",
        confidence=0.86,
    )

    entries = ReviewStorageService(db_path).list_active_lexicon_entries()

    assert [(entry["old_form"], entry["term"]) for entry in entries] == [
        ("梗盖", "梗概")
    ]
    with sqlite3.connect(str(db_path)) as conn:
        legacy_status = conn.execute(
            "SELECT status FROM local_lexicon_entries WHERE id = 'legacy-context'"
        ).fetchone()[0]
    assert legacy_status == "archived"


def test_review_storage_does_not_trim_meaningful_shared_prefix(tmp_path):
    db_path = _db_path(tmp_path)
    _insert_lexicon_entry(
        db_path,
        entry_id="meaningful-prefix",
        term="小米手鸡",
        old_form="小米手机",
    )

    entries = ReviewStorageService(db_path).list_active_lexicon_entries()

    assert [(entry["old_form"], entry["term"]) for entry in entries] == [
        ("小米手机", "小米手鸡")
    ]


def test_review_storage_archives_pending_candidates_from_old_prompt(tmp_path):
    db_path = _db_path(tmp_path)
    service = ReviewStorageService(db_path)
    service.initialize()
    suggestion = ReviewSuggestion(
        suggestion_id="legacy-pending",
        suggestion_type="lexicon_candidate",
        confidence=0.8,
        risk_level="medium",
        source_record_ids=("record-1",),
        title="张话 -> 过滤",
        detail="Legacy candidate",
        evidence_count=1,
        old_form="张话",
        new_form="过滤",
    )
    service.save_review_run(
        [suggestion],
        record_limit=8,
        reviewed_count=1,
        prompt_version="lexicon-raw-v1",
    )

    assert ReviewStorageService(db_path).list_pending_suggestions() == []
    with sqlite3.connect(str(db_path)) as conn:
        status = conn.execute(
            "SELECT status FROM review_suggestions WHERE suggestion_id = 'legacy-pending'"
        ).fetchone()[0]
    assert status == "archived"


def test_review_storage_keeps_pending_candidates_from_current_prompt(tmp_path):
    db_path = _db_path(tmp_path)
    service = ReviewStorageService(db_path)
    service.initialize()
    suggestion = ReviewSuggestion(
        suggestion_id="current-pending",
        suggestion_type="lexicon_candidate",
        confidence=0.8,
        risk_level="medium",
        source_record_ids=("record-1",),
        title="梗盖 -> 梗概",
        detail="Current candidate",
        evidence_count=1,
        old_form="梗盖",
        new_form="梗概",
    )
    service.save_review_run(
        [suggestion],
        record_limit=8,
        reviewed_count=1,
        prompt_version="lexicon-core-term-v3",
    )

    assert [item["suggestion_id"] for item in service.list_pending_suggestions()] == [
        "current-pending"
    ]


def test_review_storage_service_lists_all_active_entries(tmp_path):
    db_path = _db_path(tmp_path)
    service = ReviewStorageService(db_path)
    service.initialize()
    with sqlite3.connect(str(db_path)) as conn:
        conn.executemany(
            """
            INSERT INTO local_lexicon_entries (
                id, term, old_form, source_suggestion_id, evidence_count,
                confidence, status, created_at, updated_at
            )
            VALUES (?, ?, ?, 'test', 1, 0.8, 'active', ?, ?)
            """,
            [
                (
                    f"lex-{index}",
                    f"Term{index}",
                    f"Alias{index}",
                    "2026-06-09T02:00:00",
                    "2026-06-09T03:00:00",
                )
                for index in range(205)
            ],
        )
        conn.commit()

    assert len(service.list_active_lexicon_entries()) == 205


def test_review_storage_service_rebuilds_obsolete_term_unique_table(tmp_path):
    db_path = _db_path(tmp_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE local_lexicon_entries (
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
        conn.executemany(
            """
            INSERT INTO local_lexicon_entries (
                id, term, old_form, source_suggestion_id, evidence_count,
                confidence, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "obsolete-active",
                    "PyTorch",
                    "拍套曲",
                    "obsolete-suggestion-1",
                    3,
                    0.91,
                    "active",
                    "2026-06-08T02:00:00",
                    "2026-06-09T03:00:00",
                ),
                (
                    "obsolete-archived",
                    "TensorFlow",
                    "腾搜佛",
                    "obsolete-suggestion-2",
                    2,
                    0.82,
                    "archived",
                    "2026-06-07T02:00:00",
                    "2026-06-08T03:00:00",
                ),
            ],
        )
        conn.commit()

    service = ReviewStorageService(db_path)
    service.initialize()

    assert service.list_active_lexicon_entries() == []

    with sqlite3.connect(str(db_path)) as conn:
        conn.executemany(
            """
            INSERT INTO local_lexicon_entries (
                id, term, old_form, source_suggestion_id, evidence_count,
                confidence, status, created_at, updated_at
            )
            VALUES (?, ?, ?, 'new-suggestion', 1, 0.8, 'active', ?, ?)
            """,
            [
                (
                    "new-alias-1",
                    "PyTorch",
                    "拍套曲",
                    "2026-06-10T02:00:00",
                    "2026-06-10T03:00:00",
                ),
                (
                    "new-alias-2",
                    "pytorch",
                    "派套曲",
                    "2026-06-10T02:00:00",
                    "2026-06-10T03:00:00",
                ),
            ],
        )
        conn.commit()

    entries = service.list_active_lexicon_entries()
    assert {(entry["term"], entry["old_form"]) for entry in entries} == {
        ("PyTorch", "拍套曲"),
        ("pytorch", "派套曲"),
    }


def test_review_storage_rebuilds_obsolete_review_jobs_schema(tmp_path):
    db_path = _db_path(tmp_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE review_jobs (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL,
                record_limit INTEGER NOT NULL,
                reviewed_count INTEGER NOT NULL,
                suggestion_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            INSERT INTO review_jobs (
                id, created_at, status, record_limit, reviewed_count, suggestion_count
            )
            VALUES ('obsolete-job', '2026-06-09T03:00:00', 'completed', 20, 1, 1)
            """
        )
        conn.commit()

    service = ReviewStorageService(db_path)
    service.initialize()

    assert service.list_review_jobs() == []
    with sqlite3.connect(str(db_path)) as conn:
        assert ReviewStorageService._review_schema_is_current(conn)


def test_review_storage_rebuilds_obsolete_partial_term_constraint(tmp_path):
    db_path = _db_path(tmp_path)
    service = ReviewStorageService(db_path)
    service.initialize()
    service.save_review_run(
        [
            ReviewSuggestion(
                suggestion_id="discarded-suggestion",
                suggestion_type="lexicon_candidate",
                confidence=0.9,
                risk_level="medium",
                source_record_ids=("record-1",),
                title="拍套曲 -> PyTorch",
                detail="Repeated correction",
                evidence_count=2,
                old_form="拍套曲",
                new_form="PyTorch",
            )
        ],
        record_limit=20,
        reviewed_count=1,
    )
    service.record_decision("discarded-suggestion", "accepted")
    service.save_review_cursor(
        cursor_timestamp="2026-06-10T03:00:00",
        cursor_id="record-1",
    )
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE UNIQUE INDEX obsolete_active_term_unique
            ON local_lexicon_entries(term)
            WHERE status = 'active'
            """
        )
        conn.commit()

    assert service.list_active_lexicon_entries() == []
    assert service.list_pending_suggestions() == []
    assert service.list_review_jobs() == []
    assert service.load_review_cursor() is None

    with sqlite3.connect(str(db_path)) as conn:
        index_names = {
            str(row[1])
            for row in conn.execute(
                "PRAGMA index_list(local_lexicon_entries)"
            ).fetchall()
        }
        decision_count = conn.execute(
            "SELECT COUNT(*) FROM review_decisions"
        ).fetchone()[0]
    assert "obsolete_active_term_unique" not in index_names
    assert decision_count == 0


def test_review_storage_fresh_database_creates_current_schema(tmp_path):
    service = ReviewStorageService(_db_path(tmp_path))
    service.initialize()

    with sqlite3.connect(str(service._db_path)) as conn:
        assert ReviewStorageService._review_schema_is_current(conn)


def test_review_storage_resets_stale_review_state_when_local_table_is_missing(tmp_path):
    db_path = _db_path(tmp_path)
    service = ReviewStorageService(db_path)
    service.initialize()
    _seed_review_state(service)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("DROP TABLE local_lexicon_entries")
        conn.commit()

    assert service.list_active_lexicon_entries() == []
    assert service.list_pending_suggestions() == []
    assert service.list_review_jobs() == []
    assert service.load_review_cursor() is None

    with sqlite3.connect(str(db_path)) as conn:
        decision_count = conn.execute(
            "SELECT COUNT(*) FROM review_decisions"
        ).fetchone()[0]
    assert decision_count == 0


def test_review_storage_hard_cut_rolls_back_and_can_retry(tmp_path, monkeypatch):
    db_path = _db_path(tmp_path)
    service = ReviewStorageService(db_path)
    service.initialize()
    _seed_review_state(service)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE UNIQUE INDEX obsolete_active_term_unique
            ON local_lexicon_entries(term)
            WHERE status = 'active'
            """
        )
        conn.commit()

    original_create = ReviewStorageService._create_current_review_tables

    def fail_during_rebuild(conn):
        original_create(conn)
        raise RuntimeError("injected review-state reset failure")

    with monkeypatch.context() as patch:
        patch.setattr(
            ReviewStorageService,
            "_create_current_review_tables",
            staticmethod(fail_during_rebuild),
        )
        with pytest.raises(RuntimeError, match="injected review-state reset failure"):
            service.list_active_lexicon_entries()

    with sqlite3.connect(str(db_path)) as conn:
        entry_count = conn.execute(
            "SELECT COUNT(*) FROM local_lexicon_entries"
        ).fetchone()[0]
        suggestion_count = conn.execute(
            "SELECT COUNT(*) FROM review_suggestions"
        ).fetchone()[0]
        decision_count = conn.execute(
            "SELECT COUNT(*) FROM review_decisions"
        ).fetchone()[0]
        job_count = conn.execute("SELECT COUNT(*) FROM review_jobs").fetchone()[0]
        cursor_count = conn.execute("SELECT COUNT(*) FROM review_cursors").fetchone()[0]
        index_names = {
            str(row[1])
            for row in conn.execute(
                "PRAGMA index_list(local_lexicon_entries)"
            ).fetchall()
        }
    assert entry_count == 1
    assert suggestion_count == 1
    assert decision_count == 1
    assert job_count == 1
    assert cursor_count == 1
    assert "obsolete_active_term_unique" in index_names

    assert service.list_active_lexicon_entries() == []
    assert service.list_pending_suggestions() == []
    assert service.list_review_jobs() == []
    assert service.load_review_cursor() is None


def test_review_storage_service_can_clear_lexicon_entries(tmp_path):
    db_path = _db_path(tmp_path)
    _insert_lexicon_entry(db_path, entry_id="lex-1", term="PyTorch")
    service = ReviewStorageService(db_path)

    service.clear_lexicon_entries()

    assert service.list_active_lexicon_entries() == []


def test_review_storage_service_can_archive_one_active_lexicon_entry(tmp_path):
    db_path = _db_path(tmp_path)
    _insert_lexicon_entry(db_path, entry_id="lex-1", term="PyTorch")
    _insert_lexicon_entry(db_path, entry_id="lex-2", term="TensorFlow")
    service = ReviewStorageService(db_path)

    assert service.archive_lexicon_entry("lex-1") is True
    assert [entry["id"] for entry in service.list_active_lexicon_entries()] == ["lex-2"]
    assert service.archive_lexicon_entry("lex-1") is False
    assert service.archive_lexicon_entry("missing") is False
    assert service.archive_lexicon_entry("") is False


def test_ui_settings_service_can_export_lexicon_entries_to_json(tmp_path):
    db_path = _db_path(tmp_path)
    export_path = tmp_path / "lexicon_export.json"
    _insert_lexicon_entry(
        db_path,
        entry_id="lex-export",
        term="PyTorch",
        old_form="拍套曲",
        evidence_count=2,
        confidence=0.8,
    )
    review_storage = ReviewStorageService(db_path)
    ui_service = UISettingsService(
        config_service=Mock(),
        event_service=Mock(),
        history_service=Mock(),
        review_storage_service=review_storage,
    )

    result = ui_service.export_lexicon_entries(str(export_path))

    assert result["success"] is True
    assert result["path"] == str(export_path)
    assert result["count"] == 1
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert payload["count"] == 1
    assert payload["entries"][0]["term"] == "PyTorch"
