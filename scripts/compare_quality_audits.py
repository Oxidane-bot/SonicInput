"""Compare two privacy-safe quality audit summaries.

Usage:
    uv run python scripts/compare_quality_audits.py \
      --baseline quality_audit/before.summary.json \
      --candidate quality_audit/after.summary.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_summary(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid audit summary: {path}")
    return payload


def _delta(current: Any, baseline: Any) -> Any:
    if isinstance(current, (int, float)) and isinstance(baseline, (int, float)):
        return round(float(current) - float(baseline), 4)
    return None


def _ratio(current: Any, baseline: Any) -> float | None:
    if not isinstance(current, (int, float)) or not isinstance(baseline, (int, float)):
        return None
    baseline_value = float(baseline)
    if baseline_value == 0:
        return None
    return round(float(current) / baseline_value, 4)


def _compare_numeric_maps(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    missing_as_zero: bool = True,
) -> dict[str, dict[str, Any]]:
    keys = sorted(set(baseline) | set(candidate))
    result: dict[str, dict[str, Any]] = {}
    for key in keys:
        before = baseline.get(key, 0) if missing_as_zero else baseline.get(key)
        after = candidate.get(key, 0) if missing_as_zero else candidate.get(key)
        result[key] = {
            "baseline": before,
            "candidate": after,
            "delta": _delta(after, before),
            "ratio_vs_baseline": _ratio(after, before),
        }
    return result


def compare_summaries(
    baseline_summary: dict[str, Any],
    candidate_summary: dict[str, Any],
) -> dict[str, Any]:
    baseline_counts = dict(baseline_summary.get("counts", {}) or {})
    candidate_counts = dict(candidate_summary.get("counts", {}) or {})
    baseline_anomalies = dict(baseline_summary.get("anomalies", {}) or {})
    candidate_anomalies = dict(candidate_summary.get("anomalies", {}) or {})
    baseline_metrics = dict(baseline_summary.get("metrics", {}) or {})
    candidate_metrics = dict(candidate_summary.get("metrics", {}) or {})

    return {
        "baseline_summary_path": baseline_summary.get("summary_path")
        or baseline_summary.get("output_path"),
        "candidate_summary_path": candidate_summary.get("summary_path")
        or candidate_summary.get("output_path"),
        "counts": _compare_numeric_maps(baseline_counts, candidate_counts),
        "anomalies": _compare_numeric_maps(baseline_anomalies, candidate_anomalies),
        "metrics": _compare_numeric_maps(
            baseline_metrics,
            candidate_metrics,
            missing_as_zero=False,
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    baseline_summary = _load_summary(args.baseline)
    candidate_summary = _load_summary(args.candidate)
    comparison = compare_summaries(baseline_summary, candidate_summary)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(comparison, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(json.dumps(comparison, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
