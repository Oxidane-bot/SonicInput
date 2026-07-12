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

    def _load_review_suggestions(self) -> None:
        try:
            suggestions = self._settings_service.list_review_suggestions(limit=100)
        except Exception:
            suggestions = []
        if not isinstance(suggestions, list):
            suggestions = []
        self._review_suggestions = [
            self._format_review_suggestion(item)
            for item in suggestions
            if isinstance(item, dict)
        ]

    def _load_lexicon_entries(self) -> None:
        try:
            entries = self._settings_service.list_lexicon_entries()
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
        self._load_lexicon_entries()

    def _decide_review_suggestion(self, suggestion_id: str, decision: str) -> bool:
        try:
            success = bool(
                self._settings_service.decide_review_suggestion(suggestion_id, decision)
            )
        except Exception:
            success = False
        if success:
            self.refreshReviewSuggestions()
        return success

    @Property("QVariantList", notify=SettingsViewModelBase.changed)  # type: ignore[arg-type]
    def reviewSuggestions(self) -> list[dict[str, Any]]:
        return self._review_suggestions

    @Property("QVariantList", notify=SettingsViewModelBase.changed)  # type: ignore[arg-type]
    def lexiconEntries(self) -> list[dict[str, Any]]:
        return self._lexicon_entries

    @Property(int, notify=SettingsViewModelBase.changed)
    def reviewSuggestionCount(self) -> int:
        return len(self._review_suggestions)

    @Property(str, notify=SettingsViewModelBase.changed)
    def reviewEmptyStateText(self) -> str:
        return self.translate("no_review_suggestions", "No lexicon candidates")

    @Property(int, notify=SettingsViewModelBase.changed)
    def lexiconEntryCount(self) -> int:
        return len(self._lexicon_entries)

    @Property(str, notify=SettingsViewModelBase.changed)
    def lexiconExportMessage(self) -> str:
        return self._lexicon_export_message

    @Property(str, notify=SettingsViewModelBase.changed)
    def reviewRunMessage(self) -> str:
        return self._review_run_message

    @Slot()
    def refreshReviewSuggestions(self) -> None:
        self._refresh_lexicon_review_state()
        self.changed.emit()

    @Slot()
    def refreshLexiconEntries(self) -> None:
        self.refreshReviewSuggestions()

    @Slot(result="QVariant")  # type: ignore[arg-type]
    def runReviewNow(self) -> dict[str, Any]:
        try:
            raw = self._settings_service.run_review_now()
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

    @Slot(str, result=bool)
    def acceptReviewSuggestion(self, suggestion_id: str) -> bool:
        return self._decide_review_suggestion(suggestion_id, "accepted")

    @Slot(str, result=bool)
    def rejectReviewSuggestion(self, suggestion_id: str) -> bool:
        return self._decide_review_suggestion(suggestion_id, "rejected")

    @Slot(str, result=bool)
    def ignoreReviewSuggestion(self, suggestion_id: str) -> bool:
        return self._decide_review_suggestion(suggestion_id, "ignored")

    @Slot(result=bool)
    def clearLexiconEntries(self) -> bool:
        try:
            success = bool(self._settings_service.clear_lexicon_entries())
        except Exception:
            success = False
        if success:
            self.refreshReviewSuggestions()
        return success

    @Slot(str, result=bool)
    def removeLexiconEntry(self, entry_id: str) -> bool:
        try:
            success = bool(
                self._settings_service.remove_lexicon_entry(str(entry_id or "").strip())
            )
        except Exception:
            success = False
        if success:
            self.refreshReviewSuggestions()
        return success

    @Slot(str, result="QVariant")  # type: ignore[arg-type]
    def exportLexiconEntries(self, export_path: str = "") -> dict[str, Any]:
        try:
            raw = self._settings_service.export_lexicon_entries(export_path or None)
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
        if result.get("success"):
            count = int(result.get("count", 0) or 0)
            target = str(result.get("path", "") or "") or "local file"
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


__all__ = ["ReviewViewModelMixin"]
