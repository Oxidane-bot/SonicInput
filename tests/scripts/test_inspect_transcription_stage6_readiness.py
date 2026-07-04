import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4


def _load_module():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "inspect_transcription_stage6_readiness.py"
    )
    scripts_dir = str(module_path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(
        "inspect_transcription_stage6_readiness", module_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _create_history_db(
    db_path: Path,
    *,
    include_decision_reason: bool,
    rows: list[tuple[str, str, str, float, str, str, str | None]],
) -> None:
    decision_reason_column_sql = (
        "transcription_decision_reason TEXT,\n" if include_decision_reason else ""
    )
    decision_reason_insert_sql = (
        "transcription_decision_reason,\n                "
        if include_decision_reason
        else ""
    )
    decision_reason_value_sql = ", ?" if include_decision_reason else ""

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            f"""
            CREATE TABLE history_records (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                audio_file_path TEXT NOT NULL,
                duration REAL NOT NULL,
                transcription_provider TEXT NOT NULL,
                transcription_status TEXT NOT NULL,
                streaming_mode TEXT NOT NULL,
                transcription_path TEXT NOT NULL,
                {decision_reason_column_sql}
                transcription_text TEXT,
                final_text TEXT
            )
            """
        )
        conn.executemany(
            f"""
            INSERT INTO history_records (
                id, timestamp, audio_file_path, duration,
                transcription_provider, transcription_status, streaming_mode,
                transcription_path, {decision_reason_insert_sql}
                transcription_text, final_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?{decision_reason_value_sql}, ?, ?)
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
                    *((decision_reason,) if include_decision_reason else ()),
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


def _write_log(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_stage6_readiness_reports_waiting_for_new_build_session() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    db_path = (base_dir / f"stage6_wait_build_{token}.db").resolve()
    logs_dir = (base_dir / f"stage6_wait_build_logs_{token}").resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        _create_history_db(
            db_path,
            include_decision_reason=False,
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
                    "2026-06-09 16:05:33 | INFO     | audio        | [audio] | "
                    "Audio: History database schema upgraded | | "
                    '{"added_column":"transcription_path"}'
                ),
            ],
        )

        result = module.inspect_transcription_stage6_readiness(
            db_path=db_path,
            logs_path=logs_dir,
            timestamp_from="2026-06-09T16:06:10",
        )

        assert (
            result["readiness"]["diagnosis"]["state"] == "waiting_for_new_build_session"
        )
        assert (
            result["readiness"]["runtime_declares_current_expectation_version"] is False
        )
        assert (
            result["readiness"]["db_has_transcription_decision_reason_column"] is False
        )
        assert result["readiness"]["issue_summary"] is None
        assert (
            "inspect_transcription_stage6_readiness.py"
            in result["readiness"]["runbook"]["rerun_readiness_command"]
        )
        assert result["readiness"]["record_timeline_preview"] is None
        assert len(result["readiness"]["runbook"]["follow_up_commands"]) == 4
        assert any(
            "inspect_transcription_path_observability.py" in command
            for command in result["readiness"]["runbook"]["follow_up_commands"]
        )
        assert any(
            "inspect_recent_transcription_paths.py" in command
            for command in result["readiness"]["runbook"]["follow_up_commands"]
        )
        assert any(
            "inspect_recent_transcription_path_logs.py" in command
            for command in result["readiness"]["runbook"]["follow_up_commands"]
        )
        summary = module.format_stage6_readiness_summary(result)
        assert "Diagnosis: waiting_for_new_build_session" in summary
        assert "Runtime build expectation seen: no" in summary
        markdown = module.format_stage6_readiness_markdown(result)
        assert "# Stage 6 Readiness Report" in markdown
        assert "## Diagnosis" in markdown
        assert "`waiting_for_new_build_session`" in markdown
        assert "## Recommended Steps" in markdown
        assert "## Rerun Command" in markdown
        assert "## Follow-up Commands" in markdown
        oneline = module.format_stage6_readiness_oneline(result)
        assert "state=waiting_for_new_build_session" in oneline
        assert "db_decision_reason_column=no" in oneline
        assert "runtime_expectation_seen=no" in oneline
        assert "record_hint=none" in oneline
        assert "latest_schema_upgrade=2026-06-09 16:05:33" in oneline
        assert "message=No runtime log evidence shows a build" in oneline
        card = module.format_stage6_readiness_card(result)
        assert "## Stage 6 Readiness Card" in card
        assert "- **Diagnosis:** `waiting_for_new_build_session`" in card
        assert "- **Alignment:** `no_post_cutoff_runtime_or_db_activity`" in card
        assert "- **DB decision_reason column:** no" in card
        assert "- **Runtime expectation seen:** no" in card
        assert "- **Post-cutoff DB rows:** `0`" in card
        assert "- **Post-cutoff runtime logs:** `0`" in card
        assert "- **Newest record hint:** `none`" in card
        assert "- **Latest schema expectation event:** `none`" in card
        assert "- **Latest schema upgrade event:** `2026-06-09 16:05:33`" in card
        assert (
            "- **Guidance:** Start a newer app build and rerun this inspector" in card
        )
        assert "- **Status note:** No runtime log evidence shows a build" in card
        assert "- **Next actions:**" in card
        assert "- **Rerun command:** `" in card
    finally:
        if db_path.exists():
            db_path.unlink()
        for path in logs_dir.glob("*"):
            path.unlink()
        logs_dir.rmdir()


def test_stage6_readiness_reports_new_build_seen_db_not_migrated() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    db_path = (base_dir / f"stage6_build_seen_{token}.db").resolve()
    logs_dir = (base_dir / f"stage6_build_seen_logs_{token}").resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        _create_history_db(
            db_path,
            include_decision_reason=False,
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
        expected_version = (
            module.HistoryStorageService._HISTORY_SCHEMA_EXPECTATION_VERSION
        )
        expected_signature = module.HistoryStorageService.history_schema_signature()
        _write_log(
            logs_dir / "app.log",
            [
                (
                    "2026-06-10 09:00:00 | INFO     | audio        | [audio] | "
                    "Audio: History schema expectations declared | | "
                    f'{{"required_columns":["streaming_mode","transcription_path",'
                    f'"transcription_decision_reason"],'
                    f'"required_column_count":3,'
                    f'"history_schema_expectation_version":{expected_version},'
                    f'"history_schema_signature":"{expected_signature}",'
                    f'"expects_transcription_path":true,'
                    f'"expects_transcription_decision_reason":true}}'
                ),
            ],
        )

        result = module.inspect_transcription_stage6_readiness(
            db_path=db_path,
            logs_path=logs_dir,
            timestamp_from="2026-06-09T16:06:10",
        )

        assert (
            result["readiness"]["diagnosis"]["state"]
            == "new_build_seen_db_not_migrated"
        )
        assert (
            result["readiness"]["runtime_declares_current_expectation_version"] is True
        )
        assert result["readiness"]["runtime_declares_current_signature"] is True
        assert (
            result["readiness"]["db_has_transcription_decision_reason_column"] is False
        )
        assert any(
            "inspect_history_schema.py" in command
            for command in result["readiness"]["runbook"]["follow_up_commands"]
        )
    finally:
        if db_path.exists():
            db_path.unlink()
        for path in logs_dir.glob("*"):
            path.unlink()
        logs_dir.rmdir()


def test_stage6_readiness_reports_schema_ready_waiting_for_sample() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    db_path = (base_dir / f"stage6_wait_sample_{token}.db").resolve()
    logs_dir = (base_dir / f"stage6_wait_sample_logs_{token}").resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        _create_history_db(
            db_path,
            include_decision_reason=True,
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
        expected_version = (
            module.HistoryStorageService._HISTORY_SCHEMA_EXPECTATION_VERSION
        )
        expected_signature = module.HistoryStorageService.history_schema_signature()
        _write_log(
            logs_dir / "app.log",
            [
                (
                    "2026-06-10 09:00:00 | INFO     | audio        | [audio] | "
                    "Audio: History schema expectations declared | | "
                    f'{{"required_columns":["streaming_mode","transcription_path",'
                    f'"transcription_decision_reason"],'
                    f'"required_column_count":3,'
                    f'"history_schema_expectation_version":{expected_version},'
                    f'"history_schema_signature":"{expected_signature}",'
                    f'"expects_transcription_path":true,'
                    f'"expects_transcription_decision_reason":true}}'
                ),
            ],
        )

        result = module.inspect_transcription_stage6_readiness(
            db_path=db_path,
            logs_path=logs_dir,
            timestamp_from="2026-06-09T16:06:10",
        )

        assert (
            result["readiness"]["diagnosis"]["state"]
            == "schema_ready_waiting_for_post_cutoff_sample"
        )
        assert (
            result["readiness"]["db_has_transcription_decision_reason_column"] is True
        )
        assert result["readiness"]["post_cutoff_activity_present"] is False
        assert any(
            "Generate one new real transcription" in step
            for step in result["readiness"]["runbook"]["recommended_steps"]
        )
        assert any(
            "inspect_recent_transcription_path_logs.py" in command
            for command in result["readiness"]["runbook"]["follow_up_commands"]
        )
    finally:
        if db_path.exists():
            db_path.unlink()
        for path in logs_dir.glob("*"):
            path.unlink()
        logs_dir.rmdir()


def test_stage6_readiness_reports_ready_and_aligned() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    db_path = (base_dir / f"stage6_aligned_{token}.db").resolve()
    logs_dir = (base_dir / f"stage6_aligned_logs_{token}").resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        _create_history_db(
            db_path,
            include_decision_reason=True,
            rows=[
                (
                    "rec-1",
                    "2026-06-10T09:30:00",
                    "groq",
                    120.0,
                    "chunked",
                    "cloud_file_long_recording",
                    "long_cloud_recording_prefer_file",
                ),
            ],
        )
        expected_version = (
            module.HistoryStorageService._HISTORY_SCHEMA_EXPECTATION_VERSION
        )
        expected_signature = module.HistoryStorageService.history_schema_signature()
        _write_log(
            logs_dir / "app.log",
            [
                (
                    "2026-06-10 09:00:00 | INFO     | audio        | [audio] | "
                    "Audio: History schema expectations declared | | "
                    f'{{"required_columns":["streaming_mode","transcription_path",'
                    f'"transcription_decision_reason"],'
                    f'"required_column_count":3,'
                    f'"history_schema_expectation_version":{expected_version},'
                    f'"history_schema_signature":"{expected_signature}",'
                    f'"expects_transcription_path":true,'
                    f'"expects_transcription_decision_reason":true}}'
                ),
                (
                    "2026-06-10 09:30:00 | INFO     | audio        | [audio] | "
                    "Audio: Transcription path decision | | "
                    '{"record_id":"rec-1","selected_path":"cloud_file_long_recording",'
                    '"decision_reason":"long_cloud_recording_prefer_file"}'
                ),
            ],
        )

        result = module.inspect_transcription_stage6_readiness(
            db_path=db_path,
            logs_path=logs_dir,
            timestamp_from="2026-06-09T16:06:10",
        )

        assert result["readiness"]["diagnosis"]["state"] == "stage6_ready_and_aligned"
        assert result["readiness"]["post_cutoff_activity_present"] is True
        assert (
            result["readiness"]["alignment_state"] == "db_log_paths_and_reasons_aligned"
        )
        assert result["readiness"]["newest_record_id_hint"] == "rec-1"
        assert (
            result["readiness"]["record_timeline_preview"]["diagnosis_state"]
            == "db_log_path_aligned"
        )
        assert (
            result["readiness"]["record_timeline_preview"]["issue_summary"]
            == "record_id=rec-1 aligned: path=cloud_file_long_recording, "
            "decision_reason=long_cloud_recording_prefer_file"
        )
        assert (
            result["readiness"]["issue_summary"]
            == "record_id=rec-1 aligned: path=cloud_file_long_recording, "
            "decision_reason=long_cloud_recording_prefer_file"
        )
        assert any(
            "inspect_transcription_record_timeline.py" in command
            for command in result["readiness"]["runbook"]["follow_up_commands"]
        )
        assert any(
            "inspect_recent_transcription_paths.py" in command
            for command in result["readiness"]["runbook"]["follow_up_commands"]
        )
        summary = module.format_stage6_readiness_summary(result)
        assert "Diagnosis: stage6_ready_and_aligned" in summary
        assert "Newest record hint: rec-1" in summary
        assert (
            "Issue summary: record_id=rec-1 aligned: "
            "path=cloud_file_long_recording, "
            "decision_reason=long_cloud_recording_prefer_file"
        ) in summary
        assert "Record Timeline Preview:" in summary
        assert "Diagnosis: db_log_path_aligned" in summary
        assert "Follow-up Commands:" in summary
        markdown = module.format_stage6_readiness_markdown(result)
        assert "# Stage 6 Readiness Report" in markdown
        assert "## Diagnosis" in markdown
        assert "`stage6_ready_and_aligned`" in markdown
        assert "**Newest record hint:** rec-1" in markdown
        assert (
            "**Issue summary:** record_id=rec-1 aligned: "
            "path=cloud_file_long_recording, "
            "decision_reason=long_cloud_recording_prefer_file"
        ) in markdown
        assert "## Record Timeline Preview" in markdown
        assert "`db_log_path_aligned`" in markdown
        assert "## Recommended Steps" in markdown
        assert "## Rerun Command" in markdown
        assert "## Follow-up Commands" in markdown
        oneline = module.format_stage6_readiness_oneline(result)
        assert "state=stage6_ready_and_aligned" in oneline
        assert "db_decision_reason_column=yes" in oneline
        assert "runtime_expectation_seen=yes" in oneline
        assert "record_hint=rec-1" in oneline
        assert (
            "issue_summary=record_id=rec-1 aligned: "
            "path=cloud_file_long_recording, "
            "decision_reason=long_cloud_recording_prefer_file"
        ) in oneline
        card = module.format_stage6_readiness_card(result)
        assert "- **Diagnosis:** `stage6_ready_and_aligned`" in card
        assert "- **Alignment:** `db_log_paths_and_reasons_aligned`" in card
        assert "- **DB decision_reason column:** yes" in card
        assert "- **Runtime expectation seen:** yes" in card
        assert "- **Post-cutoff DB rows:** `1`" in card
        assert "- **Post-cutoff runtime logs:** `1`" in card
        assert "- **Newest record hint:** `rec-1`" in card
        assert "- **Latest schema expectation event:** `2026-06-10 09:00:00`" in card
        assert (
            "- **Latest issue:** record_id=rec-1 aligned: "
            "path=cloud_file_long_recording, "
            "decision_reason=long_cloud_recording_prefer_file"
        ) in card
        assert "- **Focus record:**" in card
        assert "- **Record timeline preview:**" in card
        assert "  - source: `shared_aligned`" in card
        assert "  - record_id: `rec-1`" in card
        assert "- **Next actions:**" in card
    finally:
        if db_path.exists():
            db_path.unlink()
        for path in logs_dir.glob("*"):
            path.unlink()
        logs_dir.rmdir()


def test_stage6_readiness_surfaces_log_only_record_hint_for_partial_readiness() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    db_path = (base_dir / f"stage6_log_only_{token}.db").resolve()
    logs_dir = (base_dir / f"stage6_log_only_logs_{token}").resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        _create_history_db(
            db_path,
            include_decision_reason=True,
            rows=[
                (
                    "rec-old",
                    "2026-06-09T15:00:00",
                    "groq",
                    20.0,
                    "chunked",
                    "standard",
                    "streaming_stop_result",
                ),
            ],
        )
        expected_version = (
            module.HistoryStorageService._HISTORY_SCHEMA_EXPECTATION_VERSION
        )
        expected_signature = module.HistoryStorageService.history_schema_signature()
        _write_log(
            logs_dir / "app.log",
            [
                (
                    "2026-06-10 09:00:00 | INFO     | audio        | [audio] | "
                    "Audio: History schema expectations declared | | "
                    f'{{"required_columns":["streaming_mode","transcription_path",'
                    f'"transcription_decision_reason"],'
                    f'"required_column_count":3,'
                    f'"history_schema_expectation_version":{expected_version},'
                    f'"history_schema_signature":"{expected_signature}",'
                    f'"expects_transcription_path":true,'
                    f'"expects_transcription_decision_reason":true}}'
                ),
                (
                    "2026-06-10 09:30:00 | INFO     | audio        | [audio] | "
                    "Audio: Transcription path decision | | "
                    '{"record_id":"rec-log-1","selected_path":"cloud_file_long_recording",'
                    '"decision_reason":"long_cloud_recording_prefer_file"}'
                ),
            ],
        )

        result = module.inspect_transcription_stage6_readiness(
            db_path=db_path,
            logs_path=logs_dir,
            timestamp_from="2026-06-09T16:06:10",
        )

        assert result["readiness"]["diagnosis"]["state"] == "partial_stage6_readiness"
        assert result["readiness"]["alignment_state"] == "runtime_logs_without_db_rows"
        assert result["readiness"]["newest_record_id_hint"] == "rec-log-1"
        assert (
            result["readiness"]["record_timeline_preview"]["diagnosis_state"]
            == "runtime_logs_without_db_record"
        )
        assert (
            result["readiness"]["issue_summary"]
            == "record_id=rec-log-1 runtime log exists without DB row yet: "
            "log_path=cloud_file_long_recording, "
            "log_reason=long_cloud_recording_prefer_file"
        )
        assert any(
            "inspect_transcription_record_timeline.py" in command
            and "rec-log-1" in command
            for command in result["readiness"]["runbook"]["follow_up_commands"]
        )
        assert any(
            "Confirm the app and inspected history.db refer to the same real storage path."
            == step
            for step in result["readiness"]["runbook"]["recommended_steps"]
        )
        summary = module.format_stage6_readiness_summary(result)
        assert "Diagnosis: partial_stage6_readiness" in summary
        assert "Newest record hint: rec-log-1" in summary
        assert (
            "Issue summary: record_id=rec-log-1 runtime log exists without DB row yet: "
            "log_path=cloud_file_long_recording, "
            "log_reason=long_cloud_recording_prefer_file"
        ) in summary
        markdown = module.format_stage6_readiness_markdown(result)
        assert "`partial_stage6_readiness`" in markdown
        assert "**Newest record hint:** rec-log-1" in markdown
        assert (
            "**Issue summary:** record_id=rec-log-1 runtime log exists without DB row yet: "
            "log_path=cloud_file_long_recording, "
            "log_reason=long_cloud_recording_prefer_file"
        ) in markdown
        oneline = module.format_stage6_readiness_oneline(result)
        assert "state=partial_stage6_readiness" in oneline
        assert "record_hint=rec-log-1" in oneline
        assert (
            "issue_summary=record_id=rec-log-1 runtime log exists without DB row yet: "
            "log_path=cloud_file_long_recording, "
            "log_reason=long_cloud_recording_prefer_file"
        ) in oneline
        card = module.format_stage6_readiness_card(result)
        assert "- **Diagnosis:** `partial_stage6_readiness`" in card
        assert "- **Alignment:** `runtime_logs_without_db_rows`" in card
        assert "- **Newest record hint:** `rec-log-1`" in card
        assert (
            "- **Latest issue:** record_id=rec-log-1 runtime log exists without DB row yet: "
            "log_path=cloud_file_long_recording, "
            "log_reason=long_cloud_recording_prefer_file"
        ) in card
        assert "  - source: `runtime_log_only`" in card
    finally:
        if db_path.exists():
            db_path.unlink()
        for path in logs_dir.glob("*"):
            path.unlink()
        logs_dir.rmdir()


def test_stage6_readiness_surfaces_path_mismatch_focus_record() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    db_path = (base_dir / f"stage6_path_mismatch_{token}.db").resolve()
    logs_dir = (base_dir / f"stage6_path_mismatch_logs_{token}").resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        _create_history_db(
            db_path,
            include_decision_reason=True,
            rows=[
                (
                    "rec-path-1",
                    "2026-06-10T09:30:00",
                    "groq",
                    120.0,
                    "chunked",
                    "standard",
                    "streaming_stop_result",
                ),
            ],
        )
        expected_version = (
            module.HistoryStorageService._HISTORY_SCHEMA_EXPECTATION_VERSION
        )
        expected_signature = module.HistoryStorageService.history_schema_signature()
        _write_log(
            logs_dir / "app.log",
            [
                (
                    "2026-06-10 09:00:00 | INFO     | audio        | [audio] | "
                    "Audio: History schema expectations declared | | "
                    f'{{"required_columns":["streaming_mode","transcription_path",'
                    f'"transcription_decision_reason"],'
                    f'"required_column_count":3,'
                    f'"history_schema_expectation_version":{expected_version},'
                    f'"history_schema_signature":"{expected_signature}",'
                    f'"expects_transcription_path":true,'
                    f'"expects_transcription_decision_reason":true}}'
                ),
                (
                    "2026-06-10 09:30:00 | INFO     | audio        | [audio] | "
                    "Audio: Transcription path decision | | "
                    '{"record_id":"rec-path-1","selected_path":"cloud_file_long_recording",'
                    '"decision_reason":"long_cloud_recording_prefer_file"}'
                ),
            ],
        )

        result = module.inspect_transcription_stage6_readiness(
            db_path=db_path,
            logs_path=logs_dir,
            timestamp_from="2026-06-09T16:06:10",
        )

        assert result["readiness"]["diagnosis"]["state"] == "post_cutoff_path_mismatch"
        focus_record = result["readiness"]["focus_record"]
        assert focus_record["source"] == "shared_path_mismatch"
        assert focus_record["record_id"] == "rec-path-1"
        assert focus_record["db_transcription_path"] == "standard"
        assert focus_record["log_selected_path"] == "cloud_file_long_recording"
        assert (
            result["readiness"]["issue_summary"]
            == "record_id=rec-path-1 path mismatch: "
            "db=standard vs log=cloud_file_long_recording"
        )
        assert any(
            "Compare the persisted DB path against the runtime selected_path or fallback event."
            == step
            for step in result["readiness"]["runbook"]["recommended_steps"]
        )
        summary = module.format_stage6_readiness_summary(result)
        assert (
            "Issue summary: record_id=rec-path-1 path mismatch: "
            "db=standard vs log=cloud_file_long_recording"
        ) in summary
        assert "Focus Record:" in summary
        assert "Record id: rec-path-1" in summary
        assert "DB path: standard" in summary
        assert "Log path: cloud_file_long_recording" in summary
        markdown = module.format_stage6_readiness_markdown(result)
        assert (
            "**Issue summary:** record_id=rec-path-1 path mismatch: "
            "db=standard vs log=cloud_file_long_recording"
        ) in markdown
        assert "## Focus Record" in markdown
        assert "**Record id:** rec-path-1" in markdown
        assert "**DB path:** standard" in markdown
        assert "**Log path:** cloud_file_long_recording" in markdown
        oneline = module.format_stage6_readiness_oneline(result)
        assert "state=post_cutoff_path_mismatch" in oneline
        assert (
            "issue_summary=record_id=rec-path-1 path mismatch: "
            "db=standard vs log=cloud_file_long_recording"
        ) in oneline
        card = module.format_stage6_readiness_card(result)
        assert "- **Diagnosis:** `post_cutoff_path_mismatch`" in card
        assert "- **Alignment:** `db_log_path_mismatch`" in card
        assert (
            "- **Latest issue:** record_id=rec-path-1 path mismatch: "
            "db=standard vs log=cloud_file_long_recording"
        ) in card
        assert "  - db_path: `standard`" in card
        assert "  - log_path: `cloud_file_long_recording`" in card
    finally:
        if db_path.exists():
            db_path.unlink()
        for path in logs_dir.glob("*"):
            path.unlink()
        logs_dir.rmdir()


def test_stage6_readiness_surfaces_reason_mismatch_focus_record() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    db_path = (base_dir / f"stage6_reason_mismatch_{token}.db").resolve()
    logs_dir = (base_dir / f"stage6_reason_mismatch_logs_{token}").resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        _create_history_db(
            db_path,
            include_decision_reason=True,
            rows=[
                (
                    "rec-reason-1",
                    "2026-06-10T09:30:00",
                    "groq",
                    120.0,
                    "chunked",
                    "cloud_file_long_recording",
                    "streaming_stop_result",
                ),
            ],
        )
        expected_version = (
            module.HistoryStorageService._HISTORY_SCHEMA_EXPECTATION_VERSION
        )
        expected_signature = module.HistoryStorageService.history_schema_signature()
        _write_log(
            logs_dir / "app.log",
            [
                (
                    "2026-06-10 09:00:00 | INFO     | audio        | [audio] | "
                    "Audio: History schema expectations declared | | "
                    f'{{"required_columns":["streaming_mode","transcription_path",'
                    f'"transcription_decision_reason"],'
                    f'"required_column_count":3,'
                    f'"history_schema_expectation_version":{expected_version},'
                    f'"history_schema_signature":"{expected_signature}",'
                    f'"expects_transcription_path":true,'
                    f'"expects_transcription_decision_reason":true}}'
                ),
                (
                    "2026-06-10 09:30:00 | INFO     | audio        | [audio] | "
                    "Audio: Transcription path decision | | "
                    '{"record_id":"rec-reason-1","selected_path":"cloud_file_long_recording",'
                    '"decision_reason":"long_cloud_recording_prefer_file"}'
                ),
            ],
        )

        result = module.inspect_transcription_stage6_readiness(
            db_path=db_path,
            logs_path=logs_dir,
            timestamp_from="2026-06-09T16:06:10",
        )

        assert (
            result["readiness"]["diagnosis"]["state"] == "post_cutoff_reason_mismatch"
        )
        focus_record = result["readiness"]["focus_record"]
        assert focus_record["source"] == "shared_reason_mismatch"
        assert focus_record["record_id"] == "rec-reason-1"
        assert (
            focus_record["db_transcription_decision_reason"] == "streaming_stop_result"
        )
        assert focus_record["log_decision_reason"] == "long_cloud_recording_prefer_file"
        assert (
            result["readiness"]["issue_summary"]
            == "record_id=rec-reason-1 decision reason mismatch: "
            "db=streaming_stop_result vs log=long_cloud_recording_prefer_file"
        )
        assert any(
            "Trace where the final persisted decision reason diverges from runtime logs."
            == step
            for step in result["readiness"]["runbook"]["recommended_steps"]
        )
        summary = module.format_stage6_readiness_summary(result)
        assert (
            "Issue summary: record_id=rec-reason-1 decision reason mismatch: "
            "db=streaming_stop_result vs log=long_cloud_recording_prefer_file"
        ) in summary
        assert "DB decision reason: streaming_stop_result" in summary
        assert "Log decision reason: long_cloud_recording_prefer_file" in summary
        markdown = module.format_stage6_readiness_markdown(result)
        assert (
            "**Issue summary:** record_id=rec-reason-1 decision reason mismatch: "
            "db=streaming_stop_result vs log=long_cloud_recording_prefer_file"
        ) in markdown
        assert "**DB decision reason:** streaming_stop_result" in markdown
        assert "**Log decision reason:** long_cloud_recording_prefer_file" in markdown
        card = module.format_stage6_readiness_card(result)
        assert "- **Diagnosis:** `post_cutoff_reason_mismatch`" in card
        assert "- **Alignment:** `db_log_decision_reason_mismatch`" in card
        assert (
            "- **Latest issue:** record_id=rec-reason-1 decision reason mismatch: "
            "db=streaming_stop_result vs log=long_cloud_recording_prefer_file"
        ) in card
        assert "  - db_reason: `streaming_stop_result`" in card
        assert "  - log_reason: `long_cloud_recording_prefer_file`" in card
    finally:
        if db_path.exists():
            db_path.unlink()
        for path in logs_dir.glob("*"):
            path.unlink()
        logs_dir.rmdir()


def test_stage6_readiness_can_append_snapshot_jsonl() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    db_path = (base_dir / f"stage6_snapshot_{token}.db").resolve()
    logs_dir = (base_dir / f"stage6_snapshot_logs_{token}").resolve()
    snapshot_path = (
        base_dir / "snapshots" / f"stage6_readiness_snapshot_{token}.jsonl"
    ).resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        _create_history_db(
            db_path,
            include_decision_reason=True,
            rows=[
                (
                    "rec-snap-1",
                    "2026-06-10T09:30:00",
                    "groq",
                    120.0,
                    "chunked",
                    "cloud_file_long_recording",
                    "long_cloud_recording_prefer_file",
                ),
            ],
        )
        expected_version = (
            module.HistoryStorageService._HISTORY_SCHEMA_EXPECTATION_VERSION
        )
        expected_signature = module.HistoryStorageService.history_schema_signature()
        _write_log(
            logs_dir / "app.log",
            [
                (
                    "2026-06-10 09:00:00 | INFO     | audio        | [audio] | "
                    "Audio: History schema expectations declared | | "
                    f'{{"required_columns":["streaming_mode","transcription_path",'
                    f'"transcription_decision_reason"],'
                    f'"required_column_count":3,'
                    f'"history_schema_expectation_version":{expected_version},'
                    f'"history_schema_signature":"{expected_signature}",'
                    f'"expects_transcription_path":true,'
                    f'"expects_transcription_decision_reason":true}}'
                ),
                (
                    "2026-06-10 09:30:00 | INFO     | audio        | [audio] | "
                    "Audio: Transcription path decision | | "
                    '{"record_id":"rec-snap-1","selected_path":"cloud_file_long_recording",'
                    '"decision_reason":"long_cloud_recording_prefer_file"}'
                ),
            ],
        )

        result = module.inspect_transcription_stage6_readiness(
            db_path=db_path,
            logs_path=logs_dir,
            timestamp_from="2026-06-09T16:06:10",
        )
        snapshot = module.append_stage6_readiness_snapshot(snapshot_path, result)

        assert snapshot_path.exists()
        lines = snapshot_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        loaded = json.loads(lines[0])
        assert loaded["diagnosis_state"] == "stage6_ready_and_aligned"
        assert loaded["newest_record_id_hint"] == "rec-snap-1"
        assert loaded["issue_summary"] == (
            "record_id=rec-snap-1 aligned: "
            "path=cloud_file_long_recording, "
            "decision_reason=long_cloud_recording_prefer_file"
        )
        assert loaded["focus_record"]["record_id"] == "rec-snap-1"
        assert loaded["oneline"] == module.format_stage6_readiness_oneline(result)
        assert loaded["observed_at_utc"].endswith("Z")
    finally:
        if db_path.exists():
            db_path.unlink()
        if snapshot_path.exists():
            snapshot_path.unlink()
        if snapshot_path.parent.exists() and not any(snapshot_path.parent.iterdir()):
            snapshot_path.parent.rmdir()
        for path in logs_dir.glob("*"):
            path.unlink()
        logs_dir.rmdir()
