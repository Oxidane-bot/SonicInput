"""Inspect one transcription record across history DB rows and runtime logs.

This helper is meant for the first real post-upgrade sample in Stage 6:

- look up one `record_id` in `history.db`
- collect the related runtime log events from `app.log*`
- compare the persisted `transcription_path` against the latest runtime
  path-decision / fallback event

Usage:
    uv run python scripts/inspect_transcription_record_timeline.py --record-id abc-123
    uv run python scripts/inspect_transcription_record_timeline.py --record-id abc-123 --db path/to/history.db --logs path/to/logs
    uv run python scripts/inspect_transcription_record_timeline.py --record-id abc-123 --oneline
    uv run python scripts/inspect_transcription_record_timeline.py --record-id abc-123 --summary
    uv run python scripts/inspect_transcription_record_timeline.py --record-id abc-123 --card
    uv run python scripts/inspect_transcription_record_timeline.py --record-id abc-123 --markdown
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from inspect_recent_transcription_path_logs import (  # type: ignore
    _default_logs_dir,
    _iter_log_files,
    _parse_log_line,
)
from inspect_recent_transcription_paths import _default_history_db  # type: ignore

_TARGET_EVENTS = {
    "Transcription request received",
    "Transcription path decision",
    "Transcription fallback engaged",
    "Transcription completed",
    "Transcription record saved",
    "Failed to save transcription record",
    "History record saved",
    "History record updated",
    "History record not found for update",
}

_PATH_EVENTS = {
    "Transcription path decision",
    "Transcription fallback engaged",
}
_TERMINAL_EVENTS = {
    "Transcription completed",
    "Transcription record saved",
    "Failed to save transcription record",
    "History record saved",
    "History record updated",
    "History record not found for update",
}


def _load_history_record(db_path: Path, record_id: str) -> dict[str, Any] | None:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM history_records WHERE id = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            return None
        row_keys = set(row.keys())
        return {
            "record_id": row["id"],
            "timestamp": row["timestamp"],
            "audio_file_path_present": bool(str(row["audio_file_path"] or "").strip())
            if "audio_file_path" in row_keys
            else False,
            "duration": float(row["duration"] or 0.0) if "duration" in row_keys else 0.0,
            "transcription_provider": row["transcription_provider"]
            if "transcription_provider" in row_keys
            else None,
            "transcription_status": row["transcription_status"]
            if "transcription_status" in row_keys
            else None,
            "streaming_mode": row["streaming_mode"] if "streaming_mode" in row_keys else None,
            "transcription_path": row["transcription_path"]
            if "transcription_path" in row_keys
            else "standard",
            "transcription_decision_reason": row["transcription_decision_reason"]
            if "transcription_decision_reason" in row_keys
            else None,
            "transcription_duration": row["transcription_duration"]
            if "transcription_duration" in row_keys
            else None,
            "used_fallback": bool(row["used_fallback"]) if "used_fallback" in row_keys else False,
            "fallback_type": row["fallback_type"] if "fallback_type" in row_keys else "none",
            "fallback_reason": row["fallback_reason"] if "fallback_reason" in row_keys else None,
            "diagnostics_collected": bool(row["diagnostics_collected"])
            if "diagnostics_collected" in row_keys
            else False,
        }
    finally:
        conn.close()


def _collect_related_log_events(logs_path: Path, record_id: str) -> dict[str, Any]:
    log_files = _iter_log_files(logs_path)
    entries: list[dict[str, Any]] = []
    counts_by_event: Counter[str] = Counter()

    for log_file in log_files:
        for line_number, line in enumerate(
            log_file.read_text(encoding="utf-8").splitlines(), start=1
        ):
            parsed = _parse_log_line(line)
            if parsed is None:
                continue
            if parsed["event"] not in _TARGET_EVENTS:
                continue
            context = dict(parsed.get("context") or {})
            if str(context.get("record_id") or "") != record_id:
                continue
            counts_by_event[str(parsed["event"])] += 1
            entries.append(
                {
                    "source_file": str(log_file),
                    "line_number": line_number,
                    "timestamp": parsed["timestamp"],
                    "event": parsed["event"],
                    "record_id": context.get("record_id"),
                    "selected_path": context.get("selected_path"),
                    "decision_reason": context.get("decision_reason"),
                    "streaming_mode": context.get("streaming_mode"),
                    "provider": context.get("provider"),
                    "audio_duration": context.get("audio_duration"),
                    "status": context.get("status"),
                    "text_length": context.get("text_length"),
                    "transcription_duration": context.get("transcription_duration"),
                    "used_fallback": context.get("used_fallback")
                    if "used_fallback" in context
                    else context.get("fallback_used"),
                    "fallback_type": context.get("fallback_type"),
                    "fallback_reason": context.get("fallback_reason"),
                }
            )

    entries.sort(
        key=lambda item: (item["timestamp"], item["line_number"], item["source_file"])
    )
    latest_path_event = None
    for entry in reversed(entries):
        if entry["event"] in _PATH_EVENTS and entry.get("selected_path"):
            latest_path_event = entry
            break

    return {
        "log_file_count": len(log_files),
        "selected_record_count": len(entries),
        "counts_by_event": dict(sorted(counts_by_event.items())),
        "latest_path_event": latest_path_event,
        "entries": entries,
    }


def _diagnose(
    *,
    history_record: dict[str, Any] | None,
    log_entries: list[dict[str, Any]],
    latest_path_event: dict[str, Any] | None,
) -> dict[str, str]:
    if history_record is None and not log_entries:
        return {
            "state": "record_not_found_in_db_or_logs",
            "message": "The supplied record_id was not found in history DB rows or runtime logs.",
        }
    if history_record is None:
        return {
            "state": "runtime_logs_without_db_record",
            "message": "Runtime logs exist for this record_id, but no matching history DB row was found.",
        }
    if not log_entries:
        return {
            "state": "db_record_without_runtime_logs",
            "message": "A matching history DB row exists, but no related runtime log events were found.",
        }
    if latest_path_event is None:
        return {
            "state": "related_logs_without_path_event",
            "message": "Related runtime logs exist, but none included a path decision/fallback event.",
        }
    db_path = str(history_record.get("transcription_path") or "standard")
    log_path = str(latest_path_event.get("selected_path") or "")
    if db_path == log_path:
        return {
            "state": "db_log_path_aligned",
            "message": "The latest runtime selected_path matches the persisted history transcription_path.",
        }
    return {
        "state": "db_log_path_mismatch",
        "message": (
            "The latest runtime selected_path does not match the persisted history "
            "transcription_path."
        ),
    }


def _dedupe_non_empty_in_order(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        items.append(normalized)
        seen.add(normalized)
    return items


def _build_event_flow(log_entries: list[dict[str, Any]]) -> dict[str, Any]:
    latest_terminal_event = None
    for entry in reversed(log_entries):
        if entry["event"] in _TERMINAL_EVENTS:
            latest_terminal_event = {
                "timestamp": entry.get("timestamp"),
                "event": entry.get("event"),
                "selected_path": entry.get("selected_path"),
                "decision_reason": entry.get("decision_reason"),
                "status": entry.get("status"),
                "fallback_type": entry.get("fallback_type"),
                "fallback_reason": entry.get("fallback_reason"),
            }
            break

    return {
        "first_log_timestamp": log_entries[0].get("timestamp") if log_entries else None,
        "latest_log_timestamp": log_entries[-1].get("timestamp") if log_entries else None,
        "event_count": len(log_entries),
        "path_event_count": sum(1 for entry in log_entries if entry["event"] in _PATH_EVENTS),
        "fallback_event_count": sum(
            1 for entry in log_entries if entry["event"] == "Transcription fallback engaged"
        ),
        "latest_terminal_event": latest_terminal_event,
        "events_in_order": [str(entry.get("event") or "unknown") for entry in log_entries],
        "observed_selected_paths": _dedupe_non_empty_in_order(
            [entry.get("selected_path") for entry in log_entries]
        ),
        "observed_decision_reasons": _dedupe_non_empty_in_order(
            [entry.get("decision_reason") for entry in log_entries]
        ),
        "observed_fallback_reasons": _dedupe_non_empty_in_order(
            [entry.get("fallback_reason") for entry in log_entries]
        ),
    }


def _build_issue_summary(
    *,
    record_id: str,
    history_record: dict[str, Any] | None,
    log_entries: list[dict[str, Any]],
    latest_path_event: dict[str, Any] | None,
    comparison: dict[str, Any] | None,
    diagnosis: dict[str, str],
) -> str:
    state = str(diagnosis.get("state") or "unknown")
    if state == "record_not_found_in_db_or_logs":
        return f"record_id={record_id} was not found in the inspected DB or logs"
    if state == "runtime_logs_without_db_record":
        latest_event = latest_path_event or (log_entries[-1] if log_entries else None) or {}
        return (
            f"record_id={record_id} runtime log exists without DB row: "
            f"log_path={latest_event.get('selected_path') or 'none'}, "
            f"log_reason={latest_event.get('decision_reason') or 'none'}"
        )
    if state == "db_record_without_runtime_logs":
        return (
            f"record_id={record_id} DB row exists without runtime logs: "
            f"db_path={history_record.get('transcription_path') if history_record else 'none'}, "
            f"db_reason={history_record.get('transcription_decision_reason') if history_record else 'none'}"
        )
    if state == "related_logs_without_path_event":
        latest_event = log_entries[-1] if log_entries else {}
        return (
            f"record_id={record_id} related logs were found but no path decision/fallback event: "
            f"latest_event={latest_event.get('event') or 'none'}"
        )
    if comparison is None:
        return f"record_id={record_id} requires manual inspection"

    db_path = comparison.get("db_transcription_path") or "none"
    log_path = comparison.get("log_selected_path") or "none"
    db_reason = comparison.get("db_transcription_decision_reason") or "none"
    log_reason = comparison.get("log_decision_reason") or "none"
    if comparison.get("paths_match") and comparison.get("decision_reasons_match"):
        return (
            f"record_id={record_id} aligned: "
            f"path={db_path}, decision_reason={db_reason}"
        )
    if not comparison.get("paths_match"):
        return (
            f"record_id={record_id} path mismatch: db={db_path} vs log={log_path}; "
            f"reason db={db_reason} vs log={log_reason}"
        )
    return (
        f"record_id={record_id} decision reason mismatch: "
        f"db={db_reason} vs log={log_reason}"
    )


def inspect_transcription_record_timeline(
    *,
    db_path: Path,
    logs_path: Path,
    record_id: str,
) -> dict[str, Any]:
    if not db_path.exists():
        raise FileNotFoundError(f"History database not found: {db_path}")

    history_record = _load_history_record(db_path, record_id)
    logs_result = _collect_related_log_events(logs_path, record_id)
    latest_path_event = logs_result["latest_path_event"]
    diagnosis = _diagnose(
        history_record=history_record,
        log_entries=logs_result["entries"],
        latest_path_event=latest_path_event,
    )

    comparison = None
    if history_record is not None and latest_path_event is not None:
        comparison = {
            "record_id": record_id,
            "db_transcription_path": history_record.get("transcription_path"),
            "db_transcription_decision_reason": history_record.get(
                "transcription_decision_reason"
            ),
            "log_selected_path": latest_path_event.get("selected_path"),
            "log_decision_reason": latest_path_event.get("decision_reason"),
            "paths_match": history_record.get("transcription_path")
            == latest_path_event.get("selected_path"),
            "decision_reasons_match": history_record.get(
                "transcription_decision_reason"
            )
            == latest_path_event.get("decision_reason"),
        }
    event_flow = _build_event_flow(logs_result["entries"])
    issue_summary = _build_issue_summary(
        record_id=record_id,
        history_record=history_record,
        log_entries=logs_result["entries"],
        latest_path_event=latest_path_event,
        comparison=comparison,
        diagnosis=diagnosis,
    )

    return {
        "db_path": str(db_path),
        "logs_path": str(logs_path),
        "record_id": record_id,
        "history_record_found": history_record is not None,
        "history_record": history_record,
        "logs": logs_result,
        "event_flow": event_flow,
        "comparison": comparison,
        "diagnosis": diagnosis,
        "issue_summary": issue_summary,
    }


def format_transcription_record_timeline_oneline(result: dict[str, Any]) -> str:
    diagnosis = dict(result.get("diagnosis") or {})
    history_record = dict(result.get("history_record") or {})
    comparison = dict(result.get("comparison") or {})
    event_flow = dict(result.get("event_flow") or {})
    latest_terminal_event = dict(event_flow.get("latest_terminal_event") or {})

    parts = [
        f"record_id={result.get('record_id') or 'unknown'}",
        f"state={diagnosis.get('state') or 'unknown'}",
        (
            "history_record_found="
            f"{'yes' if result.get('history_record_found') else 'no'}"
        ),
        f"log_events={event_flow.get('event_count', 0)}",
        (
            "db_path="
            f"{comparison.get('db_transcription_path') or history_record.get('transcription_path') or 'none'}"
        ),
        f"log_path={comparison.get('log_selected_path') or 'none'}",
        (
            "paths_match="
            f"{comparison.get('paths_match') if result.get('comparison') is not None else 'none'}"
        ),
        (
            "db_reason="
            f"{comparison.get('db_transcription_decision_reason') or history_record.get('transcription_decision_reason') or 'none'}"
        ),
        f"log_reason={comparison.get('log_decision_reason') or 'none'}",
        (
            "decision_reasons_match="
            f"{comparison.get('decision_reasons_match') if result.get('comparison') is not None else 'none'}"
        ),
    ]
    if latest_terminal_event:
        parts.append(
            "latest_terminal_event="
            f"{latest_terminal_event.get('event') or 'unknown'}@"
            f"{latest_terminal_event.get('timestamp') or 'unknown'}"
        )
    issue_summary = result.get("issue_summary")
    if issue_summary:
        parts.append(f"issue_summary={issue_summary}")
    else:
        parts.append(f"message={diagnosis.get('message') or 'No message available.'}")
    return " | ".join(parts)


def format_transcription_record_timeline_summary(result: dict[str, Any]) -> str:
    diagnosis = dict(result.get("diagnosis") or {})
    history_record = dict(result.get("history_record") or {})
    comparison = dict(result.get("comparison") or {})
    event_flow = dict(result.get("event_flow") or {})
    latest_terminal_event = dict(event_flow.get("latest_terminal_event") or {})

    lines = [
        "Transcription Record Timeline Summary",
        f"- Record id: {result.get('record_id') or 'unknown'}",
        f"- Diagnosis: {diagnosis.get('state') or 'unknown'}",
        f"- Message: {diagnosis.get('message') or 'No message available.'}",
        (
            "- History record found: "
            f"{'yes' if result.get('history_record_found') else 'no'}"
        ),
        f"- Runtime log events: {event_flow.get('event_count', 0)}",
        f"- First log timestamp: {event_flow.get('first_log_timestamp') or 'none'}",
        f"- Latest log timestamp: {event_flow.get('latest_log_timestamp') or 'none'}",
        f"- Path events: {event_flow.get('path_event_count', 0)}",
        f"- Fallback events: {event_flow.get('fallback_event_count', 0)}",
    ]

    issue_summary = result.get("issue_summary")
    if issue_summary:
        lines.append(f"- Issue summary: {issue_summary}")

    if history_record:
        lines.extend(
            [
                "",
                "DB Record:",
                f"- Timestamp: {history_record.get('timestamp') or 'none'}",
                f"- Provider: {history_record.get('transcription_provider') or 'none'}",
                f"- Streaming mode: {history_record.get('streaming_mode') or 'none'}",
                f"- Transcription path: {history_record.get('transcription_path') or 'none'}",
                (
                    "- Decision reason: "
                    f"{history_record.get('transcription_decision_reason') or 'none'}"
                ),
                f"- Fallback type: {history_record.get('fallback_type') or 'none'}",
                f"- Fallback reason: {history_record.get('fallback_reason') or 'none'}",
            ]
        )

    if result.get("comparison") is not None:
        lines.extend(
            [
                "",
                "DB vs Runtime Comparison:",
                f"- DB path: {comparison.get('db_transcription_path') or 'none'}",
                f"- Runtime path: {comparison.get('log_selected_path') or 'none'}",
                (
                    "- Paths match: "
                    f"{'yes' if comparison.get('paths_match') else 'no'}"
                ),
                (
                    "- DB decision reason: "
                    f"{comparison.get('db_transcription_decision_reason') or 'none'}"
                ),
                (
                    "- Runtime decision reason: "
                    f"{comparison.get('log_decision_reason') or 'none'}"
                ),
                (
                    "- Decision reasons match: "
                    f"{'yes' if comparison.get('decision_reasons_match') else 'no'}"
                ),
            ]
        )

    if latest_terminal_event:
        lines.extend(
            [
                "",
                "Latest Terminal Event:",
                (
                    "- "
                    f"{latest_terminal_event.get('event') or 'unknown'} at "
                    f"{latest_terminal_event.get('timestamp') or 'unknown'}"
                ),
            ]
        )

    observed_selected_paths = list(event_flow.get("observed_selected_paths") or [])
    observed_decision_reasons = list(event_flow.get("observed_decision_reasons") or [])
    events_in_order = list(event_flow.get("events_in_order") or [])
    if observed_selected_paths or observed_decision_reasons or events_in_order:
        lines.extend(["", "Event Flow:"])
        if observed_selected_paths:
            lines.append(f"- Observed paths: {' -> '.join(observed_selected_paths)}")
        if observed_decision_reasons:
            lines.append(
                f"- Observed decision reasons: {' -> '.join(observed_decision_reasons)}"
            )
        if events_in_order:
            lines.append(f"- Events in order: {' -> '.join(events_in_order)}")

    return "\n".join(lines)


def format_transcription_record_timeline_card(result: dict[str, Any]) -> str:
    diagnosis = dict(result.get("diagnosis") or {})
    comparison = dict(result.get("comparison") or {})
    event_flow = dict(result.get("event_flow") or {})
    latest_terminal_event = dict(event_flow.get("latest_terminal_event") or {})

    lines = [
        "## Transcription Record Timeline Card",
        f"- **Record id:** `{result.get('record_id') or 'unknown'}`",
        f"- **Diagnosis:** `{diagnosis.get('state') or 'unknown'}`",
        (
            "- **History record found:** "
            f"{'yes' if result.get('history_record_found') else 'no'}"
        ),
        f"- **Runtime log events:** `{event_flow.get('event_count', 0)}`",
        f"- **Path events:** `{event_flow.get('path_event_count', 0)}`",
        f"- **Fallback events:** `{event_flow.get('fallback_event_count', 0)}`",
        f"- **Guidance:** {diagnosis.get('message') or 'No message available.'}",
    ]

    issue_summary = result.get("issue_summary")
    if issue_summary:
        lines.append(f"- **Issue summary:** {issue_summary}")

    if result.get("comparison") is not None:
        lines.extend(
            [
                "- **DB vs runtime:**",
                f"  - db_path: `{comparison.get('db_transcription_path') or 'none'}`",
                f"  - log_path: `{comparison.get('log_selected_path') or 'none'}`",
                f"  - paths_match: `{comparison.get('paths_match')}`",
                (
                    "  - db_reason: "
                    f"`{comparison.get('db_transcription_decision_reason') or 'none'}`"
                ),
                f"  - log_reason: `{comparison.get('log_decision_reason') or 'none'}`",
                (
                    "  - decision_reasons_match: "
                    f"`{comparison.get('decision_reasons_match')}`"
                ),
            ]
        )

    if latest_terminal_event:
        lines.append(
            "- **Latest terminal event:** "
            f"`{latest_terminal_event.get('event') or 'unknown'}` at "
            f"`{latest_terminal_event.get('timestamp') or 'unknown'}`"
        )

    observed_selected_paths = list(event_flow.get("observed_selected_paths") or [])
    if observed_selected_paths:
        lines.append(
            f"- **Observed paths:** `{' -> '.join(observed_selected_paths)}`"
        )

    observed_decision_reasons = list(event_flow.get("observed_decision_reasons") or [])
    if observed_decision_reasons:
        lines.append(
            "- **Observed decision reasons:** "
            f"`{' -> '.join(observed_decision_reasons)}`"
        )

    return "\n".join(lines)


def format_transcription_record_timeline_markdown(result: dict[str, Any]) -> str:
    diagnosis = dict(result.get("diagnosis") or {})
    history_record = dict(result.get("history_record") or {})
    comparison = dict(result.get("comparison") or {})
    event_flow = dict(result.get("event_flow") or {})
    latest_terminal_event = dict(event_flow.get("latest_terminal_event") or {})

    lines = [
        "# Transcription Record Timeline Report",
        "",
        "## Diagnosis",
        f"- **Record id:** `{result.get('record_id') or 'unknown'}`",
        f"- **State:** `{diagnosis.get('state') or 'unknown'}`",
        f"- **Message:** {diagnosis.get('message') or 'No message available.'}",
        (
            "- **History record found:** "
            f"{'yes' if result.get('history_record_found') else 'no'}"
        ),
    ]

    issue_summary = result.get("issue_summary")
    if issue_summary:
        lines.append(f"- **Issue summary:** {issue_summary}")

    lines.extend(
        [
            "",
            "## Event Flow",
            f"- **Runtime log events:** {event_flow.get('event_count', 0)}",
            f"- **First log timestamp:** `{event_flow.get('first_log_timestamp') or 'none'}`",
            f"- **Latest log timestamp:** `{event_flow.get('latest_log_timestamp') or 'none'}`",
            f"- **Path events:** {event_flow.get('path_event_count', 0)}",
            f"- **Fallback events:** {event_flow.get('fallback_event_count', 0)}",
        ]
    )

    if latest_terminal_event:
        lines.append(
            "- **Latest terminal event:** "
            f"`{latest_terminal_event.get('event') or 'unknown'}` at "
            f"`{latest_terminal_event.get('timestamp') or 'unknown'}`"
        )

    observed_selected_paths = list(event_flow.get("observed_selected_paths") or [])
    observed_decision_reasons = list(event_flow.get("observed_decision_reasons") or [])
    observed_fallback_reasons = list(event_flow.get("observed_fallback_reasons") or [])
    events_in_order = list(event_flow.get("events_in_order") or [])
    if observed_selected_paths:
        lines.append(f"- **Observed paths:** `{' -> '.join(observed_selected_paths)}`")
    if observed_decision_reasons:
        lines.append(
            "- **Observed decision reasons:** "
            f"`{' -> '.join(observed_decision_reasons)}`"
        )
    if observed_fallback_reasons:
        lines.append(
            "- **Observed fallback reasons:** "
            f"`{' -> '.join(observed_fallback_reasons)}`"
        )
    if events_in_order:
        lines.append(f"- **Events in order:** `{' -> '.join(events_in_order)}`")

    if history_record:
        lines.extend(
            [
                "",
                "## DB Record",
                f"- **Timestamp:** `{history_record.get('timestamp') or 'none'}`",
                (
                    f"- **Provider:** "
                    f"`{history_record.get('transcription_provider') or 'none'}`"
                ),
                (
                    f"- **Streaming mode:** "
                    f"`{history_record.get('streaming_mode') or 'none'}`"
                ),
                (
                    f"- **Transcription path:** "
                    f"`{history_record.get('transcription_path') or 'none'}`"
                ),
                (
                    f"- **Decision reason:** "
                    f"`{history_record.get('transcription_decision_reason') or 'none'}`"
                ),
                (
                    f"- **Fallback type:** "
                    f"`{history_record.get('fallback_type') or 'none'}`"
                ),
                (
                    f"- **Fallback reason:** "
                    f"`{history_record.get('fallback_reason') or 'none'}`"
                ),
            ]
        )

    if result.get("comparison") is not None:
        lines.extend(
            [
                "",
                "## DB vs Runtime Comparison",
                (
                    f"- **DB transcription path:** "
                    f"`{comparison.get('db_transcription_path') or 'none'}`"
                ),
                (
                    f"- **Runtime selected path:** "
                    f"`{comparison.get('log_selected_path') or 'none'}`"
                ),
                (
                    f"- **Paths match:** "
                    f"`{'yes' if comparison.get('paths_match') else 'no'}`"
                ),
                (
                    f"- **DB decision reason:** "
                    f"`{comparison.get('db_transcription_decision_reason') or 'none'}`"
                ),
                (
                    f"- **Runtime decision reason:** "
                    f"`{comparison.get('log_decision_reason') or 'none'}`"
                ),
                (
                    f"- **Decision reasons match:** "
                    f"`{'yes' if comparison.get('decision_reasons_match') else 'no'}`"
                ),
            ]
        )

    log_entries = list(dict(result.get("logs") or {}).get("entries") or [])
    if log_entries:
        lines.extend(["", "## Related Runtime Log Events"])
        for entry in log_entries:
            lines.append(
                "- "
                f"`{entry.get('timestamp') or 'unknown'}` "
                f"`{entry.get('event') or 'unknown'}` "
                f"(path={entry.get('selected_path') or 'none'}, "
                f"reason={entry.get('decision_reason') or 'none'})"
            )

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=_default_history_db())
    parser.add_argument("--logs", type=Path, default=_default_logs_dir())
    parser.add_argument("--record-id", type=str, required=True)
    parser.add_argument("--oneline", action="store_true")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--card", action="store_true")
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()

    result = inspect_transcription_record_timeline(
        db_path=args.db,
        logs_path=args.logs,
        record_id=args.record_id,
    )
    if args.oneline:
        print(format_transcription_record_timeline_oneline(result))
    elif args.card:
        print(format_transcription_record_timeline_card(result))
    elif args.markdown:
        print(format_transcription_record_timeline_markdown(result))
    elif args.summary:
        print(format_transcription_record_timeline_summary(result))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
