import json
import importlib.util
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4


def _load_run_audit():
    module_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "audit_transcript_quality.py"
    )
    spec = importlib.util.spec_from_file_location(
        "audit_transcript_quality", module_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _create_history_db(db_path: Path) -> None:
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
                transcription_duration REAL NOT NULL,
                used_fallback INTEGER NOT NULL,
                fallback_type TEXT NOT NULL,
                fallback_reason TEXT,
                transcription_text TEXT,
                ai_optimized_text TEXT,
                ai_provider TEXT,
                ai_status TEXT NOT NULL,
                ai_error TEXT,
                final_text TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO history_records (
                id, timestamp, audio_file_path, duration, transcription_provider, transcription_status,
                streaming_mode, transcription_path, transcription_duration, used_fallback, fallback_type,
                fallback_reason, transcription_text, ai_optimized_text, ai_provider,
                ai_status, ai_error, final_text
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "r1",
                    "2026-06-09T10:00:00",
                    "quality_audit/r1.wav",
                    12.0,
                    "local",
                    "success",
                    "chunked",
                    "streaming_chunked",
                    6.0,
                    0,
                    "none",
                    None,
                    "今天先检查 review agent 的边界今天先检查 review agent 的边界然后再跑回归",
                    "",
                    None,
                    "pending",
                    None,
                    "今天先检查 review agent 的边界今天先检查 review agent 的边界然后再跑回归",
                ),
                (
                    "r2",
                    "2026-06-09T09:58:00",
                    "quality_audit/r2.wav",
                    10.0,
                    "local",
                    "success",
                    "chunked",
                    "local_sync_fallback",
                    5.0,
                    1,
                    "local_sync",
                    "low_quality_chunked_result",
                    "fallback recovered text",
                    "",
                    None,
                    "pending",
                    None,
                    "fallback recovered text",
                ),
                (
                    "r3",
                    "2026-06-09T09:56:00",
                    "quality_audit/r3.wav",
                    8.0,
                    "local",
                    "success",
                    "chunked",
                    "cloud_file_fallback",
                    4.0,
                    1,
                    "local_sync",
                    "empty_chunked_result",
                    "",
                    "",
                    None,
                    "pending",
                    None,
                    "",
                ),
                (
                    "r4",
                    "2026-06-09T09:54:00",
                    "quality_audit/r4.wav",
                    140.0,
                    "openai",
                    "success",
                    "chunked",
                    "cloud_file_long_recording",
                    7.0,
                    0,
                    "none",
                    None,
                    "嗯",
                    "",
                    None,
                    "skipped",
                    None,
                    "嗯",
                ),
                (
                    "r5",
                    "2026-06-09T09:52:00",
                    "quality_audit/r5.wav",
                    120.0,
                    "openai",
                    "success",
                    "chunked",
                    "streaming_chunked",
                    8.0,
                    0,
                    "none",
                    None,
                    "今天继续测试长录音 chunked 主路径的观测指标",
                    "",
                    None,
                    "pending",
                    None,
                    "今天继续测试长录音 chunked 主路径的观测指标",
                ),
                (
                    "r6",
                    "2026-06-09T09:50:00",
                    "quality_audit/r6.wav",
                    130.0,
                    "openai",
                    "success",
                    "chunked",
                    "standard",
                    0.0,
                    0,
                    "none",
                    None,
                    "今天再补一条旧样本用于区分可观测和不可观测候选",
                    "",
                    None,
                    "pending",
                    None,
                    "今天再补一条旧样本用于区分可观测和不可观测候选",
                ),
            ],
        )
        conn.commit()


def _create_legacy_history_db_without_transcription_path(db_path: Path) -> None:
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
                transcription_duration REAL NOT NULL,
                used_fallback INTEGER NOT NULL,
                fallback_type TEXT NOT NULL,
                fallback_reason TEXT,
                transcription_text TEXT,
                ai_optimized_text TEXT,
                ai_provider TEXT,
                ai_status TEXT NOT NULL,
                ai_error TEXT,
                final_text TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO history_records (
                id, timestamp, audio_file_path, duration, transcription_provider, transcription_status,
                streaming_mode, transcription_duration, used_fallback, fallback_type,
                fallback_reason, transcription_text, ai_optimized_text, ai_provider,
                ai_status, ai_error, final_text
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-r1",
                "2026-06-09T08:00:00",
                "quality_audit/legacy-r1.wav",
                95.0,
                "openai",
                "success",
                "chunked",
                4.0,
                0,
                "none",
                None,
                "legacy row still has no path column",
                "",
                None,
                "pending",
                None,
                "legacy row still has no path column",
            ),
        )
        conn.commit()


def test_run_audit_computes_phase6_metrics_and_labels() -> None:
    module = _load_run_audit()
    run_audit = module.run_audit
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    db_path = (base_dir / f"audit_metrics_{token}.db").resolve()
    output_path = (base_dir / f"audit_metrics_{token}.jsonl").resolve()
    try:
        _create_history_db(db_path)

        summary = run_audit(db_path, output_path, limit=None)

        assert summary["source_record_count"] == 6
        assert summary["selected_record_count"] == 6
        assert summary["schema"]["has_audio_file_path_column"] is True
        assert summary["schema"]["has_transcription_path_column"] is True
        assert summary["filters"]["timestamp_from"] is None
        assert summary["filters"]["observable_path_only"] is False
        assert summary["filters"]["long_recording_cloud_candidates_only"] is False
        assert summary["counts"]["records"] == 6
        assert summary["counts"]["chunked_records"] == 6
        assert summary["counts"]["fallback_used"] == 2
        assert summary["counts"]["fallback_success_records"] == 1
        assert summary["counts"]["empty_chunked_result_fallbacks"] == 1
        assert summary["counts"]["low_quality_chunked_result_fallbacks"] == 1
        assert summary["counts"]["long_recording_cloud_candidate_records"] == 3
        assert (
            summary["counts"]["long_recording_cloud_candidate_observable_records"] == 2
        )
        assert summary["counts"]["transcription_path:cloud_file_long_recording"] == 1
        assert summary["counts"]["long_recording_primary_file_path_records"] == 1
        assert summary["counts"]["transcription_path_observable_records"] == 5
        assert summary["counts"]["transcription_path_unknown_records"] == 1

        assert summary["anomalies"]["chunk_boundary_repeat"] == 1
        assert summary["anomalies"]["fallback_candidate"] == 1
        assert summary["anomalies"]["low_information_input"] == 2

        assert summary["metrics"]["transcription_duration_p50_seconds"] == 6.0
        assert summary["metrics"]["transcription_rtf_p50"] == 0.2833
        assert summary["metrics"]["chunk_boundary_repeat_rate"] == 0.1667
        assert summary["metrics"]["empty_result_rate"] == 0.1667
        assert summary["metrics"]["empty_chunked_result_fallback_rate"] == 0.1667
        assert summary["metrics"]["low_quality_chunked_result_fallback_rate"] == 0.1667
        assert summary["metrics"]["long_recording_primary_file_path_rate"] == 0.1667
        assert summary["metrics"]["long_recording_cloud_candidate_rate"] == 0.5
        assert summary["metrics"]["transcription_path_observable_rate"] == 0.8333
        assert (
            summary["metrics"]["long_recording_cloud_candidate_observable_rate"]
            == 0.6667
        )
        assert (
            summary["metrics"]["long_recording_primary_file_path_adoption_rate"]
            == 0.3333
        )
        assert (
            summary["metrics"][
                "long_recording_primary_file_path_adoption_rate_on_observable_candidates"
            ]
            == 0.5
        )
        assert summary["metrics"]["fallback_success_rate"] == 0.5
        assert summary["metrics"]["final_text_quality_alert_rate"] == 0.5

        rows = [
            json.loads(line)
            for line in output_path.read_text(encoding="utf-8").splitlines()
        ]
        by_id = {row["record_id"]: row for row in rows}
        assert by_id["r1"]["transcription_rtf"] == 0.5
        assert by_id["r4"]["transcription_path"] == "cloud_file_long_recording"
        assert by_id["r4"]["transcription_path_observable"] is True
        assert by_id["r4"]["long_recording_cloud_candidate"] is True
        assert by_id["r5"]["long_recording_cloud_candidate"] is True
        assert by_id["r6"]["transcription_path"] == "standard"
        assert by_id["r6"]["transcription_path_observable"] is False
        assert by_id["r6"]["long_recording_cloud_candidate"] is True
        assert "chunk_boundary_repeat" in by_id["r1"]["anomaly_labels"]
        assert by_id["r1"]["quality_alert"] is True
        assert "fallback_candidate" in by_id["r4"]["anomaly_labels"]
        assert by_id["r4"]["quality_alert"] is True
        assert by_id["r5"]["quality_alert"] is False
    finally:
        summary_path = output_path.with_suffix(".summary.json")
        for path in (db_path, output_path, summary_path):
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def test_run_audit_reports_legacy_schema_when_transcription_path_column_is_missing() -> (
    None
):
    module = _load_run_audit()
    run_audit = module.run_audit
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    db_path = (base_dir / f"audit_metrics_legacy_schema_{token}.db").resolve()
    output_path = (base_dir / f"audit_metrics_legacy_schema_{token}.jsonl").resolve()
    try:
        _create_legacy_history_db_without_transcription_path(db_path)

        summary = run_audit(db_path, output_path, limit=None)

        assert summary["schema"]["has_audio_file_path_column"] is True
        assert summary["schema"]["has_transcription_path_column"] is False
        assert summary["source_record_count"] == 1
        assert summary["selected_record_count"] == 1
        assert summary["counts"]["records"] == 1
        assert summary["counts"]["transcription_path_unknown_records"] == 1
        assert summary["counts"]["long_recording_cloud_candidate_records"] == 1

        rows = [
            json.loads(line)
            for line in output_path.read_text(encoding="utf-8").splitlines()
        ]
        assert rows[0]["transcription_path"] == "standard"
        assert rows[0]["transcription_path_observable"] is False
    finally:
        summary_path = output_path.with_suffix(".summary.json")
        for path in (db_path, output_path, summary_path):
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def test_run_audit_can_focus_on_observable_long_recording_candidates() -> None:
    module = _load_run_audit()
    run_audit = module.run_audit
    filters = module.AuditFilters
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    db_path = (base_dir / f"audit_metrics_filtered_{token}.db").resolve()
    output_path = (base_dir / f"audit_metrics_filtered_{token}.jsonl").resolve()
    try:
        _create_history_db(db_path)

        summary = run_audit(
            db_path,
            output_path,
            limit=None,
            filters=filters(
                observable_path_only=True,
                long_recording_cloud_candidates_only=True,
                timestamp_from="2026-06-09T09:52:00",
            ),
        )

        assert summary["source_record_count"] == 5
        assert summary["selected_record_count"] == 2
        assert summary["filters"]["timestamp_from"] == "2026-06-09T09:52:00"
        assert summary["filters"]["observable_path_only"] is True
        assert summary["filters"]["long_recording_cloud_candidates_only"] is True
        assert summary["counts"]["records"] == 2
        assert summary["counts"]["chunked_records"] == 2
        assert summary["counts"]["long_recording_cloud_candidate_records"] == 2
        assert (
            summary["counts"]["long_recording_cloud_candidate_observable_records"] == 2
        )
        assert summary["counts"]["transcription_path_observable_records"] == 2
        assert summary["counts"]["long_recording_primary_file_path_records"] == 1
        assert summary["metrics"]["long_recording_cloud_candidate_rate"] == 1.0
        assert (
            summary["metrics"]["long_recording_cloud_candidate_observable_rate"] == 1.0
        )
        assert (
            summary["metrics"]["long_recording_primary_file_path_adoption_rate"] == 0.5
        )
        assert (
            summary["metrics"][
                "long_recording_primary_file_path_adoption_rate_on_observable_candidates"
            ]
            == 0.5
        )

        rows = [
            json.loads(line)
            for line in output_path.read_text(encoding="utf-8").splitlines()
        ]
        assert {row["record_id"] for row in rows} == {"r4", "r5"}
    finally:
        summary_path = output_path.with_suffix(".summary.json")
        for path in (db_path, output_path, summary_path):
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def test_run_audit_reports_zero_selected_records_for_empty_filtered_subset() -> None:
    module = _load_run_audit()
    run_audit = module.run_audit
    filters = module.AuditFilters
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    db_path = (base_dir / f"audit_metrics_empty_filtered_{token}.db").resolve()
    output_path = (base_dir / f"audit_metrics_empty_filtered_{token}.jsonl").resolve()
    try:
        _create_history_db(db_path)

        summary = run_audit(
            db_path,
            output_path,
            limit=None,
            filters=filters(timestamp_from="2026-06-09T10:01:00"),
        )

        assert summary["source_record_count"] == 0
        assert summary["selected_record_count"] == 0
        assert summary["counts"]["records"] == 0
        assert summary["counts"]["chunked_records"] == 0
        assert summary["counts"]["long_recording_cloud_candidate_records"] == 0
        assert summary["counts"]["transcription_path_observable_records"] == 0
        assert summary["metrics"]["transcription_duration_p50_seconds"] is None
        assert (
            summary["metrics"]["long_recording_primary_file_path_adoption_rate"] is None
        )
        assert output_path.read_text(encoding="utf-8") == ""
    finally:
        summary_path = output_path.with_suffix(".summary.json")
        for path in (db_path, output_path, summary_path):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
