import json
import sqlite3
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

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
                "legacy-suggestion",
                evidence_count,
                confidence,
                status,
                "2026-06-09T02:00:00",
                updated_at,
            ),
        )
        conn.commit()


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


def test_review_storage_service_can_clear_lexicon_entries(tmp_path):
    db_path = _db_path(tmp_path)
    _insert_lexicon_entry(db_path, entry_id="lex-1", term="PyTorch")
    service = ReviewStorageService(db_path)

    service.clear_lexicon_entries()

    assert service.list_active_lexicon_entries() == []


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
