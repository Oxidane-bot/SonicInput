"""Generate a local, privacy-safe quality audit for SonicInput history.

The report intentionally omits transcript text. It only stores metadata,
lengths, ratios, and heuristic anomaly labels so it can be used for prompt and
architecture experiments without committing private voice input content.

Usage:
    uv run python scripts/audit_transcript_quality.py --limit 500
    uv run python scripts/audit_transcript_quality.py --db C:/path/history.db
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sonicinput.core.quality import TranscriptQualityValidator

_LONG_RECORDING_FILE_THRESHOLD_SECONDS = 90.0


@dataclass(frozen=True)
class AuditFilters:
    timestamp_from: str | None = None
    observable_path_only: bool = False
    long_recording_cloud_candidates_only: bool = False


def _history_schema_columns(db_path: Path) -> list[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("PRAGMA table_info(history_records)").fetchall()
        return [str(row[1]) for row in rows]
    finally:
        conn.close()


def _default_history_db() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "SonicInput" / "history" / "history.db"
    return Path.home() / "AppData" / "Roaming" / "SonicInput" / "history" / "history.db"


def _default_output_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("quality_audit") / f"transcript_quality_audit_{timestamp}.jsonl"


def _length_ratio(numerator: str | None, denominator: str | None) -> float | None:
    denominator_length = len(denominator or "")
    if denominator_length == 0:
        return None
    return round(len(numerator or "") / denominator_length, 4)


def _safe_ratio(numerator: float | int, denominator: float | int) -> float | None:
    try:
        denominator_value = float(denominator)
    except (TypeError, ValueError):
        return None
    if denominator_value <= 0:
        return None
    return round(float(numerator) / denominator_value, 4)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    if percentile <= 0:
        return round(values[0], 4)
    if percentile >= 100:
        return round(values[-1], 4)
    rank = (len(values) - 1) * (percentile / 100.0)
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(values) - 1)
    weight = rank - lower_index
    interpolated = values[lower_index] * (1.0 - weight) + values[upper_index] * weight
    return round(interpolated, 4)


def _row_value(row: sqlite3.Row, key: str, default: Any = None) -> Any:
    if key not in row.keys():
        return default
    return row[key]


def _is_observable_transcription_path(transcription_path: str | None) -> bool:
    normalized = str(transcription_path or "").strip().lower()
    return normalized not in {"", "standard"}


def _ensure_summary_counter_keys(counters: Counter[str]) -> None:
    for key in (
        "records",
        "chunked_records",
        "fallback_used",
        "fallback_success_records",
        "empty_transcription_records",
        "empty_chunked_result_fallbacks",
        "low_quality_chunked_result_fallbacks",
        "quality_alert_records",
        "long_recording_cloud_candidate_records",
        "long_recording_cloud_candidate_observable_records",
        "long_recording_primary_file_path_records",
        "transcription_path_observable_records",
        "transcription_path_unknown_records",
    ):
        counters[key] += 0


def _row_to_audit(
    row: sqlite3.Row,
    validator: TranscriptQualityValidator,
) -> dict[str, Any]:
    transcription_text = row["transcription_text"] or ""
    ai_text = row["ai_optimized_text"] or ""
    final_text = row["final_text"] or ""
    duration = float(row["duration"] or 0.0)
    transcription_duration = float(row["transcription_duration"] or 0.0)
    used_fallback = bool(row["used_fallback"])

    labels: list[str] = []
    if validator.is_low_information_input(transcription_text):
        labels.append("low_information_input")
    if ai_text:
        result = validator.validate(transcription_text, ai_text)
        labels.extend(result.reasons)
    transcription_path = _row_value(row, "transcription_path", "standard")
    transcription_path_observable = _is_observable_transcription_path(transcription_path)
    long_recording_cloud_candidate = _is_long_recording_cloud_candidate(row)

    return {
        "record_id": row["id"],
        "timestamp": row["timestamp"],
        "duration": duration,
        "transcription_provider": row["transcription_provider"],
        "transcription_status": row["transcription_status"],
        "streaming_mode": row["streaming_mode"],
        "transcription_path": transcription_path,
        "transcription_path_observable": transcription_path_observable,
        "transcription_duration": transcription_duration,
        "transcription_rtf": _safe_ratio(transcription_duration, duration),
        "long_recording_cloud_candidate": long_recording_cloud_candidate,
        "used_fallback": used_fallback,
        "fallback_type": row["fallback_type"],
        "fallback_reason": row["fallback_reason"],
        "ai_provider": row["ai_provider"],
        "ai_status": row["ai_status"],
        "ai_error": row["ai_error"],
        "transcription_length": len(transcription_text),
        "ai_length": len(ai_text),
        "final_length": len(final_text),
        "ai_to_transcription_ratio": _length_ratio(ai_text, transcription_text),
        "final_to_transcription_ratio": _length_ratio(final_text, transcription_text),
        "anomaly_labels": sorted(set(labels)),
        "quality_alert": bool(labels),
    }


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


def _iter_history_rows(db_path: Path, timestamp_from: str | None = None) -> list[sqlite3.Row]:
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


def run_audit(
    db_path: Path,
    output_path: Path,
    limit: int | None,
    *,
    filters: AuditFilters | None = None,
) -> dict[str, Any]:
    if not db_path.exists():
        raise FileNotFoundError(f"History database not found: {db_path}")

    filters = filters or AuditFilters()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    validator = TranscriptQualityValidator()
    schema_columns = _history_schema_columns(db_path)
    rows = _iter_history_rows(db_path, timestamp_from=filters.timestamp_from)

    counters: Counter[str] = Counter()
    anomaly_counters: Counter[str] = Counter()
    transcription_durations: list[float] = []
    transcription_rtfs: list[float] = []

    with output_path.open("w", encoding="utf-8") as fp:
        for row in rows:
            audit_row = _row_to_audit(row, validator)
            if filters.observable_path_only and not audit_row["transcription_path_observable"]:
                continue
            if (
                filters.long_recording_cloud_candidates_only
                and not audit_row["long_recording_cloud_candidate"]
            ):
                continue
            counters["records"] += 1
            counters[f"transcription_status:{audit_row['transcription_status']}"] += 1
            counters[f"ai_status:{audit_row['ai_status']}"] += 1
            counters[f"transcription_path:{audit_row['transcription_path']}"] += 1
            if audit_row["transcription_path_observable"]:
                counters["transcription_path_observable_records"] += 1
            else:
                counters["transcription_path_unknown_records"] += 1
            if audit_row["streaming_mode"] == "chunked":
                counters["chunked_records"] += 1
            if audit_row["long_recording_cloud_candidate"]:
                counters["long_recording_cloud_candidate_records"] += 1
                if audit_row["transcription_path_observable"]:
                    counters["long_recording_cloud_candidate_observable_records"] += 1
            if audit_row["transcription_path"] == "cloud_file_long_recording":
                counters["long_recording_primary_file_path_records"] += 1
            if audit_row["used_fallback"]:
                counters["fallback_used"] += 1
            if audit_row["fallback_reason"] == "empty_chunked_result":
                counters["empty_chunked_result_fallbacks"] += 1
            if audit_row["fallback_reason"] == "low_quality_chunked_result":
                counters["low_quality_chunked_result_fallbacks"] += 1
            if audit_row["quality_alert"]:
                counters["quality_alert_records"] += 1
            if (
                audit_row["used_fallback"]
                and audit_row["transcription_status"] == "success"
                and audit_row["transcription_length"] > 0
            ):
                counters["fallback_success_records"] += 1
            if audit_row["transcription_status"] == "success" and audit_row["transcription_length"] == 0:
                counters["empty_transcription_records"] += 1
            for label in audit_row["anomaly_labels"]:
                anomaly_counters[label] += 1
            if audit_row["transcription_duration"] > 0:
                transcription_durations.append(float(audit_row["transcription_duration"]))
            if audit_row["transcription_rtf"] is not None:
                transcription_rtfs.append(float(audit_row["transcription_rtf"]))
            fp.write(json.dumps(audit_row, ensure_ascii=False) + "\n")
            if limit is not None and counters["records"] >= limit:
                break

    transcription_durations.sort()
    transcription_rtfs.sort()
    _ensure_summary_counter_keys(counters)
    total_records = counters["records"]
    chunked_records = counters["chunked_records"]
    fallback_used = counters["fallback_used"]
    long_recording_cloud_candidates = counters["long_recording_cloud_candidate_records"]
    observable_long_recording_cloud_candidates = counters[
        "long_recording_cloud_candidate_observable_records"
    ]
    metrics = {
        "transcription_duration_p50_seconds": _percentile(
            transcription_durations, 50
        ),
        "transcription_duration_p95_seconds": _percentile(
            transcription_durations, 95
        ),
        "transcription_rtf_p50": _percentile(transcription_rtfs, 50),
        "transcription_rtf_p95": _percentile(transcription_rtfs, 95),
        "empty_result_rate": _safe_ratio(
            counters["empty_transcription_records"],
            total_records,
        ),
        "empty_chunked_result_fallback_rate": _safe_ratio(
            counters["empty_chunked_result_fallbacks"],
            chunked_records,
        ),
        "low_quality_chunked_result_fallback_rate": _safe_ratio(
            counters["low_quality_chunked_result_fallbacks"],
            chunked_records,
        ),
        "long_recording_primary_file_path_rate": _safe_ratio(
            counters["long_recording_primary_file_path_records"],
            chunked_records,
        ),
        "long_recording_cloud_candidate_rate": _safe_ratio(
            long_recording_cloud_candidates,
            chunked_records,
        ),
        "transcription_path_observable_rate": _safe_ratio(
            counters["transcription_path_observable_records"],
            total_records,
        ),
        "long_recording_cloud_candidate_observable_rate": _safe_ratio(
            observable_long_recording_cloud_candidates,
            long_recording_cloud_candidates,
        ),
        "long_recording_primary_file_path_adoption_rate": _safe_ratio(
            counters["long_recording_primary_file_path_records"],
            long_recording_cloud_candidates,
        ),
        "long_recording_primary_file_path_adoption_rate_on_observable_candidates": _safe_ratio(
            counters["long_recording_primary_file_path_records"],
            observable_long_recording_cloud_candidates,
        ),
        "fallback_success_rate": _safe_ratio(
            counters["fallback_success_records"],
            fallback_used,
        ),
        "final_text_quality_alert_rate": _safe_ratio(
            counters["quality_alert_records"],
            total_records,
        ),
    }

    summary = {
        "db_path": str(db_path),
        "output_path": str(output_path),
        "limit": limit,
        "schema": {
            "column_count": len(schema_columns),
            "has_audio_file_path_column": "audio_file_path" in schema_columns,
            "has_transcription_path_column": "transcription_path" in schema_columns,
        },
        "source_record_count": len(rows),
        "selected_record_count": counters["records"],
        "filters": {
            "timestamp_from": filters.timestamp_from,
            "observable_path_only": filters.observable_path_only,
            "long_recording_cloud_candidates_only": filters.long_recording_cloud_candidates_only,
        },
        "counts": dict(sorted(counters.items())),
        "anomalies": dict(sorted(anomaly_counters.items())),
        "metrics": metrics,
    }
    summary_path = output_path.with_suffix(".summary.json")
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary["summary_path"] = str(summary_path)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=_default_history_db())
    parser.add_argument("--output", type=Path, default=_default_output_path())
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--timestamp-from", type=str, default=None)
    parser.add_argument("--observable-path-only", action="store_true")
    parser.add_argument("--long-recording-cloud-candidates-only", action="store_true")
    args = parser.parse_args()

    summary = run_audit(
        args.db,
        args.output,
        args.limit,
        filters=AuditFilters(
            timestamp_from=args.timestamp_from,
            observable_path_only=args.observable_path_only,
            long_recording_cloud_candidates_only=args.long_recording_cloud_candidates_only,
        ),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
