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
        / "inspect_transcription_stage6_handoff.py"
    )
    scripts_dir = str(module_path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(
        "inspect_transcription_stage6_handoff", module_path
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


def _write_snapshots(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_stage6_handoff_combines_readiness_and_timeline() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    db_path = (base_dir / f"stage6_handoff_aligned_{token}.db").resolve()
    logs_dir = (base_dir / f"stage6_handoff_aligned_logs_{token}").resolve()
    snapshot_path = (
        base_dir / "snapshots" / f"stage6_handoff_aligned_{token}.jsonl"
    ).resolve()
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
        history_storage_service = (
            module.inspect_transcription_stage6_readiness.__globals__[
                "HistoryStorageService"
            ]
        )
        expected_version = history_storage_service._HISTORY_SCHEMA_EXPECTATION_VERSION
        expected_signature = history_storage_service.history_schema_signature()
        _write_log(
            logs_dir / "app.log",
            [
                (
                    "2026-06-10 09:00:00 | INFO     | audio        | [audio] | "
                    "Audio: History schema expectations declared | | "
                    f'{{"required_columns":["streaming_mode","transcription_path",'
                    f'"transcription_decision_reason"],"required_column_count":3,'
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
        _write_snapshots(
            snapshot_path,
            [
                (
                    '{"observed_at_utc":"2026-06-10T09:00:00Z",'
                    '"diagnosis_state":"new_build_seen_db_not_migrated",'
                    '"alignment_state":"no_post_cutoff_runtime_or_db_activity",'
                    '"issue_summary":null,'
                    '"oneline":"state=new_build_seen_db_not_migrated"}'
                ),
                (
                    '{"observed_at_utc":"2026-06-10T09:30:00Z",'
                    '"diagnosis_state":"stage6_ready_and_aligned",'
                    '"alignment_state":"db_log_paths_and_reasons_aligned",'
                    '"issue_summary":"record_id=rec-1 aligned: path=cloud_file_long_recording, decision_reason=long_cloud_recording_prefer_file",'
                    '"newest_record_id_hint":"rec-1",'
                    '"oneline":"state=stage6_ready_and_aligned"}'
                ),
            ],
        )

        result = module.inspect_transcription_stage6_handoff(
            db_path=db_path,
            logs_path=logs_dir,
            timestamp_from="2026-06-09T16:06:10",
            snapshot_path=snapshot_path,
        )

        combined = result["combined_assessment"]
        assert combined["overall_state"] == "aligned_with_timeline"
        assert combined["primary_blocker"] is None
        assert combined["readiness_state"] == "stage6_ready_and_aligned"
        assert combined["timeline_state"] == "stage6_ready_and_aligned"
        assert combined["timeline_progress_verdict"] == "advanced"
        assert combined["timeline_stagnation_verdict"] == "not_stuck"
        assert combined["timeline_urgency"] == "normal"
        assert combined["timeline_consecutive_count"] == 1
        assert combined["timeline_stagnation_threshold"] == 3
        assert any(
            "inspect_transcription_record_timeline.py" in command
            for command in combined["primary_corrective_commands"]
        )
        assert any(
            "inspect_transcription_path_observability.py" in command
            for command in combined["primary_corrective_commands"]
        )
        assert any(
            detail["category"] == "record_timeline"
            and "single-record drill-down for an operator spot check"
            in detail["reason"]
            for detail in combined["primary_corrective_command_details"]
        )
        assert any(
            detail["category"] == "append_snapshot"
            and "append a fresh readiness snapshot" in detail["reason"]
            for detail in combined["monitoring_command_details"]
        )
        assert any(
            "inspect_transcription_record_timeline.py" in command
            for command in combined["corrective_commands"]
        )
        assert any(
            "inspect_transcription_stage6_handoff.py" in command
            and "--append-snapshot" in command
            for command in combined["monitoring_commands"]
        )
        assert any("post-cutoff records" in step for step in combined["next_actions"])
        assert any(
            "Keep sampling a few more real records" in step
            for step in combined["next_actions"]
        )
        assert any(
            detail["category"] == "keep_sampling"
            and detail["label"] == "Keep sampling"
            and "Alignment has been seen once" in detail["reason"]
            for detail in combined["next_action_details"]
        )
        assert any(
            detail["category"] == "keep_sampling"
            and "After alignment has been observed at least once."
            == detail["when_to_run"]
            for detail in combined["next_action_details"]
        )
        assert any(
            "inspect_transcription_record_timeline.py" in command
            for command in combined["follow_up_commands"]
        )
        assert any(
            "inspect_transcription_stage6_handoff.py" in command
            and "--append-snapshot" in command
            for command in combined["follow_up_commands"]
        )
        assert any(
            "inspect_transcription_stage6_snapshot_timeline.py" in command
            and "--summary" in command
            for command in combined["follow_up_commands"]
        )
        assert any(
            "inspect_transcription_stage6_handoff.py" in command
            and "--append-snapshot" in command
            for command in result["snapshot_workflow_commands"]
        )
        assert any(
            "inspect_transcription_stage6_snapshot_timeline.py" in command
            and "--summary" in command
            for command in result["snapshot_workflow_commands"]
        )
        assert (
            result["readiness"]["readiness"]["record_timeline_preview"][
                "diagnosis_state"
            ]
            == "db_log_path_aligned"
        )
        envelope = dict(result["operator_handoff_envelope"] or {})
        assert envelope["version"] == 1
        assert envelope["overall"]["timeline_available"] is True
        assert envelope["overall"]["overall_state"] == "aligned_with_timeline"
        assert envelope["actions"][0]["kind"] == "action"
        assert envelope["actions"][0]["priority"] == 1
        assert envelope["actions"][0]["id"] == "progress_advanced"
        assert envelope["commands"]["primary_corrective"][0]["kind"] == "command"
        assert (
            envelope["commands"]["primary_corrective"][0]["phase"]
            == "primary_corrective"
        )
        assert envelope["commands"]["primary_corrective"][0]["id"] == "record_timeline"
        assert envelope["timeline"]["progress"]["id"] == "progress"
        assert (
            envelope["timeline"]["progress"]["label"]
            == "Advanced from previous snapshot"
        )
        assert envelope["timeline"]["guidance"]["urgency"] == "normal"
        assert (
            envelope["timeline"]["recent_deltas"][0]["id"]
            == "recent_delta:2026-06-10T09:30:00Z"
        )
        assert envelope["timeline"]["recent_deltas"][0]["priority"] == 1
        assert envelope["actions"][1]["related_commands"][0]["id"] == "append_snapshot"
        assert envelope["actions"][1]["related_commands"][0]["phase"] == "monitoring"
        assert (
            envelope["workflow"]["snapshot_workflow_commands"]
            == result["snapshot_workflow_commands"]
        )
        assert (
            envelope["workflow"]["follow_up_commands"] == combined["follow_up_commands"]
        )
        recent_snapshot_digest = result["recent_snapshot_digest"]
        assert len(recent_snapshot_digest) == 2
        assert (
            recent_snapshot_digest[0]["diagnosis_state"] == "stage6_ready_and_aligned"
        )
        assert (
            recent_snapshot_digest[0]["transition_summary"]
            == "new_build_seen_db_not_migrated -> stage6_ready_and_aligned"
        )
        assert recent_snapshot_digest[1]["delta_kind"] == "initial"
        assert (
            combined["timeline_progress_detail"]["label"]
            == "Advanced from previous snapshot"
        )
        assert (
            "keep validating the next state transition"
            in (combined["timeline_progress_detail"]["operator_implication"])
        )
        assert (
            combined["timeline_stagnation_detail"]["label"] == "Below stuck threshold"
        )
        assert (
            combined["timeline_guidance_detail"]["label"] == "Normal operator follow-up"
        )
        assert result["recent_snapshot_delta_details"][0]["label"] == "State changed"
        assert (
            "next sample drops out of alignment"
            in (result["recent_snapshot_delta_details"][0]["escalation_trigger"])
        )

        summary = module.format_stage6_handoff_summary(result)
        assert "Stage 6 Operator Handoff Summary" in summary
        assert "Overall state: aligned_with_timeline" in summary
        assert "Timeline progress verdict: advanced" in summary
        assert "Timeline urgency: normal" in summary
        assert "Timeline stagnation window: 1/3" in summary
        assert "Timeline progress label: Advanced from previous snapshot" in summary
        assert "Timeline guidance label: Normal operator follow-up" in summary
        assert (
            "Timeline escalate-if: Escalate only if later samples regress, mismatch, or stop reproducing the aligned state."
            in summary
        )
        assert "Readiness Summary:" in summary
        assert "Timeline Summary:" in summary
        assert "Recent Snapshot Deltas:" in summary
        assert "Primary Corrective Commands:" in summary
        assert "Supporting Corrective Commands:" in summary
        assert "Monitoring Commands:" in summary
        assert "label=Keep sampling" in summary
        assert "when=After alignment has been observed at least once." in summary
        assert (
            "related=inspect_transcription_stage6_handoff.py --append-snapshot --brief; inspect_transcription_stage6_snapshot_timeline.py --summary"
            in summary
        )
        assert "label=Single-record timeline" in summary
        assert (
            "why_now=Use after corrective checks to append a fresh readiness snapshot"
            in summary
        )
        assert "Record timeline preview: db_log_path_aligned" in summary
        assert "inspect_transcription_stage6_handoff.py" in summary
        assert "--append-snapshot --brief" in summary
        assert "inspect_transcription_stage6_snapshot_timeline.py" in summary
        assert (
            "state=stage6_ready_and_aligned | delta=new_build_seen_db_not_migrated -> stage6_ready_and_aligned"
            in summary
        )
        assert "delta_label=State changed" in summary
        assert "implication=This snapshot changed state" in summary
        brief = module.format_stage6_handoff_brief(result)
        assert "Stage 6 Operator Brief" in brief
        assert "Overall state: aligned_with_timeline" in brief
        assert "Previous timeline state: new_build_seen_db_not_migrated" in brief
        assert "Progress: advanced" in brief
        assert "Timeline urgency: normal" in brief
        assert "Stagnation window: 1/3" in brief
        assert "Timeline progress label: Advanced from previous snapshot" in brief
        assert "Timeline guidance label: Normal operator follow-up" in brief
        assert (
            "Timeline escalate-if: Escalate only if later samples regress, mismatch, or stop reproducing the aligned state."
            in brief
        )
        assert (
            "Latest transition: new_build_seen_db_not_migrated -> "
            "stage6_ready_and_aligned at 2026-06-10T09:30:00Z"
        ) in brief
        assert "- Recent deltas:" in brief
        assert "- Primary corrective commands:" in brief
        assert "- Supporting corrective commands:" in brief
        assert "- Monitoring commands:" in brief
        assert "label=Keep sampling" in brief
        assert "when=After alignment has been observed at least once." in brief
        assert (
            "related=inspect_transcription_stage6_handoff.py --append-snapshot --brief; inspect_transcription_stage6_snapshot_timeline.py --summary"
            in brief
        )
        assert "label=Single-record timeline" in brief
        assert "append a fresh readiness snapshot" in brief
        assert "- Record timeline preview: db_log_path_aligned" in brief
        assert "inspect_transcription_stage6_handoff.py" in brief
        assert (
            "2026-06-10T09:30:00Z | stage6_ready_and_aligned | new_build_seen_db_not_migrated -> stage6_ready_and_aligned"
            in brief
        )
        assert "delta_label=State changed" in brief
        assert "implication=This snapshot changed state" in brief
        assert "- Next actions:" in brief
        compare = module.format_stage6_handoff_compare(result)
        assert "Stage 6 Compare View" in compare
        assert "Timeline latest: stage6_ready_and_aligned" in compare
        assert "Timeline previous: new_build_seen_db_not_migrated" in compare
        assert "Delta verdict: advanced" in compare
        assert "Timeline urgency: normal" in compare
        assert "Stagnation window: 1/3" in compare
        assert "Timeline progress label: Advanced from previous snapshot" in compare
        assert "Timeline guidance label: Normal operator follow-up" in compare
        assert (
            "Timeline escalate-if: Escalate only if later samples regress, mismatch, or stop reproducing the aligned state."
            in compare
        )
        assert "Latest Snapshot:" in compare
        assert "Previous Snapshot:" in compare
        assert "Latest delta label: State changed" in compare
        assert "Latest delta implication: This snapshot changed state" in compare
        assert "Top primary corrective commands:" in compare
        assert "Top supporting corrective commands:" in compare
        assert "Top monitoring commands:" in compare
        assert "label=Keep sampling" in compare
        assert "when=After alignment has been observed at least once." in compare
        assert (
            "related=inspect_transcription_stage6_handoff.py --append-snapshot --brief; inspect_transcription_stage6_snapshot_timeline.py --summary"
            in compare
        )
        assert "label=Single-record timeline" in compare
        assert "append a fresh readiness snapshot" in compare
        assert "Record timeline preview: db_log_path_aligned" in compare
        assert "inspect_transcription_stage6_handoff.py" in compare
        assert (
            "- Latest transition: new_build_seen_db_not_migrated -> "
            "stage6_ready_and_aligned at 2026-06-10T09:30:00Z"
        ) in compare

        card = module.format_stage6_handoff_card(result)
        assert "# Stage 6 Operator Handoff" in card
        assert "- **Overall state:** `aligned_with_timeline`" in card
        assert "- **Timeline urgency:** `normal`" in card
        assert "- **Timeline stagnation window:** `1/3`" in card
        assert "- **Timeline progress label:** Advanced from previous snapshot" in card
        assert "- **Timeline guidance label:** Normal operator follow-up" in card
        assert (
            "- **Timeline escalate-if:** Escalate only if later samples regress, mismatch, or stop reproducing the aligned state."
            in card
        )
        assert "- **Primary corrective commands:**" in card
        assert "- **Supporting corrective commands:**" in card
        assert "- **Monitoring commands:**" in card
        assert "- Label: Keep sampling" in card
        assert "- When: After alignment has been observed at least once." in card
        assert (
            "- Related: inspect_transcription_stage6_handoff.py --append-snapshot --brief; inspect_transcription_stage6_snapshot_timeline.py --summary"
            in card
        )
        assert "- Label: Single-record timeline" in card
        assert (
            "- Why now: Use after corrective checks to append a fresh readiness snapshot"
            in card
        )
        assert "- **Record timeline preview:** `db_log_path_aligned`" in card
        assert "inspect_transcription_stage6_snapshot_timeline.py" in card
        assert "## Stage 6 Readiness Card" in card
        assert "## Stage 6 Status Card" in card
        assert "- **Timeline progress:** `advanced`" in card
        markdown = module.format_stage6_handoff_markdown(result)
        assert "# Stage 6 Operator Handoff Report" in markdown
        assert "## Combined Assessment" in markdown
        assert "- **Overall state:** `aligned_with_timeline`" in markdown
        assert "- **Timeline urgency:** `normal`" in markdown
        assert "- **Timeline stagnation window:** `1/3`" in markdown
        assert (
            "- **Timeline progress label:** Advanced from previous snapshot" in markdown
        )
        assert "- **Timeline guidance label:** Normal operator follow-up" in markdown
        assert (
            "- **Timeline escalate-if:** Escalate only if later samples regress, mismatch, or stop reproducing the aligned state."
            in markdown
        )
        assert "## Combined Next Actions" in markdown
        assert "## Primary Corrective Commands" in markdown
        assert "## Supporting Corrective Commands" in markdown
        assert "## Monitoring Commands" in markdown
        assert "- **Label:** Keep sampling" in markdown
        assert (
            "- **When:** After alignment has been observed at least once." in markdown
        )
        assert (
            "- **Related:** inspect_transcription_stage6_handoff.py --append-snapshot --brief; inspect_transcription_stage6_snapshot_timeline.py --summary"
            in markdown
        )
        assert "- **Label:** Single-record timeline" in markdown
        assert "append a fresh readiness snapshot" in markdown
        assert "- **Record timeline preview:** `db_log_path_aligned`" in markdown
        assert "inspect_transcription_stage6_handoff.py" in markdown
        assert "## Recent Snapshot Deltas" in markdown
        assert "Delta label: State changed" in markdown
        assert "Implication: This snapshot changed state" in markdown
        assert "# Stage 6 Readiness Report" in markdown
        assert "## Timeline Report" in markdown
        assert "### Timeline Summary" in markdown
        assert "```text" in markdown
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


def test_stage6_handoff_handles_readiness_without_timeline() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    db_path = (base_dir / f"stage6_handoff_no_timeline_{token}.db").resolve()
    logs_dir = (base_dir / f"stage6_handoff_no_timeline_logs_{token}").resolve()
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

        result = module.inspect_transcription_stage6_handoff(
            db_path=db_path,
            logs_path=logs_dir,
            timestamp_from="2026-06-09T16:06:10",
        )

        combined = result["combined_assessment"]
        assert combined["overall_state"] == "readiness_only_no_timeline"
        assert combined["timeline_state"] is None
        assert "no snapshot timeline" in combined["summary"].lower()
        assert result["timeline"] is None
        envelope = dict(result["operator_handoff_envelope"] or {})
        assert envelope["version"] == 1
        assert envelope["overall"]["timeline_available"] is False
        assert envelope["timeline"]["progress"]["verdict"] == "no_data"
        assert envelope["timeline"]["stagnation"]["verdict"] == "no_data"
        assert envelope["timeline"]["guidance"]["urgency"] == "unknown"
        assert envelope["timeline"]["recent_deltas"] == []
        assert envelope["actions"][0]["id"] == "start_new_build"
        assert envelope["actions"][0]["related_commands"][0]["id"] == "schema_startup"
        assert any(
            "inspect_recent_transcription_path_logs.py" in command
            for command in combined["follow_up_commands"]
        )

        card = module.format_stage6_handoff_card(result)
        assert "- **Timeline state:** `none`" in card
        assert "No snapshot timeline was supplied." in card
        brief = module.format_stage6_handoff_brief(result)
        assert "Timeline detail: No snapshot timeline was supplied." in brief
        compare = module.format_stage6_handoff_compare(result)
        assert "Timeline latest: none" in compare
        assert "Previous Snapshot:" in compare
        assert "- no timeline supplied" in compare
        assert result["recent_snapshot_digest"] == []
        markdown = module.format_stage6_handoff_markdown(result)
        assert "## Timeline Report" in markdown
        assert "No snapshot timeline was supplied." in markdown
    finally:
        if db_path.exists():
            db_path.unlink()
        for path in logs_dir.glob("*"):
            path.unlink()
        logs_dir.rmdir()


def test_stage6_handoff_flags_stuck_partial_readiness() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    db_path = (base_dir / f"stage6_handoff_stuck_{token}.db").resolve()
    logs_dir = (base_dir / f"stage6_handoff_stuck_logs_{token}").resolve()
    snapshot_path = (
        base_dir / "snapshots" / f"stage6_handoff_stuck_{token}.jsonl"
    ).resolve()
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
        history_storage_service = (
            module.inspect_transcription_stage6_readiness.__globals__[
                "HistoryStorageService"
            ]
        )
        expected_version = history_storage_service._HISTORY_SCHEMA_EXPECTATION_VERSION
        expected_signature = history_storage_service.history_schema_signature()
        _write_log(
            logs_dir / "app.log",
            [
                (
                    "2026-06-10 09:00:00 | INFO     | audio        | [audio] | "
                    "Audio: History schema expectations declared | | "
                    f'{{"required_columns":["streaming_mode","transcription_path",'
                    f'"transcription_decision_reason"],"required_column_count":3,'
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
        _write_snapshots(
            snapshot_path,
            [
                (
                    '{"observed_at_utc":"2026-06-10T09:30:00Z",'
                    '"diagnosis_state":"partial_stage6_readiness",'
                    '"alignment_state":"runtime_logs_without_db_rows",'
                    '"issue_summary":"record_id=rec-log-1 runtime log exists without DB row yet: log_path=cloud_file_long_recording, log_reason=long_cloud_recording_prefer_file",'
                    '"newest_record_id_hint":"rec-log-1",'
                    '"oneline":"state=partial_stage6_readiness"}'
                ),
                (
                    '{"observed_at_utc":"2026-06-10T09:35:00Z",'
                    '"diagnosis_state":"partial_stage6_readiness",'
                    '"alignment_state":"runtime_logs_without_db_rows",'
                    '"issue_summary":"record_id=rec-log-1 runtime log exists without DB row yet: log_path=cloud_file_long_recording, log_reason=long_cloud_recording_prefer_file",'
                    '"newest_record_id_hint":"rec-log-1",'
                    '"oneline":"state=partial_stage6_readiness"}'
                ),
                (
                    '{"observed_at_utc":"2026-06-10T09:40:00Z",'
                    '"diagnosis_state":"partial_stage6_readiness",'
                    '"alignment_state":"runtime_logs_without_db_rows",'
                    '"issue_summary":"record_id=rec-log-1 runtime log exists without DB row yet: log_path=cloud_file_long_recording, log_reason=long_cloud_recording_prefer_file",'
                    '"newest_record_id_hint":"rec-log-1",'
                    '"oneline":"state=partial_stage6_readiness"}'
                ),
            ],
        )

        result = module.inspect_transcription_stage6_handoff(
            db_path=db_path,
            logs_path=logs_dir,
            timestamp_from="2026-06-09T16:06:10",
            snapshot_path=snapshot_path,
        )

        combined = result["combined_assessment"]
        assert combined["overall_state"] == "stuck_follow_up_required"
        assert combined["timeline_stagnation_verdict"] == "stuck"
        assert combined["timeline_urgency"] == "attention"
        assert combined["timeline_consecutive_count"] == 3
        assert combined["timeline_stagnation_threshold"] == 3
        assert (
            "inspect_transcription_path_observability.py"
            in combined["primary_corrective_commands"][0]
        )
        assert (
            "inspect_transcription_record_timeline.py"
            in combined["primary_corrective_commands"][1]
        )
        assert (
            "inspect_recent_transcription_path_logs.py"
            in combined["supporting_corrective_commands"][0]
        )
        assert (
            "inspect_recent_transcription_paths.py"
            in combined["supporting_corrective_commands"][1]
        )
        assert (
            combined["primary_corrective_command_details"][0]["category"]
            == "path_observability"
        )
        assert (
            "post-cutoff path/reason alignment"
            in (combined["primary_corrective_command_details"][0]["reason"])
        )
        assert (
            combined["supporting_corrective_command_details"][0]["label"]
            == "Recent runtime logs"
        )
        assert any(
            "inspect_transcription_record_timeline.py" in command
            for command in combined["corrective_commands"]
        )
        assert any(
            "inspect_transcription_stage6_handoff.py" in command
            and "--append-snapshot" in command
            for command in combined["monitoring_commands"]
        )
        assert (
            "inspect_transcription_stage6_handoff.py"
            not in combined["follow_up_commands"][0]
        )
        assert "stuck" in combined["summary"]
        assert "record_id=rec-log-1 runtime log exists without DB row yet" in (
            combined["primary_blocker"] or ""
        )
        assert any(
            "Confirm the app and inspected history.db refer to the same real storage path."
            == step
            for step in combined["next_actions"]
        )
        assert any(
            step.startswith(
                "This state has repeated enough times to be treated as stuck"
            )
            for step in combined["next_actions"]
        )
        assert combined["next_action_details"][0]["category"] == "stuck_prioritize"
        assert (
            combined["next_action_details"][0]["when_to_run"]
            == "Now, before appending another snapshot."
        )
        envelope = dict(result["operator_handoff_envelope"] or {})
        assert envelope["version"] == 1
        assert envelope["overall"]["timeline_available"] is True
        assert envelope["actions"][0]["id"] == "stuck_prioritize"
        assert envelope["actions"][0]["phase"] == "prioritize"
        assert (
            envelope["actions"][0]["related_commands"][0]["id"] == "path_observability"
        )
        assert (
            envelope["actions"][0]["related_commands"][0]["phase"]
            == "primary_corrective"
        )
        assert (
            envelope["commands"]["primary_corrective"][0]["id"] == "path_observability"
        )
        assert envelope["commands"]["primary_corrective"][0]["priority"] == 1
        assert envelope["commands"]["monitoring"][0]["id"] == "append_snapshot"
        assert envelope["timeline"]["progress"]["label"] == "No state change yet"
        assert (
            envelope["timeline"]["guidance"]["label"] == "Attention-required follow-up"
        )
        assert (
            envelope["timeline"]["recent_deltas"][0]["id"]
            == "recent_delta:2026-06-10T09:40:00Z"
        )
        assert envelope["timeline"]["recent_deltas"][0]["priority"] == 1
        assert envelope["timeline"]["recent_deltas"][0]["delta_kind"] == "unchanged"
        assert any(
            detail["category"] == "confirm_storage_path"
            and detail["label"] == "Confirm storage path"
            and "same storage target" in detail["reason"]
            for detail in combined["next_action_details"]
        )

        summary = module.format_stage6_handoff_summary(result)
        assert "Timeline current state elapsed: 10m 0s" in summary
        assert "Timeline urgency: attention" in summary
        assert "Timeline stagnation window: 3/3" in summary
        assert "Timeline progress label: No state change yet" in summary
        assert "Timeline guidance label: Attention-required follow-up" in summary
        assert (
            "Timeline escalate-if: Escalate if the prioritized corrective commands still do not produce a new state or stronger evidence."
            in summary
        )
        assert "elapsed_since_previous=5m 0s" in summary
        assert "Record timeline preview: runtime_logs_without_db_record" in summary
        assert "Primary Corrective Commands:" in summary
        assert "Supporting Corrective Commands:" in summary
        assert "Monitoring Commands:" in summary
        assert "delta_label=State unchanged" in summary
        assert (
            "escalate_if=Escalate now unless the next corrective pass produces a different state."
            in summary
        )
        assert "label=Prioritize corrective step" in summary
        assert "when=Now, before appending another snapshot." in summary
        assert (
            "related=inspect_transcription_path_observability.py; inspect_transcription_record_timeline.py"
            in summary
        )
        assert "label=Path observability" in summary
        assert "post-cutoff path/reason alignment" in summary

        brief = module.format_stage6_handoff_brief(result)
        assert "Timeline current state elapsed: 10m 0s" in brief
        assert "Timeline urgency: attention" in brief
        assert "Stagnation window: 3/3" in brief
        assert "Timeline progress label: No state change yet" in brief
        assert "Timeline guidance label: Attention-required follow-up" in brief
        assert (
            "Timeline escalate-if: Escalate if the prioritized corrective commands still do not produce a new state or stronger evidence."
            in brief
        )
        assert "elapsed_since_previous=5m 0s" in brief
        assert "Record timeline preview: runtime_logs_without_db_record" in brief
        assert "- Primary corrective commands:" in brief
        assert "- Supporting corrective commands:" in brief
        assert "- Monitoring commands:" in brief
        assert "delta_label=State unchanged" in brief
        assert "label=Prioritize corrective step" in brief
        assert "when=Now, before appending another snapshot." in brief
        assert (
            "related=inspect_transcription_path_observability.py; inspect_transcription_record_timeline.py"
            in brief
        )
        assert "label=Path observability" in brief
        assert "post-cutoff path/reason alignment" in brief

        compare = module.format_stage6_handoff_compare(result)
        assert "Timeline current state elapsed: 10m 0s" in compare
        assert "Timeline urgency: attention" in compare
        assert "Stagnation window: 3/3" in compare
        assert "Timeline progress label: No state change yet" in compare
        assert "Timeline guidance label: Attention-required follow-up" in compare
        assert (
            "Timeline escalate-if: Escalate if the prioritized corrective commands still do not produce a new state or stronger evidence."
            in compare
        )
        assert "Elapsed since previous snapshot: 5m 0s" in compare
        assert "Record timeline preview: runtime_logs_without_db_record" in compare
        assert "Latest delta label: State unchanged" in compare
        assert "Top primary corrective commands:" in compare
        assert "Top supporting corrective commands:" in compare
        assert "Top monitoring commands:" in compare
        assert "label=Prioritize corrective step" in compare
        assert "when=Now, before appending another snapshot." in compare
        assert (
            "related=inspect_transcription_path_observability.py; inspect_transcription_record_timeline.py"
            in compare
        )
        assert "label=Path observability" in compare
        assert "post-cutoff path/reason alignment" in compare

        card = module.format_stage6_handoff_card(result)
        assert "- **Timeline current state elapsed:** `10m 0s`" in card
        assert "- **Timeline urgency:** `attention`" in card
        assert "- **Timeline stagnation window:** `3/3`" in card
        assert "- **Timeline progress label:** No state change yet" in card
        assert "- **Timeline guidance label:** Attention-required follow-up" in card
        assert (
            "- **Timeline escalate-if:** Escalate if the prioritized corrective commands still do not produce a new state or stronger evidence."
            in card
        )
        assert "- **Record timeline preview:** `runtime_logs_without_db_record`" in card
        assert "- **Primary corrective commands:**" in card
        assert "- **Supporting corrective commands:**" in card
        assert "- **Monitoring commands:**" in card
        assert "- Label: Prioritize corrective step" in card
        assert "- When: Now, before appending another snapshot." in card
        assert (
            "- Related: inspect_transcription_path_observability.py; inspect_transcription_record_timeline.py"
            in card
        )
        assert "- Label: Path observability" in card
        assert (
            "- Why now: This state is driven by post-cutoff path/reason alignment"
            in card
        )

        markdown = module.format_stage6_handoff_markdown(result)
        assert "- **Timeline current state elapsed:** 10m 0s" in markdown
        assert "- **Timeline urgency:** `attention`" in markdown
        assert "- **Timeline stagnation window:** `3/3`" in markdown
        assert "- **Timeline progress label:** No state change yet" in markdown
        assert "- **Timeline guidance label:** Attention-required follow-up" in markdown
        assert (
            "- **Timeline escalate-if:** Escalate if the prioritized corrective commands still do not produce a new state or stronger evidence."
            in markdown
        )
        assert "  - Elapsed since previous: 5m 0s" in markdown
        assert (
            "- **Record timeline preview:** `runtime_logs_without_db_record`"
            in markdown
        )
        assert "## Primary Corrective Commands" in markdown
        assert "## Supporting Corrective Commands" in markdown
        assert "## Monitoring Commands" in markdown
        assert "Delta label: State unchanged" in markdown
        assert (
            "Escalate if: Escalate now unless the next corrective pass produces a different state."
            in markdown
        )
        assert "- **Label:** Prioritize corrective step" in markdown
        assert "- **When:** Now, before appending another snapshot." in markdown
        assert (
            "- **Related:** inspect_transcription_path_observability.py; inspect_transcription_record_timeline.py"
            in markdown
        )
        assert "- **Label:** Path observability" in markdown
        assert "post-cutoff path/reason alignment" in markdown
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


def test_stage6_handoff_can_append_snapshot_before_timeline() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    db_path = (base_dir / f"stage6_handoff_append_{token}.db").resolve()
    logs_dir = (base_dir / f"stage6_handoff_append_logs_{token}").resolve()
    snapshot_path = (
        base_dir / "snapshots" / f"stage6_handoff_append_{token}.jsonl"
    ).resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        _create_history_db(
            db_path,
            include_decision_reason=True,
            rows=[
                (
                    "rec-append-1",
                    "2026-06-10T09:30:00",
                    "groq",
                    120.0,
                    "chunked",
                    "cloud_file_long_recording",
                    "long_cloud_recording_prefer_file",
                ),
            ],
        )
        history_storage_service = (
            module.inspect_transcription_stage6_readiness.__globals__[
                "HistoryStorageService"
            ]
        )
        expected_version = history_storage_service._HISTORY_SCHEMA_EXPECTATION_VERSION
        expected_signature = history_storage_service.history_schema_signature()
        _write_log(
            logs_dir / "app.log",
            [
                (
                    "2026-06-10 09:00:00 | INFO     | audio        | [audio] | "
                    "Audio: History schema expectations declared | | "
                    f'{{"required_columns":["streaming_mode","transcription_path",'
                    f'"transcription_decision_reason"],"required_column_count":3,'
                    f'"history_schema_expectation_version":{expected_version},'
                    f'"history_schema_signature":"{expected_signature}",'
                    f'"expects_transcription_path":true,'
                    f'"expects_transcription_decision_reason":true}}'
                ),
                (
                    "2026-06-10 09:30:00 | INFO     | audio        | [audio] | "
                    "Audio: Transcription path decision | | "
                    '{"record_id":"rec-append-1","selected_path":"cloud_file_long_recording",'
                    '"decision_reason":"long_cloud_recording_prefer_file"}'
                ),
            ],
        )
        _write_snapshots(
            snapshot_path,
            [
                (
                    '{"observed_at_utc":"2026-06-10T09:00:00Z",'
                    '"diagnosis_state":"new_build_seen_db_not_migrated",'
                    '"alignment_state":"no_post_cutoff_runtime_or_db_activity",'
                    '"issue_summary":null,'
                    '"oneline":"state=new_build_seen_db_not_migrated"}'
                ),
            ],
        )

        result = module.inspect_transcription_stage6_handoff(
            db_path=db_path,
            logs_path=logs_dir,
            timestamp_from="2026-06-09T16:06:10",
            snapshot_path=snapshot_path,
            append_snapshot=True,
        )

        appended_snapshot = dict(result["appended_snapshot"] or {})
        assert appended_snapshot["diagnosis_state"] == "stage6_ready_and_aligned"
        assert result["timeline"]["snapshot_count"] == 2
        assert (
            result["timeline"]["latest_diagnosis_state"] == "stage6_ready_and_aligned"
        )
        assert len(result["recent_snapshot_digest"]) == 2
        assert any(
            "inspect_transcription_stage6_handoff.py" in command
            and "--append-snapshot" in command
            for command in result["snapshot_workflow_commands"]
        )
        assert any(
            "inspect_transcription_stage6_snapshot_timeline.py" in command
            for command in result["snapshot_workflow_commands"]
        )

        lines = snapshot_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        loaded = json.loads(lines[-1])
        assert loaded["diagnosis_state"] == "stage6_ready_and_aligned"

        summary = module.format_stage6_handoff_summary(result)
        assert "Appended Snapshot:" in summary
        assert "Diagnosis state: stage6_ready_and_aligned" in summary
        assert "inspect_transcription_stage6_snapshot_timeline.py" in summary

        brief = module.format_stage6_handoff_brief(result)
        assert "Appended snapshot: stage6_ready_and_aligned at " in brief
        assert "inspect_transcription_stage6_handoff.py" in brief
        compare = module.format_stage6_handoff_compare(result)
        assert "Appended snapshot: stage6_ready_and_aligned at " in compare
        card = module.format_stage6_handoff_card(result)
        assert "- **Appended snapshot diagnosis:** `stage6_ready_and_aligned`" in card
        markdown = module.format_stage6_handoff_markdown(result)
        assert "## Appended Snapshot" in markdown
        assert "- **Diagnosis state:** `stage6_ready_and_aligned`" in markdown
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


def test_stage6_handoff_requires_snapshot_path_when_appending() -> None:
    module = _load_module()
    try:
        module.inspect_transcription_stage6_handoff(
            db_path=Path("unused.db"),
            logs_path=Path("unused_logs"),
            append_snapshot=True,
        )
    except ValueError as exc:
        assert "snapshot_path is required" in str(exc)
    else:
        raise AssertionError(
            "Expected ValueError when append_snapshot=True without snapshot_path"
        )
