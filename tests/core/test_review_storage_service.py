import json
from pathlib import Path
from uuid import uuid4
from unittest.mock import Mock

from sonicinput.core.quality import ReviewSuggestion
from sonicinput.core.services.ui_services import UISettingsService
from sonicinput.core.services.storage import ReviewStorageService


def _db_path() -> Path:
    path = Path("quality_audit") / f"test_review_storage_{uuid4().hex}.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def test_review_storage_service_saves_pending_suggestions():
    db_path = _db_path()
    service = ReviewStorageService(db_path)
    suggestion = ReviewSuggestion(
        suggestion_id="review_test_1",
        suggestion_type="bad_ai_output_alert",
        confidence=0.9,
        risk_level="high",
        source_record_ids=("r1",),
        title="AI 输出可能越界",
        detail="validator hit",
        evidence_count=1,
    )

    job_id = service.save_review_run(
        [suggestion],
        record_limit=20,
        reviewed_count=10,
    )
    pending = service.list_pending_suggestions()

    assert job_id.startswith("review_job_")
    assert len(pending) == 1
    assert pending[0]["suggestion_id"] == "review_test_1"
    assert pending[0]["source_record_ids"] == ["r1"]

    jobs = service.list_review_jobs()
    assert len(jobs) == 1
    assert jobs[0]["id"] == job_id
    assert jobs[0]["record_limit"] == 20
    assert jobs[0]["reviewed_count"] == 10
    assert jobs[0]["suggestion_count"] == 1


def test_review_storage_service_records_decision():
    db_path = _db_path()
    service = ReviewStorageService(db_path)
    suggestion = ReviewSuggestion(
        suggestion_id="review_test_2",
        suggestion_type="lexicon_candidate",
        confidence=0.75,
        risk_level="medium",
        source_record_ids=("r1", "r2"),
        title="候选术语：PyTorch",
        detail="term candidate",
        evidence_count=2,
        new_form="PyTorch",
    )
    service.save_review_run([suggestion], record_limit=20, reviewed_count=2)

    service.record_decision("review_test_2", "accepted", note="looks good")

    assert service.list_pending_suggestions() == []


def test_review_storage_service_prioritizes_high_risk_alerts_before_lexicon():
    db_path = _db_path()
    service = ReviewStorageService(db_path)
    suggestions = [
        ReviewSuggestion(
            suggestion_id="review_medium_lexicon",
            suggestion_type="lexicon_candidate",
            confidence=0.95,
            risk_level="medium",
            source_record_ids=("r1", "r2", "r3", "r4"),
            title="候选术语：Chrome",
            detail="term candidate",
            evidence_count=4,
            new_form="Chrome",
        ),
        ReviewSuggestion(
            suggestion_id="review_high_alert",
            suggestion_type="bad_ai_output_alert",
            confidence=0.8,
            risk_level="high",
            source_record_ids=("r5",),
            title="AI 输出可能越界",
            detail="validator hit",
            evidence_count=1,
        ),
        ReviewSuggestion(
            suggestion_id="review_medium_alert",
            suggestion_type="format_pollution_alert",
            confidence=0.9,
            risk_level="medium",
            source_record_ids=("r6",),
            title="AI 输出疑似格式污染",
            detail="markdown leaked",
            evidence_count=1,
        ),
    ]

    service.save_review_run(suggestions, record_limit=20, reviewed_count=6)
    pending = service.list_pending_suggestions()

    assert [item["suggestion_id"] for item in pending] == [
        "review_high_alert",
        "review_medium_alert",
        "review_medium_lexicon",
    ]


def test_review_storage_service_does_not_resurface_rejected_suggestion():
    db_path = _db_path()
    service = ReviewStorageService(db_path)
    suggestion = ReviewSuggestion(
        suggestion_id="review_test_rejected_once",
        suggestion_type="bad_ai_output_alert",
        confidence=0.9,
        risk_level="high",
        source_record_ids=("r1",),
        title="AI 输出可能越界",
        detail="validator hit",
        evidence_count=1,
    )

    service.save_review_run([suggestion], record_limit=20, reviewed_count=1)
    service.record_decision("review_test_rejected_once", "rejected")
    second_job_id = service.save_review_run(
        [suggestion],
        record_limit=20,
        reviewed_count=1,
    )

    jobs = service.list_review_jobs(limit=2)
    second_job = next(job for job in jobs if job["id"] == second_job_id)
    assert service.list_pending_suggestions() == []
    assert second_job["suggestion_count"] == 0


def test_review_storage_service_does_not_resurface_accepted_suggestion():
    db_path = _db_path()
    service = ReviewStorageService(db_path)
    suggestion = ReviewSuggestion(
        suggestion_id="review_test_accepted_once",
        suggestion_type="lexicon_candidate",
        confidence=0.8,
        risk_level="medium",
        source_record_ids=("r1", "r2"),
        title="候选术语：PyTorch",
        detail="term candidate",
        evidence_count=2,
        new_form="PyTorch",
    )

    service.save_review_run([suggestion], record_limit=20, reviewed_count=2)
    service.record_decision("review_test_accepted_once", "accepted")
    second_job_id = service.save_review_run(
        [suggestion],
        record_limit=20,
        reviewed_count=2,
    )

    jobs = service.list_review_jobs(limit=2)
    second_job = next(job for job in jobs if job["id"] == second_job_id)
    assert service.list_pending_suggestions() == []
    assert len(service.list_active_lexicon_entries()) == 1
    assert second_job["suggestion_count"] == 0


def test_review_storage_service_suppresses_similar_rejected_alert():
    db_path = _db_path()
    service = ReviewStorageService(db_path)
    original = ReviewSuggestion(
        suggestion_id="review_original_alert",
        suggestion_type="bad_ai_output_alert",
        confidence=0.9,
        risk_level="high",
        source_record_ids=("r1",),
        title="AI 输出可能越界",
        detail="validator hit A",
        evidence_count=1,
    )
    similar = ReviewSuggestion(
        suggestion_id="review_similar_alert_changed_title",
        suggestion_type="bad_ai_output_alert",
        confidence=0.88,
        risk_level="high",
        source_record_ids=("r1",),
        title="AI 清理可能失败",
        detail="validator hit B",
        evidence_count=1,
    )

    service.save_review_run([original], record_limit=20, reviewed_count=1)
    service.record_decision("review_original_alert", "rejected")
    second_job_id = service.save_review_run(
        [similar],
        record_limit=20,
        reviewed_count=1,
    )

    jobs = service.list_review_jobs(limit=2)
    second_job = next(job for job in jobs if job["id"] == second_job_id)
    assert service.list_pending_suggestions() == []
    assert second_job["suggestion_count"] == 0


def test_review_storage_service_suppresses_similar_rejected_lexicon_candidate():
    db_path = _db_path()
    service = ReviewStorageService(db_path)
    original = ReviewSuggestion(
        suggestion_id="review_original_lexicon",
        suggestion_type="lexicon_candidate",
        confidence=0.8,
        risk_level="medium",
        source_record_ids=("r1", "r2"),
        title="候选术语：PyTorch",
        detail="term candidate A",
        evidence_count=2,
        new_form="PyTorch",
    )
    similar = ReviewSuggestion(
        suggestion_id="review_similar_lexicon_new_sources",
        suggestion_type="lexicon_candidate",
        confidence=0.85,
        risk_level="medium",
        source_record_ids=("r3", "r4"),
        title="候选术语：pytorch",
        detail="term candidate B",
        evidence_count=2,
        new_form="pytorch",
    )

    service.save_review_run([original], record_limit=20, reviewed_count=2)
    service.record_decision("review_original_lexicon", "rejected")
    second_job_id = service.save_review_run(
        [similar],
        record_limit=20,
        reviewed_count=2,
    )

    jobs = service.list_review_jobs(limit=2)
    second_job = next(job for job in jobs if job["id"] == second_job_id)
    assert service.list_pending_suggestions() == []
    assert second_job["suggestion_count"] == 0


def test_review_storage_service_accepting_lexicon_candidate_creates_memory_entry():
    db_path = _db_path()
    service = ReviewStorageService(db_path)
    suggestion = ReviewSuggestion(
        suggestion_id="review_test_lexicon",
        suggestion_type="lexicon_candidate",
        confidence=0.8,
        risk_level="medium",
        source_record_ids=("r1", "r2"),
        title="候选术语：PyTorch",
        detail="term candidate",
        evidence_count=2,
        old_form="拍套曲",
        new_form="PyTorch",
    )
    service.save_review_run([suggestion], record_limit=20, reviewed_count=2)

    service.record_decision("review_test_lexicon", "accepted")

    entries = service.list_active_lexicon_entries()
    assert len(entries) == 1
    assert entries[0]["term"] == "PyTorch"
    assert entries[0]["old_form"] == "拍套曲"
    assert entries[0]["evidence_count"] == 2
    assert entries[0]["source_suggestion_id"] == "review_test_lexicon"


def test_review_storage_service_rejecting_lexicon_candidate_does_not_create_memory():
    db_path = _db_path()
    service = ReviewStorageService(db_path)
    suggestion = ReviewSuggestion(
        suggestion_id="review_test_reject_lexicon",
        suggestion_type="lexicon_candidate",
        confidence=0.8,
        risk_level="medium",
        source_record_ids=("r1", "r2"),
        title="候选术语：PyTorch",
        detail="term candidate",
        evidence_count=2,
        new_form="PyTorch",
    )
    service.save_review_run([suggestion], record_limit=20, reviewed_count=2)

    service.record_decision("review_test_reject_lexicon", "rejected")

    assert service.list_active_lexicon_entries() == []


def test_review_storage_service_can_clear_lexicon_entries():
    db_path = _db_path()
    service = ReviewStorageService(db_path)
    suggestion = ReviewSuggestion(
        suggestion_id="review_test_clear_lexicon",
        suggestion_type="lexicon_candidate",
        confidence=0.8,
        risk_level="medium",
        source_record_ids=("r1", "r2"),
        title="候选术语：PyTorch",
        detail="term candidate",
        evidence_count=2,
        new_form="PyTorch",
    )
    service.save_review_run([suggestion], record_limit=20, reviewed_count=2)
    service.record_decision("review_test_clear_lexicon", "accepted")

    service.clear_lexicon_entries()

    assert service.list_active_lexicon_entries() == []


def test_review_storage_service_can_clear_local_learning_data():
    db_path = _db_path()
    service = ReviewStorageService(db_path)
    lexicon = ReviewSuggestion(
        suggestion_id="review_learning_lexicon_original",
        suggestion_type="lexicon_candidate",
        confidence=0.8,
        risk_level="medium",
        source_record_ids=("r1", "r2"),
        title="候选术语：PyTorch",
        detail="term candidate",
        evidence_count=2,
        new_form="PyTorch",
    )
    ignored = ReviewSuggestion(
        suggestion_id="review_learning_ignored_original",
        suggestion_type="bad_ai_output_alert",
        confidence=0.9,
        risk_level="high",
        source_record_ids=("r3",),
        title="AI 输出可能越界",
        detail="validator hit",
        evidence_count=1,
    )
    service.save_review_run([lexicon, ignored], record_limit=20, reviewed_count=2)
    service.record_decision("review_learning_lexicon_original", "accepted")
    service.record_decision("review_learning_ignored_original", "ignored")

    service.clear_learning_data()

    assert service.list_active_lexicon_entries() == []

    resurfaced = [
        ReviewSuggestion(
            suggestion_id="review_learning_lexicon_resurfaced",
            suggestion_type="lexicon_candidate",
            confidence=0.8,
            risk_level="medium",
            source_record_ids=("r1", "r2"),
            title="候选术语：PyTorch",
            detail="term candidate",
            evidence_count=2,
            new_form="PyTorch",
        ),
        ReviewSuggestion(
            suggestion_id="review_learning_ignored_resurfaced",
            suggestion_type="bad_ai_output_alert",
            confidence=0.88,
            risk_level="high",
            source_record_ids=("r3",),
            title="AI 清理可能失败",
            detail="validator hit again",
            evidence_count=1,
        ),
    ]
    service.save_review_run(resurfaced, record_limit=20, reviewed_count=2)

    pending_ids = {
        item["suggestion_id"] for item in service.list_pending_suggestions(limit=10)
    }
    assert "review_learning_lexicon_resurfaced" in pending_ids
    assert "review_learning_ignored_resurfaced" in pending_ids


def test_review_storage_service_archived_suggestion_can_resurface():
    db_path = _db_path()
    service = ReviewStorageService(db_path)
    suggestion = ReviewSuggestion(
        suggestion_id="review_test_archived_once",
        suggestion_type="bad_ai_output_alert",
        confidence=0.9,
        risk_level="high",
        source_record_ids=("r1",),
        title="AI 输出可能越界",
        detail="validator hit",
        evidence_count=1,
    )

    service.save_review_run([suggestion], record_limit=20, reviewed_count=1)
    service.record_decision("review_test_archived_once", "archived")
    second_job_id = service.save_review_run(
        [suggestion],
        record_limit=20,
        reviewed_count=1,
    )

    jobs = service.list_review_jobs(limit=2)
    second_job = next(job for job in jobs if job["id"] == second_job_id)
    pending = service.list_pending_suggestions()
    assert len(pending) == 1
    assert pending[0]["suggestion_id"] == "review_test_archived_once"
    assert second_job["suggestion_count"] == 1


def test_review_storage_service_ignored_suggestion_suppresses_similar_suggestion():
    db_path = _db_path()
    service = ReviewStorageService(db_path)
    original = ReviewSuggestion(
        suggestion_id="review_original_ignored_alert",
        suggestion_type="bad_ai_output_alert",
        confidence=0.9,
        risk_level="high",
        source_record_ids=("r1",),
        title="AI 输出可能越界",
        detail="validator hit A",
        evidence_count=1,
    )
    similar = ReviewSuggestion(
        suggestion_id="review_similar_ignored_alert",
        suggestion_type="bad_ai_output_alert",
        confidence=0.88,
        risk_level="high",
        source_record_ids=("r1",),
        title="AI 清理可能失败",
        detail="validator hit B",
        evidence_count=1,
    )

    service.save_review_run([original], record_limit=20, reviewed_count=1)
    service.record_decision("review_original_ignored_alert", "ignored")
    second_job_id = service.save_review_run(
        [similar],
        record_limit=20,
        reviewed_count=1,
    )

    jobs = service.list_review_jobs(limit=2)
    second_job = next(job for job in jobs if job["id"] == second_job_id)
    assert service.list_pending_suggestions() == []
    assert second_job["suggestion_count"] == 0


def test_ui_settings_service_can_export_lexicon_entries_to_json():
    db_path = _db_path()
    export_path = Path("quality_audit") / f"lexicon_export_{uuid4().hex}.json"
    service = ReviewStorageService(db_path)
    suggestion = ReviewSuggestion(
        suggestion_id="review_export_lexicon",
        suggestion_type="lexicon_candidate",
        confidence=0.8,
        risk_level="medium",
        source_record_ids=("r1", "r2"),
        title="候选术语：PyTorch",
        detail="term candidate",
        evidence_count=2,
        old_form="拍套曲",
        new_form="PyTorch",
    )
    service.save_review_run([suggestion], record_limit=20, reviewed_count=2)
    service.record_decision("review_export_lexicon", "accepted")

    ui_service = UISettingsService(
        config_service=Mock(),
        event_service=Mock(),
        history_service=Mock(),
        review_storage_service=service,
    )

    result = ui_service.export_lexicon_entries(str(export_path))

    assert result["success"] is True
    assert result["path"] == str(export_path)
    assert result["count"] == 1
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert payload["count"] == 1
    assert payload["entries"][0]["term"] == "PyTorch"


def test_review_storage_service_suppresses_similar_prompt_failure_patterns():
    db_path = _db_path()
    service = ReviewStorageService(db_path)
    original = ReviewSuggestion(
        suggestion_id="review_prompt_failure_1",
        suggestion_type="prompt_failure_pattern",
        confidence=0.74,
        risk_level="medium",
        source_record_ids=("r1", "r2"),
        title="提示词失败模式：助手回复泄漏",
        detail="pattern A",
        evidence_count=2,
        old_form="assistant_response_tone",
    )
    similar = ReviewSuggestion(
        suggestion_id="review_prompt_failure_2",
        suggestion_type="prompt_failure_pattern",
        confidence=0.79,
        risk_level="medium",
        source_record_ids=("r3", "r4", "r5"),
        title="提示词失败模式：助手回复泄漏",
        detail="pattern B",
        evidence_count=3,
        old_form="assistant_response_tone",
    )

    service.save_review_run([original], record_limit=20, reviewed_count=2)
    service.record_decision("review_prompt_failure_1", "ignored")
    second_job_id = service.save_review_run(
        [similar],
        record_limit=20,
        reviewed_count=3,
    )

    jobs = service.list_review_jobs(limit=2)
    second_job = next(job for job in jobs if job["id"] == second_job_id)
    assert service.list_pending_suggestions() == []
    assert second_job["suggestion_count"] == 0


def test_ui_settings_service_can_export_review_debug_report_to_json():
    db_path = _db_path()
    export_path = Path("quality_audit") / f"review_debug_export_{uuid4().hex}.json"
    service = ReviewStorageService(db_path)
    prompt_issue = ReviewSuggestion(
        suggestion_id="review_export_debug_prompt_issue",
        suggestion_type="prompt_failure_pattern",
        confidence=0.74,
        risk_level="medium",
        source_record_ids=("r1", "r2"),
        title="提示词失败模式：助手回复泄漏",
        detail="pattern debug",
        evidence_count=2,
        old_form="assistant_response_tone",
    )
    unrelated = ReviewSuggestion(
        suggestion_id="review_export_debug_lexicon",
        suggestion_type="lexicon_candidate",
        confidence=0.8,
        risk_level="medium",
        source_record_ids=("r3", "r4"),
        title="候选术语：PyTorch",
        detail="term candidate",
        evidence_count=2,
        old_form="拍套曲",
        new_form="PyTorch",
    )
    service.save_review_run([prompt_issue, unrelated], record_limit=20, reviewed_count=4)

    ui_service = UISettingsService(
        config_service=Mock(),
        event_service=Mock(),
        history_service=Mock(),
        review_storage_service=service,
    )

    result = ui_service.export_review_debug_report(str(export_path))

    assert result["success"] is True
    assert result["path"] == str(export_path)
    assert result["count"] == 1
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert payload["count"] == 1
    assert payload["suggestions"][0]["suggestion_type"] == "prompt_failure_pattern"
    assert payload["recent_jobs"][0]["suggestion_count"] == 2
