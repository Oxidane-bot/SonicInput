"""Inspect recent history rows for post-upgrade transcription_path evidence.

This helper is meant to answer a narrower Stage 6 question than the full audit:

- Does the target DB schema already contain ``transcription_path``?
- Are there any rows created after a known timestamp?
- If yes, do those post-timestamp rows contain observable non-default
  ``transcription_path`` values yet?

Usage:
    uv run python scripts/inspect_recent_transcription_paths.py
    uv run python scripts/inspect_recent_transcription_paths.py --timestamp-from 2026-06-09T12:00:00
    uv run python scripts/inspect_recent_transcription_paths.py --long-recording-cloud-candidates-only
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

_LONG_RECORDING_FILE_THRESHOLD_SECONDS = 90.0


def _default_history_db() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "SonicInput" / "history" / "history.db"
    return Path.home() / "AppData" / "Roaming" / "SonicInput" / "history" / "history.db"


def _history_schema_columns(db_path: Path) -> list[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("PRAGMA table_info(history_records)").fetchall()
        return [str(row[1]) for row in rows]
    finally:
        conn.close()


def _iter_history_rows(
    db_path: Path,
    *,
    timestamp_from: str | None = None,
) -> list[sqlite3.Row]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        sql = "SELECT * FROM history_records ORDER BY timestamp DESC, id DESC"
        params: tuple[str, ...] = ()
        if timestamp_from:
            sql = (
                "SELECT * FROM history_records "
                "WHERE timestamp >= ? "
                "ORDER BY timestamp DESC, id DESC"
            )
            params = (timestamp_from,)
        return list(conn.execute(sql, params))
    finally:
        conn.close()


def _row_value(row: sqlite3.Row, key: str, default: Any = None) -> Any:
    if key not in row.keys():
        return default
    return row[key]


def _is_observable_transcription_path(transcription_path: str | None) -> bool:
    normalized = str(transcription_path or "").strip().lower()
    return normalized not in {"", "standard"}


def _is_long_recording_cloud_candidate(row: sqlite3.Row) -> bool:
    provider = str(row["transcription_provider"] or "").strip().lower()
    streaming_mode = str(row["streaming_mode"] or "").strip().lower()
    audio_file_path = str(_row_value(row, "audio_file_path", "") or "").strip()
    transcription_path = str(_row_value(row, "transcription_path", "") or "").strip()
    try:
        duration = float(row["duration"] or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    if provider in {"", "local"}:
        return False
    if streaming_mode != "chunked":
        return False
    if duration < _LONG_RECORDING_FILE_THRESHOLD_SECONDS:
        return False
    return bool(audio_file_path) or transcription_path == "cloud_file_long_recording"


def _row_to_payload(row: sqlite3.Row) -> dict[str, Any]:
    transcription_path = _row_value(row, "transcription_path", "standard")
    observable = _is_observable_transcription_path(transcription_path)
    return {
        "record_id": row["id"],
        "timestamp": row["timestamp"],
        "duration": float(row["duration"] or 0.0),
        "transcription_provider": row["transcription_provider"],
        "transcription_status": row["transcription_status"],
        "streaming_mode": row["streaming_mode"],
        "transcription_path": transcription_path,
        "transcription_decision_reason": _row_value(
            row, "transcription_decision_reason", None
        ),
        "transcription_path_observable": observable,
        "long_recording_cloud_candidate": _is_long_recording_cloud_candidate(row),
        "audio_file_path_present": bool(
            str(_row_value(row, "audio_file_path", "") or "").strip()
        ),
    }


def _diagnose(
    *,
    has_transcription_path_column: bool,
    timestamp_from: str | None,
    source_record_count: int,
    selected_records: list[dict[str, Any]],
) -> dict[str, str]:
    if not has_transcription_path_column:
        return {
            "state": "schema_missing",
            "message": (
                "history_records schema still lacks transcription_path, so runtime path "
                "writes are not observable yet."
            ),
        }
    if timestamp_from and source_record_count == 0:
        return {
            "state": "no_records_after_timestamp",
            "message": (
                "No history rows were created at or after the supplied timestamp, so no "
                "post-upgrade runtime inference is possible yet."
            ),
        }
    if not selected_records:
        return {
            "state": "no_matching_records",
            "message": (
                "Rows exist in the source window, but none matched the current filters."
            ),
        }
    observable_count = sum(
        1 for record in selected_records if record["transcription_path_observable"]
    )
    if observable_count > 0:
        return {
            "state": "observable_writes_present",
            "message": (
                "At least one selected row has a non-default transcription_path, so the "
                "runtime write path is now observable."
            ),
        }
    if timestamp_from:
        return {
            "state": "no_observable_writes_after_timestamp",
            "message": (
                "Rows exist after the supplied timestamp, but all selected rows still show "
                "the default transcription_path='standard'. This is suspicious, but only "
                "for rows truly created after the schema upgrade."
            ),
        }
    return {
        "state": "inconclusive_without_timestamp_from",
        "message": (
            "All selected rows currently show transcription_path='standard'. Without a "
            "post-upgrade timestamp filter, these may still be older rows backfilled by "
            "ALTER TABLE default values."
        ),
    }


def inspect_recent_transcription_paths(
    db_path: Path,
    *,
    timestamp_from: str | None = None,
    limit: int = 20,
    long_recording_cloud_candidates_only: bool = False,
) -> dict[str, Any]:
    if not db_path.exists():
        raise FileNotFoundError(f"History database not found: {db_path}")

    schema_columns = _history_schema_columns(db_path)
    rows = _iter_history_rows(db_path, timestamp_from=timestamp_from)
    selected_records: list[dict[str, Any]] = []
    counts_by_path: Counter[str] = Counter()

    for row in rows:
        payload = _row_to_payload(row)
        if (
            long_recording_cloud_candidates_only
            and not payload["long_recording_cloud_candidate"]
        ):
            continue
        selected_records.append(payload)
        counts_by_path[str(payload["transcription_path"])] += 1
        if len(selected_records) >= max(0, limit):
            break

    observable_count = sum(
        1 for record in selected_records if record["transcription_path_observable"]
    )
    long_candidate_count = sum(
        1 for record in selected_records if record["long_recording_cloud_candidate"]
    )
    diagnosis = _diagnose(
        has_transcription_path_column="transcription_path" in schema_columns,
        timestamp_from=timestamp_from,
        source_record_count=len(rows),
        selected_records=selected_records,
    )

    return {
        "db_path": str(db_path),
        "timestamp_from": timestamp_from,
        "limit": limit,
        "long_recording_cloud_candidates_only": long_recording_cloud_candidates_only,
        "schema": {
            "column_count": len(schema_columns),
            "has_audio_file_path_column": "audio_file_path" in schema_columns,
            "has_transcription_path_column": "transcription_path" in schema_columns,
            "has_transcription_decision_reason_column": (
                "transcription_decision_reason" in schema_columns
            ),
        },
        "source_record_count": len(rows),
        "selected_record_count": len(selected_records),
        "observable_record_count": observable_count,
        "non_observable_record_count": len(selected_records) - observable_count,
        "long_recording_cloud_candidate_record_count": long_candidate_count,
        "counts_by_transcription_path": dict(sorted(counts_by_path.items())),
        "diagnosis": diagnosis,
        "records": selected_records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=_default_history_db())
    parser.add_argument("--timestamp-from", type=str, default=None)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--long-recording-cloud-candidates-only", action="store_true")
    args = parser.parse_args()

    result = inspect_recent_transcription_paths(
        args.db,
        timestamp_from=args.timestamp_from,
        limit=args.limit,
        long_recording_cloud_candidates_only=args.long_recording_cloud_candidates_only,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
