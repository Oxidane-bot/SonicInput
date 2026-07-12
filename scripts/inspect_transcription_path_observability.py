"""Combine history DB and runtime log evidence for transcription observability.

This is the Stage 6 single-entry inspector that answers:

- Does the DB schema support transcription_path?
- Does the DB schema support transcription_decision_reason?
- Are there post-cutoff runtime path decision logs?
- Are there post-cutoff history rows?
- Do logs and DB agree on record ids, selected paths, and decision reasons?

Usage:
    uv run python scripts/inspect_transcription_path_observability.py
    uv run python scripts/inspect_transcription_path_observability.py --summary
    uv run python scripts/inspect_transcription_path_observability.py --oneline
    uv run python scripts/inspect_transcription_path_observability.py --card
    uv run python scripts/inspect_transcription_path_observability.py --markdown
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from inspect_recent_transcription_path_logs import (
    inspect_recent_transcription_path_logs,
)
from inspect_recent_transcription_paths import inspect_recent_transcription_paths


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


def _format_command(
    script_name: str,
    *,
    include_db: bool = True,
    db_path: Path,
    logs_path: Path | None = None,
    timestamp_from: str | None = None,
    limit: int | None = None,
    record_id: str | None = None,
) -> str:
    parts = [
        "uv run --cache-dir .\\.uv_cache python",
        f"scripts/{script_name}",
    ]
    if include_db:
        parts.append(f'--db "{db_path}"')
    if logs_path is not None:
        parts.append(f'--logs "{logs_path}"')
    if timestamp_from:
        parts.append(f"--timestamp-from {timestamp_from}")
    if limit is not None:
        parts.append(f"--limit {limit}")
    if record_id:
        parts.append(f"--record-id {record_id}")
    return " ".join(parts)


def _build_focus_record(
    *,
    alignment_state: str,
    matched_records: list[dict[str, Any]],
    mismatched_records: list[dict[str, Any]],
    decision_reason_mismatched_records: list[dict[str, Any]],
    db_records: list[dict[str, Any]],
    log_entries: list[dict[str, Any]],
) -> dict[str, Any] | None:
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
    if (
        alignment_state
        in {
            "db_log_paths_aligned_reason_schema_missing",
            "db_log_paths_and_reasons_aligned",
        }
        and matched_records
    ):
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
    if focus_record is None:
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
    if alignment_state == "db_log_paths_aligned_reason_schema_missing":
        return (
            f"record_id={record_id} paths aligned at {db_path}, but reason verification "
            "is blocked because the DB schema lacks transcription_decision_reason"
        )
    if alignment_state == "db_log_paths_and_reasons_aligned":
        return (
            f"record_id={record_id} aligned: path={db_path}, "
            f"decision_reason={db_reason}"
        )
    return None


def _build_operator_guidance(
    *,
    alignment_state: str,
    db_path: Path,
    logs_path: Path,
    timestamp_from: str | None,
    limit: int,
    focus_record: dict[str, Any] | None,
    issue_summary: str | None,
) -> dict[str, Any]:
    newest_record_id = (
        str(focus_record.get("record_id"))
        if focus_record and focus_record.get("record_id") not in (None, "")
        else None
    )
    steps: list[str]
    follow_up_commands = [
        _format_command(
            "inspect_recent_transcription_paths.py",
            db_path=db_path,
            timestamp_from=timestamp_from,
            limit=limit,
        ),
        _format_command(
            "inspect_recent_transcription_path_logs.py",
            include_db=False,
            db_path=db_path,
            logs_path=logs_path,
            timestamp_from=timestamp_from,
            limit=limit,
        ),
    ]

    if alignment_state == "schema_missing":
        steps = [
            "Upgrade or migrate the inspected history DB so transcription_path observability can be verified.",
            "Rerun this inspector after the real DB schema changes.",
        ]
    elif alignment_state == "no_post_cutoff_runtime_or_db_activity":
        steps = [
            "Generate one new real transcription after the cutoff timestamp.",
            "Rerun this inspector to capture both runtime path logs and DB rows for the same window.",
        ]
    elif alignment_state == "runtime_logs_without_db_rows":
        steps = [
            "Confirm the app and inspected history.db refer to the same real storage path.",
            "Wait for or trigger the matching DB write, then rerun this inspector.",
        ]
    elif alignment_state == "db_rows_without_runtime_logs":
        steps = [
            "Confirm the inspected logs directory belongs to the same app session as the DB row.",
            "Rerun after capturing a fresh runtime path decision event for the same time window.",
        ]
    elif alignment_state == "db_log_path_mismatch":
        steps = [
            "Use the single-record timeline inspector on the mismatched record_id.",
            "Compare the persisted DB path against the runtime selected_path or fallback event.",
        ]
    elif alignment_state == "db_log_decision_reason_mismatch":
        steps = [
            "Use the single-record timeline inspector on the mismatched record_id.",
            "Trace where the final persisted decision reason diverges from runtime logs.",
        ]
    elif alignment_state == "db_log_paths_aligned_reason_schema_missing":
        steps = [
            "Confirm the real DB has been migrated to include transcription_decision_reason.",
            "After migration, rerun this inspector to verify reason alignment in addition to path alignment.",
        ]
    elif alignment_state == "db_log_paths_and_reasons_aligned":
        steps = [
            "Keep sampling a few more real post-cutoff records to build confidence.",
            "Only drill into the single-record timeline again if a future mismatch appears.",
        ]
    else:
        steps = [
            "Compare the DB rows and runtime logs side by side for the newest available record_id.",
            "Rerun this inspector after each external state change.",
        ]

    if newest_record_id:
        follow_up_commands.insert(
            0,
            _format_command(
                "inspect_transcription_record_timeline.py",
                db_path=db_path,
                logs_path=logs_path,
                record_id=newest_record_id,
            ),
        )
    if issue_summary and alignment_state not in {"db_log_paths_and_reasons_aligned"}:
        steps.append(f"Focus on this latest issue summary: {issue_summary}")

    return {
        "recommended_steps": steps,
        "follow_up_commands": follow_up_commands,
    }


def _summarize_alignment(
    db_result: dict[str, Any],
    log_result: dict[str, Any],
    *,
    db_path: Path,
    logs_path: Path,
    timestamp_from: str | None,
    limit: int,
) -> dict[str, Any]:
    db_records = list(db_result.get("records", []) or [])
    log_entries = list(log_result.get("entries", []) or [])
    has_decision_reason_column = (
        db_result.get("schema", {}).get("has_transcription_decision_reason_column")
        is True
    )

    db_by_id = {
        str(record.get("record_id")): record
        for record in db_records
        if record.get("record_id") is not None
    }
    log_by_id = {
        str(entry.get("record_id")): entry
        for entry in log_entries
        if entry.get("record_id") is not None
    }

    shared_record_ids = sorted(set(db_by_id) & set(log_by_id))
    log_only_record_ids = sorted(set(log_by_id) - set(db_by_id))
    db_only_record_ids = sorted(set(db_by_id) - set(log_by_id))

    matched_records: list[dict[str, Any]] = []
    mismatched_records: list[dict[str, Any]] = []
    decision_reason_matched_records: list[dict[str, Any]] = []
    decision_reason_mismatched_records: list[dict[str, Any]] = []

    for record_id in shared_record_ids:
        db_record = db_by_id[record_id]
        log_entry = log_by_id[record_id]
        db_path = db_record.get("transcription_path")
        log_path = log_entry.get("selected_path")
        db_decision_reason = db_record.get("transcription_decision_reason")
        log_decision_reason = log_entry.get("decision_reason")
        decision_reasons_match = (
            db_decision_reason == log_decision_reason
            if has_decision_reason_column
            else None
        )
        row = {
            "record_id": record_id,
            "db_transcription_path": db_path,
            "db_transcription_decision_reason": db_decision_reason,
            "log_selected_path": log_path,
            "log_decision_reason": log_decision_reason,
            "db_timestamp": db_record.get("timestamp"),
            "log_timestamp": log_entry.get("timestamp"),
            "paths_match": db_path == log_path,
            "decision_reasons_match": decision_reasons_match,
        }
        if row["paths_match"]:
            matched_records.append(row)
            if row["decision_reasons_match"] is True:
                decision_reason_matched_records.append(row)
            elif row["decision_reasons_match"] is False:
                decision_reason_mismatched_records.append(row)
        else:
            mismatched_records.append(row)

    if db_result.get("schema", {}).get("has_transcription_path_column") is not True:
        diagnosis = {
            "state": "schema_missing",
            "message": "DB schema still lacks transcription_path, so end-to-end observability is blocked.",
        }
    elif (
        log_result.get("selected_record_count", 0) == 0
        and db_result.get("source_record_count", 0) == 0
    ):
        diagnosis = {
            "state": "no_post_cutoff_runtime_or_db_activity",
            "message": "No post-cutoff transcription path logs and no post-cutoff DB rows were found.",
        }
    elif (
        log_result.get("selected_record_count", 0) > 0
        and db_result.get("selected_record_count", 0) == 0
    ):
        diagnosis = {
            "state": "runtime_logs_without_db_rows",
            "message": "Runtime path decision logs exist, but no matching post-cutoff DB rows were found yet.",
        }
    elif (
        db_result.get("selected_record_count", 0) > 0
        and log_result.get("selected_record_count", 0) == 0
    ):
        diagnosis = {
            "state": "db_rows_without_runtime_logs",
            "message": "Post-cutoff DB rows exist, but no runtime path decision logs were found for the same window.",
        }
    elif mismatched_records:
        diagnosis = {
            "state": "db_log_path_mismatch",
            "message": "At least one shared record_id has different DB transcription_path and runtime selected_path.",
        }
    elif not has_decision_reason_column and matched_records:
        diagnosis = {
            "state": "db_log_paths_aligned_reason_schema_missing",
            "message": (
                "Shared record ids show aligned paths, but the DB schema still lacks "
                "transcription_decision_reason so reason alignment cannot be verified yet."
            ),
        }
    elif decision_reason_mismatched_records:
        diagnosis = {
            "state": "db_log_decision_reason_mismatch",
            "message": (
                "Shared record ids show aligned paths, but at least one persisted "
                "transcription_decision_reason differs from the runtime decision_reason."
            ),
        }
    elif matched_records:
        diagnosis = {
            "state": "db_log_paths_and_reasons_aligned",
            "message": (
                "Shared post-cutoff record ids show aligned DB transcription_path and "
                "transcription_decision_reason versus runtime selected_path and decision_reason."
            ),
        }
    else:
        diagnosis = {
            "state": "no_shared_record_ids_yet",
            "message": "Post-cutoff runtime and DB evidence exists, but no shared record ids were found yet.",
        }

    focus_record = _build_focus_record(
        alignment_state=diagnosis["state"],
        matched_records=matched_records,
        mismatched_records=mismatched_records,
        decision_reason_mismatched_records=decision_reason_mismatched_records,
        db_records=db_records,
        log_entries=log_entries,
    )
    issue_summary = _build_issue_summary(
        alignment_state=diagnosis["state"],
        focus_record=focus_record,
    )
    operator_guidance = _build_operator_guidance(
        alignment_state=diagnosis["state"],
        db_path=db_path,
        logs_path=logs_path,
        timestamp_from=timestamp_from,
        limit=limit,
        focus_record=focus_record,
        issue_summary=issue_summary,
    )

    return {
        "diagnosis": diagnosis,
        "shared_record_id_count": len(shared_record_ids),
        "matched_record_count": len(matched_records),
        "mismatched_record_count": len(mismatched_records),
        "decision_reason_matched_record_count": len(decision_reason_matched_records),
        "decision_reason_mismatched_record_count": len(
            decision_reason_mismatched_records
        ),
        "shared_record_ids": shared_record_ids,
        "log_only_record_ids": log_only_record_ids,
        "db_only_record_ids": db_only_record_ids,
        "matched_records": matched_records,
        "mismatched_records": mismatched_records,
        "decision_reason_matched_records": decision_reason_matched_records,
        "decision_reason_mismatched_records": decision_reason_mismatched_records,
        "focus_record": focus_record,
        "issue_summary": issue_summary,
        "operator_guidance": operator_guidance,
    }


def inspect_transcription_path_observability(
    *,
    db_path: Path,
    logs_path: Path,
    timestamp_from: str | None = None,
    limit: int = 50,
    long_recording_cloud_candidates_only: bool = False,
) -> dict[str, Any]:
    db_result = inspect_recent_transcription_paths(
        db_path,
        timestamp_from=timestamp_from,
        limit=limit,
        long_recording_cloud_candidates_only=long_recording_cloud_candidates_only,
    )
    log_result = inspect_recent_transcription_path_logs(
        logs_path,
        timestamp_from=timestamp_from,
        limit=limit,
    )
    alignment = _summarize_alignment(
        db_result,
        log_result,
        db_path=db_path,
        logs_path=logs_path,
        timestamp_from=timestamp_from,
        limit=limit,
    )

    return {
        "timestamp_from": timestamp_from,
        "limit": limit,
        "long_recording_cloud_candidates_only": long_recording_cloud_candidates_only,
        "db": db_result,
        "logs": log_result,
        "alignment": alignment,
    }


def format_transcription_path_observability_oneline(result: dict[str, Any]) -> str:
    alignment = dict(result.get("alignment") or {})
    diagnosis = dict(alignment.get("diagnosis") or {})
    issue_summary = alignment.get("issue_summary")
    db_schema = dict(result.get("db", {}).get("schema") or {})
    parts = [
        f"state={diagnosis.get('state') or 'unknown'}",
        (
            "db_path_column="
            f"{'yes' if db_schema.get('has_transcription_path_column') else 'no'}"
        ),
        (
            "db_reason_column="
            f"{'yes' if db_schema.get('has_transcription_decision_reason_column') else 'no'}"
        ),
        f"db_rows={dict(result.get('db') or {}).get('selected_record_count', 0)}",
        f"runtime_logs={dict(result.get('logs') or {}).get('selected_record_count', 0)}",
        f"shared_record_ids={alignment.get('shared_record_id_count', 0)}",
        (
            "record_hint="
            f"{dict(alignment.get('focus_record') or {}).get('record_id') or 'none'}"
        ),
    ]
    if issue_summary:
        parts.append(f"issue_summary={issue_summary}")
    else:
        parts.append(f"message={diagnosis.get('message') or 'No message available.'}")
    return " | ".join(parts)


def format_transcription_path_observability_summary(result: dict[str, Any]) -> str:
    alignment = dict(result.get("alignment") or {})
    diagnosis = dict(alignment.get("diagnosis") or {})
    focus_record = dict(alignment.get("focus_record") or {})
    operator_guidance = dict(alignment.get("operator_guidance") or {})
    db_schema = dict(result.get("db", {}).get("schema") or {})

    lines = [
        "Transcription Path Observability Summary",
        f"- Diagnosis: {diagnosis.get('state') or 'unknown'}",
        f"- Message: {diagnosis.get('message') or 'No message available.'}",
        (
            "- DB has transcription_path column: "
            f"{'yes' if db_schema.get('has_transcription_path_column') else 'no'}"
        ),
        (
            "- DB has transcription_decision_reason column: "
            f"{'yes' if db_schema.get('has_transcription_decision_reason_column') else 'no'}"
        ),
        f"- Post-cutoff DB rows: {dict(result.get('db') or {}).get('selected_record_count', 0)}",
        f"- Post-cutoff runtime logs: {dict(result.get('logs') or {}).get('selected_record_count', 0)}",
        f"- Shared record ids: {alignment.get('shared_record_id_count', 0)}",
        f"- Matched records: {alignment.get('matched_record_count', 0)}",
        f"- Path mismatches: {alignment.get('mismatched_record_count', 0)}",
        (
            "- Decision reason mismatches: "
            f"{alignment.get('decision_reason_mismatched_record_count', 0)}"
        ),
    ]
    if alignment.get("issue_summary"):
        lines.append(f"- Issue summary: {alignment.get('issue_summary')}")

    steps = list(operator_guidance.get("recommended_steps") or [])
    if steps:
        lines.extend(["", "Recommended Steps:"])
        for step in steps:
            lines.append(f"- {step}")

    follow_up_commands = list(operator_guidance.get("follow_up_commands") or [])
    if follow_up_commands:
        lines.extend(["", "Follow-up Commands:"])
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

    return "\n".join(lines)


def format_transcription_path_observability_card(result: dict[str, Any]) -> str:
    alignment = dict(result.get("alignment") or {})
    diagnosis = dict(alignment.get("diagnosis") or {})
    operator_guidance = dict(alignment.get("operator_guidance") or {})
    focus_record = dict(alignment.get("focus_record") or {})
    db_schema = dict(result.get("db", {}).get("schema") or {})

    lines = [
        "## Transcription Path Observability Card",
        f"- **Diagnosis:** `{diagnosis.get('state') or 'unknown'}`",
        (
            "- **DB path column:** "
            f"{'yes' if db_schema.get('has_transcription_path_column') else 'no'}"
        ),
        (
            "- **DB decision reason column:** "
            f"{'yes' if db_schema.get('has_transcription_decision_reason_column') else 'no'}"
        ),
        f"- **Post-cutoff DB rows:** `{dict(result.get('db') or {}).get('selected_record_count', 0)}`",
        f"- **Post-cutoff runtime logs:** `{dict(result.get('logs') or {}).get('selected_record_count', 0)}`",
        f"- **Shared record ids:** `{alignment.get('shared_record_id_count', 0)}`",
        f"- **Matched records:** `{alignment.get('matched_record_count', 0)}`",
        f"- **Path mismatches:** `{alignment.get('mismatched_record_count', 0)}`",
        (
            "- **Decision reason mismatches:** "
            f"`{alignment.get('decision_reason_mismatched_record_count', 0)}`"
        ),
        (f"- **Guidance:** {diagnosis.get('message') or 'No guidance available.'}"),
    ]
    if alignment.get("issue_summary"):
        lines.append(f"- **Issue summary:** {alignment.get('issue_summary')}")
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
                (f"  - log_path: `{focus_record.get('log_selected_path') or 'none'}`"),
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
    steps = list(operator_guidance.get("recommended_steps") or [])
    if steps:
        lines.append("- **Next actions:**")
        for step in steps:
            lines.append(f"  - {step}")
    return "\n".join(lines)


def format_transcription_path_observability_markdown(result: dict[str, Any]) -> str:
    alignment = dict(result.get("alignment") or {})
    diagnosis = dict(alignment.get("diagnosis") or {})
    operator_guidance = dict(alignment.get("operator_guidance") or {})
    focus_record = dict(alignment.get("focus_record") or {})
    db_schema = dict(result.get("db", {}).get("schema") or {})

    lines = [
        "# Transcription Path Observability Report",
        "",
        "## Diagnosis",
        f"- **State:** `{diagnosis.get('state') or 'unknown'}`",
        f"- **Message:** {diagnosis.get('message') or 'No message available.'}",
        (
            f"- **DB has `transcription_path`:** "
            f"{'yes' if db_schema.get('has_transcription_path_column') else 'no'}"
        ),
        (
            f"- **DB has `transcription_decision_reason`:** "
            f"{'yes' if db_schema.get('has_transcription_decision_reason_column') else 'no'}"
        ),
        f"- **Post-cutoff DB rows:** {dict(result.get('db') or {}).get('selected_record_count', 0)}",
        f"- **Post-cutoff runtime logs:** {dict(result.get('logs') or {}).get('selected_record_count', 0)}",
        f"- **Shared record ids:** {alignment.get('shared_record_id_count', 0)}",
        f"- **Matched records:** {alignment.get('matched_record_count', 0)}",
        f"- **Path mismatches:** {alignment.get('mismatched_record_count', 0)}",
        (
            f"- **Decision reason mismatches:** "
            f"{alignment.get('decision_reason_mismatched_record_count', 0)}"
        ),
    ]
    if alignment.get("issue_summary"):
        lines.append(f"- **Issue summary:** {alignment.get('issue_summary')}")

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

    steps = list(operator_guidance.get("recommended_steps") or [])
    if steps:
        lines.extend(["", "## Recommended Steps"])
        for step in steps:
            lines.append(f"1. {step}")

    follow_up_commands = list(operator_guidance.get("follow_up_commands") or [])
    if follow_up_commands:
        lines.extend(["", "## Follow-up Commands"])
        for command in follow_up_commands:
            lines.extend(["```powershell", command, "```"])

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=_default_history_db())
    parser.add_argument("--logs", type=Path, default=_default_logs_dir())
    parser.add_argument("--timestamp-from", type=str, default=None)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--long-recording-cloud-candidates-only", action="store_true")
    parser.add_argument("--oneline", action="store_true")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--card", action="store_true")
    args = parser.parse_args()

    result = inspect_transcription_path_observability(
        db_path=args.db,
        logs_path=args.logs,
        timestamp_from=args.timestamp_from,
        limit=args.limit,
        long_recording_cloud_candidates_only=args.long_recording_cloud_candidates_only,
    )
    if args.oneline:
        print(format_transcription_path_observability_oneline(result))
    elif args.card:
        print(format_transcription_path_observability_card(result))
    elif args.markdown:
        print(format_transcription_path_observability_markdown(result))
    elif args.summary:
        print(format_transcription_path_observability_summary(result))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
