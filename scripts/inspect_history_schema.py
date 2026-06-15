"""Inspect or upgrade the SonicInput history DB schema.

Usage:
    uv run python scripts/inspect_history_schema.py
    uv run python scripts/inspect_history_schema.py --db C:/path/history.db
    uv run python scripts/inspect_history_schema.py --db C:/path/history.db --logs C:/path/logs
    uv run python scripts/inspect_history_schema.py --upgrade
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

from sonicinput.core.services.storage.history_storage_service import (
    HistoryStorageService,
)


class _DummyConfigService:
    def get_setting(self, _key, default=None):
        return default


_TARGET_RUNTIME_EVENTS = {
    "Attempting to start HistoryStorageService",
    "HistoryStorageService started",
    "HistoryStorageService started successfully",
    "History schema expectations declared",
    "History database initialized",
    "History database schema upgraded",
}

_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| "
    r"(?P<level>[^|]+?) \| "
    r"(?P<category>[^|]+?) \| "
    r"(?:(?P<component>\[[^\]]+\]) \| )?"
    r"(?P<message>.*?)(?: \| \| (?P<context>\{.*\}))?$"
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


def _iter_log_files(logs_path: Path) -> list[Path]:
    if logs_path.is_file():
        return [logs_path]
    if not logs_path.exists():
        return []
    files = [
        path for path in logs_path.iterdir() if path.is_file() and path.name.startswith("app.log")
    ]
    return sorted(files, key=lambda path: (path.stat().st_mtime, path.name))


def _parse_log_line(line: str) -> dict[str, Any] | None:
    match = _LOG_LINE_RE.match(line.rstrip("\n"))
    if not match:
        return None
    message = str(match.group("message") or "").strip()
    event = message[7:].strip() if message.startswith("Audio: ") else message
    context_text = match.group("context")
    context: dict[str, Any] = {}
    if context_text:
        try:
            loaded = json.loads(context_text)
            if isinstance(loaded, dict):
                context = loaded
        except json.JSONDecodeError:
            context = {"raw_context": context_text}
    return {
        "timestamp": match.group("timestamp"),
        "event": event,
        "context": context,
    }


def describe_history_schema(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        raise FileNotFoundError(f"History database not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        table_row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'history_records'"
        ).fetchone()
        history_records_exists = table_row is not None
        columns: list[dict[str, Any]] = []
        if history_records_exists:
            pragma_rows = conn.execute("PRAGMA table_info(history_records)").fetchall()
            columns = [
                {
                    "cid": int(row["cid"]),
                    "name": str(row["name"]),
                    "type": str(row["type"]),
                    "notnull": bool(row["notnull"]),
                    "default": row["dflt_value"],
                    "pk": bool(row["pk"]),
                }
                for row in pragma_rows
            ]
        return {
            "db_path": str(db_path),
            "history_records_exists": history_records_exists,
            "column_count": len(columns),
            "columns": columns,
            "column_names": [column["name"] for column in columns],
            "has_audio_file_path_column": any(
                column["name"] == "audio_file_path" for column in columns
            ),
            "has_transcription_path_column": any(
                column["name"] == "transcription_path" for column in columns
            ),
            "has_transcription_decision_reason_column": any(
                column["name"] == "transcription_decision_reason" for column in columns
            ),
        }
    finally:
        conn.close()


def inspect_history_schema_runtime_logs(
    logs_path: Path,
    *,
    limit: int = 20,
) -> dict[str, Any]:
    log_files = _iter_log_files(logs_path)
    events: list[dict[str, Any]] = []
    counts_by_event: dict[str, int] = {}
    added_columns_seen: set[str] = set()
    required_columns_seen: set[str] = set()
    schema_signatures_seen: set[str] = set()
    expectation_versions_seen: set[int] = set()

    for log_file in log_files:
        for line_number, line in enumerate(
            log_file.read_text(encoding="utf-8").splitlines(), start=1
        ):
            parsed = _parse_log_line(line)
            if parsed is None:
                continue
            if parsed["event"] not in _TARGET_RUNTIME_EVENTS:
                continue
            counts_by_event[parsed["event"]] = counts_by_event.get(parsed["event"], 0) + 1
            context = dict(parsed.get("context") or {})
            added_column = context.get("added_column")
            if added_column:
                added_columns_seen.add(str(added_column))
            required_columns = context.get("required_columns")
            if isinstance(required_columns, list):
                for column_name in required_columns:
                    required_columns_seen.add(str(column_name))
            schema_signature = context.get("history_schema_signature")
            if schema_signature:
                schema_signatures_seen.add(str(schema_signature))
            expectation_version = context.get("history_schema_expectation_version")
            if isinstance(expectation_version, int):
                expectation_versions_seen.add(expectation_version)
            events.append(
                {
                    "source_file": str(log_file),
                    "line_number": line_number,
                    "timestamp": parsed["timestamp"],
                    "event": parsed["event"],
                    "context": context,
                }
            )

    events.sort(
        key=lambda item: (item["timestamp"], item["line_number"], item["source_file"]),
        reverse=True,
    )
    if limit >= 0:
        events = events[:limit]

    def _latest_event(name: str) -> dict[str, Any] | None:
        for event in events:
            if event["event"] == name:
                return event
        return None

    if not log_files:
        diagnosis = {
            "state": "no_log_files",
            "message": "No app.log files were found under the supplied logs path.",
        }
    elif not events:
        diagnosis = {
            "state": "no_matching_schema_runtime_events",
            "message": (
                "No history schema/runtime startup events were found in the supplied logs."
            ),
        }
    else:
        diagnosis = {
            "state": "schema_runtime_events_found",
            "message": (
                "Found history schema/runtime startup events. These can confirm which "
                "schema upgrade steps ran in a real app session."
            ),
        }

    return {
        "logs_path": str(logs_path),
        "limit": limit,
        "log_file_count": len(log_files),
        "selected_event_count": len(events),
        "counts_by_event": dict(sorted(counts_by_event.items())),
        "added_columns_seen": sorted(added_columns_seen),
        "required_columns_seen": sorted(required_columns_seen),
        "schema_signatures_seen": sorted(schema_signatures_seen),
        "expectation_versions_seen": sorted(expectation_versions_seen),
        "has_transcription_path_upgrade_event": "transcription_path" in added_columns_seen,
        "has_transcription_decision_reason_upgrade_event": (
            "transcription_decision_reason" in added_columns_seen
        ),
        "has_transcription_path_expectation_event": (
            "transcription_path" in required_columns_seen
        ),
        "has_transcription_decision_reason_expectation_event": (
            "transcription_decision_reason" in required_columns_seen
        ),
        "latest_schema_expectations_event": _latest_event(
            "History schema expectations declared"
        ),
        "latest_schema_upgrade_event": _latest_event("History database schema upgraded"),
        "latest_database_initialized_event": _latest_event("History database initialized"),
        "latest_history_service_start_event": _latest_event("HistoryStorageService started"),
        "diagnosis": diagnosis,
        "events": events,
    }


def inspect_or_upgrade_history_schema(
    db_path: Path,
    *,
    upgrade: bool = False,
    logs_path: Path | None = None,
) -> dict[str, Any]:
    before = describe_history_schema(db_path)

    if upgrade:
        service = HistoryStorageService(_DummyConfigService())
        service._db_path = db_path
        service._init_database()

    after = describe_history_schema(db_path)
    before_names = set(before["column_names"])
    after_names = set(after["column_names"])
    return {
        "db_path": str(db_path),
        "upgrade_requested": upgrade,
        "schema_changed": before != after,
        "added_columns": sorted(after_names - before_names),
        "removed_columns": sorted(before_names - after_names),
        "before": before,
        "after": after,
        "runtime_logs": (
            inspect_history_schema_runtime_logs(logs_path) if logs_path is not None else None
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=_default_history_db())
    parser.add_argument("--upgrade", action="store_true")
    parser.add_argument("--logs", type=Path, default=None)
    args = parser.parse_args()

    result = inspect_or_upgrade_history_schema(
        args.db,
        upgrade=args.upgrade,
        logs_path=args.logs,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
