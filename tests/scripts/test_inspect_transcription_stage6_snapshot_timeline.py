import importlib.util
import sys
from pathlib import Path
from uuid import uuid4


def _load_module():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "inspect_transcription_stage6_snapshot_timeline.py"
    )
    scripts_dir = str(module_path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(
        "inspect_transcription_stage6_snapshot_timeline", module_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_snapshots(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_stage6_snapshot_timeline_reports_latest_state_and_transitions() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = (
        base_dir / "snapshots" / f"stage6_timeline_{uuid4().hex}.jsonl"
    ).resolve()
    try:
        _write_snapshots(
            snapshot_path,
            [
                (
                    '{"observed_at_utc":"2026-06-10T09:00:00Z",'
                    '"diagnosis_state":"waiting_for_new_build_session",'
                    '"alignment_state":"no_post_cutoff_runtime_or_db_activity",'
                    '"issue_summary":null,'
                    '"oneline":"state=waiting_for_new_build_session"}'
                ),
                (
                    '{"observed_at_utc":"2026-06-10T09:10:00Z",'
                    '"diagnosis_state":"new_build_seen_db_not_migrated",'
                    '"alignment_state":"no_post_cutoff_runtime_or_db_activity",'
                    '"issue_summary":null,'
                    '"oneline":"state=new_build_seen_db_not_migrated"}'
                ),
                (
                    '{"observed_at_utc":"2026-06-10T09:20:00Z",'
                    '"diagnosis_state":"stage6_ready_and_aligned",'
                    '"alignment_state":"db_log_paths_and_reasons_aligned",'
                    '"issue_summary":"record_id=rec-1 aligned: path=cloud_file_long_recording, decision_reason=long_cloud_recording_prefer_file",'
                    '"newest_record_id_hint":"rec-1",'
                    '"oneline":"state=stage6_ready_and_aligned"}'
                ),
            ],
        )

        result = module.inspect_stage6_snapshot_timeline(snapshot_path)

        assert result["snapshot_count"] == 3
        assert result["first_observed_at_utc"] == "2026-06-10T09:00:00Z"
        assert result["latest_observed_at_utc"] == "2026-06-10T09:20:00Z"
        assert result["latest_diagnosis_state"] == "stage6_ready_and_aligned"
        assert result["latest_alignment_state"] == "db_log_paths_and_reasons_aligned"
        assert result["aligned_checkpoint"] == {
            "ever_reached_aligned": True,
            "first_reached_aligned_at_utc": "2026-06-10T09:20:00Z",
            "latest_reached_aligned_at_utc": "2026-06-10T09:20:00Z",
            "aligned_snapshot_count": 1,
        }
        assert result["milestone_overview"] == {
            "ever_seen_new_build": True,
            "first_new_build_seen_at_utc": "2026-06-10T09:10:00Z",
            "ever_reached_schema_ready": True,
            "first_schema_ready_at_utc": "2026-06-10T09:20:00Z",
            "ever_reached_aligned": True,
            "first_aligned_at_utc": "2026-06-10T09:20:00Z",
            "latest_aligned_at_utc": "2026-06-10T09:20:00Z",
        }
        assert result["first_seen_by_diagnosis_state"] == {
            "waiting_for_new_build_session": "2026-06-10T09:00:00Z",
            "new_build_seen_db_not_migrated": "2026-06-10T09:10:00Z",
            "stage6_ready_and_aligned": "2026-06-10T09:20:00Z",
        }
        assert result["latest_state_first_seen_at_utc"] == "2026-06-10T09:20:00Z"
        assert result["latest_state_snapshot_count"] == 1
        assert result["current_state_consecutive_count"] == 1
        assert result["state_transition_count"] == 2
        assert result["latest_transition_summary"] == (
            "new_build_seen_db_not_migrated -> stage6_ready_and_aligned "
            "at 2026-06-10T09:20:00Z"
        )
        assert result["recent_snapshot_limit"] == 5
        assert len(result["recent_snapshot_digest"]) == 3
        assert (
            result["recent_snapshot_digest"][0]["diagnosis_state"]
            == "stage6_ready_and_aligned"
        )
        assert (
            result["recent_snapshot_digest"][0]["transition_summary"]
            == "new_build_seen_db_not_migrated -> stage6_ready_and_aligned"
        )
        assert (
            result["recent_snapshot_digest"][0]["elapsed_since_previous_seconds"] == 600
        )
        assert (
            result["recent_snapshot_digest"][0]["elapsed_since_previous_human"]
            == "10m 0s"
        )
        assert result["state_dwell_summary"]["seconds_by_state"] == {
            "waiting_for_new_build_session": 600,
            "new_build_seen_db_not_migrated": 600,
        }
        assert (
            result["state_dwell_summary"]["latest_state_elapsed_human_since_first_seen"]
            == "0s"
        )
        assert result["progress_assessment"]["verdict"] == "advanced"
        assert (
            result["progress_assessment"]["message"]
            == "Diagnosis state advanced from new_build_seen_db_not_migrated to stage6_ready_and_aligned."
        )
        assert result["stagnation_assessment"]["verdict"] == "not_stuck"
        assert result["operator_guidance"]["urgency"] == "normal"
        assert (
            result["operator_guidance"]["summary"]
            == "Stage 6 is aligned for the latest sampled evidence."
        )
        assert result["operator_guidance"]["actions"][0].startswith(
            "Progress improved relative to the previous snapshot"
        )
        assert result["unique_diagnosis_states_in_order"] == [
            "waiting_for_new_build_session",
            "new_build_seen_db_not_migrated",
            "stage6_ready_and_aligned",
        ]
        assert (
            result["state_transitions"][0]["from_state"]
            == "waiting_for_new_build_session"
        )
        assert (
            result["state_transitions"][0]["to_state"]
            == "new_build_seen_db_not_migrated"
        )
        assert result["latest_oneline"] == "state=stage6_ready_and_aligned"

        summary = module.format_stage6_snapshot_timeline_summary(result)
        assert "Stage 6 Snapshot Timeline Summary" in summary
        assert "Snapshot count: 3" in summary
        assert "Latest diagnosis state: stage6_ready_and_aligned" in summary
        assert (
            "Diagnosis states seen: waiting_for_new_build_session, "
            "new_build_seen_db_not_migrated, stage6_ready_and_aligned"
        ) in summary
        assert "Ever seen new build: yes" in summary
        assert "First seen new build at UTC: 2026-06-10T09:10:00Z" in summary
        assert "Ever reached schema ready: yes" in summary
        assert "First reached schema ready at UTC: 2026-06-10T09:20:00Z" in summary
        assert "Ever reached aligned: yes" in summary
        assert "First reached aligned at UTC: 2026-06-10T09:20:00Z" in summary
        assert "Aligned snapshot count: 1" in summary
        assert "State transition count: 2" in summary
        assert "Current state first seen at UTC: 2026-06-10T09:20:00Z" in summary
        assert "Current state snapshot count: 1" in summary
        assert "Current state consecutive snapshots: 1" in summary
        assert "Current state elapsed since first seen: 0s" in summary
        assert "Progress verdict: advanced" in summary
        assert (
            "Progress message: Diagnosis state advanced from "
            "new_build_seen_db_not_migrated to stage6_ready_and_aligned."
        ) in summary
        assert "Stagnation verdict: not_stuck" in summary
        assert "Operator urgency: normal" in summary
        assert (
            "Operator guidance: Stage 6 is aligned for the latest sampled evidence."
            in summary
        )
        assert (
            "Latest issue summary: record_id=rec-1 aligned: path=cloud_file_long_recording, "
            "decision_reason=long_cloud_recording_prefer_file"
        ) in summary
        assert (
            "Latest transition: new_build_seen_db_not_migrated -> "
            "stage6_ready_and_aligned at 2026-06-10T09:20:00Z"
        ) in summary
        assert "Recent Snapshot Deltas:" in summary
        assert (
            "2026-06-10T09:20:00Z | state=stage6_ready_and_aligned | "
            "delta=new_build_seen_db_not_migrated -> stage6_ready_and_aligned"
        ) in summary
        assert "elapsed_since_previous=10m 0s" in summary
        assert "Recommended Actions:" in summary
        assert (
            "waiting_for_new_build_session -> new_build_seen_db_not_migrated" in summary
        )

        brief = module.format_stage6_snapshot_timeline_brief(result)
        assert "Stage 6 Timeline Brief" in brief
        assert "Current state elapsed: 0s" in brief
        assert "Previous diagnosis: new_build_seen_db_not_migrated" in brief
        assert "Progress: advanced" in brief
        assert (
            "Latest transition: new_build_seen_db_not_migrated -> "
            "stage6_ready_and_aligned at 2026-06-10T09:20:00Z"
        ) in brief
        assert "- Recent deltas:" in brief
        assert "elapsed_since_previous=10m 0s" in brief

        compare = module.format_stage6_snapshot_timeline_compare(result)
        assert "Stage 6 Timeline Compare" in compare
        assert "Current state elapsed: 0s" in compare
        assert "Latest diagnosis: stage6_ready_and_aligned" in compare
        assert "Previous diagnosis: new_build_seen_db_not_migrated" in compare
        assert "Delta verdict: advanced" in compare
        assert "Latest Snapshot:" in compare
        assert "Previous Snapshot:" in compare
        assert "Elapsed since previous snapshot: 10m 0s" in compare

        markdown = module.format_stage6_snapshot_timeline_markdown(result)
        assert "# Stage 6 Snapshot Timeline Report" in markdown
        assert "## Current State" in markdown
        assert "## Milestones" in markdown
        assert "## Progress Assessment" in markdown
        assert "- **Current state elapsed since first seen:** `0s`" in markdown
        assert "## Operator Guidance" in markdown
        assert "### Recommended Actions" in markdown
        assert "## Recent Snapshot Deltas" in markdown
        assert "Elapsed since previous: 10m 0s" in markdown
        assert "## State Transitions" in markdown
        assert "## Latest Oneline" in markdown

        table = module.format_stage6_snapshot_timeline_table(result)
        assert "Stage 6 Timeline Recent Snapshot Table" in table
        assert "observed_at_utc" in table
        assert "diagnosis_state" in table
        assert "alignment_state" in table
        assert "elapsed" in table
        assert "delta" in table
        assert "stage6_ready_and_aligned" in table
        assert "10m 0s" in table
        assert "new_build_seen_db_not_migrated ->" in table
        tsv = module.format_stage6_snapshot_timeline_tsv(result)
        assert (
            "observed_at_utc\tdiagnosis_state\talignment_state\tprevious_diagnosis_state\telapsed_since_previous\tdelta\tissue_summary"
            in tsv
        )
        assert "2026-06-10T09:20:00Z\tstage6_ready_and_aligned\t" in tsv
        assert (
            "\tnew_build_seen_db_not_migrated\t10m 0s\tnew_build_seen_db_not_migrated -> stage6_ready_and_aligned\t"
            in tsv
        )

        card = module.format_stage6_snapshot_timeline_card(result)
        assert "## Stage 6 Status Card" in card
        assert "- **Latest diagnosis:** `stage6_ready_and_aligned`" in card
        assert "- **Latest alignment:** `db_log_paths_and_reasons_aligned`" in card
        assert "- **Observed at UTC:** `2026-06-10T09:20:00Z`" in card
        assert "- **Progress:** `advanced`" in card
        assert "- **Stagnation:** `not_stuck` (1 consecutive / threshold 3)" in card
        assert (
            "- **Milestones:** new build yes · schema ready yes · aligned yes" in card
        )
        assert (
            "- **Guidance:** Stage 6 is aligned for the latest sampled evidence."
        ) in card
        assert (
            "- **Latest issue:** record_id=rec-1 aligned: path=cloud_file_long_recording, "
            "decision_reason=long_cloud_recording_prefer_file"
        ) in card
        assert (
            "- **Latest transition:** new_build_seen_db_not_migrated -> "
            "stage6_ready_and_aligned at 2026-06-10T09:20:00Z"
        ) in card
        assert "- **First new build seen at UTC:** `2026-06-10T09:10:00Z`" in card
        assert "- **First schema ready at UTC:** `2026-06-10T09:20:00Z`" in card
        assert "- **First aligned at UTC:** `2026-06-10T09:20:00Z`" in card
        assert "- **Next actions:**" in card
    finally:
        if snapshot_path.exists():
            snapshot_path.unlink()
        if snapshot_path.parent.exists() and not any(snapshot_path.parent.iterdir()):
            snapshot_path.parent.rmdir()


def test_stage6_snapshot_timeline_collapses_repeated_states() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = (
        base_dir / "snapshots" / f"stage6_timeline_repeat_{uuid4().hex}.jsonl"
    ).resolve()
    try:
        _write_snapshots(
            snapshot_path,
            [
                (
                    '{"observed_at_utc":"2026-06-10T09:00:00Z",'
                    '"diagnosis_state":"waiting_for_new_build_session",'
                    '"alignment_state":"no_post_cutoff_runtime_or_db_activity",'
                    '"issue_summary":null,'
                    '"oneline":"state=waiting_for_new_build_session"}'
                ),
                (
                    '{"observed_at_utc":"2026-06-10T09:05:00Z",'
                    '"diagnosis_state":"waiting_for_new_build_session",'
                    '"alignment_state":"no_post_cutoff_runtime_or_db_activity",'
                    '"issue_summary":null,'
                    '"oneline":"state=waiting_for_new_build_session"}'
                ),
            ],
        )

        result = module.inspect_stage6_snapshot_timeline(snapshot_path)

        assert result["snapshot_count"] == 2
        assert result["unique_diagnosis_states_in_order"] == [
            "waiting_for_new_build_session"
        ]
        assert result["aligned_checkpoint"] == {
            "ever_reached_aligned": False,
            "first_reached_aligned_at_utc": None,
            "latest_reached_aligned_at_utc": None,
            "aligned_snapshot_count": 0,
        }
        assert result["milestone_overview"] == {
            "ever_seen_new_build": False,
            "first_new_build_seen_at_utc": None,
            "ever_reached_schema_ready": False,
            "first_schema_ready_at_utc": None,
            "ever_reached_aligned": False,
            "first_aligned_at_utc": None,
            "latest_aligned_at_utc": None,
        }
        assert result["state_transition_count"] == 0
        assert result["latest_state_first_seen_at_utc"] == "2026-06-10T09:00:00Z"
        assert result["latest_state_snapshot_count"] == 2
        assert result["current_state_consecutive_count"] == 2
        assert len(result["recent_snapshot_digest"]) == 2
        assert result["recent_snapshot_digest"][0]["delta_kind"] == "unchanged"
        assert (
            result["recent_snapshot_digest"][0]["elapsed_since_previous_human"]
            == "5m 0s"
        )
        assert result["state_dwell_summary"]["seconds_by_state"] == {
            "waiting_for_new_build_session": 300
        }
        assert (
            result["state_dwell_summary"]["latest_state_elapsed_human_since_first_seen"]
            == "5m 0s"
        )
        assert result["progress_assessment"]["verdict"] == "unchanged"
        assert result["stagnation_assessment"]["verdict"] == "not_stuck"
        assert result["operator_guidance"]["urgency"] == "normal"
        assert (
            result["operator_guidance"]["summary"]
            == "Still waiting for a newer app build session that declares the current history schema expectations."
        )

        summary = module.format_stage6_snapshot_timeline_summary(result)
        assert "State transition count: 0" in summary
        assert "Ever seen new build: no" in summary
        assert "Ever reached schema ready: no" in summary
        assert "Ever reached aligned: no" in summary
        assert "Current state snapshot count: 2" in summary
        assert "Current state consecutive snapshots: 2" in summary
        assert "Current state elapsed since first seen: 5m 0s" in summary
        assert "Progress verdict: unchanged" in summary
        assert "Stagnation verdict: not_stuck" in summary
        assert (
            "Operator guidance: Still waiting for a newer app build session" in summary
        )

        compare = module.format_stage6_snapshot_timeline_compare(result)
        assert "Previous Snapshot:" in compare
        assert "2026-06-10T09:00:00Z | state=waiting_for_new_build_session" in compare
        assert "Elapsed since previous snapshot: 5m 0s" in compare

        markdown = module.format_stage6_snapshot_timeline_markdown(result)
        assert "# Stage 6 Snapshot Timeline Report" in markdown
        assert "- **Ever seen new build:** no" in markdown
        table = module.format_stage6_snapshot_timeline_table(result)
        assert "waiting_for_new_build_session" in table
        assert "5m 0s" in table
        assert "unchanged" in table
        tsv = module.format_stage6_snapshot_timeline_tsv(result)
        assert (
            "waiting_for_new_build_session\tno_post_cutoff_runtime_or_db_activity\twaiting_for_new_build_session\t5m 0s\tunchanged"
            in tsv
        )

        card = module.format_stage6_snapshot_timeline_card(result)
        assert "- **Latest diagnosis:** `waiting_for_new_build_session`" in card
        assert "- **Milestones:** new build no · schema ready no · aligned no" in card
        assert (
            "- **Guidance:** Still waiting for a newer app build session that declares the current history schema expectations."
        ) in card
        assert "- **First new build seen at UTC:**" not in card
    finally:
        if snapshot_path.exists():
            snapshot_path.unlink()
        if snapshot_path.parent.exists() and not any(snapshot_path.parent.iterdir()):
            snapshot_path.parent.rmdir()


def test_stage6_snapshot_timeline_detects_lateral_change() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = (
        base_dir / "snapshots" / f"stage6_timeline_lateral_{uuid4().hex}.jsonl"
    ).resolve()
    try:
        _write_snapshots(
            snapshot_path,
            [
                (
                    '{"observed_at_utc":"2026-06-10T09:00:00Z",'
                    '"diagnosis_state":"post_cutoff_path_mismatch",'
                    '"alignment_state":"db_log_path_mismatch",'
                    '"issue_summary":"record_id=rec-1 path mismatch",'
                    '"newest_record_id_hint":"rec-1",'
                    '"oneline":"state=post_cutoff_path_mismatch"}'
                ),
                (
                    '{"observed_at_utc":"2026-06-10T09:05:00Z",'
                    '"diagnosis_state":"post_cutoff_reason_mismatch",'
                    '"alignment_state":"db_log_decision_reason_mismatch",'
                    '"issue_summary":"record_id=rec-1 reason mismatch",'
                    '"newest_record_id_hint":"rec-1",'
                    '"oneline":"state=post_cutoff_reason_mismatch"}'
                ),
            ],
        )

        result = module.inspect_stage6_snapshot_timeline(snapshot_path)

        assert result["state_transition_count"] == 1
        assert result["latest_transition_summary"] == (
            "post_cutoff_path_mismatch -> post_cutoff_reason_mismatch "
            "at 2026-06-10T09:05:00Z"
        )
        assert result["recent_snapshot_digest"][0]["transition_summary"] == (
            "post_cutoff_path_mismatch -> post_cutoff_reason_mismatch"
        )
        assert (
            result["recent_snapshot_digest"][0]["elapsed_since_previous_human"]
            == "5m 0s"
        )
        assert result["progress_assessment"]["verdict"] == "lateral_change"
        assert (
            result["progress_assessment"]["message"]
            == "Diagnosis state changed laterally from post_cutoff_path_mismatch to "
            "post_cutoff_reason_mismatch at the same progress tier."
        )
        assert result["operator_guidance"]["urgency"] == "normal"
        assert (
            result["operator_guidance"]["summary"]
            == "A post-cutoff mismatch remains between persisted DB evidence and runtime logs."
        )
        assert "record_id rec-1" in " ".join(result["operator_guidance"]["actions"])

        summary = module.format_stage6_snapshot_timeline_summary(result)
        assert "Progress verdict: lateral_change" in summary
        assert (
            "Latest transition: post_cutoff_path_mismatch -> "
            "post_cutoff_reason_mismatch at 2026-06-10T09:05:00Z"
        ) in summary
        assert "Operator guidance: A post-cutoff mismatch remains" in summary

        brief = module.format_stage6_snapshot_timeline_brief(result)
        assert "Progress: lateral_change" in brief
        compare = module.format_stage6_snapshot_timeline_compare(result)
        assert "Delta verdict: lateral_change" in compare
        markdown = module.format_stage6_snapshot_timeline_markdown(result)
        assert "- **Latest issue:** record_id=rec-1 reason mismatch" in markdown
        table = module.format_stage6_snapshot_timeline_table(result)
        assert "post_cutoff_reason_mismatch" in table
        assert "5m 0s" in table
        assert "post_cutoff_path_mismatch ->" in table
        tsv = module.format_stage6_snapshot_timeline_tsv(result)
        assert "post_cutoff_path_mismatch -> post_cutoff_reason_mismatch" in tsv
        assert (
            "\tpost_cutoff_path_mismatch\t5m 0s\tpost_cutoff_path_mismatch -> post_cutoff_reason_mismatch\t"
            in tsv
        )

        card = module.format_stage6_snapshot_timeline_card(result)
        assert "- **Progress:** `lateral_change`" in card
        assert "- **Milestones:** new build yes · schema ready yes · aligned no" in card
        assert ("- **Latest issue:** record_id=rec-1 reason mismatch") in card
        assert (
            "- **Latest transition:** post_cutoff_path_mismatch -> "
            "post_cutoff_reason_mismatch at 2026-06-10T09:05:00Z"
        ) in card
    finally:
        if snapshot_path.exists():
            snapshot_path.unlink()
        if snapshot_path.parent.exists() and not any(snapshot_path.parent.iterdir()):
            snapshot_path.parent.rmdir()


def test_stage6_snapshot_timeline_flags_stuck_state_after_threshold() -> None:
    module = _load_module()
    base_dir = Path("quality_audit")
    base_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = (
        base_dir / "snapshots" / f"stage6_timeline_stuck_{uuid4().hex}.jsonl"
    ).resolve()
    try:
        _write_snapshots(
            snapshot_path,
            [
                (
                    '{"observed_at_utc":"2026-06-10T09:00:00Z",'
                    '"diagnosis_state":"waiting_for_new_build_session",'
                    '"alignment_state":"no_post_cutoff_runtime_or_db_activity",'
                    '"issue_summary":null,'
                    '"oneline":"state=waiting_for_new_build_session"}'
                ),
                (
                    '{"observed_at_utc":"2026-06-10T09:05:00Z",'
                    '"diagnosis_state":"waiting_for_new_build_session",'
                    '"alignment_state":"no_post_cutoff_runtime_or_db_activity",'
                    '"issue_summary":null,'
                    '"oneline":"state=waiting_for_new_build_session"}'
                ),
                (
                    '{"observed_at_utc":"2026-06-10T09:10:00Z",'
                    '"diagnosis_state":"waiting_for_new_build_session",'
                    '"alignment_state":"no_post_cutoff_runtime_or_db_activity",'
                    '"issue_summary":null,'
                    '"oneline":"state=waiting_for_new_build_session"}'
                ),
            ],
        )

        result = module.inspect_stage6_snapshot_timeline(snapshot_path)

        assert result["current_state_consecutive_count"] == 3
        assert result["stagnation_assessment"]["verdict"] == "stuck"
        assert (
            result["stagnation_assessment"]["message"]
            == "Current state waiting_for_new_build_session has repeated for 3 consecutive snapshots."
        )
        assert result["operator_guidance"]["urgency"] == "attention"
        assert result["operator_guidance"]["actions"][0].startswith(
            "This state has repeated enough times to be treated as stuck"
        )

        summary = module.format_stage6_snapshot_timeline_summary(result)
        assert "Current state consecutive snapshots: 3" in summary
        assert "Stagnation verdict: stuck" in summary
        assert (
            "Stagnation message: Current state waiting_for_new_build_session "
            "has repeated for 3 consecutive snapshots."
        ) in summary
        assert "Operator urgency: attention" in summary

        brief = module.format_stage6_snapshot_timeline_brief(result)
        assert "Stagnation: stuck" in brief
        compare = module.format_stage6_snapshot_timeline_compare(result)
        assert "Delta verdict: unchanged" in compare
        markdown = module.format_stage6_snapshot_timeline_markdown(result)
        assert "- **Stagnation verdict:** `stuck`" in markdown
        table = module.format_stage6_snapshot_timeline_table(result)
        assert "waiting_for_new_build_session" in table
        assert "5m 0s" in table
        tsv = module.format_stage6_snapshot_timeline_tsv(result)
        assert (
            "\twaiting_for_new_build_session\tno_post_cutoff_runtime_or_db_activity\twaiting_for_new_build_session\t5m 0s\tunchanged\t"
            in tsv
        )

        card = module.format_stage6_snapshot_timeline_card(result)
        assert "- **Stagnation:** `stuck` (3 consecutive / threshold 3)" in card
        assert "- **Milestones:** new build no · schema ready no · aligned no" in card
        assert "- **Next actions:**" in card
    finally:
        if snapshot_path.exists():
            snapshot_path.unlink()
        if snapshot_path.parent.exists() and not any(snapshot_path.parent.iterdir()):
            snapshot_path.parent.rmdir()
