"""Summarize Stage 6 readiness snapshot JSONL history.

This helper turns repeated `--snapshot-out` records into a compact timeline view.

Usage:
    uv run python scripts/inspect_transcription_stage6_snapshot_timeline.py --snapshots quality_audit/stage6_readiness_real_20260610.jsonl
    uv run python scripts/inspect_transcription_stage6_snapshot_timeline.py --snapshots quality_audit/stage6_readiness_real_20260610.jsonl --brief
    uv run python scripts/inspect_transcription_stage6_snapshot_timeline.py --snapshots quality_audit/stage6_readiness_real_20260610.jsonl --compare
    uv run python scripts/inspect_transcription_stage6_snapshot_timeline.py --snapshots quality_audit/stage6_readiness_real_20260610.jsonl --table
    uv run python scripts/inspect_transcription_stage6_snapshot_timeline.py --snapshots quality_audit/stage6_readiness_real_20260610.jsonl --tsv
    uv run python scripts/inspect_transcription_stage6_snapshot_timeline.py --snapshots quality_audit/stage6_readiness_real_20260610.jsonl --summary
    uv run python scripts/inspect_transcription_stage6_snapshot_timeline.py --snapshots quality_audit/stage6_readiness_real_20260610.jsonl --card
    uv run python scripts/inspect_transcription_stage6_snapshot_timeline.py --snapshots quality_audit/stage6_readiness_real_20260610.jsonl --markdown
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_STATE_PROGRESS_RANKS = {
    "waiting_for_new_build_session": 0,
    "new_build_seen_db_not_migrated": 1,
    "schema_ready_waiting_for_post_cutoff_sample": 2,
    "partial_stage6_readiness": 3,
    "post_cutoff_path_mismatch": 4,
    "post_cutoff_reason_mismatch": 4,
    "stage6_ready_and_aligned": 5,
}
_STAGNATION_CONSECUTIVE_THRESHOLD = 3
_ALIGNED_DIAGNOSIS_STATE = "stage6_ready_and_aligned"
_NEW_BUILD_SEEN_STATES = {
    "new_build_seen_db_not_migrated",
    "schema_ready_waiting_for_post_cutoff_sample",
    "partial_stage6_readiness",
    "post_cutoff_path_mismatch",
    "post_cutoff_reason_mismatch",
    "stage6_ready_and_aligned",
}
_SCHEMA_READY_STATES = {
    "schema_ready_waiting_for_post_cutoff_sample",
    "partial_stage6_readiness",
    "post_cutoff_path_mismatch",
    "post_cutoff_reason_mismatch",
    "stage6_ready_and_aligned",
}


def _parse_observed_at_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_duration_seconds(value: int | float | None) -> str | None:
    if value is None:
        return None
    total_seconds = int(value)
    if total_seconds < 60:
        return f"{total_seconds}s"
    minutes, seconds = divmod(total_seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m {seconds}s"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h {minutes}m"


def _load_snapshots(snapshot_path: Path) -> list[dict[str, Any]]:
    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot file not found: {snapshot_path}")

    snapshots: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        snapshot_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        stripped = line.strip()
        if not stripped:
            continue
        loaded = json.loads(stripped)
        if not isinstance(loaded, dict):
            raise ValueError(
                f"Snapshot line {line_number} is not a JSON object: {snapshot_path}"
            )
        snapshots.append(loaded)
    return snapshots


def _assess_progress(
    previous_snapshot: dict[str, Any] | None,
    latest_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    if previous_snapshot is None or latest_snapshot is None:
        return {
            "verdict": "insufficient_history",
            "message": "At least two snapshots are needed before progress can be assessed.",
            "previous_state": None,
            "current_state": latest_snapshot.get("diagnosis_state")
            if latest_snapshot
            else None,
            "previous_rank": None,
            "current_rank": (
                _STATE_PROGRESS_RANKS.get(str(latest_snapshot.get("diagnosis_state") or ""))
                if latest_snapshot
                else None
            ),
        }

    previous_state = str(previous_snapshot.get("diagnosis_state") or "unknown")
    current_state = str(latest_snapshot.get("diagnosis_state") or "unknown")
    previous_rank = _STATE_PROGRESS_RANKS.get(previous_state)
    current_rank = _STATE_PROGRESS_RANKS.get(current_state)

    if previous_state == current_state:
        return {
            "verdict": "unchanged",
            "message": f"Diagnosis state stayed at {current_state}.",
            "previous_state": previous_state,
            "current_state": current_state,
            "previous_rank": previous_rank,
            "current_rank": current_rank,
        }
    if previous_rank is not None and current_rank is not None:
        if current_rank > previous_rank:
            return {
                "verdict": "advanced",
                "message": (
                    f"Diagnosis state advanced from {previous_state} to {current_state}."
                ),
                "previous_state": previous_state,
                "current_state": current_state,
                "previous_rank": previous_rank,
                "current_rank": current_rank,
            }
        if current_rank < previous_rank:
            return {
                "verdict": "regressed",
                "message": (
                    f"Diagnosis state regressed from {previous_state} to {current_state}."
                ),
                "previous_state": previous_state,
                "current_state": current_state,
                "previous_rank": previous_rank,
                "current_rank": current_rank,
            }
        return {
            "verdict": "lateral_change",
            "message": (
                f"Diagnosis state changed laterally from {previous_state} to {current_state} "
                "at the same progress tier."
            ),
            "previous_state": previous_state,
            "current_state": current_state,
            "previous_rank": previous_rank,
            "current_rank": current_rank,
        }

    return {
        "verdict": "changed_unranked",
        "message": (
            f"Diagnosis state changed from {previous_state} to {current_state}, "
            "but one or both states are outside the ranked progression model."
        ),
        "previous_state": previous_state,
        "current_state": current_state,
        "previous_rank": previous_rank,
        "current_rank": current_rank,
    }


def _count_latest_state_consecutive_snapshots(
    diagnosis_states: list[str],
) -> int:
    if not diagnosis_states:
        return 0
    latest_state = diagnosis_states[-1]
    count = 0
    for state in reversed(diagnosis_states):
        if state != latest_state:
            break
        count += 1
    return count


def _assess_stagnation(
    *,
    latest_state: str | None,
    consecutive_count: int,
    threshold: int = _STAGNATION_CONSECUTIVE_THRESHOLD,
) -> dict[str, Any]:
    if latest_state is None:
        return {
            "verdict": "no_data",
            "message": "No snapshots were available for stagnation assessment.",
            "current_state": None,
            "consecutive_count": 0,
            "threshold": threshold,
        }
    if consecutive_count >= threshold:
        return {
            "verdict": "stuck",
            "message": (
                f"Current state {latest_state} has repeated for "
                f"{consecutive_count} consecutive snapshots."
            ),
            "current_state": latest_state,
            "consecutive_count": consecutive_count,
            "threshold": threshold,
        }
    return {
        "verdict": "not_stuck",
        "message": (
            f"Current state {latest_state} has repeated for "
            f"{consecutive_count} consecutive snapshots."
        ),
        "current_state": latest_state,
        "consecutive_count": consecutive_count,
        "threshold": threshold,
    }


def _build_operator_guidance(
    latest_snapshot: dict[str, Any] | None,
    *,
    progress_assessment: dict[str, Any],
    stagnation_assessment: dict[str, Any],
) -> dict[str, Any]:
    if latest_snapshot is None:
        return {
            "urgency": "unknown",
            "summary": "No snapshot data is available yet.",
            "actions": [],
        }

    latest_state = str(latest_snapshot.get("diagnosis_state") or "unknown")
    record_hint = latest_snapshot.get("newest_record_id_hint")
    issue_summary = latest_snapshot.get("issue_summary")
    progress_verdict = str(progress_assessment.get("verdict") or "unknown")
    stagnation_verdict = str(stagnation_assessment.get("verdict") or "unknown")

    urgency = "normal"
    if progress_verdict == "regressed":
        urgency = "high"
    elif stagnation_verdict == "stuck":
        urgency = "attention"

    summary: str
    actions: list[str]
    if latest_state == "waiting_for_new_build_session":
        summary = (
            "Still waiting for a newer app build session that declares the current "
            "history schema expectations."
        )
        actions = [
            "Start a newer SonicInput build and confirm a fresh startup timestamp appears in logs.",
            "After startup, rerun Stage 6 readiness with --snapshot-out to capture whether expectation events now appear.",
        ]
    elif latest_state == "new_build_seen_db_not_migrated":
        summary = (
            "A newer build session is visible, but the inspected history DB still "
            "looks unmigrated."
        )
        actions = [
            "Confirm the app session and inspected history.db path refer to the same real file.",
            "Inspect HistoryStorageService startup/runtime logs for migration failures or alternate DB paths.",
        ]
    elif latest_state == "schema_ready_waiting_for_post_cutoff_sample":
        summary = (
            "Schema readiness looks good, but a new post-cutoff transcription sample "
            "is still missing."
        )
        actions = [
            "Generate one real transcription after the cutoff timestamp.",
            "Rerun readiness and append another snapshot to check whether end-to-end alignment becomes visible.",
        ]
    elif latest_state == "partial_stage6_readiness":
        summary = (
            "Some post-cutoff evidence exists, but DB/log correlation is still incomplete."
        )
        actions = [
            "Compare schema and observability outputs side by side.",
            (
                f"Use inspect_transcription_record_timeline.py for record_id {record_hint}."
                if record_hint
                else "Use the timeline inspector for the newest available record_id when possible."
            ),
        ]
    elif latest_state in {"post_cutoff_path_mismatch", "post_cutoff_reason_mismatch"}:
        summary = "A post-cutoff mismatch remains between persisted DB evidence and runtime logs."
        actions = [
            (
                f"Run inspect_transcription_record_timeline.py for record_id {record_hint}."
                if record_hint
                else "Run the record timeline inspector for the newest mismatched record."
            ),
            "Compare the persisted DB fields against the latest runtime decision/fallback event and rerun readiness after fixing the cause.",
        ]
    elif latest_state == "stage6_ready_and_aligned":
        summary = "Stage 6 is aligned for the latest sampled evidence."
        actions = [
            "Keep sampling a few more real records to increase confidence.",
            "Only drill into the timeline inspector again if a future snapshot regresses or becomes mismatched.",
        ]
    else:
        summary = "The latest snapshot needs manual inspection."
        actions = [
            "Review the latest readiness summary and snapshot timeline output together.",
        ]

    if issue_summary and latest_state not in {"stage6_ready_and_aligned"}:
        actions.append(f"Focus on this latest issue summary: {issue_summary}")

    if stagnation_verdict == "stuck":
        actions.insert(
            0,
            "This state has repeated enough times to be treated as stuck; prioritize the next corrective action before collecting more snapshots.",
        )
    elif progress_verdict == "advanced":
        actions.insert(
            0,
            "Progress improved relative to the previous snapshot; continue the next validation step before closing the loop.",
        )
    elif progress_verdict == "regressed":
        actions.insert(
            0,
            "The latest snapshot regressed relative to the previous one; investigate before assuming the environment is stable.",
        )

    return {
        "urgency": urgency,
        "summary": summary,
        "actions": actions,
    }


def _first_seen_matching_state(
    snapshots: list[dict[str, Any]],
    *,
    matching_states: set[str],
) -> str | None:
    for snapshot in snapshots:
        state = str(snapshot.get("diagnosis_state") or "unknown")
        if state in matching_states:
            observed_at = str(snapshot.get("observed_at_utc") or "")
            if observed_at:
                return observed_at
    return None


def _build_recent_snapshot_digest(
    snapshots: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    if limit <= 0 or not snapshots:
        return []

    digest: list[dict[str, Any]] = []
    start_index = max(0, len(snapshots) - limit)
    for index in range(start_index, len(snapshots)):
        snapshot = dict(snapshots[index] or {})
        previous_snapshot = dict(snapshots[index - 1] or {}) if index > 0 else None
        current_state = str(snapshot.get("diagnosis_state") or "unknown")
        previous_state = (
            str(previous_snapshot.get("diagnosis_state") or "unknown")
            if previous_snapshot is not None
            else None
        )
        if previous_state is None:
            delta_kind = "initial"
            transition_summary = None
            elapsed_since_previous_seconds = None
        elif previous_state == current_state:
            delta_kind = "unchanged"
            transition_summary = None
            previous_dt = _parse_observed_at_utc(previous_snapshot.get("observed_at_utc"))
            current_dt = _parse_observed_at_utc(snapshot.get("observed_at_utc"))
            elapsed_since_previous_seconds = (
                int((current_dt - previous_dt).total_seconds())
                if previous_dt is not None and current_dt is not None
                else None
            )
        else:
            delta_kind = "changed"
            transition_summary = f"{previous_state} -> {current_state}"
            previous_dt = _parse_observed_at_utc(previous_snapshot.get("observed_at_utc"))
            current_dt = _parse_observed_at_utc(snapshot.get("observed_at_utc"))
            elapsed_since_previous_seconds = (
                int((current_dt - previous_dt).total_seconds())
                if previous_dt is not None and current_dt is not None
                else None
            )

        digest.append(
            {
                "observed_at_utc": snapshot.get("observed_at_utc"),
                "diagnosis_state": snapshot.get("diagnosis_state"),
                "alignment_state": snapshot.get("alignment_state"),
                "previous_diagnosis_state": previous_state,
                "delta_kind": delta_kind,
                "transition_summary": transition_summary,
                "elapsed_since_previous_seconds": elapsed_since_previous_seconds,
                "elapsed_since_previous_human": _format_duration_seconds(
                    elapsed_since_previous_seconds
                ),
                "issue_summary": snapshot.get("issue_summary"),
            }
        )

    return list(reversed(digest))


def _build_state_dwell_summary(
    snapshots: list[dict[str, Any]],
    diagnosis_states: list[str],
    *,
    latest_diagnosis_state: str | None,
    latest_state_first_seen_at_utc: str | None,
) -> dict[str, Any]:
    seconds_by_state: dict[str, int] = {}
    for index in range(len(snapshots) - 1):
        current_dt = _parse_observed_at_utc(str(snapshots[index].get("observed_at_utc") or ""))
        next_dt = _parse_observed_at_utc(str(snapshots[index + 1].get("observed_at_utc") or ""))
        if current_dt is None or next_dt is None:
            continue
        delta_seconds = int((next_dt - current_dt).total_seconds())
        if delta_seconds < 0:
            continue
        state = diagnosis_states[index]
        seconds_by_state[state] = seconds_by_state.get(state, 0) + delta_seconds

    human_by_state = {
        state: _format_duration_seconds(seconds)
        for state, seconds in seconds_by_state.items()
    }

    latest_state_elapsed_seconds_since_first_seen = None
    latest_state_elapsed_human_since_first_seen = None
    if latest_diagnosis_state is not None and latest_state_first_seen_at_utc is not None and snapshots:
        latest_dt = _parse_observed_at_utc(str(snapshots[-1].get("observed_at_utc") or ""))
        first_seen_dt = _parse_observed_at_utc(latest_state_first_seen_at_utc)
        if latest_dt is not None and first_seen_dt is not None:
            latest_state_elapsed_seconds_since_first_seen = int(
                (latest_dt - first_seen_dt).total_seconds()
            )
            if latest_state_elapsed_seconds_since_first_seen >= 0:
                latest_state_elapsed_human_since_first_seen = _format_duration_seconds(
                    latest_state_elapsed_seconds_since_first_seen
                )
            else:
                latest_state_elapsed_seconds_since_first_seen = None

    return {
        "seconds_by_state": seconds_by_state,
        "human_by_state": human_by_state,
        "latest_state_elapsed_seconds_since_first_seen": latest_state_elapsed_seconds_since_first_seen,
        "latest_state_elapsed_human_since_first_seen": latest_state_elapsed_human_since_first_seen,
    }


def inspect_stage6_snapshot_timeline(
    snapshot_path: Path,
    *,
    recent_limit: int = 5,
) -> dict[str, Any]:
    snapshots = _load_snapshots(snapshot_path)

    diagnosis_states = [
        str(snapshot.get("diagnosis_state") or "unknown") for snapshot in snapshots
    ]
    alignment_states = [
        str(snapshot.get("alignment_state") or "unknown") for snapshot in snapshots
    ]

    unique_diagnosis_states_in_order: list[str] = []
    for state in diagnosis_states:
        if not unique_diagnosis_states_in_order or unique_diagnosis_states_in_order[-1] != state:
            unique_diagnosis_states_in_order.append(state)

    first_seen_by_diagnosis_state: dict[str, str] = {}
    last_seen_by_diagnosis_state: dict[str, str] = {}
    diagnosis_state_counts: dict[str, int] = {}
    for snapshot, state in zip(snapshots, diagnosis_states, strict=False):
        observed_at = str(snapshot.get("observed_at_utc") or "")
        if state not in first_seen_by_diagnosis_state and observed_at:
            first_seen_by_diagnosis_state[state] = observed_at
        if observed_at:
            last_seen_by_diagnosis_state[state] = observed_at
        diagnosis_state_counts[state] = diagnosis_state_counts.get(state, 0) + 1
    aligned_snapshot_count = diagnosis_state_counts.get(_ALIGNED_DIAGNOSIS_STATE, 0)
    aligned_checkpoint = {
        "ever_reached_aligned": aligned_snapshot_count > 0,
        "first_reached_aligned_at_utc": first_seen_by_diagnosis_state.get(
            _ALIGNED_DIAGNOSIS_STATE
        ),
        "latest_reached_aligned_at_utc": last_seen_by_diagnosis_state.get(
            _ALIGNED_DIAGNOSIS_STATE
        ),
        "aligned_snapshot_count": aligned_snapshot_count,
    }
    milestone_overview = {
        "ever_seen_new_build": any(
            state in _NEW_BUILD_SEEN_STATES for state in diagnosis_states
        ),
        "first_new_build_seen_at_utc": _first_seen_matching_state(
            snapshots,
            matching_states=_NEW_BUILD_SEEN_STATES,
        ),
        "ever_reached_schema_ready": any(
            state in _SCHEMA_READY_STATES for state in diagnosis_states
        ),
        "first_schema_ready_at_utc": _first_seen_matching_state(
            snapshots,
            matching_states=_SCHEMA_READY_STATES,
        ),
        "ever_reached_aligned": aligned_checkpoint["ever_reached_aligned"],
        "first_aligned_at_utc": aligned_checkpoint["first_reached_aligned_at_utc"],
        "latest_aligned_at_utc": aligned_checkpoint["latest_reached_aligned_at_utc"],
    }

    state_transitions: list[dict[str, Any]] = []
    for index in range(1, len(snapshots)):
        previous_state = diagnosis_states[index - 1]
        current_state = diagnosis_states[index]
        if previous_state == current_state:
            continue
        state_transitions.append(
            {
                "from_state": previous_state,
                "to_state": current_state,
                "from_observed_at_utc": snapshots[index - 1].get("observed_at_utc"),
                "to_observed_at_utc": snapshots[index].get("observed_at_utc"),
            }
        )

    latest_snapshot = snapshots[-1] if snapshots else None
    latest_oneline = (
        str(latest_snapshot.get("oneline"))
        if latest_snapshot and latest_snapshot.get("oneline")
        else None
    )
    latest_diagnosis_state = (
        latest_snapshot.get("diagnosis_state") if latest_snapshot else None
    )
    previous_snapshot = snapshots[-2] if len(snapshots) >= 2 else None
    progress_assessment = _assess_progress(previous_snapshot, latest_snapshot)
    latest_transition = state_transitions[-1] if state_transitions else None
    latest_transition_summary = None
    if latest_transition is not None:
        latest_transition_summary = (
            f"{latest_transition.get('from_state')} -> {latest_transition.get('to_state')} "
            f"at {latest_transition.get('to_observed_at_utc') or 'unknown'}"
        )
    latest_state_first_seen_at_utc = (
        first_seen_by_diagnosis_state.get(str(latest_diagnosis_state))
        if latest_diagnosis_state is not None
        else None
    )
    latest_state_snapshot_count = (
        diagnosis_state_counts.get(str(latest_diagnosis_state), 0)
        if latest_diagnosis_state is not None
        else 0
    )
    current_state_consecutive_count = _count_latest_state_consecutive_snapshots(
        diagnosis_states
    )
    stagnation_assessment = _assess_stagnation(
        latest_state=(
            str(latest_diagnosis_state) if latest_diagnosis_state is not None else None
        ),
        consecutive_count=current_state_consecutive_count,
    )
    operator_guidance = _build_operator_guidance(
        latest_snapshot,
        progress_assessment=progress_assessment,
        stagnation_assessment=stagnation_assessment,
    )
    recent_snapshot_digest = _build_recent_snapshot_digest(
        snapshots,
        limit=recent_limit,
    )
    state_dwell_summary = _build_state_dwell_summary(
        snapshots,
        diagnosis_states,
        latest_diagnosis_state=(
            str(latest_diagnosis_state) if latest_diagnosis_state is not None else None
        ),
        latest_state_first_seen_at_utc=latest_state_first_seen_at_utc,
    )

    return {
        "snapshot_path": str(snapshot_path),
        "snapshot_count": len(snapshots),
        "recent_snapshot_limit": recent_limit,
        "recent_snapshot_digest": recent_snapshot_digest,
        "state_dwell_summary": state_dwell_summary,
        "diagnosis_states": diagnosis_states,
        "alignment_states": alignment_states,
        "unique_diagnosis_states_in_order": unique_diagnosis_states_in_order,
        "diagnosis_state_counts": diagnosis_state_counts,
        "first_seen_by_diagnosis_state": first_seen_by_diagnosis_state,
        "last_seen_by_diagnosis_state": last_seen_by_diagnosis_state,
        "aligned_checkpoint": aligned_checkpoint,
        "milestone_overview": milestone_overview,
        "state_transition_count": len(state_transitions),
        "state_transitions": state_transitions,
        "latest_transition": latest_transition,
        "latest_transition_summary": latest_transition_summary,
        "first_observed_at_utc": snapshots[0].get("observed_at_utc") if snapshots else None,
        "latest_observed_at_utc": latest_snapshot.get("observed_at_utc") if latest_snapshot else None,
        "latest_diagnosis_state": latest_diagnosis_state,
        "latest_alignment_state": latest_snapshot.get("alignment_state")
        if latest_snapshot
        else None,
        "latest_issue_summary": latest_snapshot.get("issue_summary") if latest_snapshot else None,
        "latest_state_first_seen_at_utc": latest_state_first_seen_at_utc,
        "latest_state_snapshot_count": latest_state_snapshot_count,
        "current_state_consecutive_count": current_state_consecutive_count,
        "latest_oneline": latest_oneline,
        "progress_assessment": progress_assessment,
        "stagnation_assessment": stagnation_assessment,
        "operator_guidance": operator_guidance,
        "snapshots": snapshots,
    }


def format_stage6_snapshot_timeline_summary(result: dict[str, Any]) -> str:
    lines = [
        "Stage 6 Snapshot Timeline Summary",
        f"- Snapshot count: {result.get('snapshot_count', 0)}",
        f"- First observed at UTC: {result.get('first_observed_at_utc') or 'none'}",
        f"- Latest observed at UTC: {result.get('latest_observed_at_utc') or 'none'}",
        f"- Latest diagnosis state: {result.get('latest_diagnosis_state') or 'none'}",
        f"- Latest alignment state: {result.get('latest_alignment_state') or 'none'}",
        (
            "- Diagnosis states seen: "
            f"{', '.join(result.get('unique_diagnosis_states_in_order') or []) or 'none'}"
        ),
        (
            "- Ever seen new build: "
            f"{'yes' if dict(result.get('milestone_overview') or {}).get('ever_seen_new_build') else 'no'}"
        ),
        (
            "- Ever reached schema ready: "
            f"{'yes' if dict(result.get('milestone_overview') or {}).get('ever_reached_schema_ready') else 'no'}"
        ),
        (
            "- Ever reached aligned: "
            f"{'yes' if dict(result.get('aligned_checkpoint') or {}).get('ever_reached_aligned') else 'no'}"
        ),
        f"- State transition count: {result.get('state_transition_count', 0)}",
    ]
    milestone_overview = dict(result.get("milestone_overview") or {})
    if milestone_overview.get("first_new_build_seen_at_utc"):
        lines.append(
            "- First seen new build at UTC: "
            f"{milestone_overview.get('first_new_build_seen_at_utc')}"
        )
    if milestone_overview.get("first_schema_ready_at_utc"):
        lines.append(
            "- First reached schema ready at UTC: "
            f"{milestone_overview.get('first_schema_ready_at_utc')}"
        )
    aligned_checkpoint = dict(result.get("aligned_checkpoint") or {})
    if aligned_checkpoint.get("ever_reached_aligned"):
        lines.append(
            "- First reached aligned at UTC: "
            f"{aligned_checkpoint.get('first_reached_aligned_at_utc') or 'unknown'}"
        )
        lines.append(
            "- Latest reached aligned at UTC: "
            f"{aligned_checkpoint.get('latest_reached_aligned_at_utc') or 'unknown'}"
        )
        lines.append(
            "- Aligned snapshot count: "
            f"{aligned_checkpoint.get('aligned_snapshot_count', 0)}"
        )
    latest_state_first_seen_at_utc = result.get("latest_state_first_seen_at_utc")
    if latest_state_first_seen_at_utc:
        lines.append(
            "- Current state first seen at UTC: "
            f"{latest_state_first_seen_at_utc}"
        )
        lines.append(
            "- Current state snapshot count: "
            f"{result.get('latest_state_snapshot_count', 0)}"
        )
        lines.append(
            "- Current state consecutive snapshots: "
            f"{result.get('current_state_consecutive_count', 0)}"
        )
    state_dwell_summary = dict(result.get("state_dwell_summary") or {})
    latest_state_elapsed_human = state_dwell_summary.get(
        "latest_state_elapsed_human_since_first_seen"
    )
    if latest_state_elapsed_human:
        lines.append(
            "- Current state elapsed since first seen: "
            f"{latest_state_elapsed_human}"
        )
    progress_assessment = dict(result.get("progress_assessment") or {})
    if progress_assessment:
        lines.extend(
            [
                f"- Progress verdict: {progress_assessment.get('verdict') or 'unknown'}",
                (
                    "- Progress message: "
                    f"{progress_assessment.get('message') or 'No message available.'}"
                ),
            ]
        )
    stagnation_assessment = dict(result.get("stagnation_assessment") or {})
    if stagnation_assessment:
        lines.extend(
            [
                (
                    "- Stagnation verdict: "
                    f"{stagnation_assessment.get('verdict') or 'unknown'}"
                ),
                (
                    "- Stagnation message: "
                    f"{stagnation_assessment.get('message') or 'No message available.'}"
                ),
            ]
        )
    operator_guidance = dict(result.get("operator_guidance") or {})
    if operator_guidance:
        lines.extend(
            [
                (
                    "- Operator urgency: "
                    f"{operator_guidance.get('urgency') or 'unknown'}"
                ),
                (
                    "- Operator guidance: "
                    f"{operator_guidance.get('summary') or 'No guidance available.'}"
                ),
            ]
        )

    latest_issue_summary = result.get("latest_issue_summary")
    if latest_issue_summary:
        lines.append(f"- Latest issue summary: {latest_issue_summary}")

    latest_transition_summary = result.get("latest_transition_summary")
    if latest_transition_summary:
        lines.append(f"- Latest transition: {latest_transition_summary}")

    latest_oneline = result.get("latest_oneline")
    if latest_oneline:
        lines.extend(["", "Latest Oneline:", latest_oneline])

    recent_snapshot_digest = list(result.get("recent_snapshot_digest") or [])
    if recent_snapshot_digest:
        lines.extend(["", "Recent Snapshot Deltas:"])
        for item in recent_snapshot_digest:
            transition = item.get("transition_summary")
            transition_part = transition or item.get("delta_kind") or "unknown"
            lines.append(
                "- "
                f"{item.get('observed_at_utc') or 'unknown'} | "
                f"state={item.get('diagnosis_state') or 'unknown'} | "
                f"delta={transition_part}"
            )
            if item.get("elapsed_since_previous_human"):
                lines.append(
                    f"  elapsed_since_previous={item.get('elapsed_since_previous_human')}"
                )
            if item.get("issue_summary"):
                lines.append(f"  issue={item.get('issue_summary')}")

    actions = list(operator_guidance.get("actions") or [])
    if actions:
        lines.extend(["", "Recommended Actions:"])
        for action in actions:
            lines.append(f"- {action}")

    transitions = list(result.get("state_transitions") or [])
    if transitions:
        lines.extend(["", "State Transitions:"])
        for transition in transitions:
            lines.append(
                "- "
                f"{transition.get('from_state')} -> {transition.get('to_state')} "
                f"at {transition.get('to_observed_at_utc') or 'unknown'}"
            )

    return "\n".join(lines)


def format_stage6_snapshot_timeline_card(result: dict[str, Any]) -> str:
    milestone_overview = dict(result.get("milestone_overview") or {})
    stagnation_assessment = dict(result.get("stagnation_assessment") or {})
    operator_guidance = dict(result.get("operator_guidance") or {})

    lines = [
        "## Stage 6 Status Card",
        (
            "- **Latest diagnosis:** "
            f"`{result.get('latest_diagnosis_state') or 'none'}`"
        ),
        (
            "- **Latest alignment:** "
            f"`{result.get('latest_alignment_state') or 'none'}`"
        ),
        f"- **Observed at UTC:** `{result.get('latest_observed_at_utc') or 'none'}`",
        (
            "- **Progress:** "
            f"`{dict(result.get('progress_assessment') or {}).get('verdict') or 'unknown'}`"
        ),
        (
            "- **Stagnation:** "
            f"`{stagnation_assessment.get('verdict') or 'unknown'}` "
            f"({result.get('current_state_consecutive_count', 0)} consecutive / "
            f"threshold {stagnation_assessment.get('threshold', _STAGNATION_CONSECUTIVE_THRESHOLD)})"
        ),
        (
            "- **Milestones:** "
            f"new build {'yes' if milestone_overview.get('ever_seen_new_build') else 'no'} · "
            f"schema ready {'yes' if milestone_overview.get('ever_reached_schema_ready') else 'no'} · "
            f"aligned {'yes' if milestone_overview.get('ever_reached_aligned') else 'no'}"
        ),
        (
            "- **Guidance:** "
            f"{operator_guidance.get('summary') or 'No guidance available.'}"
        ),
    ]
    latest_state_elapsed_human = dict(result.get("state_dwell_summary") or {}).get(
        "latest_state_elapsed_human_since_first_seen"
    )
    if latest_state_elapsed_human:
        lines.append(
            "- **Current state elapsed:** "
            f"`{latest_state_elapsed_human}`"
        )

    latest_issue_summary = result.get("latest_issue_summary")
    if latest_issue_summary:
        lines.append(f"- **Latest issue:** {latest_issue_summary}")

    latest_transition_summary = result.get("latest_transition_summary")
    if latest_transition_summary:
        lines.append(f"- **Latest transition:** {latest_transition_summary}")

    if milestone_overview.get("first_new_build_seen_at_utc"):
        lines.append(
            "- **First new build seen at UTC:** "
            f"`{milestone_overview.get('first_new_build_seen_at_utc')}`"
        )
    if milestone_overview.get("first_schema_ready_at_utc"):
        lines.append(
            "- **First schema ready at UTC:** "
            f"`{milestone_overview.get('first_schema_ready_at_utc')}`"
        )
    if milestone_overview.get("first_aligned_at_utc"):
        lines.append(
            "- **First aligned at UTC:** "
            f"`{milestone_overview.get('first_aligned_at_utc')}`"
        )

    actions = list(operator_guidance.get("actions") or [])
    if actions:
        lines.append("- **Next actions:**")
        for action in actions:
            lines.append(f"  - {action}")

    return "\n".join(lines)


def format_stage6_snapshot_timeline_brief(result: dict[str, Any]) -> str:
    progress_assessment = dict(result.get("progress_assessment") or {})
    stagnation_assessment = dict(result.get("stagnation_assessment") or {})
    recent_snapshot_digest = list(result.get("recent_snapshot_digest") or [])

    lines = [
        "Stage 6 Timeline Brief",
        f"- Latest diagnosis: {result.get('latest_diagnosis_state') or 'none'}",
        f"- Latest alignment: {result.get('latest_alignment_state') or 'none'}",
        f"- Latest observed at UTC: {result.get('latest_observed_at_utc') or 'none'}",
        f"- Previous diagnosis: {progress_assessment.get('previous_state') or 'none'}",
        f"- Progress: {progress_assessment.get('verdict') or 'unknown'}",
        (
            "- Progress detail: "
            f"{progress_assessment.get('message') or 'No progress detail available.'}"
        ),
        f"- Stagnation: {stagnation_assessment.get('verdict') or 'unknown'}",
    ]
    latest_state_elapsed_human = dict(result.get("state_dwell_summary") or {}).get(
        "latest_state_elapsed_human_since_first_seen"
    )
    if latest_state_elapsed_human:
        lines.append(f"- Current state elapsed: {latest_state_elapsed_human}")

    latest_transition_summary = result.get("latest_transition_summary")
    if latest_transition_summary:
        lines.append(f"- Latest transition: {latest_transition_summary}")

    latest_issue_summary = result.get("latest_issue_summary")
    if latest_issue_summary:
        lines.append(f"- Latest issue: {latest_issue_summary}")

    if recent_snapshot_digest:
        lines.append("- Recent deltas:")
        for item in recent_snapshot_digest[:3]:
            transition = item.get("transition_summary")
            transition_part = transition or item.get("delta_kind") or "unknown"
            lines.append(
                "  - "
                f"{item.get('observed_at_utc') or 'unknown'} | "
                f"{item.get('diagnosis_state') or 'unknown'} | "
                f"{transition_part}"
            )
            if item.get("elapsed_since_previous_human"):
                lines.append(
                    f"    elapsed_since_previous={item.get('elapsed_since_previous_human')}"
                )
        remaining_count = len(recent_snapshot_digest) - 3
        if remaining_count > 0:
            lines.append(
                f"  - (+{remaining_count} more recent deltas in summary output)"
            )

    actions = list(dict(result.get("operator_guidance") or {}).get("actions") or [])
    if actions:
        lines.append("- Next actions:")
        for action in actions[:3]:
            lines.append(f"  - {action}")

    return "\n".join(lines)


def format_stage6_snapshot_timeline_compare(result: dict[str, Any]) -> str:
    progress_assessment = dict(result.get("progress_assessment") or {})
    stagnation_assessment = dict(result.get("stagnation_assessment") or {})
    recent_snapshot_digest = list(result.get("recent_snapshot_digest") or [])
    latest_item = recent_snapshot_digest[0] if recent_snapshot_digest else None
    previous_item = recent_snapshot_digest[1] if len(recent_snapshot_digest) >= 2 else None

    lines = [
        "Stage 6 Timeline Compare",
        f"- Latest diagnosis: {result.get('latest_diagnosis_state') or 'none'}",
        f"- Previous diagnosis: {progress_assessment.get('previous_state') or 'none'}",
        f"- Delta verdict: {progress_assessment.get('verdict') or 'unknown'}",
        (
            "- Delta detail: "
            f"{progress_assessment.get('message') or 'No delta detail available.'}"
        ),
        f"- Stagnation: {stagnation_assessment.get('verdict') or 'unknown'}",
    ]
    latest_state_elapsed_human = dict(result.get("state_dwell_summary") or {}).get(
        "latest_state_elapsed_human_since_first_seen"
    )
    if latest_state_elapsed_human:
        lines.append(f"- Current state elapsed: {latest_state_elapsed_human}")

    if latest_item is not None:
        lines.extend(
            [
                "",
                "Latest Snapshot:",
                (
                    "- "
                    f"{latest_item.get('observed_at_utc') or 'unknown'} | "
                    f"state={latest_item.get('diagnosis_state') or 'unknown'} | "
                    f"alignment={latest_item.get('alignment_state') or 'unknown'}"
                ),
            ]
        )
        if latest_item.get("elapsed_since_previous_human"):
            lines.append(
                f"- Elapsed since previous snapshot: {latest_item.get('elapsed_since_previous_human')}"
            )
        if latest_item.get("issue_summary"):
            lines.append(f"- Issue: {latest_item.get('issue_summary')}")

    if previous_item is not None:
        lines.extend(
            [
                "",
                "Previous Snapshot:",
                (
                    "- "
                    f"{previous_item.get('observed_at_utc') or 'unknown'} | "
                    f"state={previous_item.get('diagnosis_state') or 'unknown'} | "
                    f"alignment={previous_item.get('alignment_state') or 'unknown'}"
                ),
            ]
        )
        if previous_item.get("issue_summary"):
            lines.append(f"- Issue: {previous_item.get('issue_summary')}")
    else:
        lines.extend(["", "Previous Snapshot:", "- none"])

    latest_transition_summary = result.get("latest_transition_summary")
    if latest_transition_summary:
        lines.append(f"- Latest transition: {latest_transition_summary}")

    actions = list(dict(result.get("operator_guidance") or {}).get("actions") or [])
    if actions:
        lines.extend(["", "Top actions:"])
        for action in actions[:3]:
            lines.append(f"- {action}")

    return "\n".join(lines)


def format_stage6_snapshot_timeline_markdown(result: dict[str, Any]) -> str:
    milestone_overview = dict(result.get("milestone_overview") or {})
    progress_assessment = dict(result.get("progress_assessment") or {})
    stagnation_assessment = dict(result.get("stagnation_assessment") or {})
    operator_guidance = dict(result.get("operator_guidance") or {})
    aligned_checkpoint = dict(result.get("aligned_checkpoint") or {})

    lines = [
        "# Stage 6 Snapshot Timeline Report",
        "",
        "## Current State",
        f"- **Latest diagnosis:** `{result.get('latest_diagnosis_state') or 'none'}`",
        f"- **Latest alignment:** `{result.get('latest_alignment_state') or 'none'}`",
        f"- **First observed at UTC:** `{result.get('first_observed_at_utc') or 'none'}`",
        f"- **Latest observed at UTC:** `{result.get('latest_observed_at_utc') or 'none'}`",
        f"- **Snapshot count:** {result.get('snapshot_count', 0)}",
        f"- **State transition count:** {result.get('state_transition_count', 0)}",
        "",
        "## Milestones",
        (
            f"- **Ever seen new build:** "
            f"{'yes' if milestone_overview.get('ever_seen_new_build') else 'no'}"
        ),
        (
            f"- **Ever reached schema ready:** "
            f"{'yes' if milestone_overview.get('ever_reached_schema_ready') else 'no'}"
        ),
        (
            f"- **Ever reached aligned:** "
            f"{'yes' if aligned_checkpoint.get('ever_reached_aligned') else 'no'}"
        ),
    ]

    if milestone_overview.get("first_new_build_seen_at_utc"):
        lines.append(
            "- **First new build seen at UTC:** "
            f"`{milestone_overview.get('first_new_build_seen_at_utc')}`"
        )
    if milestone_overview.get("first_schema_ready_at_utc"):
        lines.append(
            "- **First schema ready at UTC:** "
            f"`{milestone_overview.get('first_schema_ready_at_utc')}`"
        )
    if aligned_checkpoint.get("first_reached_aligned_at_utc"):
        lines.append(
            "- **First aligned at UTC:** "
            f"`{aligned_checkpoint.get('first_reached_aligned_at_utc')}`"
        )
    if aligned_checkpoint.get("latest_reached_aligned_at_utc"):
        lines.append(
            "- **Latest aligned at UTC:** "
            f"`{aligned_checkpoint.get('latest_reached_aligned_at_utc')}`"
        )

    lines.extend(
        [
            "",
            "## Progress Assessment",
            (
                f"- **Progress verdict:** "
                f"`{progress_assessment.get('verdict') or 'unknown'}`"
            ),
            (
                f"- **Progress detail:** "
                f"{progress_assessment.get('message') or 'No progress detail available.'}"
            ),
            (
                f"- **Stagnation verdict:** "
                f"`{stagnation_assessment.get('verdict') or 'unknown'}`"
            ),
            (
                f"- **Stagnation detail:** "
                f"{stagnation_assessment.get('message') or 'No stagnation detail available.'}"
            ),
            (
                f"- **Current state consecutive snapshots:** "
                f"{result.get('current_state_consecutive_count', 0)}"
            ),
        ]
    )
    latest_state_elapsed_human = dict(result.get("state_dwell_summary") or {}).get(
        "latest_state_elapsed_human_since_first_seen"
    )
    if latest_state_elapsed_human:
        lines.append(
            f"- **Current state elapsed since first seen:** `{latest_state_elapsed_human}`"
        )

    latest_transition_summary = result.get("latest_transition_summary")
    if latest_transition_summary:
        lines.append(f"- **Latest transition:** {latest_transition_summary}")

    latest_issue_summary = result.get("latest_issue_summary")
    if latest_issue_summary:
        lines.append(f"- **Latest issue:** {latest_issue_summary}")

    lines.extend(
        [
            "",
            "## Operator Guidance",
            (
                f"- **Urgency:** "
                f"`{operator_guidance.get('urgency') or 'unknown'}`"
            ),
            (
                f"- **Summary:** "
                f"{operator_guidance.get('summary') or 'No guidance available.'}"
            ),
        ]
    )

    actions = list(operator_guidance.get("actions") or [])
    if actions:
        lines.append("")
        lines.append("### Recommended Actions")
        for action in actions:
            lines.append(f"1. {action}")

    recent_snapshot_digest = list(result.get("recent_snapshot_digest") or [])
    if recent_snapshot_digest:
        lines.extend(["", "## Recent Snapshot Deltas"])
        for item in recent_snapshot_digest:
            transition = item.get("transition_summary")
            transition_part = transition or item.get("delta_kind") or "unknown"
            lines.append(
                "- "
                f"`{item.get('observed_at_utc') or 'unknown'}` "
                f"`{item.get('diagnosis_state') or 'unknown'}` "
                f"(delta: {transition_part})"
            )
            if item.get("elapsed_since_previous_human"):
                lines.append(
                    f"  - Elapsed since previous: {item.get('elapsed_since_previous_human')}"
                )
            if item.get("issue_summary"):
                lines.append(f"  - Issue: {item.get('issue_summary')}")

    transitions = list(result.get("state_transitions") or [])
    if transitions:
        lines.extend(["", "## State Transitions"])
        for transition in transitions:
            lines.append(
                "- "
                f"`{transition.get('from_state')}` -> `{transition.get('to_state')}` "
                f"at `{transition.get('to_observed_at_utc') or 'unknown'}`"
            )

    latest_oneline = result.get("latest_oneline")
    if latest_oneline:
        lines.extend(["", "## Latest Oneline", "```text", latest_oneline, "```"])

    return "\n".join(lines)


def _truncate_for_table(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    if width <= 3:
        return value[:width]
    return value[: width - 3] + "..."


def format_stage6_snapshot_timeline_table(result: dict[str, Any]) -> str:
    recent_snapshot_digest = list(result.get("recent_snapshot_digest") or [])
    if not recent_snapshot_digest:
        return "No recent snapshot rows are available."

    columns = [
        ("observed_at_utc", "observed_at_utc", 20),
        ("diagnosis_state", "diagnosis_state", 36),
        ("alignment_state", "alignment_state", 36),
        ("elapsed", "elapsed", 12),
        ("delta", "delta", 48),
    ]

    rows: list[dict[str, str]] = []
    for item in recent_snapshot_digest:
        transition = item.get("transition_summary")
        rows.append(
            {
                "observed_at_utc": str(item.get("observed_at_utc") or "unknown"),
                "diagnosis_state": str(item.get("diagnosis_state") or "unknown"),
                "alignment_state": str(item.get("alignment_state") or "unknown"),
                "elapsed": str(item.get("elapsed_since_previous_human") or ""),
                "delta": str(transition or item.get("delta_kind") or "unknown"),
            }
        )

    widths: dict[str, int] = {}
    for key, header, max_width in columns:
        widths[key] = len(header)
        for row in rows:
            widths[key] = min(
                max(widths[key], len(row[key])),
                max_width,
            )

    header_line = " | ".join(
        header.ljust(widths[key]) for key, header, _ in columns
    )
    separator_line = "-+-".join("-" * widths[key] for key, _, _ in columns)
    row_lines = []
    for row in rows:
        row_lines.append(
            " | ".join(
                _truncate_for_table(row[key], widths[key]).ljust(widths[key])
                for key, _, _ in columns
            )
        )

    return "\n".join(
        [
            "Stage 6 Timeline Recent Snapshot Table",
            header_line,
            separator_line,
            *row_lines,
        ]
    )


def format_stage6_snapshot_timeline_tsv(result: dict[str, Any]) -> str:
    recent_snapshot_digest = list(result.get("recent_snapshot_digest") or [])
    headers = [
        "observed_at_utc",
        "diagnosis_state",
        "alignment_state",
        "previous_diagnosis_state",
        "elapsed_since_previous",
        "delta",
        "issue_summary",
    ]
    rows = ["\t".join(headers)]
    for item in recent_snapshot_digest:
        delta = str(item.get("transition_summary") or item.get("delta_kind") or "unknown")
        row = [
            str(item.get("observed_at_utc") or ""),
            str(item.get("diagnosis_state") or ""),
            str(item.get("alignment_state") or ""),
            str(item.get("previous_diagnosis_state") or ""),
            str(item.get("elapsed_since_previous_human") or ""),
            delta,
            str(item.get("issue_summary") or ""),
        ]
        rows.append("\t".join(row))
    return "\n".join(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshots", type=Path, required=True)
    parser.add_argument("--recent-limit", type=int, default=5)
    parser.add_argument("--brief", action="store_true")
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--table", action="store_true")
    parser.add_argument("--tsv", action="store_true")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--card", action="store_true")
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()

    result = inspect_stage6_snapshot_timeline(
        args.snapshots,
        recent_limit=args.recent_limit,
    )
    if args.brief:
        print(format_stage6_snapshot_timeline_brief(result))
    elif args.compare:
        print(format_stage6_snapshot_timeline_compare(result))
    elif args.table:
        print(format_stage6_snapshot_timeline_table(result))
    elif args.tsv:
        print(format_stage6_snapshot_timeline_tsv(result))
    elif args.card:
        print(format_stage6_snapshot_timeline_card(result))
    elif args.markdown:
        print(format_stage6_snapshot_timeline_markdown(result))
    elif args.summary:
        print(format_stage6_snapshot_timeline_summary(result))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
