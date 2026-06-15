"""Combine Stage 6 readiness and snapshot timeline into one operator handoff view.

Usage:
    uv run python scripts/inspect_transcription_stage6_handoff.py --snapshots quality_audit/stage6_readiness_real_20260610.jsonl
    uv run python scripts/inspect_transcription_stage6_handoff.py --timestamp-from 2026-06-09T16:06:10 --snapshots quality_audit/stage6_readiness_real_20260610.jsonl --brief
    uv run python scripts/inspect_transcription_stage6_handoff.py --timestamp-from 2026-06-09T16:06:10 --snapshots quality_audit/stage6_readiness_real_20260610.jsonl --brief --recent-limit 5
    uv run python scripts/inspect_transcription_stage6_handoff.py --timestamp-from 2026-06-09T16:06:10 --snapshots quality_audit/stage6_readiness_real_20260610.jsonl --compare
    uv run python scripts/inspect_transcription_stage6_handoff.py --timestamp-from 2026-06-09T16:06:10 --snapshots quality_audit/stage6_readiness_real_20260610.jsonl --summary
    uv run python scripts/inspect_transcription_stage6_handoff.py --timestamp-from 2026-06-09T16:06:10 --snapshots quality_audit/stage6_readiness_real_20260610.jsonl --card
    uv run python scripts/inspect_transcription_stage6_handoff.py --timestamp-from 2026-06-09T16:06:10 --snapshots quality_audit/stage6_readiness_real_20260610.jsonl --markdown
    uv run python scripts/inspect_transcription_stage6_handoff.py --timestamp-from 2026-06-09T16:06:10 --snapshots quality_audit/stage6_readiness_real_20260610.jsonl --append-snapshot --card
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from inspect_transcription_stage6_readiness import (
    _format_stage6_command,
    _default_history_db,
    _default_logs_dir,
    append_stage6_readiness_snapshot,
    format_stage6_readiness_card,
    format_stage6_readiness_markdown,
    format_stage6_readiness_summary,
    inspect_transcription_stage6_readiness,
)
from inspect_transcription_stage6_snapshot_timeline import (
    format_stage6_snapshot_timeline_card,
    format_stage6_snapshot_timeline_summary,
    inspect_stage6_snapshot_timeline,
)

_OPERATOR_HANDOFF_ENVELOPE_VERSION = 1


def _action_key(action: str) -> str:
    normalized = " ".join(action.lower().split())
    if "start a newer sonicinput build" in normalized or "start a newer app build" in normalized:
        return "start_new_build"
    if (
        "rerun" in normalized
        and "readiness" in normalized
        and ("expectation event" in normalized or "--snapshot-out" in normalized)
    ):
        return "rerun_readiness_after_startup"
    if "fresh app session timestamp" in normalized or "fresh startup timestamp" in normalized:
        return "confirm_fresh_session_timestamp"
    return normalized


def _merge_actions(*action_groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in action_groups:
        for action in group:
            key = _action_key(action)
            if key not in seen:
                merged.append(action)
                seen.add(key)
    return merged


def _action_group_key(action: str) -> str:
    normalized = " ".join(str(action or "").lower().split())
    if normalized.startswith("this state has repeated enough times"):
        return "stuck_prioritize"
    if normalized.startswith("progress improved relative to the previous snapshot"):
        return "progress_advanced"
    if normalized.startswith("the latest snapshot regressed relative to the previous one"):
        return "progress_regressed"
    if "start a newer sonicinput build" in normalized or "start a newer app build" in normalized:
        return "start_new_build"
    if "rerun the readiness inspector" in normalized or "rerun stage 6 readiness" in normalized:
        return "rerun_after_startup"
    if "fresh app session timestamp" in normalized or "fresh startup timestamp" in normalized:
        return "confirm_fresh_session"
    if "refer to the same real file" in normalized or "refer to the same real storage path" in normalized:
        return "confirm_storage_path"
    if "migration failures" in normalized or "alternate db paths" in normalized:
        return "inspect_migration_logs"
    if "generate one real transcription after the cutoff timestamp" in normalized:
        return "generate_post_cutoff_sample"
    if "append another snapshot" in normalized:
        return "append_snapshot_check"
    if "compare schema and observability outputs side by side" in normalized:
        return "compare_schema_observability"
    if (
        "inspect_transcription_record_timeline.py" in normalized
        or "timeline inspector" in normalized
    ):
        return "record_timeline_drilldown"
    if "compare the persisted db fields against the latest runtime" in normalized:
        return "compare_db_runtime_mismatch"
    if "keep sampling a few more real records" in normalized or "keep sampling newer real records" in normalized:
        return "keep_sampling"
    if "only drill into the timeline inspector again" in normalized:
        return "drilldown_on_regress"
    if normalized.startswith("focus on this latest issue summary:"):
        return "focus_issue_summary"
    if "review the latest readiness summary and snapshot timeline output together" in normalized:
        return "review_outputs"
    return "other"


def _priority_order_for_action_state(readiness_state: str) -> list[str]:
    if readiness_state in {"waiting_for_new_build_session", "new_build_seen_db_not_migrated"}:
        return [
            "stuck_prioritize",
            "progress_regressed",
            "progress_advanced",
            "start_new_build",
            "confirm_storage_path",
            "inspect_migration_logs",
            "rerun_after_startup",
            "confirm_fresh_session",
            "focus_issue_summary",
            "review_outputs",
            "other",
        ]
    if readiness_state in {
        "schema_ready_waiting_for_post_cutoff_sample",
        "partial_stage6_readiness",
        "post_cutoff_reason_mismatch",
        "post_cutoff_path_mismatch",
    }:
        return [
            "stuck_prioritize",
            "progress_regressed",
            "progress_advanced",
            "compare_schema_observability",
            "record_timeline_drilldown",
            "compare_db_runtime_mismatch",
            "generate_post_cutoff_sample",
            "append_snapshot_check",
            "focus_issue_summary",
            "review_outputs",
            "other",
        ]
    if readiness_state == "stage6_ready_and_aligned":
        return [
            "progress_regressed",
            "progress_advanced",
            "keep_sampling",
            "drilldown_on_regress",
            "focus_issue_summary",
            "review_outputs",
            "other",
        ]
    return [
        "stuck_prioritize",
        "progress_regressed",
        "progress_advanced",
        "review_outputs",
        "focus_issue_summary",
        "other",
    ]


def _prioritize_actions(readiness_state: str, actions: list[str]) -> list[str]:
    ordered_categories = _priority_order_for_action_state(readiness_state)
    grouped: dict[str, list[str]] = {key: [] for key in ordered_categories}
    grouped["other"] = grouped.get("other", [])
    for action in actions:
        category = _action_group_key(action)
        grouped.setdefault(category, []).append(action)

    ordered: list[str] = []
    for category in ordered_categories:
        ordered.extend(grouped.get(category, []))
    for category, items in grouped.items():
        if category not in ordered_categories:
            ordered.extend(items)
    return ordered


def _merge_commands(*command_groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in command_groups:
        for command in group:
            normalized = " ".join(str(command or "").split())
            if not normalized or normalized in seen:
                continue
            merged.append(command)
            seen.add(normalized)
    return merged


def _limit_with_remaining(items: list[str], shown: int) -> tuple[list[str], int]:
    if shown < 0:
        shown = 0
    visible = list(items[:shown])
    remaining = max(0, len(items) - len(visible))
    return visible, remaining


def _command_group_key(command: str) -> str:
    normalized = str(command or "").replace("\\", "/").lower()
    if (
        "inspect_transcription_stage6_handoff.py" in normalized
        and "--append-snapshot" in normalized
    ):
        return "append_snapshot"
    if "inspect_transcription_stage6_snapshot_timeline.py" in normalized:
        return "snapshot_timeline"
    if "inspect_transcription_record_timeline.py" in normalized:
        return "record_timeline"
    if "inspect_transcription_path_observability.py" in normalized:
        return "path_observability"
    if "inspect_recent_transcription_path_logs.py" in normalized:
        return "recent_runtime_logs"
    if "inspect_recent_transcription_paths.py" in normalized:
        return "recent_db_rows"
    if "inspect_history_schema.py" in normalized:
        return "schema_startup"
    return "other"


def _priority_order_for_state(readiness_state: str) -> list[str]:
    if readiness_state in {"waiting_for_new_build_session", "new_build_seen_db_not_migrated"}:
        return [
            "schema_startup",
            "path_observability",
            "recent_runtime_logs",
            "recent_db_rows",
            "record_timeline",
            "other",
        ]
    if readiness_state in {
        "schema_ready_waiting_for_post_cutoff_sample",
        "partial_stage6_readiness",
        "post_cutoff_reason_mismatch",
        "post_cutoff_path_mismatch",
    }:
        return [
            "path_observability",
            "record_timeline",
            "recent_runtime_logs",
            "recent_db_rows",
            "schema_startup",
            "other",
        ]
    if readiness_state == "stage6_ready_and_aligned":
        return [
            "record_timeline",
            "path_observability",
            "recent_runtime_logs",
            "recent_db_rows",
            "schema_startup",
            "other",
        ]
    return [
        "path_observability",
        "schema_startup",
        "recent_runtime_logs",
        "recent_db_rows",
        "record_timeline",
        "other",
    ]


def _split_corrective_commands(
    readiness_state: str,
    commands: list[str],
) -> tuple[list[str], list[str]]:
    ordered_groups = _priority_order_for_state(readiness_state)
    grouped: dict[str, list[str]] = {key: [] for key in ordered_groups}
    grouped["other"] = grouped.get("other", [])
    for command in commands:
        key = _command_group_key(command)
        grouped.setdefault(key, []).append(command)

    ordered_commands: list[str] = []
    for key in ordered_groups:
        ordered_commands.extend(grouped.get(key, []))

    primary_keys = set(ordered_groups[:2])
    primary = [command for command in ordered_commands if _command_group_key(command) in primary_keys]
    supporting = [
        command
        for command in ordered_commands
        if _command_group_key(command) not in primary_keys
    ]
    return primary, supporting


def _command_category_label(category: str) -> str:
    return {
        "schema_startup": "Schema/startup evidence",
        "path_observability": "Path observability",
        "recent_runtime_logs": "Recent runtime logs",
        "recent_db_rows": "Recent DB rows",
        "record_timeline": "Single-record timeline",
        "append_snapshot": "Append fresh snapshot",
        "snapshot_timeline": "Snapshot timeline summary",
        "other": "Follow-up",
    }.get(category, "Follow-up")


def _command_reason(readiness_state: str, category: str) -> str:
    if category == "append_snapshot":
        return "Use after corrective checks to append a fresh readiness snapshot and see whether the state changes."
    if category == "snapshot_timeline":
        return "Use after appending or refreshing snapshots to confirm whether the timeline is advancing or still stuck."

    if readiness_state in {"waiting_for_new_build_session", "new_build_seen_db_not_migrated"}:
        return {
            "schema_startup": (
                "Current state still lacks enough runtime declaration evidence for the latest schema expectation, so confirm startup/schema signals first."
            ),
            "path_observability": (
                "After startup/schema confirmation, compare post-cutoff runtime path evidence against DB visibility before collecting more snapshots."
            ),
            "recent_runtime_logs": (
                "Use after the primary checks to see whether fresh runtime events exist even while the DB still looks unchanged."
            ),
            "recent_db_rows": (
                "Use after the primary checks to confirm whether post-cutoff DB rows appeared without matching runtime/schema evidence."
            ),
            "record_timeline": (
                "Keep this as a lower-priority drill-down until a concrete post-cutoff record_id is available from the newer session."
            ),
            "other": "Use as supporting follow-up once startup/schema and path evidence have been checked.",
        }.get(category, "Use as supporting follow-up once startup/schema and path evidence have been checked.")

    if readiness_state in {
        "schema_ready_waiting_for_post_cutoff_sample",
        "partial_stage6_readiness",
        "post_cutoff_reason_mismatch",
        "post_cutoff_path_mismatch",
    }:
        return {
            "path_observability": (
                "This state is driven by post-cutoff path/reason alignment, so inspect runtime-vs-DB path evidence first."
            ),
            "record_timeline": (
                "Drill into the concrete record_id once path-level mismatch or partial readiness has been identified."
            ),
            "recent_runtime_logs": (
                "Use as supporting evidence to confirm whether runtime keeps emitting decisions for the suspect record or time window."
            ),
            "recent_db_rows": (
                "Use as supporting evidence to confirm whether DB persistence is lagging behind the runtime path evidence."
            ),
            "schema_startup": (
                "Keep this as a fallback check in case path mismatches suggest the running build/schema expectation is not the one you think it is."
            ),
            "other": "Use as supporting follow-up after the path mismatch evidence has been reviewed.",
        }.get(category, "Use as supporting follow-up after the path mismatch evidence has been reviewed.")

    if readiness_state == "stage6_ready_and_aligned":
        return {
            "record_timeline": (
                "Use first when aligned evidence exists and you want a single-record drill-down for an operator spot check."
            ),
            "path_observability": (
                "Use next to spot-check whether newly sampled runtime path evidence still stays aligned with the DB."
            ),
            "recent_runtime_logs": (
                "Keep as supporting context when a later sample looks suspicious and you need raw runtime evidence."
            ),
            "recent_db_rows": (
                "Keep as supporting context to confirm later samples still persist the expected Stage 6 fields."
            ),
            "schema_startup": (
                "Keep as a fallback only if later samples suggest the running build/schema expectation may have drifted."
            ),
            "other": "Use as supporting follow-up while alignment is being spot-checked.",
        }.get(category, "Use as supporting follow-up while alignment is being spot-checked.")

    return {
        "path_observability": "Inspect runtime-vs-DB path evidence first for the current readiness state.",
        "schema_startup": "Confirm startup/schema evidence for the current readiness state.",
        "recent_runtime_logs": "Review recent runtime evidence for the current readiness state.",
        "recent_db_rows": "Review recent DB rows for the current readiness state.",
        "record_timeline": "Use single-record drill-down for the current readiness state.",
        "other": "Use as follow-up for the current readiness state.",
    }.get(category, "Use as follow-up for the current readiness state.")


def _build_command_details(
    readiness_state: str,
    commands: list[str],
) -> list[dict[str, str]]:
    details: list[dict[str, str]] = []
    for command in commands:
        category = _command_group_key(command)
        details.append(
            {
                "command": command,
                "category": category,
                "label": _command_category_label(category),
                "reason": _command_reason(readiness_state, category),
            }
        )
    return details


def _command_details_by_command(
    details: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for detail in details:
        command = str(detail.get("command") or "")
        if command:
            mapped[command] = detail
    return mapped


def _action_label(category: str) -> str:
    return {
        "stuck_prioritize": "Prioritize corrective step",
        "progress_advanced": "Progress advanced",
        "progress_regressed": "Investigate regression",
        "start_new_build": "Start new build",
        "rerun_after_startup": "Rerun after startup",
        "confirm_fresh_session": "Confirm fresh session",
        "confirm_storage_path": "Confirm storage path",
        "inspect_migration_logs": "Inspect migration/runtime logs",
        "generate_post_cutoff_sample": "Generate post-cutoff sample",
        "append_snapshot_check": "Append snapshot after sample",
        "compare_schema_observability": "Compare schema vs observability",
        "record_timeline_drilldown": "Drill into record timeline",
        "compare_db_runtime_mismatch": "Compare DB vs runtime fields",
        "keep_sampling": "Keep sampling",
        "drilldown_on_regress": "Drill down only on regressions",
        "focus_issue_summary": "Focus the latest issue",
        "review_outputs": "Review outputs together",
        "other": "Follow-up action",
    }.get(category, "Follow-up action")


def _action_reason(readiness_state: str, category: str) -> str:
    if category == "stuck_prioritize":
        return "The same readiness state has repeated across enough snapshots that corrective work now matters more than collecting another snapshot immediately."
    if category == "progress_advanced":
        return "The latest snapshot moved in the right direction, so the operator should keep momentum and validate the next state transition before pausing."
    if category == "progress_regressed":
        return "The latest snapshot got worse than the previous one, so treat the environment as unstable until the regression is explained."

    if readiness_state in {"waiting_for_new_build_session", "new_build_seen_db_not_migrated"}:
        return {
            "start_new_build": "Stage 6 cannot progress until a newer app session declares the expected schema evidence in runtime logs.",
            "rerun_after_startup": "A fresh readiness rerun is needed right after startup so the operator can confirm whether the expected schema declaration finally appears.",
            "confirm_fresh_session": "Old logs can make this state look newer than it is, so verifying a fresh session timestamp prevents chasing stale evidence.",
            "confirm_storage_path": "When the build and DB do not appear to move together, first confirm the app and inspected DB path are really the same storage target.",
            "inspect_migration_logs": "If a newer build exists but persistence still looks old, startup/runtime logs are the fastest place to catch migration or alternate-path issues.",
            "focus_issue_summary": "The latest issue summary usually names the missing schema/startup evidence that is blocking this state.",
            "review_outputs": "Reviewing readiness and timeline together helps confirm whether the blocker is still startup/schema related or has shifted elsewhere.",
        }.get(category, "This action supports unblocking the missing startup/schema evidence for the current readiness state.")

    if readiness_state in {
        "schema_ready_waiting_for_post_cutoff_sample",
        "partial_stage6_readiness",
        "post_cutoff_reason_mismatch",
        "post_cutoff_path_mismatch",
    }:
        return {
            "generate_post_cutoff_sample": "Schema readiness alone is not enough here; the operator still needs fresh post-cutoff evidence to prove end-to-end behavior.",
            "append_snapshot_check": "After a fresh sample or correction, append another snapshot so the timeline can show whether the state advanced or stayed stuck.",
            "compare_schema_observability": "This state depends on correlating DB persistence with runtime path evidence, so compare both views side by side before guessing.",
            "record_timeline_drilldown": "A single-record drill-down is the fastest way to explain a partial or mismatched post-cutoff state once a candidate record_id exists.",
            "compare_db_runtime_mismatch": "Mismatch states need field-by-field comparison between persisted DB values and runtime decision events before trusting a fix.",
            "confirm_storage_path": "When runtime evidence exists without matching DB rows, first confirm the app and inspected DB path still point to the same storage target.",
            "inspect_migration_logs": "If the DB still does not reflect post-cutoff runtime evidence, inspect startup/runtime logs for storage-path or migration clues.",
            "focus_issue_summary": "The latest issue summary usually points to the exact record, path, or missing correlation that needs attention first.",
            "review_outputs": "Reviewing readiness and timeline together clarifies whether the issue is incomplete evidence, a mismatch, or simple lack of sampling.",
        }.get(category, "This action helps correlate post-cutoff runtime and DB evidence for the current readiness state.")

    if readiness_state == "stage6_ready_and_aligned":
        return {
            "keep_sampling": "Alignment has been seen once, but repeated healthy samples are still needed before Stage 6 can be treated as robust.",
            "drilldown_on_regress": "Timeline drill-down should stay on standby until a later sample regresses or shows a mismatch again.",
            "append_snapshot_check": "Appending another snapshot after a fresh sample shows whether alignment keeps holding across consecutive observations.",
            "focus_issue_summary": "If an issue reappears after alignment, focus the operator on the newest concrete regression signal instead of reopening everything.",
        }.get(category, "This action helps confirm that aligned behavior remains stable across more real samples.")

    return {
        "review_outputs": "Review the latest operator evidence before choosing the next corrective step.",
        "focus_issue_summary": "Use the latest issue summary to narrow the next debugging step.",
    }.get(category, "This action supports the current follow-up state.")


def _action_when_to_run(
    readiness_state: str,
    category: str,
    *,
    timeline_progress: str | None,
    timeline_stagnation: str | None,
) -> str:
    if category == "stuck_prioritize":
        return "Now, before appending another snapshot."
    if category == "progress_regressed":
        return "Immediately after noticing the regression."
    if category == "progress_advanced":
        return "Immediately after the improved snapshot, before the environment changes again."
    if category in {"start_new_build", "generate_post_cutoff_sample"}:
        return "Now, as the next real environment action."
    if category in {"rerun_after_startup", "append_snapshot_check"}:
        return "Right after the startup/sample/corrective step completes."
    if category in {"confirm_fresh_session", "confirm_storage_path", "inspect_migration_logs"}:
        return "During the first corrective pass, before deeper record-level drill-down."
    if category in {"compare_schema_observability", "record_timeline_drilldown", "compare_db_runtime_mismatch"}:
        if timeline_stagnation == "stuck":
            return "During the corrective pass that should break the stuck state."
        return "After the latest sample is available and before declaring the state resolved."
    if category in {"keep_sampling", "drilldown_on_regress"}:
        return "After alignment has been observed at least once."
    if category in {"focus_issue_summary", "review_outputs"}:
        if timeline_progress == "regressed":
            return "Use immediately while triaging the regression."
        if timeline_stagnation == "stuck":
            return "Use now while deciding the next corrective step."
        return "Use during the current review pass."
    if readiness_state == "stage6_ready_and_aligned":
        return "After the current aligned snapshot, as part of ongoing spot checks."
    return "During the current follow-up pass."


def _related_commands_for_action(
    category: str,
    *,
    primary_corrective_commands: list[str],
    supporting_corrective_commands: list[str],
    monitoring_commands: list[str],
) -> list[str]:
    all_corrective = list(primary_corrective_commands) + list(supporting_corrective_commands)

    if category == "stuck_prioritize":
        return list(primary_corrective_commands[:2])
    if category in {"progress_advanced", "append_snapshot_check", "keep_sampling"}:
        return list(monitoring_commands[:2])
    if category == "progress_regressed":
        return list(primary_corrective_commands[:2] + monitoring_commands[:1])
    if category == "start_new_build":
        return list(monitoring_commands[:1] + primary_corrective_commands[:1])
    if category in {"rerun_after_startup", "drilldown_on_regress"}:
        return list(monitoring_commands[:2] + primary_corrective_commands[:1])
    if category in {"confirm_fresh_session", "inspect_migration_logs"}:
        desired = {"schema_startup", "recent_runtime_logs"}
    elif category == "confirm_storage_path":
        desired = {"schema_startup", "path_observability"}
    elif category == "compare_schema_observability":
        desired = {"schema_startup", "path_observability"}
    elif category == "record_timeline_drilldown":
        desired = {"record_timeline"}
    elif category == "compare_db_runtime_mismatch":
        desired = {"path_observability", "recent_runtime_logs", "recent_db_rows", "record_timeline"}
    elif category in {"focus_issue_summary", "review_outputs"}:
        return list(primary_corrective_commands[:2] + monitoring_commands[:1])
    else:
        return []

    related: list[str] = []
    for command in all_corrective + list(monitoring_commands):
        if _command_group_key(command) in desired and command not in related:
            related.append(command)
    return related[:3]


def _build_action_details(
    readiness_state: str,
    actions: list[str],
    *,
    timeline_progress: str | None,
    timeline_stagnation: str | None,
    primary_corrective_commands: list[str],
    supporting_corrective_commands: list[str],
    monitoring_commands: list[str],
) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for action in actions:
        category = _action_group_key(action)
        details.append(
            {
                "action": action,
                "category": category,
                "label": _action_label(category),
                "reason": _action_reason(readiness_state, category),
                "when_to_run": _action_when_to_run(
                    readiness_state,
                    category,
                    timeline_progress=timeline_progress,
                    timeline_stagnation=timeline_stagnation,
                ),
                "related_commands": _related_commands_for_action(
                    category,
                    primary_corrective_commands=primary_corrective_commands,
                    supporting_corrective_commands=supporting_corrective_commands,
                    monitoring_commands=monitoring_commands,
                ),
            }
        )
    return details


def _action_details_by_action(
    details: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for detail in details:
        action = str(detail.get("action") or "")
        if action:
            mapped[action] = detail
    return mapped


def _recent_delta_details_by_observed_at(
    details: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for detail in details:
        observed_at_utc = str(detail.get("observed_at_utc") or "")
        if observed_at_utc:
            mapped[observed_at_utc] = detail
    return mapped


def _related_command_hint(command: str) -> str:
    normalized = str(command or "").replace("\\", "/")
    if "inspect_transcription_stage6_handoff.py" in normalized and "--append-snapshot" in normalized:
        return "inspect_transcription_stage6_handoff.py --append-snapshot --brief"
    if "inspect_transcription_stage6_snapshot_timeline.py" in normalized:
        return "inspect_transcription_stage6_snapshot_timeline.py --summary"
    match = re.search(r"scripts/([^\s\"]+\.py)", normalized)
    if match:
        return Path(match.group(1)).name
    return normalized.strip()


def _related_command_summary(commands: list[str], *, limit: int = 2) -> str | None:
    if not commands:
        return None
    hints: list[str] = []
    for command in commands[:limit]:
        hint = _related_command_hint(command)
        if hint not in hints:
            hints.append(hint)
    remaining = len(commands) - len(commands[:limit])
    if remaining > 0:
        hints.append(f"+{remaining} more")
    return "; ".join(hints)


def _action_phase(category: str) -> str:
    if category in {"stuck_prioritize", "progress_regressed"}:
        return "prioritize"
    if category == "progress_advanced":
        return "validate_next_step"
    if category in {
        "keep_sampling",
        "append_snapshot_check",
        "drilldown_on_regress",
        "focus_issue_summary",
        "review_outputs",
    }:
        return "monitoring"
    return "corrective"


def _command_reference(
    command: str,
    *,
    phase: str,
) -> dict[str, Any]:
    category = _command_group_key(command)
    return {
        "id": category if category != "other" else None,
        "phase": phase,
        "command": command,
    }


def _build_action_envelope_entries(
    actions: list[str],
    action_details: list[dict[str, Any]],
    *,
    primary_corrective_commands: list[str],
    supporting_corrective_commands: list[str],
    monitoring_commands: list[str],
) -> list[dict[str, Any]]:
    detail_map = _action_details_by_action(action_details)
    action_entries: list[dict[str, Any]] = []
    for priority, action in enumerate(actions, start=1):
        detail = dict(detail_map.get(action) or {})
        category = str(detail.get("category") or _action_group_key(action))
        phase = _action_phase(category)
        related_commands = [
            _command_reference(command, phase=_command_phase(command, primary_corrective_commands, supporting_corrective_commands, monitoring_commands))
            for command in list(detail.get("related_commands") or [])
        ]
        action_entries.append(
            {
                "kind": "action",
                "id": category if category != "other" else f"action:{priority}",
                "label": detail.get("label") or _action_label(category),
                "operator_implication": detail.get("reason") or None,
                "escalation_trigger": None,
                "priority": priority,
                "phase": phase,
                "when_to_run": detail.get("when_to_run") or None,
                "related_commands": related_commands,
                "raw_text": action,
            }
        )
    return action_entries


def _command_phase(
    command: str,
    primary_corrective_commands: list[str],
    supporting_corrective_commands: list[str],
    monitoring_commands: list[str],
) -> str:
    if command in primary_corrective_commands:
        return "primary_corrective"
    if command in supporting_corrective_commands:
        return "supporting_corrective"
    if command in monitoring_commands:
        return "monitoring"
    return "supporting_corrective"


def _build_command_envelope_entries(
    commands: list[str],
    details: list[dict[str, Any]],
    *,
    phase: str,
) -> list[dict[str, Any]]:
    detail_map = _command_details_by_command(details)
    command_entries: list[dict[str, Any]] = []
    for priority, command in enumerate(commands, start=1):
        detail = dict(detail_map.get(command) or {})
        category = str(detail.get("category") or _command_group_key(command))
        command_entries.append(
            {
                "kind": "command",
                "id": category if category != "other" else f"command:{phase}:{priority}",
                "label": detail.get("label") or _command_category_label(category),
                "operator_implication": detail.get("reason") or None,
                "escalation_trigger": None,
                "priority": priority,
                "phase": phase,
                "command": command,
                "related_commands": [],
            }
        )
    return command_entries


def _no_data_timeline_signal(
    signal_id: str,
) -> dict[str, Any]:
    if signal_id == "progress":
        return {
            "kind": "timeline_signal",
            "id": "progress",
            "label": "No snapshot data",
            "operator_implication": "No snapshot data is available yet, so no trend conclusion can be drawn.",
            "escalation_trigger": "Escalate only after snapshot history becomes available and still fails to show progress.",
            "priority": 1,
            "phase": "assessment",
            "verdict": "no_data",
            "urgency": None,
            "state": None,
            "previous_state": None,
        }
    if signal_id == "stagnation":
        return {
            "kind": "timeline_signal",
            "id": "stagnation",
            "label": "No stagnation history",
            "operator_implication": "There is not enough snapshot history yet to assess whether the state is stuck.",
            "escalation_trigger": "Escalate after more history if stagnation can still not be judged clearly.",
            "priority": 2,
            "phase": "assessment",
            "verdict": "no_data",
            "urgency": None,
            "state": None,
            "previous_state": None,
        }
    return {
        "kind": "timeline_signal",
        "id": "guidance",
        "label": "Unknown operator urgency",
        "operator_implication": "No snapshot data is available yet.",
        "escalation_trigger": "Escalate only after timeline evidence becomes available and contradicts the readiness-only view.",
        "priority": 3,
        "phase": "guidance",
        "verdict": None,
        "urgency": "unknown",
        "state": None,
        "previous_state": None,
    }


def _build_timeline_signal_entry(
    signal_id: str,
    detail: dict[str, Any] | None,
    *,
    timeline_result: dict[str, Any] | None,
) -> dict[str, Any]:
    if not timeline_result:
        return _no_data_timeline_signal(signal_id)

    detail = dict(detail or {})
    progress_assessment = dict(timeline_result.get("progress_assessment") or {})
    stagnation_assessment = dict(timeline_result.get("stagnation_assessment") or {})
    operator_guidance = dict(timeline_result.get("operator_guidance") or {})
    latest_state = timeline_result.get("latest_diagnosis_state")
    previous_state = progress_assessment.get("previous_state")
    phase = "guidance" if signal_id == "guidance" else "assessment"
    priority = {"progress": 1, "stagnation": 2, "guidance": 3}.get(signal_id, 99)
    verdict = detail.get("verdict")
    urgency = detail.get("urgency")
    if signal_id == "progress":
        verdict = verdict or progress_assessment.get("verdict")
    elif signal_id == "stagnation":
        verdict = verdict or stagnation_assessment.get("verdict")
    elif signal_id == "guidance":
        urgency = urgency or operator_guidance.get("urgency")

    return {
        "kind": "timeline_signal",
        "id": signal_id,
        "label": detail.get("label") or _no_data_timeline_signal(signal_id).get("label"),
        "operator_implication": detail.get("operator_implication") or _no_data_timeline_signal(signal_id).get("operator_implication"),
        "escalation_trigger": detail.get("escalation_trigger") or _no_data_timeline_signal(signal_id).get("escalation_trigger"),
        "priority": priority,
        "phase": phase,
        "verdict": verdict,
        "urgency": urgency,
        "state": latest_state,
        "previous_state": previous_state,
    }


def _build_recent_delta_envelope_entries(
    recent_snapshot_digest: list[dict[str, Any]],
    recent_snapshot_delta_details: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    detail_map = _recent_delta_details_by_observed_at(recent_snapshot_delta_details)
    entries: list[dict[str, Any]] = []
    for priority, item in enumerate(recent_snapshot_digest, start=1):
        observed_at_utc = str(item.get("observed_at_utc") or "")
        detail = dict(detail_map.get(observed_at_utc) or {})
        entries.append(
            {
                "kind": "timeline_delta",
                "id": f"recent_delta:{observed_at_utc}" if observed_at_utc else f"recent_delta:{priority}",
                "label": detail.get("label") or "Unknown delta",
                "operator_implication": detail.get("operator_implication") or None,
                "escalation_trigger": detail.get("escalation_trigger") or None,
                "priority": priority,
                "phase": "evidence",
                "observed_at_utc": item.get("observed_at_utc"),
                "delta_kind": item.get("delta_kind"),
                "state": item.get("diagnosis_state"),
                "previous_state": item.get("previous_diagnosis_state"),
                "transition_summary": item.get("transition_summary"),
                "alignment_state": item.get("alignment_state"),
                "elapsed_since_previous_human": item.get("elapsed_since_previous_human"),
                "issue_summary": item.get("issue_summary"),
            }
        )
    return entries


def _build_operator_handoff_envelope(
    *,
    combined_assessment: dict[str, Any],
    timeline_result: dict[str, Any] | None,
    recent_snapshot_digest: list[dict[str, Any]],
    recent_snapshot_delta_details: list[dict[str, Any]],
    snapshot_workflow_commands: list[str],
) -> dict[str, Any]:
    primary_corrective_commands = list(combined_assessment.get("primary_corrective_commands") or [])
    supporting_corrective_commands = list(combined_assessment.get("supporting_corrective_commands") or [])
    monitoring_commands = list(combined_assessment.get("monitoring_commands") or [])
    follow_up_commands = list(combined_assessment.get("follow_up_commands") or [])
    action_details = list(combined_assessment.get("next_action_details") or [])
    timeline_result = dict(timeline_result or {})

    actions = _build_action_envelope_entries(
        list(combined_assessment.get("next_actions") or []),
        action_details,
        primary_corrective_commands=primary_corrective_commands,
        supporting_corrective_commands=supporting_corrective_commands,
        monitoring_commands=monitoring_commands,
    )
    primary_command_entries = _build_command_envelope_entries(
        primary_corrective_commands,
        list(combined_assessment.get("primary_corrective_command_details") or []),
        phase="primary_corrective",
    )
    supporting_command_entries = _build_command_envelope_entries(
        supporting_corrective_commands,
        list(combined_assessment.get("supporting_corrective_command_details") or []),
        phase="supporting_corrective",
    )
    monitoring_command_entries = _build_command_envelope_entries(
        monitoring_commands,
        list(combined_assessment.get("monitoring_command_details") or []),
        phase="monitoring",
    )
    progress_signal = _build_timeline_signal_entry(
        "progress",
        dict(combined_assessment.get("timeline_progress_detail") or {}),
        timeline_result=timeline_result or None,
    )
    stagnation_signal = _build_timeline_signal_entry(
        "stagnation",
        dict(combined_assessment.get("timeline_stagnation_detail") or {}),
        timeline_result=timeline_result or None,
    )
    guidance_signal = _build_timeline_signal_entry(
        "guidance",
        dict(combined_assessment.get("timeline_guidance_detail") or {}),
        timeline_result=timeline_result or None,
    )

    return {
        "version": _OPERATOR_HANDOFF_ENVELOPE_VERSION,
        "overall": {
            "overall_state": combined_assessment.get("overall_state"),
            "readiness_state": combined_assessment.get("readiness_state"),
            "timeline_state": combined_assessment.get("timeline_state"),
            "timeline_available": bool(timeline_result),
            "summary": combined_assessment.get("summary"),
            "primary_blocker": combined_assessment.get("primary_blocker"),
            "timeline_urgency": combined_assessment.get("timeline_urgency"),
            "timeline_progress_verdict": combined_assessment.get("timeline_progress_verdict"),
            "timeline_stagnation_verdict": combined_assessment.get("timeline_stagnation_verdict"),
        },
        "actions": actions,
        "commands": {
            "primary_corrective": primary_command_entries,
            "supporting_corrective": supporting_command_entries,
            "monitoring": monitoring_command_entries,
        },
        "timeline": {
            "progress": progress_signal,
            "stagnation": stagnation_signal,
            "guidance": guidance_signal,
            "recent_deltas": _build_recent_delta_envelope_entries(
                recent_snapshot_digest,
                recent_snapshot_delta_details,
            ),
        },
        "workflow": {
            "snapshot_workflow_commands": list(snapshot_workflow_commands),
            "follow_up_commands": list(follow_up_commands),
        },
    }


def _timeline_progress_detail(
    readiness_state: str,
    progress_assessment: dict[str, Any] | None,
    stagnation_assessment: dict[str, Any] | None,
) -> dict[str, Any]:
    progress_assessment = dict(progress_assessment or {})
    stagnation_assessment = dict(stagnation_assessment or {})
    verdict = str(progress_assessment.get("verdict") or "unknown")
    previous_state = progress_assessment.get("previous_state")
    current_state = progress_assessment.get("current_state")
    stagnation_verdict = str(stagnation_assessment.get("verdict") or "unknown")

    label = {
        "advanced": "Advanced from previous snapshot",
        "regressed": "Regressed from previous snapshot",
        "unchanged": "No state change yet",
        "no_previous_snapshot": "First snapshot only",
        "no_data": "No snapshot data",
        "unknown": "Unknown timeline progress",
    }.get(verdict, "Unknown timeline progress")

    implication = {
        "advanced": (
            f"The latest snapshot moved from `{previous_state or 'none'}` to "
            f"`{current_state or 'unknown'}`, so keep validating the next state transition before closing the loop."
        ),
        "regressed": (
            f"The latest snapshot moved backward from `{previous_state or 'none'}` to "
            f"`{current_state or 'unknown'}`, so treat the environment as unstable until the regression is explained."
        ),
        "unchanged": (
            "The latest snapshot did not change diagnosis state, so the operator should look for stronger corrective evidence instead of assuming silent progress."
        ),
        "no_previous_snapshot": (
            "Only one snapshot exists so far, so there is not enough history yet to judge whether the state is genuinely improving."
        ),
        "no_data": "No snapshot data is available yet, so no trend conclusion can be drawn.",
    }.get(verdict, "Timeline progress needs manual interpretation.")

    if verdict == "unchanged" and stagnation_verdict == "stuck":
        escalation_trigger = (
            "Escalate immediately to the top corrective path because the unchanged state has already crossed the stuck threshold."
        )
    elif verdict == "regressed":
        escalation_trigger = (
            "Escalate immediately if the next snapshot does not recover or if runtime/DB evidence contradicts the regression story."
        )
    elif verdict == "advanced" and readiness_state == "stage6_ready_and_aligned":
        escalation_trigger = (
            "Escalate if the next snapshot drops out of alignment or if a newly sampled record contradicts the aligned baseline."
        )
    elif verdict == "advanced":
        escalation_trigger = (
            "Escalate if the next validation step fails to continue the forward movement."
        )
    elif verdict == "no_previous_snapshot":
        escalation_trigger = (
            "Escalate only after another snapshot is collected and the state still fails to advance."
        )
    else:
        escalation_trigger = (
            "Escalate if another corrective pass still leaves the timeline without a meaningful state change."
        )

    return {
        "verdict": verdict,
        "label": label,
        "operator_implication": implication,
        "escalation_trigger": escalation_trigger,
    }


def _timeline_stagnation_detail(
    readiness_state: str,
    stagnation_assessment: dict[str, Any] | None,
) -> dict[str, Any]:
    stagnation_assessment = dict(stagnation_assessment or {})
    verdict = str(stagnation_assessment.get("verdict") or "unknown")
    threshold = stagnation_assessment.get("threshold")
    consecutive_count = stagnation_assessment.get("consecutive_count")

    label = {
        "stuck": "Stuck window reached",
        "not_stuck": "Below stuck threshold",
        "no_data": "No stagnation history",
        "unknown": "Unknown stagnation state",
    }.get(verdict, "Unknown stagnation state")

    implication = {
        "stuck": (
            f"The current state has repeated for {consecutive_count or 0} snapshots, so corrective work now has higher priority than collecting another snapshot first."
        ),
        "not_stuck": (
            f"The current state has repeated {consecutive_count or 0} times, which is still below the stuck threshold of {threshold or 'unknown'}."
        ),
        "no_data": "There is not enough snapshot history yet to assess whether the state is stuck.",
    }.get(verdict, "Stagnation needs manual interpretation.")

    if verdict == "stuck":
        escalation_trigger = (
            "Escalate now if the next corrective pass does not produce a different state or stronger runtime/DB evidence."
        )
    elif verdict == "not_stuck" and readiness_state != "stage6_ready_and_aligned":
        escalation_trigger = (
            "Escalate if the same state reaches the configured stuck threshold without a clear corrective explanation."
        )
    elif verdict == "not_stuck":
        escalation_trigger = (
            "Escalate only if later aligned samples stop holding or the state begins to regress."
        )
    else:
        escalation_trigger = "Escalate after more history if stagnation can still not be judged clearly."

    return {
        "verdict": verdict,
        "label": label,
        "operator_implication": implication,
        "escalation_trigger": escalation_trigger,
    }


def _timeline_guidance_detail(
    readiness_state: str,
    operator_guidance: dict[str, Any] | None,
    progress_assessment: dict[str, Any] | None,
    stagnation_assessment: dict[str, Any] | None,
) -> dict[str, Any]:
    operator_guidance = dict(operator_guidance or {})
    progress_assessment = dict(progress_assessment or {})
    stagnation_assessment = dict(stagnation_assessment or {})
    urgency = str(operator_guidance.get("urgency") or "unknown")
    progress_verdict = str(progress_assessment.get("verdict") or "unknown")
    stagnation_verdict = str(stagnation_assessment.get("verdict") or "unknown")

    label = {
        "high": "High urgency investigation",
        "attention": "Attention-required follow-up",
        "normal": "Normal operator follow-up",
        "unknown": "Unknown operator urgency",
    }.get(urgency, "Unknown operator urgency")

    if urgency == "high":
        implication = (
            "The timeline is signaling a regression-risk situation, so the operator should stabilize the environment before trusting more samples."
        )
    elif urgency == "attention":
        implication = (
            "The timeline is no longer just observational; it is asking for a corrective pass that should break the repeated state."
        )
    elif readiness_state == "stage6_ready_and_aligned":
        implication = (
            "The timeline supports continued sampling and spot checks rather than immediate corrective work."
        )
    else:
        implication = (
            "The timeline supports the current follow-up path but does not yet require a full escalation."
        )

    if progress_verdict == "regressed":
        escalation_trigger = (
            "Escalate immediately if the regression remains after one focused corrective pass."
        )
    elif stagnation_verdict == "stuck":
        escalation_trigger = (
            "Escalate if the prioritized corrective commands still do not produce a new state or stronger evidence."
        )
    elif urgency == "normal" and readiness_state == "stage6_ready_and_aligned":
        escalation_trigger = (
            "Escalate only if later samples regress, mismatch, or stop reproducing the aligned state."
        )
    else:
        escalation_trigger = (
            "Escalate if the next snapshot contradicts the current guidance summary."
        )

    return {
        "urgency": urgency,
        "label": label,
        "operator_implication": implication,
        "escalation_trigger": escalation_trigger,
    }


def _recent_snapshot_delta_details(
    recent_snapshot_digest: list[dict[str, Any]],
    *,
    timeline_progress_detail: dict[str, Any] | None,
    timeline_stagnation_detail: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    progress_verdict = str(dict(timeline_progress_detail or {}).get("verdict") or "unknown")
    stagnation_verdict = str(dict(timeline_stagnation_detail or {}).get("verdict") or "unknown")
    details: list[dict[str, Any]] = []
    for item in recent_snapshot_digest:
        delta_kind = str(item.get("delta_kind") or "unknown")
        transition_summary = item.get("transition_summary")
        diagnosis_state = str(item.get("diagnosis_state") or "unknown")
        label = {
            "changed": "State changed",
            "unchanged": "State unchanged",
            "initial": "Initial snapshot",
        }.get(delta_kind, "Unknown delta")

        if delta_kind == "changed":
            implication = (
                f"This snapshot changed state ({transition_summary or diagnosis_state}), so compare the new state against the planned next validation step."
            )
            if diagnosis_state == "stage6_ready_and_aligned":
                escalation_trigger = (
                    "Escalate only if the next sample drops out of alignment or if runtime/DB evidence now disagrees."
                )
            else:
                escalation_trigger = (
                    "Escalate if the next snapshot regresses further or the new state immediately repeats into another stuck window."
                )
        elif delta_kind == "unchanged":
            implication = (
                f"This snapshot stayed at `{diagnosis_state}`, so it adds confidence about the current state but not about forward progress."
            )
            if stagnation_verdict == "stuck":
                escalation_trigger = (
                    "Escalate now unless the next corrective pass produces a different state."
                )
            else:
                escalation_trigger = (
                    "Escalate if another snapshot remains unchanged after the current corrective pass."
                )
        else:
            implication = (
                "This is the first snapshot in the visible history, so use it as a baseline rather than as proof of trend."
            )
            escalation_trigger = (
                "Escalate only after another snapshot is collected and the state still does not advance."
            )

        if progress_verdict == "regressed" and delta_kind != "initial":
            escalation_trigger = (
                "Escalate immediately if the regression is not explained by the latest corrective evidence."
            )

        details.append(
            {
                "observed_at_utc": item.get("observed_at_utc"),
                "diagnosis_state": diagnosis_state,
                "delta_kind": delta_kind,
                "label": label,
                "operator_implication": implication,
                "escalation_trigger": escalation_trigger,
            }
        )
    return details


def _build_snapshot_workflow_commands(
    *,
    db_path: Path,
    logs_path: Path,
    timestamp_from: str | None,
    limit: int,
    long_recording_cloud_candidates_only: bool,
    snapshot_path: Path | None,
    recent_limit: int,
) -> list[str]:
    if snapshot_path is None:
        return []

    handoff_command_parts = [
        _format_stage6_command(
            "inspect_transcription_stage6_handoff.py",
            db_path=db_path,
            logs_path=logs_path,
            timestamp_from=timestamp_from,
            limit=limit,
        ),
        f'--snapshots "{snapshot_path}"',
        "--append-snapshot",
        "--brief",
    ]
    if long_recording_cloud_candidates_only:
        handoff_command_parts.insert(-3, "--long-recording-cloud-candidates-only")

    timeline_command_parts = [
        "uv run --cache-dir .\\.uv_cache python",
        "scripts/inspect_transcription_stage6_snapshot_timeline.py",
        f'--snapshots "{snapshot_path}"',
        f"--recent-limit {recent_limit}",
        "--summary",
    ]
    return [
        " ".join(handoff_command_parts),
        " ".join(timeline_command_parts),
    ]


def _build_combined_assessment(
    readiness_result: dict[str, Any],
    timeline_result: dict[str, Any] | None,
) -> dict[str, Any]:
    readiness = dict(readiness_result.get("readiness") or {})
    diagnosis = dict(readiness.get("diagnosis") or {})
    runbook = dict(readiness.get("runbook") or {})
    readiness_state = str(diagnosis.get("state") or "unknown")
    readiness_message = str(diagnosis.get("message") or "No message available.")
    readiness_next_action = str(
        diagnosis.get("next_action") or diagnosis.get("message") or "No guidance available."
    )
    readiness_actions = list(runbook.get("recommended_steps") or [])
    readiness_commands = list(runbook.get("follow_up_commands") or [])

    prioritized_actions = _prioritize_actions(readiness_state, list(readiness_actions))

    if timeline_result is None:
        return {
            "overall_state": "readiness_only_no_timeline",
            "summary": (
                "Readiness evidence is available, but no snapshot timeline was supplied "
                "for historical trend analysis."
            ),
            "primary_blocker": readiness.get("issue_summary") or readiness_message,
            "readiness_state": readiness_state,
            "timeline_state": None,
            "timeline_progress_verdict": None,
            "timeline_stagnation_verdict": None,
            "timeline_urgency": None,
            "timeline_consecutive_count": None,
            "timeline_stagnation_threshold": None,
            "timeline_progress_detail": {},
            "timeline_stagnation_detail": {},
            "timeline_guidance_detail": {},
            "next_actions": prioritized_actions,
            "primary_corrective_commands": readiness_commands,
            "supporting_corrective_commands": [],
            "corrective_commands": readiness_commands,
            "monitoring_commands": [],
            "follow_up_commands": readiness_commands,
        }

    progress_assessment = dict(timeline_result.get("progress_assessment") or {})
    stagnation_assessment = dict(timeline_result.get("stagnation_assessment") or {})
    operator_guidance = dict(timeline_result.get("operator_guidance") or {})
    timeline_state = str(timeline_result.get("latest_diagnosis_state") or "unknown")
    timeline_progress = str(progress_assessment.get("verdict") or "unknown")
    timeline_stagnation = str(stagnation_assessment.get("verdict") or "unknown")
    timeline_actions = list(operator_guidance.get("actions") or [])
    timeline_issue = timeline_result.get("latest_issue_summary")
    timeline_urgency = operator_guidance.get("urgency")
    timeline_consecutive_count = timeline_result.get("current_state_consecutive_count")
    timeline_stagnation_threshold = stagnation_assessment.get("threshold")

    overall_state = "needs_follow_up"
    summary = (
        f"Readiness is `{readiness_state}` while the latest timeline state is "
        f"`{timeline_state}`; continue Stage 6 follow-up actions."
    )
    primary_blocker = readiness.get("issue_summary") or timeline_issue or readiness_message

    if readiness_state == "stage6_ready_and_aligned" and timeline_state == "stage6_ready_and_aligned":
        overall_state = "aligned_with_timeline"
        summary = (
            "Both readiness and the latest snapshot timeline indicate Stage 6 alignment "
            "for the most recent observed evidence."
        )
        primary_blocker = None
    elif readiness_state == "waiting_for_new_build_session":
        overall_state = "blocked_on_new_build_session"
        summary = (
            "Stage 6 is still blocked on a newer app build session that declares the "
            "current history schema expectations."
        )
        primary_blocker = readiness_message
    elif readiness_state == "new_build_seen_db_not_migrated":
        overall_state = "blocked_on_db_migration"
        summary = (
            "A newer build session is visible, but the inspected history DB still looks "
            "unmigrated for Stage 6 persistence."
        )
        primary_blocker = readiness_message
    elif timeline_stagnation == "stuck" and readiness_state != "stage6_ready_and_aligned":
        overall_state = "stuck_follow_up_required"
        summary = (
            f"Readiness remains `{readiness_state}`, and the snapshot timeline is stuck "
            f"at `{timeline_state}`."
        )
        primary_blocker = timeline_issue or readiness.get("issue_summary") or readiness_message
    elif timeline_progress == "advanced":
        overall_state = "advancing_follow_up"
        summary = (
            f"Readiness is `{readiness_state}`, and the latest snapshot advanced to "
            f"`{timeline_state}`; continue the next validation step."
        )
    elif timeline_progress == "regressed":
        overall_state = "regressed_follow_up_required"
        summary = (
            f"Readiness is `{readiness_state}`, but the latest snapshot regressed to "
            f"`{timeline_state}`; investigate before trusting the environment."
        )

    merged_actions = _prioritize_actions(
        readiness_state,
        _merge_actions(readiness_actions, timeline_actions),
    )

    timeline_progress_detail = _timeline_progress_detail(
        readiness_state,
        progress_assessment,
        stagnation_assessment,
    )
    timeline_stagnation_detail = _timeline_stagnation_detail(
        readiness_state,
        stagnation_assessment,
    )
    timeline_guidance_detail = _timeline_guidance_detail(
        readiness_state,
        operator_guidance,
        progress_assessment,
        stagnation_assessment,
    )

    return {
        "overall_state": overall_state,
        "summary": summary,
        "primary_blocker": primary_blocker,
        "readiness_state": readiness_state,
        "timeline_state": timeline_state,
        "timeline_progress_verdict": timeline_progress,
        "timeline_stagnation_verdict": timeline_stagnation,
        "timeline_urgency": timeline_urgency,
        "timeline_consecutive_count": timeline_consecutive_count,
        "timeline_stagnation_threshold": timeline_stagnation_threshold,
        "timeline_progress_detail": timeline_progress_detail,
        "timeline_stagnation_detail": timeline_stagnation_detail,
        "timeline_guidance_detail": timeline_guidance_detail,
        "readiness_next_action": readiness_next_action,
        "timeline_guidance": operator_guidance.get("summary"),
        "next_actions": merged_actions,
        "corrective_commands": _merge_commands(readiness_commands),
        "monitoring_commands": [],
        "follow_up_commands": _merge_commands(readiness_commands),
    }


def inspect_transcription_stage6_handoff(
    *,
    db_path: Path,
    logs_path: Path,
    timestamp_from: str | None = None,
    limit: int = 20,
    long_recording_cloud_candidates_only: bool = False,
    snapshot_path: Path | None = None,
    append_snapshot: bool = False,
    recent_limit: int = 5,
) -> dict[str, Any]:
    if append_snapshot and snapshot_path is None:
        raise ValueError("snapshot_path is required when append_snapshot=True")

    snapshot_workflow_commands = _build_snapshot_workflow_commands(
        db_path=db_path,
        logs_path=logs_path,
        timestamp_from=timestamp_from,
        limit=limit,
        long_recording_cloud_candidates_only=long_recording_cloud_candidates_only,
        snapshot_path=snapshot_path,
        recent_limit=recent_limit,
    )
    readiness_result = inspect_transcription_stage6_readiness(
        db_path=db_path,
        logs_path=logs_path,
        timestamp_from=timestamp_from,
        limit=limit,
        long_recording_cloud_candidates_only=long_recording_cloud_candidates_only,
    )
    appended_snapshot = None
    if append_snapshot and snapshot_path is not None:
        appended_snapshot = append_stage6_readiness_snapshot(snapshot_path, readiness_result)
    timeline_result = (
        inspect_stage6_snapshot_timeline(snapshot_path, recent_limit=recent_limit)
        if snapshot_path is not None
        else None
    )
    combined_assessment = _build_combined_assessment(readiness_result, timeline_result)
    corrective_commands = _merge_commands(
        list(combined_assessment.get("corrective_commands") or [])
    )
    primary_corrective_commands, supporting_corrective_commands = _split_corrective_commands(
        str(combined_assessment.get("readiness_state") or "unknown"),
        corrective_commands,
    )
    monitoring_commands = _merge_commands(snapshot_workflow_commands)
    combined_assessment["primary_corrective_commands"] = primary_corrective_commands
    combined_assessment["supporting_corrective_commands"] = supporting_corrective_commands
    combined_assessment["corrective_commands"] = corrective_commands
    combined_assessment["monitoring_commands"] = monitoring_commands
    combined_assessment["primary_corrective_command_details"] = _build_command_details(
        str(combined_assessment.get("readiness_state") or "unknown"),
        primary_corrective_commands,
    )
    combined_assessment["supporting_corrective_command_details"] = _build_command_details(
        str(combined_assessment.get("readiness_state") or "unknown"),
        supporting_corrective_commands,
    )
    combined_assessment["monitoring_command_details"] = _build_command_details(
        str(combined_assessment.get("readiness_state") or "unknown"),
        monitoring_commands,
    )
    combined_assessment["next_action_details"] = _build_action_details(
        str(combined_assessment.get("readiness_state") or "unknown"),
        list(combined_assessment.get("next_actions") or []),
        timeline_progress=(
            str(combined_assessment.get("timeline_progress_verdict"))
            if combined_assessment.get("timeline_progress_verdict") is not None
            else None
        ),
        timeline_stagnation=(
            str(combined_assessment.get("timeline_stagnation_verdict"))
            if combined_assessment.get("timeline_stagnation_verdict") is not None
            else None
        ),
        primary_corrective_commands=primary_corrective_commands,
        supporting_corrective_commands=supporting_corrective_commands,
        monitoring_commands=monitoring_commands,
    )
    if combined_assessment.get("timeline_stagnation_verdict") == "stuck":
        combined_assessment["follow_up_commands"] = _merge_commands(
            primary_corrective_commands,
            supporting_corrective_commands,
            monitoring_commands,
        )
    else:
        combined_assessment["follow_up_commands"] = _merge_commands(
            monitoring_commands,
            primary_corrective_commands,
            supporting_corrective_commands,
        )
    recent_snapshot_digest = list(
        dict(timeline_result or {}).get("recent_snapshot_digest") or []
    )
    recent_snapshot_delta_details = _recent_snapshot_delta_details(
        recent_snapshot_digest,
        timeline_progress_detail=dict(
            combined_assessment.get("timeline_progress_detail") or {}
        ),
        timeline_stagnation_detail=dict(
            combined_assessment.get("timeline_stagnation_detail") or {}
        ),
    )
    operator_handoff_envelope = _build_operator_handoff_envelope(
        combined_assessment=combined_assessment,
        timeline_result=timeline_result,
        recent_snapshot_digest=recent_snapshot_digest,
        recent_snapshot_delta_details=recent_snapshot_delta_details,
        snapshot_workflow_commands=snapshot_workflow_commands,
    )

    return {
        "db_path": str(db_path),
        "logs_path": str(logs_path),
        "timestamp_from": timestamp_from,
        "limit": limit,
        "long_recording_cloud_candidates_only": long_recording_cloud_candidates_only,
        "snapshot_path": str(snapshot_path) if snapshot_path is not None else None,
        "append_snapshot": append_snapshot,
        "appended_snapshot": appended_snapshot,
        "recent_snapshot_limit": recent_limit,
        "recent_snapshot_digest": recent_snapshot_digest,
        "recent_snapshot_delta_details": recent_snapshot_delta_details,
        "snapshot_workflow_commands": snapshot_workflow_commands,
        "operator_handoff_envelope": operator_handoff_envelope,
        "combined_assessment": combined_assessment,
        "readiness": readiness_result,
        "timeline": timeline_result,
    }


def format_stage6_handoff_summary(result: dict[str, Any]) -> str:
    combined = dict(result.get("combined_assessment") or {})
    readiness = dict(result.get("readiness") or {})
    readiness_core = dict(readiness.get("readiness") or {})
    record_timeline_preview = dict(readiness_core.get("record_timeline_preview") or {})
    timeline_result = dict(result.get("timeline") or {})
    state_dwell_summary = dict(timeline_result.get("state_dwell_summary") or {})
    lines = [
        "Stage 6 Operator Handoff Summary",
        f"- Overall state: {combined.get('overall_state') or 'unknown'}",
        f"- Summary: {combined.get('summary') or 'No summary available.'}",
        f"- Readiness state: {combined.get('readiness_state') or 'unknown'}",
        f"- Timeline state: {combined.get('timeline_state') or 'none'}",
        (
            "- Timeline progress verdict: "
            f"{combined.get('timeline_progress_verdict') or 'none'}"
        ),
        (
            "- Timeline stagnation verdict: "
            f"{combined.get('timeline_stagnation_verdict') or 'none'}"
        ),
    ]
    timeline_urgency = combined.get("timeline_urgency")
    if timeline_urgency:
        lines.append(f"- Timeline urgency: {timeline_urgency}")
    timeline_consecutive_count = combined.get("timeline_consecutive_count")
    timeline_stagnation_threshold = combined.get("timeline_stagnation_threshold")
    if timeline_consecutive_count is not None and timeline_stagnation_threshold is not None:
        lines.append(
            "- Timeline stagnation window: "
            f"{timeline_consecutive_count}/{timeline_stagnation_threshold}"
        )
    latest_state_elapsed_human = state_dwell_summary.get(
        "latest_state_elapsed_human_since_first_seen"
    )
    if latest_state_elapsed_human:
        lines.append(f"- Timeline current state elapsed: {latest_state_elapsed_human}")
    timeline_progress_detail = dict(combined.get("timeline_progress_detail") or {})
    if timeline_progress_detail.get("label"):
        lines.append(
            f"- Timeline progress label: {timeline_progress_detail.get('label')}"
        )
    if timeline_progress_detail.get("operator_implication"):
        lines.append(
            "- Timeline progress implication: "
            f"{timeline_progress_detail.get('operator_implication')}"
        )
    timeline_stagnation_detail = dict(combined.get("timeline_stagnation_detail") or {})
    if timeline_stagnation_detail.get("label"):
        lines.append(
            f"- Timeline stagnation label: {timeline_stagnation_detail.get('label')}"
        )
    if timeline_stagnation_detail.get("operator_implication"):
        lines.append(
            "- Timeline stagnation implication: "
            f"{timeline_stagnation_detail.get('operator_implication')}"
        )
    timeline_guidance_detail = dict(combined.get("timeline_guidance_detail") or {})
    if timeline_guidance_detail.get("label"):
        lines.append(
            f"- Timeline guidance label: {timeline_guidance_detail.get('label')}"
        )
    if timeline_guidance_detail.get("operator_implication"):
        lines.append(
            "- Timeline guidance implication: "
            f"{timeline_guidance_detail.get('operator_implication')}"
        )
    escalation_trigger = (
        timeline_guidance_detail.get("escalation_trigger")
        or timeline_stagnation_detail.get("escalation_trigger")
        or timeline_progress_detail.get("escalation_trigger")
    )
    if escalation_trigger:
        lines.append(f"- Timeline escalate-if: {escalation_trigger}")

    primary_blocker = combined.get("primary_blocker")
    if primary_blocker:
        lines.append(f"- Primary blocker: {primary_blocker}")
    if record_timeline_preview:
        lines.append(
            "- Record timeline preview: "
            f"{record_timeline_preview.get('diagnosis_state') or 'unknown'}"
        )

    actions = list(combined.get("next_actions") or [])
    action_detail_map = _action_details_by_action(
        list(combined.get("next_action_details") or [])
    )
    if actions:
        lines.extend(["", "Combined Next Actions:"])
        for action in actions:
            lines.append(f"- {action}")
            detail = action_detail_map.get(action) or {}
            if detail.get("label"):
                lines.append(f"  label={detail.get('label')}")
            if detail.get("when_to_run"):
                lines.append(f"  when={detail.get('when_to_run')}")
            if detail.get("reason"):
                lines.append(f"  why_now={detail.get('reason')}")
            related_summary = _related_command_summary(
                list(detail.get("related_commands") or [])
            )
            if related_summary:
                lines.append(f"  related={related_summary}")
    primary_corrective_commands = list(combined.get("primary_corrective_commands") or [])
    supporting_corrective_commands = list(combined.get("supporting_corrective_commands") or [])
    corrective_commands = list(combined.get("corrective_commands") or [])
    monitoring_commands = list(combined.get("monitoring_commands") or [])
    follow_up_commands = list(combined.get("follow_up_commands") or [])
    primary_detail_map = _command_details_by_command(
        list(combined.get("primary_corrective_command_details") or [])
    )
    supporting_detail_map = _command_details_by_command(
        list(combined.get("supporting_corrective_command_details") or [])
    )
    monitoring_detail_map = _command_details_by_command(
        list(combined.get("monitoring_command_details") or [])
    )
    if primary_corrective_commands:
        lines.extend(["", "Primary Corrective Commands:"])
        for command in primary_corrective_commands:
            lines.append(f"- {command}")
            detail = primary_detail_map.get(command) or {}
            if detail.get("label"):
                lines.append(f"  label={detail.get('label')}")
            if detail.get("reason"):
                lines.append(f"  why_now={detail.get('reason')}")
    if supporting_corrective_commands:
        lines.extend(["", "Supporting Corrective Commands:"])
        for command in supporting_corrective_commands:
            lines.append(f"- {command}")
            detail = supporting_detail_map.get(command) or {}
            if detail.get("label"):
                lines.append(f"  label={detail.get('label')}")
            if detail.get("reason"):
                lines.append(f"  why_now={detail.get('reason')}")
    if monitoring_commands:
        lines.extend(["", "Monitoring Commands:"])
        for command in monitoring_commands:
            lines.append(f"- {command}")
            detail = monitoring_detail_map.get(command) or {}
            if detail.get("label"):
                lines.append(f"  label={detail.get('label')}")
            if detail.get("reason"):
                lines.append(f"  why_now={detail.get('reason')}")
    elif follow_up_commands and not corrective_commands:
        lines.extend(["", "Combined Follow-up Commands:"])
        for command in follow_up_commands:
            lines.append(f"- {command}")

    appended_snapshot = dict(result.get("appended_snapshot") or {})
    if appended_snapshot:
        lines.extend(
            [
                "",
                "Appended Snapshot:",
                f"- Observed at UTC: {appended_snapshot.get('observed_at_utc') or 'unknown'}",
                f"- Diagnosis state: {appended_snapshot.get('diagnosis_state') or 'unknown'}",
            ]
        )

    recent_snapshot_digest = list(result.get("recent_snapshot_digest") or [])
    recent_delta_detail_map = _recent_delta_details_by_observed_at(
        list(result.get("recent_snapshot_delta_details") or [])
    )
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
            detail = recent_delta_detail_map.get(str(item.get("observed_at_utc") or "")) or {}
            if detail.get("label"):
                lines.append(f"  delta_label={detail.get('label')}")
            if detail.get("operator_implication"):
                lines.append(f"  implication={detail.get('operator_implication')}")
            if detail.get("escalation_trigger"):
                lines.append(f"  escalate_if={detail.get('escalation_trigger')}")

    lines.extend(
        [
            "",
            "Readiness Summary:",
            format_stage6_readiness_summary(dict(result.get("readiness") or {})),
        ]
    )

    if result.get("timeline") is not None:
        lines.extend(
            [
                "",
                "Timeline Summary:",
                format_stage6_snapshot_timeline_summary(timeline_result),
            ]
        )
    else:
        lines.extend(["", "Timeline Summary:", "No snapshot timeline was supplied."])

    return "\n".join(lines)


def format_stage6_handoff_brief(result: dict[str, Any]) -> str:
    combined = dict(result.get("combined_assessment") or {})
    readiness = dict(result.get("readiness") or {})
    readiness_core = dict(readiness.get("readiness") or {})
    record_timeline_preview = dict(readiness_core.get("record_timeline_preview") or {})
    timeline_result = dict(result.get("timeline") or {})
    state_dwell_summary = dict(timeline_result.get("state_dwell_summary") or {})
    progress_assessment = dict(timeline_result.get("progress_assessment") or {})
    stagnation_assessment = dict(timeline_result.get("stagnation_assessment") or {})

    lines = [
        "Stage 6 Operator Brief",
        f"- Overall state: {combined.get('overall_state') or 'unknown'}",
        f"- Summary: {combined.get('summary') or 'No summary available.'}",
        f"- Readiness state: {combined.get('readiness_state') or 'unknown'}",
        f"- Timeline state: {combined.get('timeline_state') or 'none'}",
    ]

    if timeline_result:
        lines.extend(
            [
                (
                    "- Latest observed at UTC: "
                    f"{timeline_result.get('latest_observed_at_utc') or 'none'}"
                ),
                (
                    "- Previous timeline state: "
                    f"{progress_assessment.get('previous_state') or 'none'}"
                ),
                (
                    "- Progress: "
                    f"{progress_assessment.get('verdict') or 'none'}"
                ),
                (
                    "- Progress detail: "
                    f"{progress_assessment.get('message') or 'No progress detail available.'}"
                ),
                (
                    "- Stagnation: "
                    f"{stagnation_assessment.get('verdict') or 'none'}"
                ),
            ]
        )
        timeline_urgency = combined.get("timeline_urgency")
        if timeline_urgency:
            lines.append(f"- Timeline urgency: {timeline_urgency}")
        timeline_consecutive_count = combined.get("timeline_consecutive_count")
        timeline_stagnation_threshold = combined.get("timeline_stagnation_threshold")
        if timeline_consecutive_count is not None and timeline_stagnation_threshold is not None:
            lines.append(
                "- Stagnation window: "
                f"{timeline_consecutive_count}/{timeline_stagnation_threshold}"
            )
        latest_state_elapsed_human = state_dwell_summary.get(
            "latest_state_elapsed_human_since_first_seen"
        )
        if latest_state_elapsed_human:
            lines.append(f"- Timeline current state elapsed: {latest_state_elapsed_human}")
        latest_transition_summary = timeline_result.get("latest_transition_summary")
        if latest_transition_summary:
            lines.append(f"- Latest transition: {latest_transition_summary}")
        timeline_progress_detail = dict(combined.get("timeline_progress_detail") or {})
        if timeline_progress_detail.get("label"):
            lines.append(f"- Timeline progress label: {timeline_progress_detail.get('label')}")
        timeline_guidance_detail = dict(combined.get("timeline_guidance_detail") or {})
        if timeline_guidance_detail.get("label"):
            lines.append(f"- Timeline guidance label: {timeline_guidance_detail.get('label')}")
        escalation_trigger = (
            timeline_guidance_detail.get("escalation_trigger")
            or dict(combined.get("timeline_stagnation_detail") or {}).get("escalation_trigger")
            or timeline_progress_detail.get("escalation_trigger")
        )
        if escalation_trigger:
            lines.append(f"- Timeline escalate-if: {escalation_trigger}")
    else:
        lines.append("- Timeline detail: No snapshot timeline was supplied.")

    primary_blocker = combined.get("primary_blocker")
    if primary_blocker:
        lines.append(f"- Primary blocker: {primary_blocker}")
    if record_timeline_preview:
        lines.append(
            "- Record timeline preview: "
            f"{record_timeline_preview.get('diagnosis_state') or 'unknown'}"
        )

    appended_snapshot = dict(result.get("appended_snapshot") or {})
    if appended_snapshot:
        lines.append(
            "- Appended snapshot: "
            f"{appended_snapshot.get('diagnosis_state') or 'unknown'} at "
            f"{appended_snapshot.get('observed_at_utc') or 'unknown'}"
        )

    recent_snapshot_digest = list(result.get("recent_snapshot_digest") or [])
    recent_delta_detail_map = _recent_delta_details_by_observed_at(
        list(result.get("recent_snapshot_delta_details") or [])
    )
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
                    "    elapsed_since_previous="
                    f"{item.get('elapsed_since_previous_human')}"
                )
            detail = recent_delta_detail_map.get(str(item.get("observed_at_utc") or "")) or {}
            if detail.get("label"):
                lines.append(f"    delta_label={detail.get('label')}")
            if detail.get("operator_implication"):
                lines.append(f"    implication={detail.get('operator_implication')}")
        remaining_count = len(recent_snapshot_digest) - 3
        if remaining_count > 0:
            lines.append(f"  - (+{remaining_count} more recent deltas in summary/markdown output)")

    actions = list(combined.get("next_actions") or [])
    action_detail_map = _action_details_by_action(
        list(combined.get("next_action_details") or [])
    )
    if actions:
        lines.append("- Next actions:")
        for action in actions[:3]:
            lines.append(f"  - {action}")
            detail = action_detail_map.get(action) or {}
            if detail.get("label"):
                lines.append(f"    label={detail.get('label')}")
            if detail.get("when_to_run"):
                lines.append(f"    when={detail.get('when_to_run')}")
            if detail.get("reason"):
                lines.append(f"    why_now={detail.get('reason')}")
            related_summary = _related_command_summary(
                list(detail.get("related_commands") or [])
            )
            if related_summary:
                lines.append(f"    related={related_summary}")
        remaining_count = len(actions) - 3
        if remaining_count > 0:
            lines.append(f"  - (+{remaining_count} more actions in summary/card output)")
    primary_corrective_commands = list(combined.get("primary_corrective_commands") or [])
    supporting_corrective_commands = list(combined.get("supporting_corrective_commands") or [])
    corrective_commands = list(combined.get("corrective_commands") or [])
    monitoring_commands = list(combined.get("monitoring_commands") or [])
    follow_up_commands = list(combined.get("follow_up_commands") or [])
    primary_detail_map = _command_details_by_command(
        list(combined.get("primary_corrective_command_details") or [])
    )
    supporting_detail_map = _command_details_by_command(
        list(combined.get("supporting_corrective_command_details") or [])
    )
    monitoring_detail_map = _command_details_by_command(
        list(combined.get("monitoring_command_details") or [])
    )
    if primary_corrective_commands:
        visible, remaining_count = _limit_with_remaining(primary_corrective_commands, 2)
        lines.append("- Primary corrective commands:")
        for command in visible:
            lines.append(f"  - {command}")
            detail = primary_detail_map.get(command) or {}
            if detail.get("label"):
                lines.append(f"    label={detail.get('label')}")
            if detail.get("reason"):
                lines.append(f"    why_now={detail.get('reason')}")
        if remaining_count > 0:
            lines.append(
                f"  - (+{remaining_count} more primary corrective commands in summary/markdown output)"
            )
    elif follow_up_commands:
        visible, remaining_count = _limit_with_remaining(follow_up_commands, 2)
        lines.append("- Follow-up commands:")
        for command in visible:
            lines.append(f"  - {command}")
        if remaining_count > 0:
            lines.append(f"  - (+{remaining_count} more commands in summary/markdown output)")
    if supporting_corrective_commands:
        visible, remaining_count = _limit_with_remaining(supporting_corrective_commands, 2)
        lines.append("- Supporting corrective commands:")
        for command in visible:
            lines.append(f"  - {command}")
            detail = supporting_detail_map.get(command) or {}
            if detail.get("label"):
                lines.append(f"    label={detail.get('label')}")
            if detail.get("reason"):
                lines.append(f"    why_now={detail.get('reason')}")
        if remaining_count > 0:
            lines.append(
                f"  - (+{remaining_count} more supporting corrective commands in summary/markdown output)"
            )
    if monitoring_commands:
        visible, remaining_count = _limit_with_remaining(monitoring_commands, 1)
        lines.append("- Monitoring commands:")
        for command in visible:
            lines.append(f"  - {command}")
            detail = monitoring_detail_map.get(command) or {}
            if detail.get("label"):
                lines.append(f"    label={detail.get('label')}")
            if detail.get("reason"):
                lines.append(f"    why_now={detail.get('reason')}")
        if remaining_count > 0:
            lines.append(
                f"  - (+{remaining_count} more monitoring commands in summary/markdown output)"
            )

    return "\n".join(lines)


def format_stage6_handoff_compare(result: dict[str, Any]) -> str:
    combined = dict(result.get("combined_assessment") or {})
    readiness = dict(result.get("readiness") or {})
    readiness_core = dict(readiness.get("readiness") or {})
    record_timeline_preview = dict(readiness_core.get("record_timeline_preview") or {})
    timeline_result = dict(result.get("timeline") or {})
    state_dwell_summary = dict(timeline_result.get("state_dwell_summary") or {})
    progress_assessment = dict(timeline_result.get("progress_assessment") or {})
    stagnation_assessment = dict(timeline_result.get("stagnation_assessment") or {})
    recent_snapshot_digest = list(result.get("recent_snapshot_digest") or [])
    latest_item = recent_snapshot_digest[0] if recent_snapshot_digest else None
    previous_item = recent_snapshot_digest[1] if len(recent_snapshot_digest) >= 2 else None

    lines = [
        "Stage 6 Compare View",
        f"- Overall state: {combined.get('overall_state') or 'unknown'}",
        f"- Readiness state: {combined.get('readiness_state') or 'unknown'}",
        (
            "- Timeline latest: "
            f"{combined.get('timeline_state') or 'none'}"
        ),
        (
            "- Timeline previous: "
            f"{progress_assessment.get('previous_state') or 'none'}"
        ),
        f"- Delta verdict: {progress_assessment.get('verdict') or 'none'}",
        (
            "- Delta detail: "
            f"{progress_assessment.get('message') or 'No delta detail available.'}"
        ),
        (
            "- Stagnation: "
            f"{stagnation_assessment.get('verdict') or 'none'}"
        ),
    ]
    timeline_urgency = combined.get("timeline_urgency")
    if timeline_urgency:
        lines.append(f"- Timeline urgency: {timeline_urgency}")
    timeline_consecutive_count = combined.get("timeline_consecutive_count")
    timeline_stagnation_threshold = combined.get("timeline_stagnation_threshold")
    if timeline_consecutive_count is not None and timeline_stagnation_threshold is not None:
        lines.append(
            "- Stagnation window: "
            f"{timeline_consecutive_count}/{timeline_stagnation_threshold}"
        )
    latest_state_elapsed_human = state_dwell_summary.get(
        "latest_state_elapsed_human_since_first_seen"
    )
    if latest_state_elapsed_human:
        lines.append(f"- Timeline current state elapsed: {latest_state_elapsed_human}")
    timeline_progress_detail = dict(combined.get("timeline_progress_detail") or {})
    if timeline_progress_detail.get("label"):
        lines.append(f"- Timeline progress label: {timeline_progress_detail.get('label')}")
    timeline_guidance_detail = dict(combined.get("timeline_guidance_detail") or {})
    if timeline_guidance_detail.get("label"):
        lines.append(f"- Timeline guidance label: {timeline_guidance_detail.get('label')}")
    escalation_trigger = (
        timeline_guidance_detail.get("escalation_trigger")
        or dict(combined.get("timeline_stagnation_detail") or {}).get("escalation_trigger")
        or timeline_progress_detail.get("escalation_trigger")
    )
    if escalation_trigger:
        lines.append(f"- Timeline escalate-if: {escalation_trigger}")
    if record_timeline_preview:
        lines.append(
            "- Record timeline preview: "
            f"{record_timeline_preview.get('diagnosis_state') or 'unknown'}"
        )

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
                "- Elapsed since previous snapshot: "
                f"{latest_item.get('elapsed_since_previous_human')}"
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
    elif timeline_result:
        lines.extend(["", "Previous Snapshot:", "- none"])
    else:
        lines.extend(["", "Previous Snapshot:", "- no timeline supplied"])

    latest_transition_summary = timeline_result.get("latest_transition_summary")
    if latest_transition_summary:
        lines.append(f"- Latest transition: {latest_transition_summary}")

    primary_blocker = combined.get("primary_blocker")
    if primary_blocker:
        lines.extend(["", f"Primary blocker: {primary_blocker}"])

    appended_snapshot = dict(result.get("appended_snapshot") or {})
    if appended_snapshot:
        lines.append(
            "Appended snapshot: "
            f"{appended_snapshot.get('diagnosis_state') or 'unknown'} at "
            f"{appended_snapshot.get('observed_at_utc') or 'unknown'}"
        )

    recent_delta_detail_map = _recent_delta_details_by_observed_at(
        list(result.get("recent_snapshot_delta_details") or [])
    )
    if latest_item is not None:
        detail = recent_delta_detail_map.get(str(latest_item.get("observed_at_utc") or "")) or {}
        if detail.get("label"):
            lines.append(f"- Latest delta label: {detail.get('label')}")
        if detail.get("operator_implication"):
            lines.append(f"- Latest delta implication: {detail.get('operator_implication')}")
        if detail.get("escalation_trigger"):
            lines.append(f"- Latest delta escalate-if: {detail.get('escalation_trigger')}")

    actions = list(combined.get("next_actions") or [])
    action_detail_map = _action_details_by_action(
        list(combined.get("next_action_details") or [])
    )
    if actions:
        lines.extend(["", "Top actions:"])
        for action in actions[:3]:
            lines.append(f"- {action}")
            detail = action_detail_map.get(action) or {}
            if detail.get("label"):
                lines.append(f"  label={detail.get('label')}")
            if detail.get("when_to_run"):
                lines.append(f"  when={detail.get('when_to_run')}")
            if detail.get("reason"):
                lines.append(f"  why_now={detail.get('reason')}")
            related_summary = _related_command_summary(
                list(detail.get("related_commands") or [])
            )
            if related_summary:
                lines.append(f"  related={related_summary}")
    primary_corrective_commands = list(combined.get("primary_corrective_commands") or [])
    supporting_corrective_commands = list(combined.get("supporting_corrective_commands") or [])
    corrective_commands = list(combined.get("corrective_commands") or [])
    monitoring_commands = list(combined.get("monitoring_commands") or [])
    follow_up_commands = list(combined.get("follow_up_commands") or [])
    primary_detail_map = _command_details_by_command(
        list(combined.get("primary_corrective_command_details") or [])
    )
    supporting_detail_map = _command_details_by_command(
        list(combined.get("supporting_corrective_command_details") or [])
    )
    monitoring_detail_map = _command_details_by_command(
        list(combined.get("monitoring_command_details") or [])
    )
    if primary_corrective_commands:
        lines.extend(["", "Top primary corrective commands:"])
        for command in primary_corrective_commands[:2]:
            lines.append(f"- {command}")
            detail = primary_detail_map.get(command) or {}
            if detail.get("label"):
                lines.append(f"  label={detail.get('label')}")
            if detail.get("reason"):
                lines.append(f"  why_now={detail.get('reason')}")
    elif follow_up_commands:
        lines.extend(["", "Top follow-up commands:"])
        for command in follow_up_commands[:2]:
            lines.append(f"- {command}")
    if supporting_corrective_commands:
        lines.extend(["", "Top supporting corrective commands:"])
        for command in supporting_corrective_commands[:2]:
            lines.append(f"- {command}")
            detail = supporting_detail_map.get(command) or {}
            if detail.get("label"):
                lines.append(f"  label={detail.get('label')}")
            if detail.get("reason"):
                lines.append(f"  why_now={detail.get('reason')}")
    if monitoring_commands:
        lines.extend(["", "Top monitoring commands:"])
        for command in monitoring_commands[:1]:
            lines.append(f"- {command}")
            detail = monitoring_detail_map.get(command) or {}
            if detail.get("label"):
                lines.append(f"  label={detail.get('label')}")
            if detail.get("reason"):
                lines.append(f"  why_now={detail.get('reason')}")

    return "\n".join(lines)


def format_stage6_handoff_card(result: dict[str, Any]) -> str:
    combined = dict(result.get("combined_assessment") or {})
    readiness = dict(result.get("readiness") or {})
    readiness_core = dict(readiness.get("readiness") or {})
    record_timeline_preview = dict(readiness_core.get("record_timeline_preview") or {})
    timeline_result = dict(result.get("timeline") or {})
    state_dwell_summary = dict(timeline_result.get("state_dwell_summary") or {})
    lines = [
        "# Stage 6 Operator Handoff",
        f"- **Overall state:** `{combined.get('overall_state') or 'unknown'}`",
        f"- **Summary:** {combined.get('summary') or 'No summary available.'}",
        f"- **Readiness state:** `{combined.get('readiness_state') or 'unknown'}`",
        f"- **Timeline state:** `{combined.get('timeline_state') or 'none'}`",
        (
            "- **Timeline progress:** "
            f"`{combined.get('timeline_progress_verdict') or 'none'}`"
        ),
        (
            "- **Timeline stagnation:** "
            f"`{combined.get('timeline_stagnation_verdict') or 'none'}`"
        ),
    ]
    timeline_urgency = combined.get("timeline_urgency")
    if timeline_urgency:
        lines.append(f"- **Timeline urgency:** `{timeline_urgency}`")
    timeline_consecutive_count = combined.get("timeline_consecutive_count")
    timeline_stagnation_threshold = combined.get("timeline_stagnation_threshold")
    if timeline_consecutive_count is not None and timeline_stagnation_threshold is not None:
        lines.append(
            "- **Timeline stagnation window:** "
            f"`{timeline_consecutive_count}/{timeline_stagnation_threshold}`"
        )
    latest_state_elapsed_human = state_dwell_summary.get(
        "latest_state_elapsed_human_since_first_seen"
    )
    if latest_state_elapsed_human:
        lines.append(f"- **Timeline current state elapsed:** `{latest_state_elapsed_human}`")
    timeline_progress_detail = dict(combined.get("timeline_progress_detail") or {})
    if timeline_progress_detail.get("label"):
        lines.append(
            f"- **Timeline progress label:** {timeline_progress_detail.get('label')}"
        )
    timeline_guidance_detail = dict(combined.get("timeline_guidance_detail") or {})
    if timeline_guidance_detail.get("label"):
        lines.append(
            f"- **Timeline guidance label:** {timeline_guidance_detail.get('label')}"
        )
    escalation_trigger = (
        timeline_guidance_detail.get("escalation_trigger")
        or dict(combined.get("timeline_stagnation_detail") or {}).get("escalation_trigger")
        or timeline_progress_detail.get("escalation_trigger")
    )
    if escalation_trigger:
        lines.append(f"- **Timeline escalate-if:** {escalation_trigger}")
    if record_timeline_preview:
        lines.append(
            "- **Record timeline preview:** "
            f"`{record_timeline_preview.get('diagnosis_state') or 'unknown'}`"
        )

    primary_blocker = combined.get("primary_blocker")
    if primary_blocker:
        lines.append(f"- **Primary blocker:** {primary_blocker}")

    actions = list(combined.get("next_actions") or [])
    action_detail_map = _action_details_by_action(
        list(combined.get("next_action_details") or [])
    )
    if actions:
        lines.append("- **Combined next actions:**")
        for action in actions:
            lines.append(f"  - {action}")
            detail = action_detail_map.get(action) or {}
            if detail.get("label"):
                lines.append(f"    - Label: {detail.get('label')}")
            if detail.get("when_to_run"):
                lines.append(f"    - When: {detail.get('when_to_run')}")
            if detail.get("reason"):
                lines.append(f"    - Why now: {detail.get('reason')}")
            related_summary = _related_command_summary(
                list(detail.get("related_commands") or [])
            )
            if related_summary:
                lines.append(f"    - Related: {related_summary}")
    primary_corrective_commands = list(combined.get("primary_corrective_commands") or [])
    supporting_corrective_commands = list(combined.get("supporting_corrective_commands") or [])
    corrective_commands = list(combined.get("corrective_commands") or [])
    monitoring_commands = list(combined.get("monitoring_commands") or [])
    follow_up_commands = list(combined.get("follow_up_commands") or [])
    primary_detail_map = _command_details_by_command(
        list(combined.get("primary_corrective_command_details") or [])
    )
    supporting_detail_map = _command_details_by_command(
        list(combined.get("supporting_corrective_command_details") or [])
    )
    monitoring_detail_map = _command_details_by_command(
        list(combined.get("monitoring_command_details") or [])
    )
    if primary_corrective_commands:
        lines.append("- **Primary corrective commands:**")
        for command in primary_corrective_commands:
            lines.append(f"  - `{command}`")
            detail = primary_detail_map.get(command) or {}
            if detail.get("label"):
                lines.append(f"    - Label: {detail.get('label')}")
            if detail.get("reason"):
                lines.append(f"    - Why now: {detail.get('reason')}")
    elif follow_up_commands:
        lines.append("- **Combined follow-up commands:**")
        for command in follow_up_commands:
            lines.append(f"  - `{command}`")
    if supporting_corrective_commands:
        lines.append("- **Supporting corrective commands:**")
        for command in supporting_corrective_commands:
            lines.append(f"  - `{command}`")
            detail = supporting_detail_map.get(command) or {}
            if detail.get("label"):
                lines.append(f"    - Label: {detail.get('label')}")
            if detail.get("reason"):
                lines.append(f"    - Why now: {detail.get('reason')}")
    if monitoring_commands:
        lines.append("- **Monitoring commands:**")
        for command in monitoring_commands:
            lines.append(f"  - `{command}`")
            detail = monitoring_detail_map.get(command) or {}
            if detail.get("label"):
                lines.append(f"    - Label: {detail.get('label')}")
            if detail.get("reason"):
                lines.append(f"    - Why now: {detail.get('reason')}")

    appended_snapshot = dict(result.get("appended_snapshot") or {})
    if appended_snapshot:
        lines.extend(
            [
                f"- **Appended snapshot observed at UTC:** `{appended_snapshot.get('observed_at_utc') or 'unknown'}`",
                f"- **Appended snapshot diagnosis:** `{appended_snapshot.get('diagnosis_state') or 'unknown'}`",
            ]
        )

    lines.extend(
        [
            "",
            format_stage6_readiness_card(dict(result.get("readiness") or {})),
            "",
        ]
    )

    timeline_value = result.get("timeline")
    if timeline_value is not None:
        lines.append(format_stage6_snapshot_timeline_card(timeline_result))
    else:
        lines.extend(
            [
                "## Stage 6 Status Card",
                "- **Latest diagnosis:** `none`",
                "- **Guidance:** No snapshot timeline was supplied.",
            ]
        )

    return "\n".join(lines)


def format_stage6_handoff_markdown(result: dict[str, Any]) -> str:
    combined = dict(result.get("combined_assessment") or {})
    readiness = dict(result.get("readiness") or {})
    readiness_core = dict(readiness.get("readiness") or {})
    record_timeline_preview = dict(readiness_core.get("record_timeline_preview") or {})
    timeline_result = dict(result.get("timeline") or {})
    state_dwell_summary = dict(timeline_result.get("state_dwell_summary") or {})
    lines = [
        "# Stage 6 Operator Handoff Report",
        "",
        "## Combined Assessment",
        f"- **Overall state:** `{combined.get('overall_state') or 'unknown'}`",
        f"- **Summary:** {combined.get('summary') or 'No summary available.'}",
        f"- **Readiness state:** `{combined.get('readiness_state') or 'unknown'}`",
        f"- **Timeline state:** `{combined.get('timeline_state') or 'none'}`",
        (
            "- **Timeline progress verdict:** "
            f"`{combined.get('timeline_progress_verdict') or 'none'}`"
        ),
        (
            "- **Timeline stagnation verdict:** "
            f"`{combined.get('timeline_stagnation_verdict') or 'none'}`"
        ),
    ]
    timeline_urgency = combined.get("timeline_urgency")
    if timeline_urgency:
        lines.append(f"- **Timeline urgency:** `{timeline_urgency}`")
    timeline_consecutive_count = combined.get("timeline_consecutive_count")
    timeline_stagnation_threshold = combined.get("timeline_stagnation_threshold")
    if timeline_consecutive_count is not None and timeline_stagnation_threshold is not None:
        lines.append(
            "- **Timeline stagnation window:** "
            f"`{timeline_consecutive_count}/{timeline_stagnation_threshold}`"
        )
    latest_state_elapsed_human = state_dwell_summary.get(
        "latest_state_elapsed_human_since_first_seen"
    )
    if latest_state_elapsed_human:
        lines.append(f"- **Timeline current state elapsed:** {latest_state_elapsed_human}")
    timeline_progress_detail = dict(combined.get("timeline_progress_detail") or {})
    if timeline_progress_detail.get("label"):
        lines.append(
            f"- **Timeline progress label:** {timeline_progress_detail.get('label')}"
        )
    if timeline_progress_detail.get("operator_implication"):
        lines.append(
            "- **Timeline progress implication:** "
            f"{timeline_progress_detail.get('operator_implication')}"
        )
    timeline_stagnation_detail = dict(combined.get("timeline_stagnation_detail") or {})
    if timeline_stagnation_detail.get("label"):
        lines.append(
            f"- **Timeline stagnation label:** {timeline_stagnation_detail.get('label')}"
        )
    if timeline_stagnation_detail.get("operator_implication"):
        lines.append(
            "- **Timeline stagnation implication:** "
            f"{timeline_stagnation_detail.get('operator_implication')}"
        )
    timeline_guidance_detail = dict(combined.get("timeline_guidance_detail") or {})
    if timeline_guidance_detail.get("label"):
        lines.append(
            f"- **Timeline guidance label:** {timeline_guidance_detail.get('label')}"
        )
    if timeline_guidance_detail.get("operator_implication"):
        lines.append(
            "- **Timeline guidance implication:** "
            f"{timeline_guidance_detail.get('operator_implication')}"
        )
    escalation_trigger = (
        timeline_guidance_detail.get("escalation_trigger")
        or timeline_stagnation_detail.get("escalation_trigger")
        or timeline_progress_detail.get("escalation_trigger")
    )
    if escalation_trigger:
        lines.append(f"- **Timeline escalate-if:** {escalation_trigger}")
    if record_timeline_preview:
        lines.append(
            "- **Record timeline preview:** "
            f"`{record_timeline_preview.get('diagnosis_state') or 'unknown'}`"
        )

    primary_blocker = combined.get("primary_blocker")
    if primary_blocker:
        lines.append(f"- **Primary blocker:** {primary_blocker}")

    actions = list(combined.get("next_actions") or [])
    action_detail_map = _action_details_by_action(
        list(combined.get("next_action_details") or [])
    )
    if actions:
        lines.extend(["", "## Combined Next Actions"])
        for action in actions:
            lines.append(f"1. {action}")
            detail = action_detail_map.get(action) or {}
            if detail.get("label"):
                lines.append(f"   - **Label:** {detail.get('label')}")
            if detail.get("when_to_run"):
                lines.append(f"   - **When:** {detail.get('when_to_run')}")
            if detail.get("reason"):
                lines.append(f"   - **Why now:** {detail.get('reason')}")
            related_summary = _related_command_summary(
                list(detail.get("related_commands") or [])
            )
            if related_summary:
                lines.append(f"   - **Related:** {related_summary}")
    primary_corrective_commands = list(combined.get("primary_corrective_commands") or [])
    supporting_corrective_commands = list(combined.get("supporting_corrective_commands") or [])
    corrective_commands = list(combined.get("corrective_commands") or [])
    monitoring_commands = list(combined.get("monitoring_commands") or [])
    follow_up_commands = list(combined.get("follow_up_commands") or [])
    primary_detail_map = _command_details_by_command(
        list(combined.get("primary_corrective_command_details") or [])
    )
    supporting_detail_map = _command_details_by_command(
        list(combined.get("supporting_corrective_command_details") or [])
    )
    monitoring_detail_map = _command_details_by_command(
        list(combined.get("monitoring_command_details") or [])
    )
    if primary_corrective_commands:
        lines.extend(["", "## Primary Corrective Commands"])
        for command in primary_corrective_commands:
            detail = primary_detail_map.get(command) or {}
            if detail.get("label"):
                lines.append(f"- **Label:** {detail.get('label')}")
            lines.extend(["```powershell", command, "```"])
            if detail.get("reason"):
                lines.append(f"  - Why now: {detail.get('reason')}")
    elif follow_up_commands:
        lines.extend(["", "## Combined Follow-up Commands"])
        for command in follow_up_commands:
            lines.extend(["```powershell", command, "```"])
    if supporting_corrective_commands:
        lines.extend(["", "## Supporting Corrective Commands"])
        for command in supporting_corrective_commands:
            detail = supporting_detail_map.get(command) or {}
            if detail.get("label"):
                lines.append(f"- **Label:** {detail.get('label')}")
            lines.extend(["```powershell", command, "```"])
            if detail.get("reason"):
                lines.append(f"  - Why now: {detail.get('reason')}")
    if monitoring_commands:
        lines.extend(["", "## Monitoring Commands"])
        for command in monitoring_commands:
            detail = monitoring_detail_map.get(command) or {}
            if detail.get("label"):
                lines.append(f"- **Label:** {detail.get('label')}")
            lines.extend(["```powershell", command, "```"])
            if detail.get("reason"):
                lines.append(f"  - Why now: {detail.get('reason')}")

    appended_snapshot = dict(result.get("appended_snapshot") or {})
    if appended_snapshot:
        lines.extend(
            [
                "",
                "## Appended Snapshot",
                (
                    f"- **Observed at UTC:** "
                    f"`{appended_snapshot.get('observed_at_utc') or 'unknown'}`"
                ),
                (
                    f"- **Diagnosis state:** "
                    f"`{appended_snapshot.get('diagnosis_state') or 'unknown'}`"
                ),
            ]
        )

    recent_snapshot_digest = list(result.get("recent_snapshot_digest") or [])
    recent_delta_detail_map = _recent_delta_details_by_observed_at(
        list(result.get("recent_snapshot_delta_details") or [])
    )
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
            detail = recent_delta_detail_map.get(str(item.get("observed_at_utc") or "")) or {}
            if detail.get("label"):
                lines.append(f"  - Delta label: {detail.get('label')}")
            if detail.get("operator_implication"):
                lines.append(f"  - Implication: {detail.get('operator_implication')}")
            if detail.get("escalation_trigger"):
                lines.append(f"  - Escalate if: {detail.get('escalation_trigger')}")

    lines.extend(["", format_stage6_readiness_markdown(dict(result.get("readiness") or {}))])

    timeline_value = result.get("timeline")
    if timeline_value is not None:
        lines.extend(
            [
                "",
                "## Timeline Report",
                "",
                format_stage6_snapshot_timeline_card(timeline_result),
                "",
                "### Timeline Summary",
                "```text",
                format_stage6_snapshot_timeline_summary(timeline_result),
                "```",
            ]
        )
    else:
        lines.extend(["", "## Timeline Report", "", "No snapshot timeline was supplied."])

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=_default_history_db())
    parser.add_argument("--logs", type=Path, default=_default_logs_dir())
    parser.add_argument("--timestamp-from", type=str, default=None)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--long-recording-cloud-candidates-only", action="store_true")
    parser.add_argument("--snapshots", type=Path, default=None)
    parser.add_argument("--append-snapshot", action="store_true")
    parser.add_argument("--recent-limit", type=int, default=5)
    parser.add_argument("--brief", action="store_true")
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--card", action="store_true")
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()

    result = inspect_transcription_stage6_handoff(
        db_path=args.db,
        logs_path=args.logs,
        timestamp_from=args.timestamp_from,
        limit=args.limit,
        long_recording_cloud_candidates_only=args.long_recording_cloud_candidates_only,
        snapshot_path=args.snapshots,
        append_snapshot=args.append_snapshot,
        recent_limit=args.recent_limit,
    )
    if args.brief:
        print(format_stage6_handoff_brief(result))
    elif args.compare:
        print(format_stage6_handoff_compare(result))
    elif args.card:
        print(format_stage6_handoff_card(result))
    elif args.markdown:
        print(format_stage6_handoff_markdown(result))
    elif args.summary:
        print(format_stage6_handoff_summary(result))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
