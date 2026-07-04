import importlib.util
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4


def _load_schema_module():
    module_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "inspect_history_schema.py"
    )
    spec = importlib.util.spec_from_file_location("inspect_history_schema", module_path)
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
        conn.execute(
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


def _write_log(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_inspect_history_schema_reports_legacy_state_without_upgrading() -> None:
    module = _load_schema_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    db_path = (base_dir / f"inspect_history_schema_{uuid4().hex}.db").resolve()
    try:
        _create_legacy_history_db(db_path)

        result = module.inspect_or_upgrade_history_schema(db_path, upgrade=False)

        assert result["upgrade_requested"] is False
        assert result["schema_changed"] is False
        assert result["added_columns"] == []
        assert result["before"]["has_audio_file_path_column"] is True
        assert result["before"]["has_transcription_path_column"] is False
        assert result["before"]["has_transcription_decision_reason_column"] is False
        assert result["after"]["has_transcription_path_column"] is False
        assert result["after"]["has_transcription_decision_reason_column"] is False
    finally:
        if db_path.exists():
            db_path.unlink()


def test_inspect_history_schema_can_upgrade_legacy_db() -> None:
    module = _load_schema_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    db_path = (base_dir / f"inspect_history_schema_upgrade_{uuid4().hex}.db").resolve()
    try:
        _create_legacy_history_db(db_path)

        result = module.inspect_or_upgrade_history_schema(db_path, upgrade=True)

        assert result["upgrade_requested"] is True
        assert result["schema_changed"] is True
        assert "transcription_path" in result["added_columns"]
        assert "transcription_decision_reason" in result["added_columns"]
        assert result["before"]["has_transcription_path_column"] is False
        assert result["after"]["has_transcription_path_column"] is True
        assert result["after"]["has_transcription_decision_reason_column"] is True
        assert result["after"]["history_records_exists"] is True
    finally:
        if db_path.exists():
            db_path.unlink()


def test_inspect_history_schema_reports_runtime_schema_events() -> None:
    module = _load_schema_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    db_path = (base_dir / f"inspect_history_schema_logs_{token}.db").resolve()
    logs_dir = (base_dir / f"inspect_history_schema_logs_dir_{token}").resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        _create_legacy_history_db(db_path)
        _write_log(
            logs_dir / "app.log",
            [
                (
                    "2026-06-10 08:59:59 | INFO     | audio        | [audio] | "
                    "Audio: History schema expectations declared | | "
                    '{"required_columns":["streaming_mode","transcription_path",'
                    '"transcription_decision_reason"],'
                    '"required_column_count":3,'
                    '"history_schema_expectation_version":2,'
                    '"history_schema_signature":"streaming_mode|transcription_decision_reason|transcription_path",'
                    '"expects_transcription_path":true,'
                    '"expects_transcription_decision_reason":true}'
                ),
                (
                    "2026-06-10 09:00:00 | INFO     | audio        | [audio] | "
                    "Audio: Attempting to start HistoryStorageService | | "
                    '{"component":"di_container","service":"HistoryStorageService"}'
                ),
                (
                    "2026-06-10 09:00:01 | INFO     | audio        | [audio] | "
                    "Audio: History database schema upgraded | | "
                    '{"added_column":"transcription_path"}'
                ),
                (
                    "2026-06-10 09:00:02 | INFO     | audio        | [audio] | "
                    "Audio: History database schema upgraded | | "
                    '{"added_column":"transcription_decision_reason"}'
                ),
                (
                    "2026-06-10 09:00:03 | INFO     | audio        | [audio] | "
                    "Audio: History database initialized | | "
                    '{"wal_mode":true}'
                ),
                (
                    "2026-06-10 09:00:04 | INFO     | audio        | [audio] | "
                    "Audio: HistoryStorageService started | | "
                    '{"db_path":"C:/Users/Test/AppData/Roaming/SonicInput/history/history.db"}'
                ),
            ],
        )

        result = module.inspect_or_upgrade_history_schema(
            db_path,
            upgrade=False,
            logs_path=logs_dir,
        )

        runtime_logs = result["runtime_logs"]
        assert runtime_logs is not None
        assert runtime_logs["diagnosis"]["state"] == "schema_runtime_events_found"
        assert runtime_logs["selected_event_count"] == 6
        assert runtime_logs["has_transcription_path_upgrade_event"] is True
        assert runtime_logs["has_transcription_decision_reason_upgrade_event"] is True
        assert runtime_logs["has_transcription_path_expectation_event"] is True
        assert (
            runtime_logs["has_transcription_decision_reason_expectation_event"] is True
        )
        assert runtime_logs["added_columns_seen"] == [
            "transcription_decision_reason",
            "transcription_path",
        ]
        assert runtime_logs["required_columns_seen"] == [
            "streaming_mode",
            "transcription_decision_reason",
            "transcription_path",
        ]
        assert runtime_logs["expectation_versions_seen"] == [2]
        assert runtime_logs["schema_signatures_seen"] == [
            "streaming_mode|transcription_decision_reason|transcription_path"
        ]
        assert (
            runtime_logs["latest_schema_expectations_event"]["context"][
                "expects_transcription_decision_reason"
            ]
            is True
        )
        assert (
            runtime_logs["latest_schema_upgrade_event"]["context"]["added_column"]
            == "transcription_decision_reason"
        )
        assert (
            runtime_logs["latest_database_initialized_event"]["context"]["wal_mode"]
            is True
        )
    finally:
        if db_path.exists():
            db_path.unlink()
        for path in logs_dir.glob("*"):
            path.unlink()
        logs_dir.rmdir()
