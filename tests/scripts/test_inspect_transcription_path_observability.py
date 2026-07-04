import importlib.util
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4


def _load_module():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "inspect_transcription_path_observability.py"
    )
    scripts_dir = str(module_path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(
        "inspect_transcription_path_observability", module_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _create_history_db_with_transcription_path(
    db_path: Path,
    *,
    rows: list[tuple[str, str, str, float, str, str, str | None]],
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
                transcription_path, transcription_decision_reason,
                transcription_text, final_text
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
                for (
                    row_id,
                    timestamp,
                    provider,
                    duration,
                    streaming_mode,
                    transcription_path,
                    decision_reason,
                ) in rows
            ],
        )
        conn.commit()


def _create_history_db_with_path_only(
    db_path: Path,
    *,
    rows: list[tuple[str, str, str, float, str, str]],
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
                transcription_path, transcription_text, final_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    "sample text",
                    "sample text",
                )
                for (
                    row_id,
                    timestamp,
                    provider,
                    duration,
                    streaming_mode,
                    transcription_path,
                ) in rows
            ],
        )
        conn.commit()


def _write_log(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_observability_reports_no_post_cutoff_runtime_or_db_activity() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    db_path = (base_dir / f"obs_none_{token}.db").resolve()
    logs_dir = (base_dir / f"obs_none_logs_{token}").resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        _create_history_db_with_transcription_path(
            db_path,
            rows=[
                (
                    "r1",
                    "2026-06-09T15:00:00",
                    "groq",
                    20.0,
                    "chunked",
                    "standard",
                    None,
                ),
            ],
        )
        _write_log(logs_dir / "app.log", [])

        result = module.inspect_transcription_path_observability(
            db_path=db_path,
            logs_path=logs_dir,
            timestamp_from="2026-06-09T16:00:00",
        )

        assert (
            result["alignment"]["diagnosis"]["state"]
            == "no_post_cutoff_runtime_or_db_activity"
        )
        assert result["alignment"]["issue_summary"] is None
        summary = module.format_transcription_path_observability_summary(result)
        assert "Transcription Path Observability Summary" in summary
        assert "Diagnosis: no_post_cutoff_runtime_or_db_activity" in summary
        assert "Post-cutoff DB rows: 0" in summary
        assert "Post-cutoff runtime logs: 0" in summary
        assert "Recommended Steps:" in summary
        assert any(
            "inspect_recent_transcription_path_logs.py" in command
            and "--db" not in command
            for command in result["alignment"]["operator_guidance"][
                "follow_up_commands"
            ]
        )
        oneline = module.format_transcription_path_observability_oneline(result)
        assert "state=no_post_cutoff_runtime_or_db_activity" in oneline
        assert "record_hint=none" in oneline
        assert "message=No post-cutoff transcription path logs" in oneline
        card = module.format_transcription_path_observability_card(result)
        assert "## Transcription Path Observability Card" in card
        assert "- **Diagnosis:** `no_post_cutoff_runtime_or_db_activity`" in card
        markdown = module.format_transcription_path_observability_markdown(result)
        assert "# Transcription Path Observability Report" in markdown
        assert "## Diagnosis" in markdown
        assert "## Recommended Steps" in markdown
        assert "## Follow-up Commands" in markdown
    finally:
        if db_path.exists():
            db_path.unlink()
        for path in logs_dir.glob("*"):
            path.unlink()
        logs_dir.rmdir()


def test_observability_reports_runtime_logs_without_db_rows() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    db_path = (base_dir / f"obs_logs_only_{token}.db").resolve()
    logs_dir = (base_dir / f"obs_logs_only_logs_{token}").resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        _create_history_db_with_transcription_path(
            db_path,
            rows=[
                (
                    "r1",
                    "2026-06-09T15:00:00",
                    "groq",
                    20.0,
                    "chunked",
                    "standard",
                    None,
                ),
            ],
        )
        _write_log(
            logs_dir / "app.log",
            [
                (
                    "2026-06-09 16:20:00 | INFO     | audio        | [audio] | "
                    "Audio: Transcription path decision | | "
                    '{"record_id":"rec-1","selected_path":"streaming_chunked",'
                    '"decision_reason":"streaming_stop_result"}'
                ),
            ],
        )

        result = module.inspect_transcription_path_observability(
            db_path=db_path,
            logs_path=logs_dir,
            timestamp_from="2026-06-09T16:00:00",
        )

        assert (
            result["alignment"]["diagnosis"]["state"] == "runtime_logs_without_db_rows"
        )
        assert result["alignment"]["focus_record"]["source"] == "runtime_log_only"
        assert result["alignment"]["focus_record"]["record_id"] == "rec-1"
        assert (
            result["alignment"]["issue_summary"]
            == "record_id=rec-1 runtime log exists without DB row yet: "
            "log_path=streaming_chunked, log_reason=streaming_stop_result"
        )
        summary = module.format_transcription_path_observability_summary(result)
        assert "Diagnosis: runtime_logs_without_db_rows" in summary
        assert "Record id: rec-1" in summary
        assert "Log path: streaming_chunked" in summary
        assert (
            "Issue summary: record_id=rec-1 runtime log exists without DB row yet: "
            "log_path=streaming_chunked, log_reason=streaming_stop_result"
        ) in summary
        oneline = module.format_transcription_path_observability_oneline(result)
        assert "state=runtime_logs_without_db_rows" in oneline
        assert "record_hint=rec-1" in oneline
        card = module.format_transcription_path_observability_card(result)
        assert "- **Focus record:**" in card
        assert "  - source: `runtime_log_only`" in card
    finally:
        if db_path.exists():
            db_path.unlink()
        for path in logs_dir.glob("*"):
            path.unlink()
        logs_dir.rmdir()


def test_observability_reports_aligned_db_and_log_paths() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    db_path = (base_dir / f"obs_aligned_{token}.db").resolve()
    logs_dir = (base_dir / f"obs_aligned_logs_{token}").resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        _create_history_db_with_transcription_path(
            db_path,
            rows=[
                (
                    "rec-1",
                    "2026-06-09T16:20:00",
                    "groq",
                    120.0,
                    "chunked",
                    "cloud_file_long_recording",
                    "long_cloud_recording_prefer_file",
                ),
            ],
        )
        _write_log(
            logs_dir / "app.log",
            [
                (
                    "2026-06-09 16:20:00 | INFO     | audio        | [audio] | "
                    "Audio: Transcription path decision | | "
                    '{"record_id":"rec-1","selected_path":"cloud_file_long_recording",'
                    '"decision_reason":"long_cloud_recording_prefer_file"}'
                ),
            ],
        )

        result = module.inspect_transcription_path_observability(
            db_path=db_path,
            logs_path=logs_dir,
            timestamp_from="2026-06-09T16:00:00",
        )

        assert (
            result["alignment"]["diagnosis"]["state"]
            == "db_log_paths_and_reasons_aligned"
        )
        assert result["alignment"]["matched_record_count"] == 1
        assert result["alignment"]["mismatched_record_count"] == 0
        assert result["alignment"]["decision_reason_matched_record_count"] == 1
        assert result["alignment"]["decision_reason_mismatched_record_count"] == 0
        assert result["alignment"]["focus_record"]["source"] == "shared_aligned"
        assert (
            result["alignment"]["issue_summary"]
            == "record_id=rec-1 aligned: path=cloud_file_long_recording, "
            "decision_reason=long_cloud_recording_prefer_file"
        )
        summary = module.format_transcription_path_observability_summary(result)
        assert "Diagnosis: db_log_paths_and_reasons_aligned" in summary
        assert "Matched records: 1" in summary
        oneline = module.format_transcription_path_observability_oneline(result)
        assert "state=db_log_paths_and_reasons_aligned" in oneline
        assert (
            "issue_summary=record_id=rec-1 aligned: path=cloud_file_long_recording, "
            "decision_reason=long_cloud_recording_prefer_file"
        ) in oneline
        markdown = module.format_transcription_path_observability_markdown(result)
        assert "## Focus Record" in markdown
    finally:
        if db_path.exists():
            db_path.unlink()
        for path in logs_dir.glob("*"):
            path.unlink()
        logs_dir.rmdir()


def test_observability_reports_mismatched_db_and_log_paths() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    db_path = (base_dir / f"obs_mismatch_{token}.db").resolve()
    logs_dir = (base_dir / f"obs_mismatch_logs_{token}").resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        _create_history_db_with_transcription_path(
            db_path,
            rows=[
                (
                    "rec-1",
                    "2026-06-09T16:20:00",
                    "groq",
                    120.0,
                    "chunked",
                    "standard",
                    None,
                ),
            ],
        )
        _write_log(
            logs_dir / "app.log",
            [
                (
                    "2026-06-09 16:20:00 | INFO     | audio        | [audio] | "
                    "Audio: Transcription path decision | | "
                    '{"record_id":"rec-1","selected_path":"cloud_file_long_recording",'
                    '"decision_reason":"long_cloud_recording_prefer_file"}'
                ),
            ],
        )

        result = module.inspect_transcription_path_observability(
            db_path=db_path,
            logs_path=logs_dir,
            timestamp_from="2026-06-09T16:00:00",
        )

        assert result["alignment"]["diagnosis"]["state"] == "db_log_path_mismatch"
        assert result["alignment"]["matched_record_count"] == 0
        assert result["alignment"]["mismatched_record_count"] == 1
        assert result["alignment"]["focus_record"]["source"] == "shared_path_mismatch"
        assert (
            result["alignment"]["issue_summary"]
            == "record_id=rec-1 path mismatch: db=standard vs log=cloud_file_long_recording"
        )
        card = module.format_transcription_path_observability_card(result)
        assert (
            "- **Issue summary:** record_id=rec-1 path mismatch: db=standard vs log=cloud_file_long_recording"
            in card
        )
    finally:
        if db_path.exists():
            db_path.unlink()
        for path in logs_dir.glob("*"):
            path.unlink()
        logs_dir.rmdir()


def test_observability_reports_decision_reason_mismatch_with_aligned_paths() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    db_path = (base_dir / f"obs_reason_mismatch_{token}.db").resolve()
    logs_dir = (base_dir / f"obs_reason_mismatch_logs_{token}").resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        _create_history_db_with_transcription_path(
            db_path,
            rows=[
                (
                    "rec-1",
                    "2026-06-09T16:20:00",
                    "groq",
                    120.0,
                    "chunked",
                    "cloud_file_long_recording",
                    "streaming_stop_result",
                ),
            ],
        )
        _write_log(
            logs_dir / "app.log",
            [
                (
                    "2026-06-09 16:20:00 | INFO     | audio        | [audio] | "
                    "Audio: Transcription path decision | | "
                    '{"record_id":"rec-1","selected_path":"cloud_file_long_recording",'
                    '"decision_reason":"long_cloud_recording_prefer_file"}'
                ),
            ],
        )

        result = module.inspect_transcription_path_observability(
            db_path=db_path,
            logs_path=logs_dir,
            timestamp_from="2026-06-09T16:00:00",
        )

        assert (
            result["alignment"]["diagnosis"]["state"]
            == "db_log_decision_reason_mismatch"
        )
        assert result["alignment"]["matched_record_count"] == 1
        assert result["alignment"]["mismatched_record_count"] == 0
        assert result["alignment"]["decision_reason_matched_record_count"] == 0
        assert result["alignment"]["decision_reason_mismatched_record_count"] == 1
        assert result["alignment"]["focus_record"]["source"] == "shared_reason_mismatch"
        assert (
            result["alignment"]["issue_summary"]
            == "record_id=rec-1 decision reason mismatch: "
            "db=streaming_stop_result vs log=long_cloud_recording_prefer_file"
        )
        assert (
            result["alignment"]["decision_reason_mismatched_records"][0][
                "db_transcription_decision_reason"
            ]
            == "streaming_stop_result"
        )
        summary = module.format_transcription_path_observability_summary(result)
        assert "Decision reason mismatches: 1" in summary
        markdown = module.format_transcription_path_observability_markdown(result)
        assert (
            "- **Issue summary:** record_id=rec-1 decision reason mismatch: "
            "db=streaming_stop_result vs log=long_cloud_recording_prefer_file"
        ) in markdown
    finally:
        if db_path.exists():
            db_path.unlink()
        for path in logs_dir.glob("*"):
            path.unlink()
        logs_dir.rmdir()


def test_observability_reports_paths_aligned_but_reason_schema_missing() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    db_path = (base_dir / f"obs_reason_schema_missing_{token}.db").resolve()
    logs_dir = (base_dir / f"obs_reason_schema_missing_logs_{token}").resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        _create_history_db_with_path_only(
            db_path,
            rows=[
                (
                    "rec-1",
                    "2026-06-09T16:20:00",
                    "groq",
                    120.0,
                    "chunked",
                    "cloud_file_long_recording",
                ),
            ],
        )
        _write_log(
            logs_dir / "app.log",
            [
                (
                    "2026-06-09 16:20:00 | INFO     | audio        | [audio] | "
                    "Audio: Transcription path decision | | "
                    '{"record_id":"rec-1","selected_path":"cloud_file_long_recording",'
                    '"decision_reason":"long_cloud_recording_prefer_file"}'
                ),
            ],
        )

        result = module.inspect_transcription_path_observability(
            db_path=db_path,
            logs_path=logs_dir,
            timestamp_from="2026-06-09T16:00:00",
        )

        assert (
            result["db"]["schema"]["has_transcription_decision_reason_column"] is False
        )
        assert (
            result["alignment"]["diagnosis"]["state"]
            == "db_log_paths_aligned_reason_schema_missing"
        )
        assert result["alignment"]["matched_record_count"] == 1
        assert result["alignment"]["decision_reason_mismatched_record_count"] == 0
        assert result["alignment"]["focus_record"]["source"] == "shared_aligned"
        assert (
            result["alignment"]["issue_summary"]
            == "record_id=rec-1 paths aligned at cloud_file_long_recording, but reason verification "
            "is blocked because the DB schema lacks transcription_decision_reason"
        )
        oneline = module.format_transcription_path_observability_oneline(result)
        assert "db_reason_column=no" in oneline
        assert "record_hint=rec-1" in oneline
    finally:
        if db_path.exists():
            db_path.unlink()
        for path in logs_dir.glob("*"):
            path.unlink()
        logs_dir.rmdir()
