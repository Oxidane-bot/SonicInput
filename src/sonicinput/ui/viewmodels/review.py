"""本地词汇审查与记忆领域 mixin。"""

from typing import Any

from PySide6.QtCore import Property, Slot

from .base import SettingsViewModelBase


class ReviewViewModelMixin(SettingsViewModelBase):
    """词汇候选审查、接受后的本地词汇记忆列表、导出和清空。"""

    def _format_lexicon_entry(self, item: dict[str, Any]) -> dict[str, Any]:
        evidence_count = int(item.get("evidence_count", 0) or 0)
        return {
            "id": str(item.get("id", "") or ""),
            "term": str(item.get("term", "") or ""),
            "oldForm": str(item.get("old_form", "") or ""),
            "confidenceText": self._format_confidence(item.get("confidence")),
            "evidenceText": self.translate("evidence", "Evidence")
            + f": {evidence_count}",
            "updatedAt": str(item.get("updated_at", "") or ""),
        }

    def _format_review_suggestion(self, item: dict[str, Any]) -> dict[str, Any]:
        evidence_count = int(item.get("evidence_count", 0) or 0)
        old_form = str(item.get("old_form", "") or "")
        new_form = str(item.get("new_form", "") or "")
        return {
            "id": str(item.get("suggestion_id", "") or ""),
            "title": str(item.get("title", "") or f"{old_form} -> {new_form}"),
            "detail": str(item.get("detail", "") or ""),
            "oldForm": old_form,
            "newForm": new_form,
            "confidenceText": self._format_confidence(item.get("confidence")),
            "evidenceText": self.translate("evidence", "Evidence")
            + f": {evidence_count}",
            "createdAt": str(item.get("created_at", "") or ""),
        }

    def _format_review_job(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(item.get("id", "") or ""),
            "createdAt": str(item.get("created_at", "") or ""),
            "reviewSource": str(item.get("review_source", "") or ""),
            "summary": self.translate(
                "review_job_summary",
                "{records} records, {suggestions} candidates",
            ).format(
                records=int(item.get("reviewed_count", 0) or 0),
                suggestions=int(item.get("suggestion_count", 0) or 0),
            ),
        }

    def _load_review_suggestions(self) -> None:
        list_suggestions = getattr(
            self._settings_service, "list_review_suggestions", None
        )
        if not callable(list_suggestions):
            self._review_suggestions = []
            return
        try:
            suggestions = list_suggestions(limit=100)
        except Exception:
            suggestions = []
        if not isinstance(suggestions, list):
            suggestions = []
        self._review_suggestions = [
            self._format_review_suggestion(item)
            for item in suggestions
            if isinstance(item, dict)
        ]

    def _load_review_jobs(self) -> None:
        list_jobs = getattr(self._settings_service, "list_review_jobs", None)
        if not callable(list_jobs):
            self._review_jobs = []
            return
        try:
            jobs = list_jobs(limit=5)
        except Exception:
            jobs = []
        if not isinstance(jobs, list):
            jobs = []
        self._review_jobs = [
            self._format_review_job(item) for item in jobs if isinstance(item, dict)
        ]

    def _load_lexicon_entries(self) -> None:
        list_entries = getattr(self._settings_service, "list_lexicon_entries", None)
        if not callable(list_entries):
            self._lexicon_entries = []
            return
        try:
            entries = list_entries(limit=200)
        except Exception:
            entries = []
        if not isinstance(entries, list):
            entries = []
        self._lexicon_entries = [
            self._format_lexicon_entry(item)
            for item in entries
            if isinstance(item, dict)
        ]

    def _refresh_lexicon_review_state(self) -> None:
        self._load_review_suggestions()
        self._load_review_jobs()
        self._load_lexicon_entries()

    def _decide_review_suggestion(self, suggestion_id: str, decision: str) -> bool:
        decide = getattr(self._settings_service, "decide_review_suggestion", None)
        if not callable(decide):
            return False
        try:
            success = bool(decide(suggestion_id, decision))
        except Exception:
            success = False
        if success:
            self.refreshReviewSuggestions()
        return success

    @Property("QVariantList", notify=SettingsViewModelBase.changed)  # type: ignore[arg-type]
    def reviewSuggestions(self) -> list[dict[str, Any]]:
        return self._review_suggestions

    @Property("QVariantList", notify=SettingsViewModelBase.changed)  # type: ignore[arg-type]
    def reviewSuggestionGroups(self) -> list[dict[str, Any]]:
        return []

    @Property("QVariantList", notify=SettingsViewModelBase.changed)  # type: ignore[arg-type]
    def reviewCategorySummaries(self) -> list[dict[str, Any]]:
        return []

    @Property(str, notify=SettingsViewModelBase.changed)
    def reviewSelectedCategory(self) -> str:
        return "all"

    @Property(str, notify=SettingsViewModelBase.changed)
    def reviewSelectedCategoryLabel(self) -> str:
        return self.translate("review_filter_all_categories", "All Categories")

    @Property(bool, notify=SettingsViewModelBase.changed)
    def reviewCategoryFilterActive(self) -> bool:
        return False

    @Property("QVariantList", notify=SettingsViewModelBase.changed)  # type: ignore[arg-type]
    def lexiconEntries(self) -> list[dict[str, Any]]:
        return self._lexicon_entries

    @Property("QVariantList", notify=SettingsViewModelBase.changed)  # type: ignore[arg-type]
    def reviewJobs(self) -> list[dict[str, Any]]:
        return self._review_jobs

    @Property(int, notify=SettingsViewModelBase.changed)
    def reviewSuggestionCount(self) -> int:
        return len(self._review_suggestions)

    @Property(str, notify=SettingsViewModelBase.changed)
    def reviewEmptyStateText(self) -> str:
        return self.translate("no_review_suggestions", "No lexicon candidates")

    @Property(str, notify=SettingsViewModelBase.changed)
    def reviewIgnoreScopeHint(self) -> str:
        return ""

    @Property(str, notify=SettingsViewModelBase.changed)
    def reviewSuggestionOverflowText(self) -> str:
        return ""

    @Property(int, notify=SettingsViewModelBase.changed)
    def lexiconEntryCount(self) -> int:
        return len(self._lexicon_entries)

    @Property(str, notify=SettingsViewModelBase.changed)
    def lexiconExportMessage(self) -> str:
        return self._lexicon_export_message

    @Property(str, notify=SettingsViewModelBase.changed)
    def reviewLearningDataMessage(self) -> str:
        return self._review_learning_data_message

    @Property(str, notify=SettingsViewModelBase.changed)
    def lexiconLastExportPath(self) -> str:
        return self._lexicon_last_export_path

    @Property(str, notify=SettingsViewModelBase.changed)
    def reviewDebugExportMessage(self) -> str:
        return ""

    @Property(str, notify=SettingsViewModelBase.changed)
    def reviewDebugLastExportPath(self) -> str:
        return ""

    @Property(int, notify=SettingsViewModelBase.changed)
    def reviewJobCount(self) -> int:
        return len(self._review_jobs)

    @Property(str, notify=SettingsViewModelBase.changed)
    def reviewRunMessage(self) -> str:
        return self._review_run_message

    @Property("QVariantMap", notify=SettingsViewModelBase.changed)  # type: ignore[arg-type]
    def reviewLastRunResult(self) -> dict[str, Any]:
        return self._review_last_run_result

    @Slot()
    def refreshReviewSuggestions(self) -> None:
        self._refresh_lexicon_review_state()
        self.changed.emit()

    @Slot()
    def refreshLexiconEntries(self) -> None:
        self.refreshReviewSuggestions()

    @Slot(str, result=bool)
    def setReviewCategoryFilter(self, category: str) -> bool:
        del category
        return False

    @Slot(str, result=bool)
    def toggleReviewSuggestionGroup(self, category: str) -> bool:
        del category
        return False

    @Slot(str, bool, result=bool)
    def setReviewSuggestionGroupExpanded(self, category: str, expanded: bool) -> bool:
        del category, expanded
        return False

    @Slot(result="QVariant")  # type: ignore[arg-type]
    def runReviewNow(self) -> dict[str, Any]:
        run_review = getattr(self._settings_service, "run_review_now", None)
        if not callable(run_review):
            result = {
                "ran": False,
                "reason": "review_unavailable",
                "jobId": "",
                "reviewedRecordCount": 0,
                "suggestionCount": 0,
            }
        else:
            try:
                raw = run_review()
            except Exception as exc:
                raw = {
                    "ran": False,
                    "reason": str(exc),
                    "jobId": "",
                    "reviewedRecordCount": 0,
                    "suggestionCount": 0,
                }
            result = (
                dict(raw)
                if isinstance(raw, dict)
                else {
                    "ran": False,
                    "reason": "review_failed",
                    "jobId": "",
                    "reviewedRecordCount": 0,
                    "suggestionCount": 0,
                }
            )
        self._review_last_run_result = result
        if result.get("ran"):
            self._review_run_message = self.translate(
                "review_run_completed",
                "Lexicon review completed: {records} records, {suggestions} candidates",
            ).format(
                records=int(result.get("reviewedRecordCount", 0) or 0),
                suggestions=int(result.get("suggestionCount", 0) or 0),
            )
        else:
            self._review_run_message = self.translate(
                "review_run_skipped",
                "Lexicon review skipped: {reason}",
            ).format(reason=str(result.get("reason", "unknown") or "unknown"))
        self.refreshReviewSuggestions()
        return result

    @Slot(result="QVariant")  # type: ignore[arg-type]
    def runIdleReviewOnce(self) -> dict[str, Any]:
        run_review = getattr(self._settings_service, "run_idle_review_once", None)
        if not callable(run_review):
            return {
                "ran": False,
                "reason": "review_unavailable",
                "jobId": "",
                "reviewedRecordCount": 0,
                "suggestionCount": 0,
            }
        try:
            result = run_review()
        except Exception as exc:
            result = {
                "ran": False,
                "reason": str(exc),
                "jobId": "",
                "reviewedRecordCount": 0,
                "suggestionCount": 0,
            }
        if isinstance(result, dict) and result.get("ran"):
            self.refreshReviewSuggestions()
        return (
            dict(result)
            if isinstance(result, dict)
            else {
                "ran": False,
                "reason": "review_failed",
                "jobId": "",
                "reviewedRecordCount": 0,
                "suggestionCount": 0,
            }
        )

    @Slot(str, result=bool)
    def acceptReviewSuggestion(self, suggestion_id: str) -> bool:
        return self._decide_review_suggestion(suggestion_id, "accepted")

    @Slot(str, result=bool)
    def rejectReviewSuggestion(self, suggestion_id: str) -> bool:
        return self._decide_review_suggestion(suggestion_id, "rejected")

    @Slot(str, result=bool)
    def ignoreReviewSuggestion(self, suggestion_id: str) -> bool:
        return self._decide_review_suggestion(suggestion_id, "ignored")

    @Slot(str, result=bool)
    def archiveReviewSuggestion(self, suggestion_id: str) -> bool:
        return self._decide_review_suggestion(suggestion_id, "archived")

    @Slot(str, result=bool)
    def reprocessReviewSuggestion(self, suggestion_id: str) -> bool:
        del suggestion_id
        return False

    @Slot(str, result=bool)
    def revertReviewSuggestionToRaw(self, suggestion_id: str) -> bool:
        del suggestion_id
        return False

    @Slot(str, result=bool)
    def openReviewSourceRecord(self, suggestion_id: str) -> bool:
        del suggestion_id
        return False

    @Slot(result=bool)
    def clearLexiconEntries(self) -> bool:
        clear_entries = getattr(self._settings_service, "clear_lexicon_entries", None)
        if not callable(clear_entries):
            return False
        try:
            success = bool(clear_entries())
        except Exception:
            success = False
        if success:
            self.refreshReviewSuggestions()
        return success

    @Slot(result=bool)
    def clearReviewLearningData(self) -> bool:
        clear_data = getattr(self._settings_service, "clear_review_learning_data", None)
        if not callable(clear_data):
            return False
        try:
            success = bool(clear_data())
        except Exception:
            success = False
        self._review_learning_data_message = self.translate(
            "clear_learning_data_success" if success else "clear_learning_data_failed",
            "Cleared lexicon learning data."
            if success
            else "Failed to clear lexicon learning data.",
        )
        if success:
            self.refreshReviewSuggestions()
        else:
            self.changed.emit()
        return success

    @Slot(str, result="QVariant")  # type: ignore[arg-type]
    def exportLexiconEntries(self, export_path: str = "") -> dict[str, Any]:
        export_entries = getattr(self._settings_service, "export_lexicon_entries", None)
        if not callable(export_entries):
            result: dict[str, Any] = {
                "success": False,
                "path": "",
                "count": 0,
                "reason": "export_unavailable",
            }
        else:
            try:
                raw = export_entries(export_path or None)
            except Exception as exc:
                raw = {"success": False, "path": "", "count": 0, "reason": str(exc)}
            result = (
                dict(raw)
                if isinstance(raw, dict)
                else {
                    "success": False,
                    "path": "",
                    "count": 0,
                    "reason": "export_failed",
                }
            )
        self._lexicon_last_export_path = str(result.get("path", "") or "")
        if result.get("success"):
            count = int(result.get("count", 0) or 0)
            target = self._lexicon_last_export_path or "local file"
            self._lexicon_export_message = self.translate(
                "export_lexicon_success",
                "Exported {count} lexicon entries to {path}",
            ).format(count=count, path=target)
        else:
            reason = str(result.get("reason", "export_failed") or "export_failed")
            self._lexicon_export_message = self.translate(
                "export_lexicon_failed",
                "Lexicon export failed: {reason}",
            ).format(reason=reason)
        self.changed.emit()
        return result

    @Slot(str, result="QVariant")  # type: ignore[arg-type]
    def exportReviewDebugReport(self, export_path: str = "") -> dict[str, Any]:
        del export_path
        return {
            "success": False,
            "path": "",
            "count": 0,
            "reason": "debug_report_removed",
        }


__all__ = ["ReviewViewModelMixin"]
