import importlib.util
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4


def _load_module():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "inspect_transcription_record_timeline.py"
    )
    scripts_dir = str(module_path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(
        "inspect_transcription_record_timeline", module_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _create_history_db(
    db_path: Path, *, row: tuple[str, str, str, float, str, str, str | None]
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
                transcription_duration REAL,
                used_fallback INTEGER NOT NULL DEFAULT 0,
                fallback_type TEXT NOT NULL DEFAULT 'none',
                fallback_reason TEXT,
                diagnostics_collected INTEGER NOT NULL DEFAULT 1,
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
                transcription_path, transcription_decision_reason, transcription_duration, used_fallback,
                fallback_type, fallback_reason, diagnostics_collected,
                transcription_text, final_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row[0],
                row[1],
                "quality_audit/sample.wav",
                row[3],
                row[2],
                "success",
                row[4],
                row[5],
                row[6],
                0.25,
                0,
                "none",
                None,
                1,
                "sample text",
                "sample text",
            ),
        )
        conn.commit()


def _write_log(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_timeline_reports_aligned_db_and_runtime_path() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    db_path = (base_dir / f"timeline_aligned_{token}.db").resolve()
    logs_dir = (base_dir / f"timeline_aligned_logs_{token}").resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        _create_history_db(
            db_path,
            row=(
                "rec-1",
                "2026-06-10T10:00:03",
                "groq",
                98.6,
                "chunked",
                "streaming_chunked",
                "streaming_stop_result",
            ),
        )
        _write_log(
            logs_dir / "app.log",
            [
                (
                    "2026-06-10 10:00:00 | INFO     | audio        | [audio] | "
                    "Audio: Transcription request received | | "
                    '{"record_id":"rec-1","audio_file_path":"sample.wav","audio_duration":98.6}'
                ),
                (
                    "2026-06-10 10:00:02 | INFO     | audio        | [audio] | "
                    "Audio: Transcription path decision | | "
                    '{"record_id":"rec-1","selected_path":"streaming_chunked",'
                    '"decision_reason":"streaming_stop_result","streaming_mode":"chunked"}'
                ),
                (
                    "2026-06-10 10:00:03 | INFO     | audio        | [audio] | "
                    "Audio: Transcription record saved | | "
                    '{"record_id":"rec-1","status":"success","transcription_path":"streaming_chunked"}'
                ),
                (
                    "2026-06-10 10:00:03 | INFO     | audio        | [audio] | "
                    "Audio: History record saved | | "
                    '{"record_id":"rec-1","thread_id":1234}'
                ),
            ],
        )

        result = module.inspect_transcription_record_timeline(
            db_path=db_path,
            logs_path=logs_dir,
            record_id="rec-1",
        )

        assert result["history_record_found"] is True
        assert result["diagnosis"]["state"] == "db_log_path_aligned"
        assert result["comparison"]["paths_match"] is True
        assert result["comparison"]["decision_reasons_match"] is True
        assert (
            result["issue_summary"]
            == "record_id=rec-1 aligned: path=streaming_chunked, "
            "decision_reason=streaming_stop_result"
        )
        assert result["logs"]["counts_by_event"]["Transcription path decision"] == 1
        assert (
            result["logs"]["latest_path_event"]["selected_path"] == "streaming_chunked"
        )
        assert result["event_flow"]["event_count"] == 4
        assert result["event_flow"]["path_event_count"] == 1
        assert result["event_flow"]["fallback_event_count"] == 0
        assert result["event_flow"]["observed_selected_paths"] == ["streaming_chunked"]
        assert result["event_flow"]["observed_decision_reasons"] == [
            "streaming_stop_result"
        ]
        assert (
            result["event_flow"]["latest_terminal_event"]["event"]
            == "History record saved"
        )

        oneline = module.format_transcription_record_timeline_oneline(result)
        assert "record_id=rec-1" in oneline
        assert "state=db_log_path_aligned" in oneline
        assert "history_record_found=yes" in oneline
        assert "db_path=streaming_chunked" in oneline
        assert "log_path=streaming_chunked" in oneline
        assert "paths_match=True" in oneline
        assert "decision_reasons_match=True" in oneline
        assert (
            "latest_terminal_event=History record saved@2026-06-10 10:00:03" in oneline
        )
        assert (
            "issue_summary=record_id=rec-1 aligned: "
            "path=streaming_chunked, "
            "decision_reason=streaming_stop_result"
        ) in oneline

        summary = module.format_transcription_record_timeline_summary(result)
        assert "Transcription Record Timeline Summary" in summary
        assert "Diagnosis: db_log_path_aligned" in summary
        assert (
            "Issue summary: record_id=rec-1 aligned: path=streaming_chunked, decision_reason=streaming_stop_result"
            in summary
        )
        assert "DB vs Runtime Comparison:" in summary
        assert "Observed paths: streaming_chunked" in summary
        assert (
            "Events in order: Transcription request received -> Transcription path decision -> Transcription record saved -> History record saved"
            in summary
        )

        card = module.format_transcription_record_timeline_card(result)
        assert "## Transcription Record Timeline Card" in card
        assert "- **Record id:** `rec-1`" in card
        assert "- **Diagnosis:** `db_log_path_aligned`" in card
        assert "  - paths_match: `True`" in card
        assert "- **Observed decision reasons:** `streaming_stop_result`" in card

        markdown = module.format_transcription_record_timeline_markdown(result)
        assert "# Transcription Record Timeline Report" in markdown
        assert "## Diagnosis" in markdown
        assert "## Event Flow" in markdown
        assert "## DB Record" in markdown
        assert "## DB vs Runtime Comparison" in markdown
        assert "## Related Runtime Log Events" in markdown
        assert (
            "- **Issue summary:** record_id=rec-1 aligned: path=streaming_chunked, decision_reason=streaming_stop_result"
            in markdown
        )
    finally:
        if db_path.exists():
            db_path.unlink()
        for path in logs_dir.glob("*"):
            path.unlink()
        logs_dir.rmdir()


def test_timeline_reports_runtime_logs_without_db_record() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    db_path = (base_dir / f"timeline_logs_only_{token}.db").resolve()
    logs_dir = (base_dir / f"timeline_logs_only_logs_{token}").resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        _create_history_db(
            db_path,
            row=(
                "other-rec",
                "2026-06-10T10:00:03",
                "groq",
                98.6,
                "chunked",
                "streaming_chunked",
                "streaming_stop_result",
            ),
        )
        _write_log(
            logs_dir / "app.log",
            [
                (
                    "2026-06-10 10:00:02 | INFO     | audio        | [audio] | "
                    "Audio: Transcription path decision | | "
                    '{"record_id":"rec-1","selected_path":"cloud_file_long_recording",'
                    '"decision_reason":"long_cloud_recording_prefer_file"}'
                ),
            ],
        )

        result = module.inspect_transcription_record_timeline(
            db_path=db_path,
            logs_path=logs_dir,
            record_id="rec-1",
        )

        assert result["history_record_found"] is False
        assert result["diagnosis"]["state"] == "runtime_logs_without_db_record"
        assert result["logs"]["selected_record_count"] == 1
        assert (
            result["issue_summary"]
            == "record_id=rec-1 runtime log exists without DB row: "
            "log_path=cloud_file_long_recording, "
            "log_reason=long_cloud_recording_prefer_file"
        )
        assert result["event_flow"]["path_event_count"] == 1
        assert result["event_flow"]["observed_selected_paths"] == [
            "cloud_file_long_recording"
        ]
        summary = module.format_transcription_record_timeline_summary(result)
        assert "Diagnosis: runtime_logs_without_db_record" in summary
        assert (
            "Issue summary: record_id=rec-1 runtime log exists without DB row: "
            "log_path=cloud_file_long_recording, "
            "log_reason=long_cloud_recording_prefer_file"
        ) in summary
        markdown = module.format_transcription_record_timeline_markdown(result)
        assert "`runtime_logs_without_db_record`" in markdown
    finally:
        if db_path.exists():
            db_path.unlink()
        for path in logs_dir.glob("*"):
            path.unlink()
        logs_dir.rmdir()


def test_timeline_reports_db_log_path_mismatch() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    db_path = (base_dir / f"timeline_mismatch_{token}.db").resolve()
    logs_dir = (base_dir / f"timeline_mismatch_logs_{token}").resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        _create_history_db(
            db_path,
            row=(
                "rec-1",
                "2026-06-10T10:00:03",
                "groq",
                120.0,
                "chunked",
                "standard",
                None,
            ),
        )
        _write_log(
            logs_dir / "app.log",
            [
                (
                    "2026-06-10 10:00:02 | INFO     | audio        | [audio] | "
                    "Audio: Transcription fallback engaged | | "
                    '{"record_id":"rec-1","selected_path":"cloud_file_fallback",'
                    '"decision_reason":"low_quality_chunked_result",'
                    '"fallback_type":"cloud_file","fallback_reason":"low_quality_chunked_result"}'
                ),
            ],
        )

        result = module.inspect_transcription_record_timeline(
            db_path=db_path,
            logs_path=logs_dir,
            record_id="rec-1",
        )

        assert result["diagnosis"]["state"] == "db_log_path_mismatch"
        assert result["comparison"]["db_transcription_path"] == "standard"
        assert result["comparison"]["db_transcription_decision_reason"] is None
        assert result["comparison"]["log_selected_path"] == "cloud_file_fallback"
        assert result["comparison"]["decision_reasons_match"] is False
        assert result["comparison"]["paths_match"] is False
        assert (
            result["issue_summary"]
            == "record_id=rec-1 path mismatch: db=standard vs log=cloud_file_fallback; "
            "reason db=none vs log=low_quality_chunked_result"
        )
        assert result["event_flow"]["fallback_event_count"] == 1
        assert result["event_flow"]["observed_fallback_reasons"] == [
            "low_quality_chunked_result"
        ]
        oneline = module.format_transcription_record_timeline_oneline(result)
        assert "state=db_log_path_mismatch" in oneline
        assert "paths_match=False" in oneline
        assert "decision_reasons_match=False" in oneline
        summary = module.format_transcription_record_timeline_summary(result)
        assert "Diagnosis: db_log_path_mismatch" in summary
        assert (
            "Issue summary: record_id=rec-1 path mismatch: db=standard vs log=cloud_file_fallback; "
            "reason db=none vs log=low_quality_chunked_result"
        ) in summary
        assert "Fallback events: 1" in summary
        card = module.format_transcription_record_timeline_card(result)
        assert "- **Diagnosis:** `db_log_path_mismatch`" in card
        assert "  - log_path: `cloud_file_fallback`" in card
        markdown = module.format_transcription_record_timeline_markdown(result)
        assert "`db_log_path_mismatch`" in markdown
        assert (
            "- **Observed fallback reasons:** `low_quality_chunked_result`" in markdown
        )
    finally:
        if db_path.exists():
            db_path.unlink()
        for path in logs_dir.glob("*"):
            path.unlink()
        logs_dir.rmdir()


def test_timeline_reports_related_logs_without_path_event() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    db_path = (base_dir / f"timeline_no_path_event_{token}.db").resolve()
    logs_dir = (base_dir / f"timeline_no_path_event_logs_{token}").resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        _create_history_db(
            db_path,
            row=(
                "rec-1",
                "2026-06-10T10:00:03",
                "groq",
                98.6,
                "chunked",
                "standard",
                None,
            ),
        )
        _write_log(
            logs_dir / "app.log",
            [
                (
                    "2026-06-10 10:00:00 | INFO     | audio        | [audio] | "
                    "Audio: Transcription request received | | "
                    '{"record_id":"rec-1","audio_file_path":"sample.wav","audio_duration":98.6}'
                ),
                (
                    "2026-06-10 10:00:03 | INFO     | audio        | [audio] | "
                    "Audio: Transcription record saved | | "
                    '{"record_id":"rec-1","status":"success","transcription_path":"standard"}'
                ),
                (
                    "2026-06-10 10:00:04 | INFO     | audio        | [audio] | "
                    "Audio: History record updated | | "
                    '{"record_id":"rec-1","thread_id":1234}'
                ),
            ],
        )

        result = module.inspect_transcription_record_timeline(
            db_path=db_path,
            logs_path=logs_dir,
            record_id="rec-1",
        )

        assert result["diagnosis"]["state"] == "related_logs_without_path_event"
        assert result["comparison"] is None
        assert (
            result["issue_summary"]
            == "record_id=rec-1 related logs were found but no path decision/fallback event: "
            "latest_event=History record updated"
        )
        assert result["event_flow"]["event_count"] == 3
        assert result["event_flow"]["path_event_count"] == 0
        assert (
            result["event_flow"]["latest_terminal_event"]["event"]
            == "History record updated"
        )

        oneline = module.format_transcription_record_timeline_oneline(result)
        assert "state=related_logs_without_path_event" in oneline
        assert "db_path=standard" in oneline
        assert "db_reason=none" in oneline
        assert "log_path=none" in oneline
        assert "paths_match=none" in oneline

        summary = module.format_transcription_record_timeline_summary(result)
        assert "Diagnosis: related_logs_without_path_event" in summary
        assert "Path events: 0" in summary
        assert "Latest Terminal Event:" in summary

        markdown = module.format_transcription_record_timeline_markdown(result)
        assert "`related_logs_without_path_event`" in markdown
        assert "- **Path events:** 0" in markdown
    finally:
        if db_path.exists():
            db_path.unlink()
        for path in logs_dir.glob("*"):
            path.unlink()
        logs_dir.rmdir()
