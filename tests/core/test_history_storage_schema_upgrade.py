import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from sonicinput.core.interfaces import HistoryRecord
from sonicinput.core.services.storage.history_storage_service import (
    HistoryStorageService,
)


class _DummyConfigService:
    def get_setting(self, _key, default=None):
        return default


def _create_legacy_schema(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE history_records (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                audio_file_path TEXT NOT NULL,
                duration REAL NOT NULL,
                transcription_text TEXT NOT NULL,
                transcription_provider TEXT NOT NULL,
                transcription_status TEXT NOT NULL,
                transcription_error TEXT,
                ai_optimized_text TEXT,
                ai_provider TEXT,
                ai_status TEXT NOT NULL,
                ai_error TEXT,
                final_text TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            INSERT INTO history_records (
                id, timestamp, audio_file_path, duration,
                transcription_text, transcription_provider, transcription_status,
                transcription_error, ai_optimized_text, ai_provider, ai_status, ai_error,
                final_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-1",
                "2026-01-01T00:00:00",
                "C:/legacy.wav",
                1.0,
                "legacy text",
                "local",
                "success",
                None,
                None,
                None,
                "pending",
                None,
                "legacy text",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_init_database_adds_diagnostic_columns_for_legacy_db() -> None:
    temp_dir = Path(".tmp_pytest")
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"history_schema_upgrade_{uuid.uuid4().hex}.db"
    _create_legacy_schema(db_path)

    service = HistoryStorageService(_DummyConfigService())
    service._db_path = db_path
    service._init_database()

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(history_records)")
        columns = {row[1] for row in cursor.fetchall()}
    finally:
        conn.close()

    assert "streaming_mode" in columns
    assert "transcription_duration" in columns
    assert "used_fallback" in columns
    assert "fallback_type" in columns
    assert "fallback_reason" in columns
    assert "diagnostics_collected" in columns
    assert "reprocess_parent_id" in columns
    assert service._fts_enabled is True

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT diagnostics_collected, fallback_type, fallback_reason "
            "FROM history_records WHERE id = 'legacy-1'"
        )
        row = cursor.fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row[0] == 0
    assert row[1] == "none"
    assert row[2] is None

    if db_path.exists():
        db_path.unlink()


def test_save_and_load_record_with_extended_diagnostics() -> None:
    temp_dir = Path(".tmp_pytest")
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"history_save_load_{uuid.uuid4().hex}.db"

    service = HistoryStorageService(_DummyConfigService())
    service._db_path = db_path
    service._init_database()

    record = HistoryRecord(
        id="rec-extended-1",
        timestamp=datetime(2026, 3, 8, 12, 0, 0),
        audio_file_path="C:/audio.wav",
        duration=2.5,
        transcription_text="hello",
        transcription_provider="local",
        transcription_status="success",
        streaming_mode="chunked",
        transcription_duration=0.25,
        used_fallback=True,
        fallback_type="local_sync",
        fallback_reason="empty_chunked_result",
        diagnostics_collected=True,
        reprocess_parent_id="orig-1",
        transcription_error=None,
        ai_optimized_text=None,
        ai_provider=None,
        ai_status="pending",
        ai_error=None,
        final_text="hello",
    )

    assert service.save_record(record) is True

    loaded = service.get_record_by_id("rec-extended-1")
    assert loaded is not None
    assert loaded.fallback_type == "local_sync"
    assert loaded.fallback_reason == "empty_chunked_result"
    assert loaded.diagnostics_collected is True
    assert loaded.reprocess_parent_id == "orig-1"

    service._do_stop()
    if db_path.exists():
        db_path.unlink()


def test_fts_index_syncs_with_save_and_update() -> None:
    temp_dir = Path(".tmp_pytest")
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"history_fts_sync_{uuid.uuid4().hex}.db"

    service = HistoryStorageService(_DummyConfigService())
    service._db_path = db_path
    service._init_database()

    record = HistoryRecord(
        id="rec-fts-1",
        timestamp=datetime(2026, 3, 8, 12, 0, 0),
        audio_file_path="C:/audio.wav",
        duration=1.5,
        transcription_text="hello world",
        transcription_provider="local",
        transcription_status="success",
        streaming_mode="chunked",
        transcription_duration=0.2,
        used_fallback=False,
        fallback_type="none",
        fallback_reason=None,
        diagnostics_collected=True,
        reprocess_parent_id=None,
        transcription_error=None,
        ai_optimized_text="optimized text",
        ai_provider="groq",
        ai_status="success",
        ai_error=None,
        final_text="hello world",
    )

    assert service.save_record(record) is True

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT record_id FROM history_records_fts WHERE history_records_fts MATCH ?",
            ('"hello"',),
        )
        row = cursor.fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row[0] == "rec-fts-1"

    record.transcription_text = "updated transcription"
    record.final_text = "updated transcription"
    assert service.update_record(record) is True

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT record_id FROM history_records_fts WHERE history_records_fts MATCH ?",
            ('"updated"',),
        )
        updated_row = cursor.fetchone()
        cursor.execute(
            "SELECT record_id FROM history_records_fts WHERE history_records_fts MATCH ?",
            ('"hello"',),
        )
        old_row = cursor.fetchone()
    finally:
        conn.close()

    assert updated_row is not None
    assert updated_row[0] == "rec-fts-1"
    assert old_row is None

    service._do_stop()
    if db_path.exists():
        db_path.unlink()


def test_delete_record_keeps_shared_audio_file_until_last_reference() -> None:
    temp_dir = Path(".tmp_pytest")
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"history_delete_shared_{uuid.uuid4().hex}.db"
    audio_path = temp_dir / f"shared_audio_{uuid.uuid4().hex}.wav"
    audio_path.write_bytes(b"wav")

    service = HistoryStorageService(_DummyConfigService())
    service._db_path = db_path
    service._init_database()

    first_record = HistoryRecord(
        id="rec-shared-1",
        timestamp=datetime(2026, 3, 8, 12, 0, 0),
        audio_file_path=str(audio_path),
        duration=1.0,
        transcription_text="one",
        transcription_provider="local",
        transcription_status="success",
        streaming_mode="chunked",
        transcription_duration=0.1,
        used_fallback=False,
        fallback_type="none",
        fallback_reason=None,
        diagnostics_collected=True,
        reprocess_parent_id=None,
        transcription_error=None,
        ai_optimized_text=None,
        ai_provider=None,
        ai_status="skipped",
        ai_error=None,
        final_text="one",
    )
    second_record = HistoryRecord(
        id="rec-shared-2",
        timestamp=datetime(2026, 3, 8, 12, 1, 0),
        audio_file_path=str(audio_path),
        duration=1.0,
        transcription_text="two",
        transcription_provider="local",
        transcription_status="success",
        streaming_mode="chunked",
        transcription_duration=0.1,
        used_fallback=False,
        fallback_type="none",
        fallback_reason=None,
        diagnostics_collected=True,
        reprocess_parent_id=None,
        transcription_error=None,
        ai_optimized_text=None,
        ai_provider=None,
        ai_status="skipped",
        ai_error=None,
        final_text="two",
    )

    assert service.save_record(first_record) is True
    assert service.save_record(second_record) is True

    assert service.delete_record("rec-shared-1") is True
    assert audio_path.exists() is True
    assert service.get_record_by_id("rec-shared-2") is not None

    assert service.delete_record("rec-shared-2") is True
    assert audio_path.exists() is False

    service._do_stop()
    if db_path.exists():
        db_path.unlink()
