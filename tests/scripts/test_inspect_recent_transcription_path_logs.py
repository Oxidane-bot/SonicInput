import importlib.util
import sys
from pathlib import Path
from uuid import uuid4


def _load_module():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "inspect_recent_transcription_path_logs.py"
    )
    spec = importlib.util.spec_from_file_location(
        "inspect_recent_transcription_path_logs", module_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_log(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_inspect_recent_transcription_path_logs_parses_decision_and_fallback_lines() -> (
    None
):
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = (base_dir / f"logs_parse_{uuid4().hex}").resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        _write_log(
            logs_dir / "app.log",
            [
                (
                    "2026-06-09 16:20:00 | INFO     | audio        | [audio] | "
                    "Audio: Transcription path decision | | "
                    '{"record_id":"rec-1","selected_path":"streaming_chunked",'
                    '"decision_reason":"streaming_stop_result","streaming_mode":"chunked",'
                    '"provider":"groq","audio_duration":98.624}'
                ),
                (
                    "2026-06-09 16:20:01 | INFO     | audio        | [audio] | "
                    "Audio: Transcription fallback engaged | | "
                    '{"record_id":"rec-1","selected_path":"cloud_file_fallback",'
                    '"decision_reason":"low_quality_chunked_result","fallback_used":true,'
                    '"fallback_type":"cloud_file","fallback_reason":"low_quality_chunked_result"}'
                ),
            ],
        )

        result = module.inspect_recent_transcription_path_logs(logs_dir)

        assert result["selected_record_count"] == 2
        assert result["counts_by_event"] == {
            "Transcription fallback engaged": 1,
            "Transcription path decision": 1,
        }
        assert result["counts_by_selected_path"] == {
            "cloud_file_fallback": 1,
            "streaming_chunked": 1,
        }
        assert result["counts_by_decision_reason"] == {
            "low_quality_chunked_result": 1,
            "streaming_stop_result": 1,
        }
        assert result["entries"][0]["event"] == "Transcription fallback engaged"
        assert result["entries"][1]["event"] == "Transcription path decision"
    finally:
        for path in logs_dir.glob("*"):
            path.unlink()
        logs_dir.rmdir()


def test_inspect_recent_transcription_path_logs_filters_by_timestamp_and_record_id() -> (
    None
):
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = (base_dir / f"logs_filter_{uuid4().hex}").resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        _write_log(
            logs_dir / "app.log",
            [
                (
                    "2026-06-09 16:19:59 | INFO     | audio        | [audio] | "
                    "Audio: Transcription path decision | | "
                    '{"record_id":"old-rec","selected_path":"streaming_chunked",'
                    '"decision_reason":"streaming_stop_result"}'
                ),
                (
                    "2026-06-09 16:20:00 | INFO     | audio        | [audio] | "
                    "Audio: Transcription path decision | | "
                    '{"record_id":"rec-1","selected_path":"cloud_file_long_recording",'
                    '"decision_reason":"long_cloud_recording_prefer_file"}'
                ),
            ],
        )

        result = module.inspect_recent_transcription_path_logs(
            logs_dir,
            timestamp_from="2026-06-09T16:20:00",
            record_id="rec-1",
        )

        assert result["selected_record_count"] == 1
        assert result["entries"][0]["record_id"] == "rec-1"
        assert result["entries"][0]["selected_path"] == "cloud_file_long_recording"
    finally:
        for path in logs_dir.glob("*"):
            path.unlink()
        logs_dir.rmdir()


def test_inspect_recent_transcription_path_logs_reads_rotated_app_logs() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = (base_dir / f"logs_rotated_{uuid4().hex}").resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        _write_log(
            logs_dir / "app.log.1",
            [
                (
                    "2026-06-09 16:20:00 | INFO     | audio        | [audio] | "
                    "Audio: Transcription path decision | | "
                    '{"record_id":"rec-1","selected_path":"streaming_realtime",'
                    '"decision_reason":"streaming_stop_result"}'
                ),
            ],
        )
        _write_log(logs_dir / "app.log", [])

        result = module.inspect_recent_transcription_path_logs(logs_dir)

        assert result["log_file_count"] == 2
        assert result["selected_record_count"] == 1
        assert result["entries"][0]["selected_path"] == "streaming_realtime"
    finally:
        for path in logs_dir.glob("*"):
            path.unlink()
        logs_dir.rmdir()


def test_inspect_recent_transcription_path_logs_reports_missing_log_files() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    missing_dir = (base_dir / f"logs_missing_{uuid4().hex}").resolve()

    result = module.inspect_recent_transcription_path_logs(missing_dir)

    assert result["log_file_count"] == 0
    assert result["selected_record_count"] == 0
    assert result["diagnosis"]["state"] == "no_log_files"
