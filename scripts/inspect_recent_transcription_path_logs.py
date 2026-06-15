"""Inspect recent transcription path decision logs from SonicInput app.log files.

This complements history DB inspection by reading runtime log evidence such as:

- ``Transcription path decision``
- ``Transcription fallback engaged``

Usage:
    uv run python scripts/inspect_recent_transcription_path_logs.py
    uv run python scripts/inspect_recent_transcription_path_logs.py --timestamp-from 2026-06-09T16:06:10
    uv run python scripts/inspect_recent_transcription_path_logs.py --record-id abc-123
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

_TARGET_EVENTS = {
    "Transcription path decision",
    "Transcription fallback engaged",
}

_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| "
    r"(?P<level>[^|]+?) \| "
    r"(?P<category>[^|]+?) \| "
    r"(?:(?P<component>\[[^\]]+\]) \| )?"
    r"(?P<message>.*?)(?: \| \| (?P<context>\{.*\}))?$"
)


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
    files = [path for path in logs_path.iterdir() if path.is_file() and path.name.startswith("app.log")]
    return sorted(files, key=lambda path: (path.stat().st_mtime, path.name))


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    for parser in (datetime.fromisoformat,):
        try:
            return parser(normalized)
        except ValueError:
            continue
    return None


def _parse_log_line(line: str) -> dict[str, Any] | None:
    match = _LOG_LINE_RE.match(line.rstrip("\n"))
    if not match:
        return None
    message = str(match.group("message") or "").strip()
    event = message[7:].strip() if message.startswith("Audio: ") else message
    context_text = match.group("context")
    context: dict[str, Any] | None = None
    if context_text:
        try:
            loaded = json.loads(context_text)
            if isinstance(loaded, dict):
                context = loaded
        except json.JSONDecodeError:
            context = {"raw_context": context_text}
    return {
        "timestamp": match.group("timestamp"),
        "level": str(match.group("level") or "").strip(),
        "category": str(match.group("category") or "").strip(),
        "component": (str(match.group("component")).strip("[]") if match.group("component") else None),
        "message": message,
        "event": event,
        "context": context or {},
    }


def inspect_recent_transcription_path_logs(
    logs_path: Path,
    *,
    timestamp_from: str | None = None,
    limit: int = 50,
    record_id: str | None = None,
) -> dict[str, Any]:
    log_files = _iter_log_files(logs_path)
    timestamp_from_dt = _parse_timestamp(timestamp_from)

    parsed_line_count = 0
    selected_entries: list[dict[str, Any]] = []
    counts_by_event: Counter[str] = Counter()
    counts_by_selected_path: Counter[str] = Counter()
    counts_by_decision_reason: Counter[str] = Counter()

    for log_file in log_files:
        for line_number, line in enumerate(log_file.read_text(encoding="utf-8").splitlines(), start=1):
            parsed = _parse_log_line(line)
            if parsed is None:
                continue
            parsed_line_count += 1
            if parsed["event"] not in _TARGET_EVENTS:
                continue
            parsed_timestamp = _parse_timestamp(parsed["timestamp"].replace(" ", "T"))
            if timestamp_from_dt is not None and parsed_timestamp is not None and parsed_timestamp < timestamp_from_dt:
                continue
            context = dict(parsed.get("context") or {})
            if record_id and str(context.get("record_id") or "") != record_id:
                continue
            selected_path = context.get("selected_path")
            decision_reason = context.get("decision_reason")
            if selected_path:
                counts_by_selected_path[str(selected_path)] += 1
            if decision_reason:
                counts_by_decision_reason[str(decision_reason)] += 1
            counts_by_event[str(parsed["event"])] += 1
            selected_entries.append(
                {
                    "source_file": str(log_file),
                    "line_number": line_number,
                    "timestamp": parsed["timestamp"],
                    "event": parsed["event"],
                    "record_id": context.get("record_id"),
                    "selected_path": selected_path,
                    "decision_reason": decision_reason,
                    "streaming_mode": context.get("streaming_mode"),
                    "provider": context.get("provider"),
                    "audio_duration": context.get("audio_duration"),
                    "audio_file_path_present": context.get("audio_file_path_present"),
                    "prefer_file_for_long_cloud_recording": context.get(
                        "prefer_file_for_long_cloud_recording"
                    ),
                    "long_recording_file_threshold_seconds": context.get(
                        "long_recording_file_threshold_seconds"
                    ),
                    "fallback_used": context.get("fallback_used"),
                    "fallback_type": context.get("fallback_type"),
                    "fallback_reason": context.get("fallback_reason"),
                }
            )

    selected_entries.sort(
        key=lambda item: (item["timestamp"], item["line_number"], item["source_file"]),
        reverse=True,
    )
    if limit >= 0:
        selected_entries = selected_entries[:limit]

    if not log_files:
        diagnosis = {
            "state": "no_log_files",
            "message": "No app.log files were found under the supplied logs path.",
        }
    elif not selected_entries:
        diagnosis = {
            "state": "no_matching_path_decision_logs",
            "message": (
                "No matching transcription path decision/fallback logs were found "
                "for the supplied filters."
            ),
        }
    else:
        diagnosis = {
            "state": "path_decision_logs_found",
            "message": (
                "Found transcription path decision/fallback runtime logs. These can "
                "now be compared against history DB rows."
            ),
        }

    return {
        "logs_path": str(logs_path),
        "timestamp_from": timestamp_from,
        "limit": limit,
        "record_id": record_id,
        "log_file_count": len(log_files),
        "parsed_line_count": parsed_line_count,
        "selected_record_count": len(selected_entries),
        "counts_by_event": dict(sorted(counts_by_event.items())),
        "counts_by_selected_path": dict(sorted(counts_by_selected_path.items())),
        "counts_by_decision_reason": dict(sorted(counts_by_decision_reason.items())),
        "diagnosis": diagnosis,
        "entries": selected_entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", type=Path, default=_default_logs_dir())
    parser.add_argument("--timestamp-from", type=str, default=None)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--record-id", type=str, default=None)
    args = parser.parse_args()

    result = inspect_recent_transcription_path_logs(
        args.logs,
        timestamp_from=args.timestamp_from,
        limit=args.limit,
        record_id=args.record_id,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
