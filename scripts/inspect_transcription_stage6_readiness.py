"""Summarize Stage 6 real-world transcription observability readiness.

This single-entry helper combines:

- history schema inspection
- runtime build/schema expectation evidence
- post-cutoff transcription path/reason observability

Usage:
    uv run python scripts/inspect_transcription_stage6_readiness.py
    uv run python scripts/inspect_transcription_stage6_readiness.py --timestamp-from 2026-06-09T16:06:10
    uv run python scripts/inspect_transcription_stage6_readiness.py --snapshot-out quality_audit/stage6-readiness.jsonl
    uv run python scripts/inspect_transcription_stage6_readiness.py --oneline
    uv run python scripts/inspect_transcription_stage6_readiness.py --summary
    uv run python scripts/inspect_transcription_stage6_readiness.py --markdown
    uv run python scripts/inspect_transcription_stage6_readiness.py --card
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from inspect_history_schema import inspect_or_upgrade_history_schema
from inspect_transcription_path_observability import (
    inspect_transcription_path_observability,
)
from inspect_transcription_record_timeline import (
    format_transcription_record_timeline_oneline,
    inspect_transcription_record_timeline,
)
from sonicinput.core.services.storage.history_storage_service import (
    HistoryStorageService,
)


def _default_history_db() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "SonicInput" / "history" / "history.db"
    return Path.home() / "AppData" / "Roaming" / "SonicInput" / "history" / "history.db"


def _default_logs_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "SonicInput" / "logs"
    return Path.home() / "AppData" / "Roaming" / "SonicInput" / "logs"


def _format_stage6_command(
    script_name: str,
    *,
    db_path: Path,
    logs_path: Path | None = None,
    timestamp_from: str | None = None,
    limit: int | None = None,
    record_id: str | None = None,
) -> str:
    parts = [
        "uv run --cache-dir .\\.uv_cache python",
        f"scripts/{script_name}",
        f'--db "{db_path}"',
    ]
    if logs_path is not None:
        parts.append(f'--logs "{logs_path}"')
    if timestamp_from:
        parts.append(f"--timestamp-from {timestamp_from}")
    if limit is not None:
        parts.append(f"--limit {limit}")
    if record_id:
        parts.append(f"--record-id {record_id}")
    return " ".join(parts)


def _merge_unique_commands(*command_groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in command_groups:
        for command in group:
            normalized = " ".join(str(command or "").split())
            if not normalized or normalized in seen:
                continue
            merged.append(command)
            seen.add(normalized)
    return merged


def _build_runbook(
    *,
    diagnosis_state: str,
    db_path: Path,
    logs_path: Path,
    timestamp_from: str | None,
    limit: int,
    newest_record_id: str | None,
    observability_guidance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_readiness_command = _format_stage6_command(
        "inspect_transcription_stage6_readiness.py",
        db_path=db_path,
        logs_path=logs_path,
        timestamp_from=timestamp_from,
        limit=limit,
    )
    schema_command = _format_stage6_command(
        "inspect_history_schema.py",
        db_path=db_path,
        logs_path=logs_path,
    )
    observability_command = _format_stage6_command(
        "inspect_transcription_path_observability.py",
        db_path=db_path,
        logs_path=logs_path,
        timestamp_from=timestamp_from,
        limit=limit,
    )
    timeline_command = (
        _format_stage6_command(
            "inspect_transcription_record_timeline.py",
            db_path=db_path,
            logs_path=logs_path,
            record_id=newest_record_id,
        )
        if newest_record_id
        else None
    )
    observability_guidance = dict(observability_guidance or {})
    observability_steps = list(observability_guidance.get("recommended_steps") or [])
    observability_follow_up_commands = list(
        observability_guidance.get("follow_up_commands") or []
    )

    steps: list[str]
    follow_up_commands = _merge_unique_commands(
        [schema_command, observability_command],
        observability_follow_up_commands,
    )
    if diagnosis_state == "waiting_for_new_build_session":
        steps = [
            "Start a newer SonicInput build that should include the latest history schema expectations.",
            "After the app finishes startup, rerun the readiness inspector to confirm the expectation event appears in logs.",
            "Do not rely on old log files; confirm a fresh app session timestamp is visible.",
        ]
    elif diagnosis_state == "new_build_seen_db_not_migrated":
        steps = [
            "Confirm the app session and inspected DB path refer to the same real history.db file.",
            "Check HistoryStorageService startup/runtime logs for migration failures or unexpected alternate storage paths.",
            "Rerun the readiness inspector after resolving the migration gap.",
        ]
    elif diagnosis_state == "schema_ready_waiting_for_post_cutoff_sample":
        steps = observability_steps or [
            "Generate one new real transcription after the cutoff timestamp.",
            "Rerun the readiness inspector to see whether path/reason alignment becomes observable.",
            "If the new sample appears, use the timeline inspector for the newest record_id when deeper debugging is needed.",
        ]
        if timeline_command is not None:
            follow_up_commands = _merge_unique_commands(
                follow_up_commands,
                [timeline_command],
            )
    elif diagnosis_state in {"post_cutoff_reason_mismatch", "post_cutoff_path_mismatch"}:
        steps = observability_steps or [
            "Identify the newest shared record_id from the observability output.",
            "Run the single-record timeline inspector for that record_id.",
            "Compare the persisted DB fields against the latest runtime path decision/fallback event.",
        ]
        if timeline_command is not None:
            follow_up_commands = _merge_unique_commands([timeline_command], follow_up_commands)
    elif diagnosis_state == "stage6_ready_and_aligned":
        steps = observability_steps or [
            "Keep sampling newer real records to increase confidence.",
            "Use the timeline inspector only when a future record deviates from the aligned baseline.",
        ]
        if timeline_command is not None:
            follow_up_commands = _merge_unique_commands(
                follow_up_commands,
                [timeline_command],
            )
    else:
        steps = observability_steps or [
            "Inspect the schema and observability outputs side by side.",
            "Use the newest real record_id for a timeline drill-down when available.",
            "Rerun the readiness inspector after each external state change.",
        ]
        if timeline_command is not None:
            follow_up_commands = _merge_unique_commands(
                follow_up_commands,
                [timeline_command],
            )

    return {
        "recommended_steps": steps,
        "rerun_readiness_command": base_readiness_command,
        "follow_up_commands": follow_up_commands,
    }


def _build_focus_record(
    *,
    alignment_state: str,
    alignment: dict[str, Any],
    observability_result: dict[str, Any],
) -> dict[str, Any] | None:
    mismatched_records = list(alignment.get("mismatched_records") or [])
    decision_reason_mismatched_records = list(
        alignment.get("decision_reason_mismatched_records") or []
    )
    matched_records = list(alignment.get("matched_records") or [])
    db_records = list(observability_result.get("db", {}).get("records", []) or [])
    log_entries = list(observability_result.get("logs", {}).get("entries", []) or [])

    if alignment_state == "db_log_path_mismatch" and mismatched_records:
        record = dict(mismatched_records[0])
        record["source"] = "shared_path_mismatch"
        return record
    if (
        alignment_state == "db_log_decision_reason_mismatch"
        and decision_reason_mismatched_records
    ):
        record = dict(decision_reason_mismatched_records[0])
        record["source"] = "shared_reason_mismatch"
        return record
    if alignment_state == "db_log_paths_and_reasons_aligned" and matched_records:
        record = dict(matched_records[0])
        record["source"] = "shared_aligned"
        return record
    if alignment_state == "runtime_logs_without_db_rows" and log_entries:
        entry = dict(log_entries[0])
        return {
            "source": "runtime_log_only",
            "record_id": entry.get("record_id"),
            "db_timestamp": None,
            "log_timestamp": entry.get("timestamp"),
            "db_transcription_path": None,
            "db_transcription_decision_reason": None,
            "log_selected_path": entry.get("selected_path"),
            "log_decision_reason": entry.get("decision_reason"),
            "paths_match": None,
            "decision_reasons_match": None,
        }
    if alignment_state == "db_rows_without_runtime_logs" and db_records:
        record = dict(db_records[0])
        return {
            "source": "db_row_only",
            "record_id": record.get("record_id"),
            "db_timestamp": record.get("timestamp"),
            "log_timestamp": None,
            "db_transcription_path": record.get("transcription_path"),
            "db_transcription_decision_reason": record.get(
                "transcription_decision_reason"
            ),
            "log_selected_path": None,
            "log_decision_reason": None,
            "paths_match": None,
            "decision_reasons_match": None,
        }
    if alignment_state == "no_shared_record_ids_yet":
        if log_entries:
            entry = dict(log_entries[0])
            return {
                "source": "pending_correlation_runtime_log",
                "record_id": entry.get("record_id"),
                "db_timestamp": None,
                "log_timestamp": entry.get("timestamp"),
                "db_transcription_path": None,
                "db_transcription_decision_reason": None,
                "log_selected_path": entry.get("selected_path"),
                "log_decision_reason": entry.get("decision_reason"),
                "paths_match": None,
                "decision_reasons_match": None,
            }
        if db_records:
            record = dict(db_records[0])
            return {
                "source": "pending_correlation_db_row",
                "record_id": record.get("record_id"),
                "db_timestamp": record.get("timestamp"),
                "log_timestamp": None,
                "db_transcription_path": record.get("transcription_path"),
                "db_transcription_decision_reason": record.get(
                    "transcription_decision_reason"
                ),
                "log_selected_path": None,
                "log_decision_reason": None,
                "paths_match": None,
                "decision_reasons_match": None,
            }
    return None


def _build_issue_summary(
    *,
    alignment_state: str,
    focus_record: dict[str, Any] | None,
) -> str | None:
    if not focus_record:
        return None

    record_id = focus_record.get("record_id") or "unknown"
    db_path = focus_record.get("db_transcription_path") or "none"
    log_path = focus_record.get("log_selected_path") or "none"
    db_reason = focus_record.get("db_transcription_decision_reason") or "none"
    log_reason = focus_record.get("log_decision_reason") or "none"

    if alignment_state == "db_log_path_mismatch":
        return f"record_id={record_id} path mismatch: db={db_path} vs log={log_path}"
    if alignment_state == "db_log_decision_reason_mismatch":
        return (
            f"record_id={record_id} decision reason mismatch: "
            f"db={db_reason} vs log={log_reason}"
        )
    if alignment_state == "runtime_logs_without_db_rows":
        return (
            f"record_id={record_id} runtime log exists without DB row yet: "
            f"log_path={log_path}, log_reason={log_reason}"
        )
    if alignment_state == "db_rows_without_runtime_logs":
        return (
            f"record_id={record_id} DB row exists without runtime log yet: "
            f"db_path={db_path}, db_reason={db_reason}"
        )
    if alignment_state == "no_shared_record_ids_yet":
        return (
            f"record_id={record_id} post-cutoff evidence exists but has not "
            "correlated across DB/log sources yet"
        )
    if alignment_state == "db_log_paths_and_reasons_aligned":
        return (
            f"record_id={record_id} aligned: "
            f"path={db_path}, decision_reason={db_reason}"
        )
    return None


def _build_record_timeline_preview(
    *,
    db_path: Path,
    logs_path: Path,
    record_id: str | None,
) -> dict[str, Any] | None:
    if record_id in (None, ""):
        return None
    timeline_result = inspect_transcription_record_timeline(
        db_path=db_path,
        logs_path=logs_path,
        record_id=str(record_id),
    )
    event_flow = dict(timeline_result.get("event_flow") or {})
    latest_terminal_event = dict(event_flow.get("latest_terminal_event") or {})
    return {
        "record_id": str(record_id),
        "diagnosis_state": dict(timeline_result.get("diagnosis") or {}).get("state"),
        "diagnosis_message": dict(timeline_result.get("diagnosis") or {}).get("message"),
        "issue_summary": timeline_result.get("issue_summary"),
        "history_record_found": timeline_result.get("history_record_found"),
        "runtime_log_event_count": event_flow.get("event_count", 0),
        "path_event_count": event_flow.get("path_event_count", 0),
        "fallback_event_count": event_flow.get("fallback_event_count", 0),
        "latest_terminal_event": latest_terminal_event or None,
        "oneline": format_transcription_record_timeline_oneline(timeline_result),
    }


def _summarize_readiness(
    *,
    expected_version: int,
    expected_signature: str,
    schema_result: dict[str, Any],
    observability_result: dict[str, Any],
    db_path: Path,
    logs_path: Path,
    timestamp_from: str | None,
    limit: int,
) -> dict[str, Any]:
    runtime_logs = dict(schema_result.get("runtime_logs") or {})
    after_schema = dict(schema_result.get("after") or {})
    alignment = dict(observability_result.get("alignment") or {})
    alignment_guidance = dict(alignment.get("operator_guidance") or {})
    alignment_state = str(alignment.get("diagnosis", {}).get("state") or "")
    focus_record = (
        dict(alignment.get("focus_record") or {})
        if alignment.get("focus_record") is not None
        else None
    )
    newest_record_id = focus_record.get("record_id") if focus_record else None

    expectation_versions_seen = list(runtime_logs.get("expectation_versions_seen") or [])
    schema_signatures_seen = list(runtime_logs.get("schema_signatures_seen") or [])

    runtime_declares_current_expectation_version = expected_version in expectation_versions_seen
    runtime_declares_current_signature = expected_signature in schema_signatures_seen
    db_has_decision_reason_column = (
        after_schema.get("has_transcription_decision_reason_column") is True
    )
    runtime_has_decision_reason_expectation = (
        runtime_logs.get("has_transcription_decision_reason_expectation_event") is True
    )
    runtime_has_decision_reason_upgrade_event = (
        runtime_logs.get("has_transcription_decision_reason_upgrade_event") is True
    )
    post_cutoff_activity_present = not (
        alignment_state == "no_post_cutoff_runtime_or_db_activity"
    )
    issue_summary = alignment.get("issue_summary")

    if not runtime_declares_current_expectation_version and not runtime_declares_current_signature:
        diagnosis = {
            "state": "waiting_for_new_build_session",
            "message": (
                "No runtime log evidence shows a build that declares the current "
                "history schema expectation version/signature yet."
            ),
            "next_action": (
                "Start a newer app build and rerun this inspector before expecting "
                "decision_reason persistence evidence."
            ),
        }
    elif not db_has_decision_reason_column:
        diagnosis = {
            "state": "new_build_seen_db_not_migrated",
            "message": (
                "Runtime evidence shows a newer build session, but the real history DB "
                "still lacks transcription_decision_reason."
            ),
            "next_action": (
                "Inspect startup/runtime errors around HistoryStorageService and confirm "
                "the DB file being migrated is the same one being inspected."
            ),
        }
    elif not post_cutoff_activity_present:
        diagnosis = {
            "state": "schema_ready_waiting_for_post_cutoff_sample",
            "message": (
                "The runtime build and DB schema appear ready, but there is still no "
                "post-cutoff transcription sample to validate end-to-end persistence."
            ),
            "next_action": (
                "Generate one new real transcription after the cutoff timestamp and rerun "
                "this inspector."
            ),
        }
    elif alignment_state == "db_log_paths_and_reasons_aligned":
        diagnosis = {
            "state": "stage6_ready_and_aligned",
            "message": (
                "Post-cutoff runtime and DB evidence show aligned transcription path "
                "and decision reason."
            ),
            "next_action": "Continue sampling more real records if broader confidence is needed.",
        }
    elif alignment_state == "db_log_decision_reason_mismatch":
        diagnosis = {
            "state": "post_cutoff_reason_mismatch",
            "message": (
                "A post-cutoff record exists, and path alignment succeeded, but the "
                "persisted decision reason differs from runtime logs."
            ),
            "next_action": (
                "Use the record timeline inspector on the affected record_id and trace "
                "where the final decision reason diverges."
            ),
        }
    elif alignment_state == "db_log_path_mismatch":
        diagnosis = {
            "state": "post_cutoff_path_mismatch",
            "message": (
                "A post-cutoff record exists, but persisted transcription_path differs "
                "from the runtime selected_path."
            ),
            "next_action": (
                "Use the record timeline inspector on the mismatched record_id and verify "
                "the final saved path."
            ),
        }
    else:
        diagnosis = {
            "state": "partial_stage6_readiness",
            "message": (
                "The runtime build and schema are partially ready, but the current "
                "post-cutoff evidence still needs correlation or debugging."
            ),
            "next_action": (
                "Inspect the readiness summary fields and fall back to the single-record "
                "timeline tool for the newest record_id."
            ),
        }

    runbook = _build_runbook(
        diagnosis_state=diagnosis["state"],
        db_path=db_path,
        logs_path=logs_path,
        timestamp_from=timestamp_from,
        limit=limit,
        newest_record_id=(
            str(newest_record_id) if newest_record_id not in (None, "") else None
        ),
        observability_guidance=alignment_guidance,
    )
    record_timeline_preview = _build_record_timeline_preview(
        db_path=db_path,
        logs_path=logs_path,
        record_id=(str(newest_record_id) if newest_record_id not in (None, "") else None),
    )

    return {
        "repo_expected_history_schema_expectation_version": expected_version,
        "repo_expected_history_schema_signature": expected_signature,
        "runtime_declares_current_expectation_version": (
            runtime_declares_current_expectation_version
        ),
        "runtime_declares_current_signature": runtime_declares_current_signature,
        "runtime_has_decision_reason_expectation_event": (
            runtime_has_decision_reason_expectation
        ),
        "runtime_has_decision_reason_upgrade_event": runtime_has_decision_reason_upgrade_event,
        "db_has_transcription_decision_reason_column": db_has_decision_reason_column,
        "post_cutoff_activity_present": post_cutoff_activity_present,
        "alignment_state": alignment_state,
        "newest_record_id_hint": newest_record_id,
        "focus_record": focus_record,
        "issue_summary": issue_summary,
        "record_timeline_preview": record_timeline_preview,
        "diagnosis": diagnosis,
        "runbook": runbook,
    }


def inspect_transcription_stage6_readiness(
    *,
    db_path: Path,
    logs_path: Path,
    timestamp_from: str | None = None,
    limit: int = 20,
    long_recording_cloud_candidates_only: bool = False,
) -> dict[str, Any]:
    schema_result = inspect_or_upgrade_history_schema(
        db_path,
        upgrade=False,
        logs_path=logs_path,
    )
    observability_result = inspect_transcription_path_observability(
        db_path=db_path,
        logs_path=logs_path,
        timestamp_from=timestamp_from,
        limit=limit,
        long_recording_cloud_candidates_only=long_recording_cloud_candidates_only,
    )
    expected_version = HistoryStorageService._HISTORY_SCHEMA_EXPECTATION_VERSION
    expected_signature = HistoryStorageService.history_schema_signature()
    readiness = _summarize_readiness(
        expected_version=expected_version,
        expected_signature=expected_signature,
        schema_result=schema_result,
        observability_result=observability_result,
        db_path=db_path,
        logs_path=logs_path,
        timestamp_from=timestamp_from,
        limit=limit,
    )

    return {
        "timestamp_from": timestamp_from,
        "limit": limit,
        "long_recording_cloud_candidates_only": long_recording_cloud_candidates_only,
        "repo_expectations": {
            "history_schema_expectation_version": expected_version,
            "history_schema_signature": expected_signature,
            "required_columns": sorted(
                HistoryStorageService._history_record_required_columns().keys()
            ),
        },
        "schema": schema_result,
        "observability": observability_result,
        "readiness": readiness,
    }


def format_stage6_readiness_summary(result: dict[str, Any]) -> str:
    readiness = dict(result.get("readiness") or {})
    diagnosis = dict(readiness.get("diagnosis") or {})
    runbook = dict(readiness.get("runbook") or {})
    schema_after = dict(result.get("schema", {}).get("after") or {})
    runtime_logs = dict(result.get("schema", {}).get("runtime_logs") or {})
    observability = dict(result.get("observability") or {})
    db_window = dict(observability.get("db") or {})
    log_window = dict(observability.get("logs") or {})
    focus_record = dict(readiness.get("focus_record") or {})
    record_timeline_preview = dict(readiness.get("record_timeline_preview") or {})
    issue_summary = readiness.get("issue_summary")
    latest_expectation_event = runtime_logs.get("latest_schema_expectations_event") or {}
    latest_upgrade_event = runtime_logs.get("latest_schema_upgrade_event") or {}

    lines = [
        "Stage 6 Readiness Summary",
        f"- Diagnosis: {diagnosis.get('state', 'unknown')}",
        f"- Message: {diagnosis.get('message', 'No message available.')}",
        (
            "- DB decision_reason column: "
            f"{'yes' if readiness.get('db_has_transcription_decision_reason_column') else 'no'}"
        ),
        (
            "- Runtime build expectation seen: "
            f"{'yes' if readiness.get('runtime_declares_current_expectation_version') else 'no'}"
        ),
        (
            "- Post-cutoff DB rows: "
            f"{db_window.get('selected_record_count', 0)}"
        ),
        (
            "- Post-cutoff runtime path logs: "
            f"{log_window.get('selected_record_count', 0)}"
        ),
        f"- Alignment state: {readiness.get('alignment_state', 'unknown')}",
        (
            "- Latest schema expectation event: "
            f"{latest_expectation_event.get('timestamp') or 'none'}"
        ),
        (
            "- Latest schema upgrade event: "
            f"{latest_upgrade_event.get('timestamp') or 'none'}"
        ),
        (
            "- Newest record hint: "
            f"{readiness.get('newest_record_id_hint') or 'none'}"
        ),
    ]

    if issue_summary:
        lines.append(f"- Issue summary: {issue_summary}")

    lines.extend(["", "Recommended Steps:"])

    for step in runbook.get("recommended_steps", []) or []:
        lines.append(f"- {step}")

    rerun_command = runbook.get("rerun_readiness_command")
    if rerun_command:
        lines.extend(["", "Rerun Command:", rerun_command])

    follow_up_commands = list(runbook.get("follow_up_commands") or [])
    if follow_up_commands:
        lines.append("")
        lines.append("Follow-up Commands:")
        for command in follow_up_commands:
            lines.append(f"- {command}")

    if focus_record:
        lines.extend(
            [
                "",
                "Focus Record:",
                f"- Source: {focus_record.get('source') or 'unknown'}",
                f"- Record id: {focus_record.get('record_id') or 'none'}",
                f"- DB path: {focus_record.get('db_transcription_path') or 'none'}",
                f"- Log path: {focus_record.get('log_selected_path') or 'none'}",
                (
                    "- DB decision reason: "
                    f"{focus_record.get('db_transcription_decision_reason') or 'none'}"
                ),
                (
                    "- Log decision reason: "
                    f"{focus_record.get('log_decision_reason') or 'none'}"
                ),
            ]
        )

    if record_timeline_preview:
        lines.extend(
            [
                "",
                "Record Timeline Preview:",
                (
                    "- Diagnosis: "
                    f"{record_timeline_preview.get('diagnosis_state') or 'unknown'}"
                ),
                (
                    "- History record found: "
                    f"{'yes' if record_timeline_preview.get('history_record_found') else 'no'}"
                ),
                (
                    "- Runtime log events: "
                    f"{record_timeline_preview.get('runtime_log_event_count', 0)}"
                ),
                (
                    "- Path events: "
                    f"{record_timeline_preview.get('path_event_count', 0)}"
                ),
            ]
        )
        if record_timeline_preview.get("issue_summary"):
            lines.append(
                "- Timeline issue: "
                f"{record_timeline_preview.get('issue_summary')}"
            )
        if record_timeline_preview.get("oneline"):
            lines.append(
                "- Timeline oneline: "
                f"{record_timeline_preview.get('oneline')}"
            )

    expected_version = readiness.get("repo_expected_history_schema_expectation_version")
    expected_signature = readiness.get("repo_expected_history_schema_signature")
    if expected_version is not None or expected_signature:
        lines.extend(
            [
                "",
                "Repo Expectations:",
                f"- Expectation version: {expected_version}",
                f"- Expectation signature: {expected_signature}",
                (
                    "- Real DB column count: "
                    f"{schema_after.get('column_count', 'unknown')}"
                ),
            ]
        )

    return "\n".join(lines)


def format_stage6_readiness_oneline(result: dict[str, Any]) -> str:
    readiness = dict(result.get("readiness") or {})
    diagnosis = dict(readiness.get("diagnosis") or {})
    issue_summary = readiness.get("issue_summary")
    latest_upgrade_event = (
        dict(result.get("schema", {}).get("runtime_logs") or {}).get(
            "latest_schema_upgrade_event"
        )
        or {}
    )

    parts = [
        f"state={diagnosis.get('state', 'unknown')}",
        (
            "db_decision_reason_column="
            f"{'yes' if readiness.get('db_has_transcription_decision_reason_column') else 'no'}"
        ),
        (
            "runtime_expectation_seen="
            f"{'yes' if readiness.get('runtime_declares_current_expectation_version') else 'no'}"
        ),
        f"alignment_state={readiness.get('alignment_state', 'unknown')}",
        f"record_hint={readiness.get('newest_record_id_hint') or 'none'}",
        f"latest_schema_upgrade={latest_upgrade_event.get('timestamp') or 'none'}",
    ]
    if issue_summary:
        parts.append(f"issue_summary={issue_summary}")
    else:
        parts.append(
            "message="
            f"{diagnosis.get('message', 'No message available.')}"
        )
    return " | ".join(parts)


def build_stage6_readiness_snapshot(result: dict[str, Any]) -> dict[str, Any]:
    readiness = dict(result.get("readiness") or {})
    diagnosis = dict(readiness.get("diagnosis") or {})
    runtime_logs = dict(result.get("schema", {}).get("runtime_logs") or {})
    observability = dict(result.get("observability") or {})
    db_window = dict(observability.get("db") or {})
    log_window = dict(observability.get("logs") or {})
    focus_record = dict(readiness.get("focus_record") or {})
    record_timeline_preview = dict(readiness.get("record_timeline_preview") or {})
    latest_expectation_event = runtime_logs.get("latest_schema_expectations_event") or {}
    latest_upgrade_event = runtime_logs.get("latest_schema_upgrade_event") or {}

    return {
        "observed_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "timestamp_from": result.get("timestamp_from"),
        "limit": result.get("limit"),
        "long_recording_cloud_candidates_only": result.get(
            "long_recording_cloud_candidates_only"
        ),
        "diagnosis_state": diagnosis.get("state"),
        "diagnosis_message": diagnosis.get("message"),
        "issue_summary": readiness.get("issue_summary"),
        "alignment_state": readiness.get("alignment_state"),
        "db_has_transcription_decision_reason_column": readiness.get(
            "db_has_transcription_decision_reason_column"
        ),
        "runtime_declares_current_expectation_version": readiness.get(
            "runtime_declares_current_expectation_version"
        ),
        "runtime_declares_current_signature": readiness.get(
            "runtime_declares_current_signature"
        ),
        "post_cutoff_db_rows": db_window.get("selected_record_count", 0),
        "post_cutoff_runtime_path_logs": log_window.get("selected_record_count", 0),
        "newest_record_id_hint": readiness.get("newest_record_id_hint"),
        "latest_schema_expectation_event_timestamp": latest_expectation_event.get(
            "timestamp"
        ),
        "latest_schema_upgrade_event_timestamp": latest_upgrade_event.get("timestamp"),
        "focus_record": focus_record or None,
        "oneline": format_stage6_readiness_oneline(result),
    }


def append_stage6_readiness_snapshot(
    snapshot_path: Path,
    result: dict[str, Any],
) -> dict[str, Any]:
    snapshot = build_stage6_readiness_snapshot(result)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    with snapshot_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
    return snapshot


def format_stage6_readiness_markdown(result: dict[str, Any]) -> str:
    readiness = dict(result.get("readiness") or {})
    diagnosis = dict(readiness.get("diagnosis") or {})
    runbook = dict(readiness.get("runbook") or {})
    schema_after = dict(result.get("schema", {}).get("after") or {})
    runtime_logs = dict(result.get("schema", {}).get("runtime_logs") or {})
    observability = dict(result.get("observability") or {})
    db_window = dict(observability.get("db") or {})
    log_window = dict(observability.get("logs") or {})
    focus_record = dict(readiness.get("focus_record") or {})
    record_timeline_preview = dict(readiness.get("record_timeline_preview") or {})
    issue_summary = readiness.get("issue_summary")
    latest_expectation_event = runtime_logs.get("latest_schema_expectations_event") or {}
    latest_upgrade_event = runtime_logs.get("latest_schema_upgrade_event") or {}

    lines = [
        "# Stage 6 Readiness Report",
        "",
        "## Diagnosis",
        f"- **State:** `{diagnosis.get('state', 'unknown')}`",
        f"- **Message:** {diagnosis.get('message', 'No message available.')}",
        f"- **Next action:** {diagnosis.get('next_action', 'No next action available.')}",
        "",
        "## Key Facts",
        (
            f"- **DB has `transcription_decision_reason`:** "
            f"{'yes' if readiness.get('db_has_transcription_decision_reason_column') else 'no'}"
        ),
        (
            f"- **Runtime build expectation seen:** "
            f"{'yes' if readiness.get('runtime_declares_current_expectation_version') else 'no'}"
        ),
        (
            f"- **Post-cutoff DB rows:** {db_window.get('selected_record_count', 0)}"
        ),
        (
            f"- **Post-cutoff runtime path logs:** {log_window.get('selected_record_count', 0)}"
        ),
        f"- **Alignment state:** `{readiness.get('alignment_state', 'unknown')}`",
        (
            f"- **Latest schema expectation event:** "
            f"{latest_expectation_event.get('timestamp') or 'none'}"
        ),
        (
            f"- **Latest schema upgrade event:** "
            f"{latest_upgrade_event.get('timestamp') or 'none'}"
        ),
        f"- **Newest record hint:** {readiness.get('newest_record_id_hint') or 'none'}",
    ]

    if issue_summary:
        lines.append(f"- **Issue summary:** {issue_summary}")

    lines.extend(
        [
            "",
            "## Repo Expectations",
            (
                f"- **Expectation version:** "
                f"{readiness.get('repo_expected_history_schema_expectation_version')}"
            ),
            (
                f"- **Expectation signature:** "
                f"`{readiness.get('repo_expected_history_schema_signature')}`"
            ),
            f"- **Real DB column count:** {schema_after.get('column_count', 'unknown')}",
            "",
            "## Recommended Steps",
        ]
    )

    for step in runbook.get("recommended_steps", []) or []:
        lines.append(f"1. {step}")

    if focus_record:
        lines.extend(
            [
                "",
                "## Focus Record",
                f"- **Source:** `{focus_record.get('source') or 'unknown'}`",
                f"- **Record id:** {focus_record.get('record_id') or 'none'}",
                f"- **DB path:** {focus_record.get('db_transcription_path') or 'none'}",
                f"- **Log path:** {focus_record.get('log_selected_path') or 'none'}",
                (
                    f"- **DB decision reason:** "
                    f"{focus_record.get('db_transcription_decision_reason') or 'none'}"
                ),
                (
                    f"- **Log decision reason:** "
                    f"{focus_record.get('log_decision_reason') or 'none'}"
                ),
            ]
        )

    if record_timeline_preview:
        lines.extend(
            [
                "",
                "## Record Timeline Preview",
                (
                    f"- **Diagnosis:** "
                    f"`{record_timeline_preview.get('diagnosis_state') or 'unknown'}`"
                ),
                (
                    f"- **History record found:** "
                    f"{'yes' if record_timeline_preview.get('history_record_found') else 'no'}"
                ),
                (
                    f"- **Runtime log events:** "
                    f"{record_timeline_preview.get('runtime_log_event_count', 0)}"
                ),
                (
                    f"- **Path events:** "
                    f"{record_timeline_preview.get('path_event_count', 0)}"
                ),
            ]
        )
        if record_timeline_preview.get("issue_summary"):
            lines.append(
                f"- **Timeline issue:** {record_timeline_preview.get('issue_summary')}"
            )
        if record_timeline_preview.get("oneline"):
            lines.extend(
                [
                    "",
                    "### Timeline Oneline",
                    "```text",
                    str(record_timeline_preview.get("oneline")),
                    "```",
                ]
            )

    rerun_command = runbook.get("rerun_readiness_command")
    if rerun_command:
        lines.extend(
            [
                "",
                "## Rerun Command",
                "```powershell",
                rerun_command,
                "```",
            ]
        )

    follow_up_commands = list(runbook.get("follow_up_commands") or [])
    if follow_up_commands:
        lines.extend(["", "## Follow-up Commands"])
        for command in follow_up_commands:
            lines.extend(["```powershell", command, "```"])

    return "\n".join(lines)


def format_stage6_readiness_card(result: dict[str, Any]) -> str:
    readiness = dict(result.get("readiness") or {})
    diagnosis = dict(readiness.get("diagnosis") or {})
    runbook = dict(readiness.get("runbook") or {})
    runtime_logs = dict(result.get("schema", {}).get("runtime_logs") or {})
    observability = dict(result.get("observability") or {})
    db_window = dict(observability.get("db") or {})
    log_window = dict(observability.get("logs") or {})
    focus_record = dict(readiness.get("focus_record") or {})
    record_timeline_preview = dict(readiness.get("record_timeline_preview") or {})
    latest_expectation_event = runtime_logs.get("latest_schema_expectations_event") or {}
    latest_upgrade_event = runtime_logs.get("latest_schema_upgrade_event") or {}

    lines = [
        "## Stage 6 Readiness Card",
        f"- **Diagnosis:** `{diagnosis.get('state', 'unknown')}`",
        f"- **Alignment:** `{readiness.get('alignment_state', 'unknown')}`",
        (
            "- **DB decision_reason column:** "
            f"{'yes' if readiness.get('db_has_transcription_decision_reason_column') else 'no'}"
        ),
        (
            "- **Runtime expectation seen:** "
            f"{'yes' if readiness.get('runtime_declares_current_expectation_version') else 'no'}"
        ),
        f"- **Post-cutoff DB rows:** `{db_window.get('selected_record_count', 0)}`",
        f"- **Post-cutoff runtime logs:** `{log_window.get('selected_record_count', 0)}`",
        (
            "- **Newest record hint:** "
            f"`{readiness.get('newest_record_id_hint') or 'none'}`"
        ),
        (
            "- **Latest schema expectation event:** "
            f"`{latest_expectation_event.get('timestamp') or 'none'}`"
        ),
        (
            "- **Latest schema upgrade event:** "
            f"`{latest_upgrade_event.get('timestamp') or 'none'}`"
        ),
        (
            "- **Guidance:** "
            f"{diagnosis.get('next_action', diagnosis.get('message', 'No guidance available.'))}"
        ),
    ]

    issue_summary = readiness.get("issue_summary")
    if issue_summary:
        lines.append(f"- **Latest issue:** {issue_summary}")
    else:
        lines.append(
            f"- **Status note:** {diagnosis.get('message', 'No message available.')}"
        )

    if focus_record:
        lines.extend(
            [
                "- **Focus record:**",
                f"  - source: `{focus_record.get('source') or 'unknown'}`",
                f"  - record_id: `{focus_record.get('record_id') or 'none'}`",
                (
                    "  - db_path: "
                    f"`{focus_record.get('db_transcription_path') or 'none'}`"
                ),
                (
                    "  - log_path: "
                    f"`{focus_record.get('log_selected_path') or 'none'}`"
                ),
                (
                    "  - db_reason: "
                    f"`{focus_record.get('db_transcription_decision_reason') or 'none'}`"
                ),
                (
                    "  - log_reason: "
                    f"`{focus_record.get('log_decision_reason') or 'none'}`"
                ),
            ]
        )

    if record_timeline_preview:
        lines.extend(
            [
                "- **Record timeline preview:**",
                (
                    "  - diagnosis: "
                    f"`{record_timeline_preview.get('diagnosis_state') or 'unknown'}`"
                ),
                (
                    "  - history_record_found: "
                    f"`{'yes' if record_timeline_preview.get('history_record_found') else 'no'}`"
                ),
                (
                    "  - runtime_log_events: "
                    f"`{record_timeline_preview.get('runtime_log_event_count', 0)}`"
                ),
            ]
        )
        if record_timeline_preview.get("issue_summary"):
            lines.append(
                "  - issue: "
                f"`{record_timeline_preview.get('issue_summary')}`"
            )

    actions = list(runbook.get("recommended_steps") or [])
    if actions:
        lines.append("- **Next actions:**")
        for action in actions:
            lines.append(f"  - {action}")

    rerun_command = runbook.get("rerun_readiness_command")
    if rerun_command:
        lines.append(f"- **Rerun command:** `{rerun_command}`")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=_default_history_db())
    parser.add_argument("--logs", type=Path, default=_default_logs_dir())
    parser.add_argument("--timestamp-from", type=str, default=None)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--long-recording-cloud-candidates-only", action="store_true")
    parser.add_argument("--snapshot-out", type=Path, default=None)
    parser.add_argument("--oneline", action="store_true")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--card", action="store_true")
    args = parser.parse_args()

    result = inspect_transcription_stage6_readiness(
        db_path=args.db,
        logs_path=args.logs,
        timestamp_from=args.timestamp_from,
        limit=args.limit,
        long_recording_cloud_candidates_only=args.long_recording_cloud_candidates_only,
    )
    if args.oneline:
        print(format_stage6_readiness_oneline(result))
    elif args.card:
        print(format_stage6_readiness_card(result))
    elif args.markdown:
        print(format_stage6_readiness_markdown(result))
    elif args.summary:
        print(format_stage6_readiness_summary(result))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.snapshot_out is not None:
        append_stage6_readiness_snapshot(args.snapshot_out, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
