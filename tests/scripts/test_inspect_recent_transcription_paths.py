import importlib.util
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4


def _load_module():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "inspect_recent_transcription_paths.py"
    )
    spec = importlib.util.spec_from_file_location(
        "inspect_recent_transcription_paths", module_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _create_legacy_history_db(db_path: Path) -> None:
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE history_records (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                audio_file_path TEXT NOT NULL,
                duration REAL NOT NULL,
                transcription_provider TEXT NOT NULL,
                transcription_status TEXT NOT NULL,
                streaming_mode TEXT NOT NULL,
                transcription_text TEXT,
                final_text TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO history_records (
                id, timestamp, audio_file_path, duration,
                transcription_provider, transcription_status, streaming_mode,
                transcription_text, final_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-1",
                "2026-06-09T09:00:00",
                "quality_audit/legacy.wav",
                100.0,
                "openai",
                "success",
                "chunked",
                "legacy text",
                "legacy text",
            ),
        )
        conn.commit()


def _create_history_db_with_transcription_path(
    db_path: Path,
    *,
    rows: list[tuple[str, str, str, float, str, str, str | None, str]],
) -> None:
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE history_records (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                audio_file_path TEXT NOT NULL,
                duration REAL NOT NULL,
                transcription_provider TEXT NOT NULL,
                transcription_status TEXT NOT NULL,
                streaming_mode TEXT NOT NULL,
                transcription_path TEXT NOT NULL,
                transcription_decision_reason TEXT,
                transcription_text TEXT,
                final_text TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO history_records (
                id, timestamp, audio_file_path, duration,
                transcription_provider, transcription_status, streaming_mode,
                transcription_path, transcription_decision_reason, transcription_text, final_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row_id,
                    timestamp,
                    "quality_audit/sample.wav",
                    duration,
                    provider,
                    "success",
                    streaming_mode,
                    transcription_path,
                    decision_reason,
                    "sample text",
                    "sample text",
                )
                for row_id, timestamp, provider, duration, streaming_mode, transcription_path, decision_reason, _tag in rows
            ],
        )
        conn.commit()


def test_inspect_recent_transcription_paths_reports_schema_missing() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    db_path = (base_dir / f"inspect_recent_paths_legacy_{uuid4().hex}.db").resolve()
    try:
        _create_legacy_history_db(db_path)

        result = module.inspect_recent_transcription_paths(
            db_path,
            timestamp_from="2026-06-09T00:00:00",
        )

        assert result["schema"]["has_transcription_path_column"] is False
        assert result["source_record_count"] == 1
        assert result["selected_record_count"] == 1
        assert result["diagnosis"]["state"] == "schema_missing"
        assert result["records"][0]["transcription_path"] == "standard"
        assert result["records"][0]["long_recording_cloud_candidate"] is True
    finally:
        if db_path.exists():
            db_path.unlink()


def test_inspect_recent_transcription_paths_reports_no_observable_post_timestamp_rows() -> (
    None
):
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    db_path = (base_dir / f"inspect_recent_paths_standard_{uuid4().hex}.db").resolve()
    try:
        _create_history_db_with_transcription_path(
            db_path,
            rows=[
                (
                    "r1",
                    "2026-06-09T12:10:00",
                    "groq",
                    130.0,
                    "chunked",
                    "standard",
                    None,
                    "candidate",
                ),
                (
                    "r2",
                    "2026-06-09T12:05:00",
                    "groq",
                    30.0,
                    "chunked",
                    "standard",
                    None,
                    "short",
                ),
            ],
        )

        result = module.inspect_recent_transcription_paths(
            db_path,
            timestamp_from="2026-06-09T12:00:00",
            long_recording_cloud_candidates_only=True,
        )

        assert result["schema"]["has_transcription_path_column"] is True
        assert result["source_record_count"] == 2
        assert result["selected_record_count"] == 1
        assert result["observable_record_count"] == 0
        assert result["long_recording_cloud_candidate_record_count"] == 1
        assert result["counts_by_transcription_path"] == {"standard": 1}
        assert result["records"][0]["transcription_decision_reason"] is None
        assert result["diagnosis"]["state"] == "no_observable_writes_after_timestamp"
    finally:
        if db_path.exists():
            db_path.unlink()


def test_inspect_recent_transcription_paths_reports_observable_runtime_writes() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    db_path = (base_dir / f"inspect_recent_paths_observable_{uuid4().hex}.db").resolve()
    try:
        _create_history_db_with_transcription_path(
            db_path,
            rows=[
                (
                    "r1",
                    "2026-06-09T12:15:00",
                    "groq",
                    140.0,
                    "chunked",
                    "cloud_file_long_recording",
                    "long_cloud_recording_prefer_file",
                    "candidate",
                ),
                (
                    "r2",
                    "2026-06-09T12:12:00",
                    "groq",
                    20.0,
                    "realtime",
                    "streaming_realtime",
                    "streaming_stop_result",
                    "realtime",
                ),
            ],
        )

        result = module.inspect_recent_transcription_paths(
            db_path,
            timestamp_from="2026-06-09T12:00:00",
        )

        assert result["selected_record_count"] == 2
        assert result["observable_record_count"] == 2
        assert result["counts_by_transcription_path"] == {
            "cloud_file_long_recording": 1,
            "streaming_realtime": 1,
        }
        assert result["diagnosis"]["state"] == "observable_writes_present"
        assert result["records"][0]["transcription_path_observable"] is True
        assert (
            result["records"][0]["transcription_decision_reason"]
            == "long_cloud_recording_prefer_file"
        )
    finally:
        if db_path.exists():
            db_path.unlink()


def test_inspect_recent_transcription_paths_reports_empty_post_timestamp_window() -> (
    None
):
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    db_path = (base_dir / f"inspect_recent_paths_empty_{uuid4().hex}.db").resolve()
    try:
        _create_history_db_with_transcription_path(
            db_path,
            rows=[
                (
                    "r1",
                    "2026-06-09T11:00:00",
                    "groq",
                    140.0,
                    "chunked",
                    "cloud_file_long_recording",
                    "long_cloud_recording_prefer_file",
                    "candidate",
                ),
            ],
        )

        result = module.inspect_recent_transcription_paths(
            db_path,
            timestamp_from="2026-06-09T12:00:00",
        )

        assert result["source_record_count"] == 0
        assert result["selected_record_count"] == 0
        assert result["diagnosis"]["state"] == "no_records_after_timestamp"
    finally:
        if db_path.exists():
            db_path.unlink()
