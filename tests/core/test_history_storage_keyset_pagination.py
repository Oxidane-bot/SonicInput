import uuid
from datetime import datetime
from pathlib import Path

from sonicinput.core.interfaces import HistoryRecord
from sonicinput.core.services.storage.history_storage_service import HistoryStorageService


class _DummyConfigService:
    def get_setting(self, _key, default=None):
        return default


def _make_record(record_id: str, ts: datetime, text: str) -> HistoryRecord:
    return HistoryRecord(
        id=record_id,
        timestamp=ts,
        audio_file_path=f"C:/{record_id}.wav",
        duration=1.0,
        transcription_text=text,
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
        ai_optimized_text=text,
        ai_provider="groq",
        ai_status="success",
        ai_error=None,
        final_text=text,
    )


def test_get_records_keyset_pagination_is_stable_for_same_timestamp() -> None:
    temp_dir = Path(".tmp_pytest")
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"history_keyset_{uuid.uuid4().hex}.db"

    service = HistoryStorageService(_DummyConfigService())
    service._db_path = db_path
    service._init_database()

    records = [
        _make_record("a-1", datetime(2026, 3, 8, 10, 0, 0), "hello a"),
        _make_record("b-1", datetime(2026, 3, 8, 10, 0, 0), "hello b"),
        _make_record("c-1", datetime(2026, 3, 8, 9, 59, 0), "hello c"),
        _make_record("d-1", datetime(2026, 3, 8, 9, 58, 0), "hello d"),
        _make_record("e-1", datetime(2026, 3, 8, 9, 57, 0), "hello e"),
    ]
    assert service.save_records_batch(records) == len(records)

    page1 = service.get_records_keyset(limit=2)
    assert [r.id for r in page1] == ["b-1", "a-1"]

    page2 = service.get_records_keyset(
        limit=2,
        cursor_timestamp=page1[-1].timestamp,
        cursor_id=page1[-1].id,
    )
    assert [r.id for r in page2] == ["c-1", "d-1"]

    page3 = service.get_records_keyset(
        limit=2,
        cursor_timestamp=page2[-1].timestamp,
        cursor_id=page2[-1].id,
    )
    assert [r.id for r in page3] == ["e-1"]

    page4 = service.get_records_keyset(
        limit=2,
        cursor_timestamp=page3[-1].timestamp,
        cursor_id=page3[-1].id,
    )
    assert page4 == []

    service._do_stop()
    if db_path.exists():
        db_path.unlink()


def test_search_records_keyset_pagination_works_with_query() -> None:
    temp_dir = Path(".tmp_pytest")
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"history_search_keyset_{uuid.uuid4().hex}.db"

    service = HistoryStorageService(_DummyConfigService())
    service._db_path = db_path
    service._init_database()

    records = [
        _make_record("k-1", datetime(2026, 3, 8, 12, 0, 0), "alpha hello"),
        _make_record("k-2", datetime(2026, 3, 8, 11, 0, 0), "beta hello"),
        _make_record("k-3", datetime(2026, 3, 8, 10, 0, 0), "gamma world"),
        _make_record("k-4", datetime(2026, 3, 8, 9, 0, 0), "delta hello"),
    ]
    assert service.save_records_batch(records) == len(records)

    page1 = service.search_records_keyset(query="hello", limit=2)
    assert [r.id for r in page1] == ["k-1", "k-2"]

    page2 = service.search_records_keyset(
        query="hello",
        limit=2,
        cursor_timestamp=page1[-1].timestamp,
        cursor_id=page1[-1].id,
    )
    assert [r.id for r in page2] == ["k-4"]

    service._do_stop()
    if db_path.exists():
        db_path.unlink()


def test_get_records_keyset_supports_ascending_order() -> None:
    temp_dir = Path(".tmp_pytest")
    temp_dir.mkdir(exist_ok=True)
    db_path = temp_dir / f"history_keyset_asc_{uuid.uuid4().hex}.db"

    service = HistoryStorageService(_DummyConfigService())
    service._db_path = db_path
    service._init_database()

    records = [
        _make_record("asc-1", datetime(2026, 3, 8, 8, 0, 0), "one"),
        _make_record("asc-2", datetime(2026, 3, 8, 9, 0, 0), "two"),
        _make_record("asc-3", datetime(2026, 3, 8, 10, 0, 0), "three"),
    ]
    assert service.save_records_batch(records) == len(records)

    page1 = service.get_records_keyset(limit=2, order="ASC")
    assert [r.id for r in page1] == ["asc-1", "asc-2"]

    page2 = service.get_records_keyset(
        limit=2,
        cursor_timestamp=page1[-1].timestamp,
        cursor_id=page1[-1].id,
        order="ASC",
    )
    assert [r.id for r in page2] == ["asc-3"]

    service._do_stop()
    if db_path.exists():
        db_path.unlink()
