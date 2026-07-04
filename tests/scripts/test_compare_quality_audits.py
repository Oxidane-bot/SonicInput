import importlib.util
from pathlib import Path


def _load_compare_summaries():
    module_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "compare_quality_audits.py"
    )
    spec = importlib.util.spec_from_file_location("compare_quality_audits", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.compare_summaries


def test_compare_quality_audits_reports_count_anomaly_and_metric_deltas() -> None:
    compare_summaries = _load_compare_summaries()

    baseline = {
        "summary_path": "quality_audit/before.summary.json",
        "counts": {"records": 100, "fallback_used": 10},
        "anomalies": {"chunk_boundary_repeat": 12},
        "metrics": {"fallback_success_rate": 0.4, "transcription_rtf_p95": 0.2},
    }
    candidate = {
        "summary_path": "quality_audit/after.summary.json",
        "counts": {"records": 100, "fallback_used": 8},
        "anomalies": {"chunk_boundary_repeat": 6, "fallback_candidate": 2},
        "metrics": {"fallback_success_rate": 0.625, "transcription_rtf_p95": 0.18},
    }

    result = compare_summaries(baseline, candidate)

    assert result["baseline_summary_path"] == "quality_audit/before.summary.json"
    assert result["candidate_summary_path"] == "quality_audit/after.summary.json"

    assert result["counts"]["fallback_used"]["baseline"] == 10
    assert result["counts"]["fallback_used"]["candidate"] == 8
    assert result["counts"]["fallback_used"]["delta"] == -2.0
    assert result["counts"]["fallback_used"]["ratio_vs_baseline"] == 0.8

    assert result["anomalies"]["chunk_boundary_repeat"]["delta"] == -6.0
    assert result["anomalies"]["fallback_candidate"]["baseline"] == 0
    assert result["anomalies"]["fallback_candidate"]["candidate"] == 2
    assert result["anomalies"]["fallback_candidate"]["ratio_vs_baseline"] is None

    assert result["metrics"]["fallback_success_rate"]["delta"] == 0.225
    assert result["metrics"]["transcription_rtf_p95"]["delta"] == -0.02


def test_compare_quality_audits_keeps_missing_metrics_distinct_from_zero() -> None:
    compare_summaries = _load_compare_summaries()

    baseline = {
        "summary_path": "quality_audit/before.summary.json",
        "counts": {"records": 100},
        "anomalies": {},
        "metrics": {"fallback_success_rate": 0.4},
    }
    candidate = {
        "summary_path": "quality_audit/after.summary.json",
        "counts": {"records": 100},
        "anomalies": {},
        "metrics": {
            "fallback_success_rate": 0.5,
            "transcription_path_observable_rate": 0.75,
        },
    }

    result = compare_summaries(baseline, candidate)

    assert result["counts"]["records"]["baseline"] == 100
    assert result["counts"]["records"]["candidate"] == 100
    assert result["metrics"]["fallback_success_rate"]["delta"] == 0.1
    assert result["metrics"]["transcription_path_observable_rate"]["baseline"] is None
    assert result["metrics"]["transcription_path_observable_rate"]["candidate"] == 0.75
    assert result["metrics"]["transcription_path_observable_rate"]["delta"] is None
    assert (
        result["metrics"]["transcription_path_observable_rate"]["ratio_vs_baseline"]
        is None
    )
