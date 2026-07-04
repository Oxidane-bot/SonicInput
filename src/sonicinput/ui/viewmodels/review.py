"""模型审查/词汇记忆领域 mixin — 建议格式化、分类分组、决策与导出

注意: 任务 #10 会把审查流程改造为词汇库词条确认流,本文件是该改造的
主要工作区。
"""

from collections import Counter
from typing import Any

from PySide6.QtCore import Property, Slot

from .base import SettingsViewModelBase


class ReviewViewModelMixin(SettingsViewModelBase):
    """审查建议列表 + 本地词汇记忆 + 审查运行记录。"""

    _REVIEW_SUGGESTION_DISPLAY_LIMIT = 24
    _REVIEW_NON_LEXICON_DISPLAY_LIMIT = 16
    _REVIEW_LEXICON_DISPLAY_LIMIT = 8
    _REVIEW_SOURCE_RECORD_PREVIEW_LIMIT = 2
    _REVIEW_SOURCE_RECORD_PREVIEW_CHARS = 96

    # ---- 格式化 ----

    def _format_review_suggestion(self, item: dict[str, Any]) -> dict[str, Any]:
        suggestion_type = str(item.get("suggestion_type", "") or "")
        risk_level = str(item.get("risk_level", "") or "")
        source_record_ids = item.get("source_record_ids", [])
        if isinstance(source_record_ids, list):
            source_record_text = ", ".join(str(value) for value in source_record_ids)
            source_record_id_list = [
                str(value) for value in source_record_ids if str(value)
            ]
        else:
            source_record_text = str(source_record_ids or "")
            source_record_id_list = [source_record_text] if source_record_text else []

        source_record_label = self.translate("source_records", "Source Records")
        source_record_preview_text = self._review_source_record_preview_text(
            source_record_id_list
        )
        source_record_open_id = self._first_viewable_source_record_id(
            source_record_id_list
        )
        if source_record_preview_text:
            source_record_label = self._review_source_record_label(
                len(source_record_id_list)
            )
            source_record_text = source_record_preview_text
        primary_source_record_id = (
            source_record_id_list[0] if len(source_record_id_list) == 1 else ""
        )
        primary_source_record = self._get_history_record_by_id(primary_source_record_id)
        can_reprocess_sample = (
            bool(primary_source_record_id) and suggestion_type != "lexicon_candidate"
        )
        can_revert_to_raw = (
            bool(primary_source_record_id)
            and suggestion_type != "lexicon_candidate"
            and primary_source_record is not None
            and bool(getattr(primary_source_record, "transcription_text", "") or "")
            and str(getattr(primary_source_record, "final_text", "") or "")
            != str(getattr(primary_source_record, "transcription_text", "") or "")
        )

        evidence_count = int(item.get("evidence_count", 0) or 0)
        category_key = self._review_category_key(suggestion_type)
        return {
            "id": str(item.get("suggestion_id", "") or ""),
            "type": suggestion_type,
            "typeLabel": self._review_type_label(suggestion_type),
            "category": category_key,
            "categoryLabel": self._review_category_label(category_key),
            "categoryDescription": self._review_category_description(category_key),
            "categoryPriorityLevel": self._review_category_priority_level(category_key),
            "categoryPriorityLabel": self._review_category_priority_label(category_key),
            "title": str(item.get("title", "") or ""),
            "detail": str(item.get("detail", "") or ""),
            "riskLevel": risk_level,
            "riskLabel": self._review_risk_label(risk_level),
            "riskDescription": self._review_risk_description(risk_level),
            "confidenceText": self._format_confidence(item.get("confidence")),
            "evidenceText": self.translate("evidence", "Evidence")
            + f": {evidence_count}",
            "actionHint": self._review_action_hint(suggestion_type),
            "sourceRecordLabel": source_record_label,
            "sourceRecordText": source_record_text,
            "sourceRecordPreviewText": source_record_preview_text,
            "sourceRecordIds": source_record_id_list,
            "sourceRecordOpenId": source_record_open_id,
            "canOpenSourceRecord": bool(source_record_open_id),
            "sourceRecordActionLabel": self._review_source_record_action_label(
                len(source_record_id_list)
            ),
            "primarySourceRecordId": primary_source_record_id,
            "canReprocessSample": can_reprocess_sample,
            "canRevertToRaw": can_revert_to_raw,
            "oldForm": str(item.get("old_form", "") or ""),
            "newForm": str(item.get("new_form", "") or ""),
            "createdAt": str(item.get("created_at", "") or ""),
        }

    def _get_history_record_by_id(self, record_id: str) -> Any:
        normalized = str(record_id or "").strip()
        if not normalized:
            return None
        if normalized in self._review_source_record_cache:
            return self._review_source_record_cache[normalized]
        service = self._get_history_service()
        if not service:
            self._review_source_record_cache[normalized] = None
            return None
        get_record = getattr(service, "get_record_by_id", None)
        if not callable(get_record):
            self._review_source_record_cache[normalized] = None
            return None
        try:
            record = get_record(normalized)
        except Exception:
            record = None
        self._review_source_record_cache[normalized] = record
        return record

    def _review_source_record_label(self, source_count: int) -> str:
        if source_count == 1:
            return self.translate("local_example", "Local Example")
        return self.translate("local_examples", "Local Examples")

    def _review_source_record_preview_text(self, source_record_ids: list[str]) -> str:
        if not source_record_ids:
            return ""

        previews: list[str] = []
        for record_id in source_record_ids:
            preview = self._review_source_record_preview(record_id)
            if preview:
                previews.append(preview)
            if len(previews) >= self._REVIEW_SOURCE_RECORD_PREVIEW_LIMIT:
                break

        if not previews:
            return ""

        preview_text = " • ".join(previews)
        extra_count = max(
            0,
            len(source_record_ids) - self._REVIEW_SOURCE_RECORD_PREVIEW_LIMIT,
        )
        if extra_count > 0:
            preview_text += " " + self.translate(
                "local_examples_more",
                "(+{count} more)",
            ).format(count=extra_count)
        return preview_text

    def _review_source_record_preview(self, record_id: str) -> str:
        record = self._get_history_record_by_id(record_id)
        if record is None:
            return ""

        for attribute in ("final_text", "ai_optimized_text", "transcription_text"):
            preview = self._compact_review_source_text(
                getattr(record, attribute, "") or ""
            )
            if preview:
                return preview
        return ""

    def _compact_review_source_text(self, text: str) -> str:
        compact = " ".join(str(text or "").split())
        if not compact:
            return ""
        if len(compact) <= self._REVIEW_SOURCE_RECORD_PREVIEW_CHARS:
            return compact
        return compact[: self._REVIEW_SOURCE_RECORD_PREVIEW_CHARS - 1].rstrip() + "…"

    def _review_source_record_action_label(self, source_count: int) -> str:
        if source_count <= 1:
            return self.translate("open_source_record", "Open Source Record")
        return self.translate("open_example_record", "Open Example Record")

    def _first_viewable_source_record_id(self, source_record_ids: list[str]) -> str:
        for record_id in source_record_ids:
            if self._get_history_record_by_id(record_id) is not None:
                return record_id
        return ""

    def _review_type_label(self, suggestion_type: str) -> str:
        fallbacks = {
            "abnormal_repetition_alert": "Abnormal Repetition",
            "assistant_response_leak_alert": "Assistant Response Leak",
            "asr_failure_alert": "ASR Failure Sample",
            "bad_ai_output_alert": "AI Boundary Alert",
            "chunk_boundary_repeat_alert": "Chunk Boundary Repeat",
            "collapsed_to_fragment_alert": "Collapsed to Fragment",
            "fallback_candidate_alert": "Fallback Candidate",
            "format_pollution_alert": "Format Pollution Alert",
            "lexicon_candidate": "Lexicon Candidate",
            "low_information_expansion_alert": "Low-Information Expansion",
            "over_compressed_long_input_alert": "Over-Compressed Long Input",
            "over_expanded_short_input_alert": "Over-Expanded Short Input",
            "prompt_failure_pattern": "Prompt Failure Pattern",
            "translation_command_leak_alert": "Translation Command Leak",
            "unexpected_language_shift_alert": "Unexpected Language Shift",
        }
        return self.translate(
            f"review_type_{suggestion_type}",
            fallbacks.get(suggestion_type, suggestion_type),
        )

    @staticmethod
    def _review_category_key(suggestion_type: str) -> str:
        if suggestion_type == "lexicon_candidate":
            return "lexicon_learning"
        if suggestion_type == "prompt_failure_pattern":
            return "prompt_quality"
        if suggestion_type in {
            "asr_failure_alert",
            "chunk_boundary_repeat_alert",
            "fallback_candidate_alert",
        }:
            return "diagnostics"
        if suggestion_type in {
            "assistant_response_leak_alert",
            "bad_ai_output_alert",
            "format_pollution_alert",
            "translation_command_leak_alert",
            "unexpected_language_shift_alert",
        }:
            return "boundary_violation"
        return "content_distortion"

    def _review_category_label(self, category_key: str) -> str:
        fallbacks = {
            "boundary_violation": "Boundary Violation",
            "content_distortion": "Content Distortion",
            "diagnostics": "Diagnostic Sample",
            "lexicon_learning": "Lexicon Learning",
            "prompt_quality": "Prompt Issue",
        }
        return self.translate(
            f"review_category_{category_key}",
            fallbacks.get(category_key, category_key),
        )

    def _review_category_description(self, category_key: str) -> str:
        fallbacks = {
            "boundary_violation": "AI left transcript-cleaning boundaries and instead answered, translated, switched language, or emitted structured output.",
            "content_distortion": "AI over-compressed, over-expanded, repeated, or otherwise distorted the original content.",
            "diagnostics": "Mainly useful for ASR or fallback diagnostics rather than direct AI cleanup boundary violations.",
            "lexicon_learning": "Used to accumulate confirmable local terminology memory; it only takes effect after you accept it.",
            "prompt_quality": "Aggregates recurring prompt or validator failure patterns for local debugging; exporting or accepting it does not change prompts automatically.",
        }
        return self.translate(
            f"review_category_{category_key}_desc",
            fallbacks.get(category_key, ""),
        )

    @staticmethod
    def _review_category_priority_level(category_key: str) -> str:
        if category_key in {"boundary_violation", "content_distortion"}:
            return "high"
        if category_key in {"diagnostics", "prompt_quality"}:
            return "medium"
        return "low"

    def _review_category_priority_label(self, category_key: str) -> str:
        level = self._review_category_priority_level(category_key)
        fallbacks = {
            "high": "Review First",
            "medium": "Worth Checking",
            "low": "Review Later",
        }
        return self.translate(
            f"review_priority_{level}",
            fallbacks.get(level, level),
        )

    def _review_risk_label(self, risk_level: str) -> str:
        fallbacks = {"high": "High Risk", "medium": "Medium Risk", "low": "Low Risk"}
        return self.translate(
            f"review_risk_{risk_level}",
            fallbacks.get(risk_level, risk_level),
        )

    def _review_risk_description(self, risk_level: str) -> str:
        fallbacks = {
            "high": "May already affect final input quality; review this first.",
            "medium": "May improve future cleanup, but only after you confirm it.",
            "low": "Mostly useful for diagnostics or sample collection.",
        }
        return self.translate(
            f"review_risk_{risk_level}_desc",
            fallbacks.get(risk_level, ""),
        )

    def _review_action_hint(self, suggestion_type: str) -> str:
        fallbacks = {
            "abnormal_repetition_alert": "Check whether AI got stuck repeating a segment; this usually should be retried or rolled back.",
            "assistant_response_leak_alert": "Check whether AI turned into an assistant reply, refusal, or placeholder instead of cleaning the transcript.",
            "asr_failure_alert": "Keep as an ASR/fallback debugging sample; it will not change typed output automatically.",
            "bad_ai_output_alert": "Check the record; if AI crossed the boundary, keep the raw transcript or reprocess it.",
            "chunk_boundary_repeat_alert": "Keep this as an ASR/chunk debugging sample; repeated adjacent fragments usually point to chunk overlap or boundary dedup issues.",
            "collapsed_to_fragment_alert": "Check whether a long dictation collapsed into a tiny fragment or stray word; this usually should be rolled back or reprocessed immediately.",
            "fallback_candidate_alert": "Keep this as a fallback-threshold debugging sample; a longer recording stayed near-empty without triggering fallback.",
            "format_pollution_alert": "Check whether markdown, labels, or list formatting leaked into the final input.",
            "lexicon_candidate": "Accepting adds this to local lexicon memory; reject/ignore does not affect future input.",
            "low_information_expansion_alert": "Check whether short noise or filler was expanded; history is not rewritten automatically.",
            "over_compressed_long_input_alert": "Check whether a long dictation was summarized or had important clauses removed.",
            "over_expanded_short_input_alert": "Check whether a short input was expanded into an explanation, answer, or much longer rewrite.",
            "prompt_failure_pattern": "This is a local fallback debugging clue. Accepting or exporting it does not change the live prompt automatically.",
            "translation_command_leak_alert": "Check whether AI executed a dictated translation command instead of preserving the transcript.",
            "unexpected_language_shift_alert": "Check whether AI unexpectedly switched the transcript into a different language.",
        }
        return self.translate(
            f"review_action_{suggestion_type}",
            fallbacks.get(suggestion_type, ""),
        )

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

    def _format_review_job(self, item: dict[str, Any]) -> dict[str, Any]:
        reviewed_count = int(item.get("reviewed_count", 0) or 0)
        suggestion_count = int(item.get("suggestion_count", 0) or 0)
        review_source = str(item.get("review_source", "") or "local")
        provider = str(item.get("provider", "") or "")
        model_id = str(item.get("model_id", "") or "")
        fallback_reason = str(item.get("fallback_reason", "") or "")
        return {
            "id": str(item.get("id", "") or ""),
            "createdAt": str(item.get("created_at", "") or ""),
            "status": str(item.get("status", "") or ""),
            "recordLimit": int(item.get("record_limit", 0) or 0),
            "reviewedRecordCount": reviewed_count,
            "suggestionCount": suggestion_count,
            "reviewSource": review_source,
            "provider": provider,
            "modelId": model_id,
            "fallbackReason": fallback_reason,
            "summaryText": self.translate(
                "review_job_summary",
                "{records} records, {suggestions} suggestions",
            ).format(records=reviewed_count, suggestions=suggestion_count),
        }

    # ---- 加载与分组 ----

    def _load_review_suggestions(self) -> None:
        self._review_source_record_cache = {}
        list_suggestions = getattr(
            self._settings_service, "list_review_suggestions", None
        )
        if not callable(list_suggestions):
            self._review_suggestions = []
            self._review_suggestion_groups = []
            self._review_suggestion_overflow_text = ""
            self._review_category_summaries = []
            self._review_selected_category = "all"
            return
        try:
            suggestions = list_suggestions(limit=100)
        except Exception:
            suggestions = []
        normalized = [item for item in suggestions if isinstance(item, dict)]
        display_items = self._select_review_suggestion_items(normalized)
        self._review_suggestions = [
            self._format_review_suggestion(item) for item in display_items
        ]
        self._review_category_summaries = self._build_review_category_summaries(
            normalized,
            display_items,
        )
        self._review_suggestion_groups = self._build_review_suggestion_groups(
            display_items,
            self._review_category_summaries,
        )
        self._review_suggestion_overflow_text = self._build_review_overflow_text(
            normalized,
            display_items,
        )

    def _select_review_suggestion_items(
        self, suggestions: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if self._review_selected_category == "all":
            return self._limit_review_suggestion_items(suggestions)

        filtered = [
            item
            for item in suggestions
            if self._review_category_key(str(item.get("suggestion_type", "") or ""))
            == self._review_selected_category
        ]
        return filtered[: self._REVIEW_SUGGESTION_DISPLAY_LIMIT]

    def _limit_review_suggestion_items(
        self, suggestions: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not suggestions:
            return []

        non_lexicon = [
            item
            for item in suggestions
            if str(item.get("suggestion_type", "") or "") != "lexicon_candidate"
        ]
        lexicon = [
            item
            for item in suggestions
            if str(item.get("suggestion_type", "") or "") == "lexicon_candidate"
        ]

        limited_non_lexicon = non_lexicon[: self._REVIEW_NON_LEXICON_DISPLAY_LIMIT]
        remaining_slots = max(
            0, self._REVIEW_SUGGESTION_DISPLAY_LIMIT - len(limited_non_lexicon)
        )
        limited_lexicon = lexicon[
            : min(self._REVIEW_LEXICON_DISPLAY_LIMIT, remaining_slots)
        ]
        return [*limited_non_lexicon, *limited_lexicon]

    def _build_review_category_summaries(
        self,
        all_items: list[dict[str, Any]],
        shown_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not all_items:
            return []

        total_counts = Counter(
            self._review_category_key(str(item.get("suggestion_type", "") or ""))
            for item in all_items
        )
        shown_counts = Counter(
            self._review_category_key(str(item.get("suggestion_type", "") or ""))
            for item in shown_items
        )
        order = (
            "boundary_violation",
            "content_distortion",
            "prompt_quality",
            "diagnostics",
            "lexicon_learning",
        )
        summaries: list[dict[str, Any]] = []
        for category_key in order:
            total_count = int(total_counts.get(category_key, 0))
            if total_count <= 0:
                continue
            shown_count = int(shown_counts.get(category_key, 0))
            summaries.append(
                {
                    "category": category_key,
                    "categoryLabel": self._review_category_label(category_key),
                    "categoryDescription": self._review_category_description(
                        category_key
                    ),
                    "priorityLevel": self._review_category_priority_level(category_key),
                    "priorityLabel": self._review_category_priority_label(category_key),
                    "totalCount": total_count,
                    "shownCount": shown_count,
                    "hiddenCount": max(0, total_count - shown_count),
                    "isSelected": category_key == self._review_selected_category,
                }
            )
        return summaries

    def _build_review_overflow_text(
        self,
        all_items: list[dict[str, Any]],
        shown_items: list[dict[str, Any]],
    ) -> str:
        if not all_items:
            return ""

        if self._review_selected_category == "all":
            hidden_count = max(0, len(all_items) - len(shown_items))
            if hidden_count <= 0:
                return ""
            return self.translate(
                "review_suggestion_overflow",
                "Showing {shown}/{total} pending suggestions. High-risk issues are prioritized and extra lexicon candidates are temporarily hidden.",
            ).format(shown=len(shown_items), total=len(all_items))

        total_in_category = sum(
            1
            for item in all_items
            if self._review_category_key(str(item.get("suggestion_type", "") or ""))
            == self._review_selected_category
        )
        hidden_count = max(0, total_in_category - len(shown_items))
        if hidden_count <= 0:
            return ""
        return self.translate(
            "review_suggestion_overflow_category",
            "Showing {shown}/{total} pending suggestions in {category}.",
        ).format(
            shown=len(shown_items),
            total=total_in_category,
            category=self.reviewSelectedCategoryLabel,
        )

    def _build_review_suggestion_groups(
        self,
        shown_items: list[dict[str, Any]],
        summaries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not shown_items or not summaries:
            return []

        group_items: dict[str, list[dict[str, Any]]] = {}
        for item in shown_items:
            category_key = self._review_category_key(
                str(item.get("suggestion_type", "") or "")
            )
            group_items.setdefault(category_key, []).append(
                self._format_review_suggestion(item)
            )

        groups: list[dict[str, Any]] = []
        for summary in summaries:
            category_key = str(summary.get("category", "") or "")
            items = group_items.get(category_key, [])
            if not items:
                continue
            groups.append(
                {
                    "category": category_key,
                    "categoryLabel": summary.get("categoryLabel", ""),
                    "categoryDescription": summary.get("categoryDescription", ""),
                    "priorityLevel": summary.get("priorityLevel", "low"),
                    "priorityLabel": summary.get("priorityLabel", ""),
                    "totalCount": int(summary.get("totalCount", 0) or 0),
                    "shownCount": int(summary.get("shownCount", 0) or 0),
                    "hiddenCount": int(summary.get("hiddenCount", 0) or 0),
                    "isSelected": bool(summary.get("isSelected", False)),
                    "defaultExpanded": self._review_group_default_expanded(
                        category_key,
                        bool(summary.get("isSelected", False)),
                    ),
                    "isExpanded": self._review_group_expanded(
                        category_key,
                        bool(summary.get("isSelected", False)),
                    ),
                    "items": items,
                }
            )
        return groups

    @staticmethod
    def _review_group_default_expanded(
        category_key: str,
        is_selected: bool,
    ) -> bool:
        if is_selected:
            return True
        return category_key in {"boundary_violation", "content_distortion"}

    def _review_group_expanded(
        self,
        category_key: str,
        is_selected: bool,
    ) -> bool:
        if category_key in self._review_group_expanded_overrides:
            return bool(self._review_group_expanded_overrides[category_key])
        return self._review_group_default_expanded(category_key, is_selected)

    def _load_lexicon_entries(self) -> None:
        list_entries = getattr(self._settings_service, "list_lexicon_entries", None)
        if not callable(list_entries):
            self._lexicon_entries = []
            return
        try:
            entries = list_entries(limit=200)
        except Exception:
            entries = []
        self._lexicon_entries = [
            self._format_lexicon_entry(item)
            for item in entries
            if isinstance(item, dict)
        ]

    def _load_review_jobs(self) -> None:
        list_jobs = getattr(self._settings_service, "list_review_jobs", None)
        if not callable(list_jobs):
            self._review_jobs = []
            return
        try:
            jobs = list_jobs(limit=20)
        except Exception:
            jobs = []
        self._review_jobs = [
            self._format_review_job(item) for item in jobs if isinstance(item, dict)
        ]

    def _decide_review_suggestion(self, suggestion_id: str, decision: str) -> bool:
        suggestion_id = str(suggestion_id or "").strip()
        if not suggestion_id:
            return False

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

    def _format_review_run_message(self, result: dict[str, Any]) -> str:
        if result.get("ran"):
            records = int(result.get("reviewedRecordCount", 0) or 0)
            suggestions = int(result.get("suggestionCount", 0) or 0)
            review_source = str(result.get("reviewSource", "") or "local")
            if review_source == "fallback":
                prefix = self.translate(
                    "review_run_completed_fallback",
                    "Fallback safety validation completed",
                )
            else:
                prefix = self.translate(
                    "review_run_completed",
                    "Model review completed: {records} records, {suggestions} suggestions",
                )
            if suggestions <= 0:
                if review_source == "fallback":
                    return self.translate(
                        "review_run_completed_fallback_empty",
                        "Fallback safety validation completed: checked {records} records, no suggestions",
                    ).format(records=records)
                return self.translate(
                    "review_run_completed_empty",
                    "Model review completed: checked {records} records, no suggestions",
                ).format(records=records)
            return prefix.format(records=records, suggestions=suggestions)
        return self.translate(
            "review_run_skipped",
            "Review did not run: {reason}",
        ).format(reason=self._review_run_reason_text(result))

    def _review_run_reason_text(self, result: dict[str, Any]) -> str:
        reason = str(result.get("reason", "unknown") or "unknown")
        return {
            "review_disabled": self.translate("review_disabled", "Review is disabled"),
            "review_scheduler_unavailable": self.translate(
                "review_scheduler_unavailable", "Review scheduler unavailable"
            ),
            "review_run_failed": self.translate(
                "review_run_failed", "Review failed to run"
            ),
            "not_idle_long_enough": self.translate(
                "not_idle_long_enough", "Not idle long enough"
            ),
            "min_interval_not_reached": self.translate(
                "min_interval_not_reached", "Minimum interval not reached"
            ),
            "session_budget_exhausted": self.translate(
                "session_budget_exhausted", "Session review budget exhausted"
            ),
        }.get(reason, reason)

    def _run_review(self, method_names: tuple[str, str]) -> dict[str, Any]:
        """按优先级尝试调用 settings service 上的审查入口并规范化结果。"""
        run_review = None
        for name in method_names:
            candidate = getattr(self._settings_service, name, None)
            if callable(candidate):
                run_review = candidate
                break
        if run_review is None:
            result: dict[str, Any] = {
                "ran": False,
                "reason": "review_scheduler_unavailable",
                "jobId": "",
                "reviewedRecordCount": 0,
                "suggestionCount": 0,
            }
        else:
            try:
                raw_result = run_review()
            except Exception:
                raw_result = {
                    "ran": False,
                    "reason": "review_run_failed",
                    "jobId": "",
                    "reviewedRecordCount": 0,
                    "suggestionCount": 0,
                }
            result = dict(raw_result) if isinstance(raw_result, dict) else {}
            result.setdefault("ran", False)
            result.setdefault("reason", "review_run_failed")
            result.setdefault("jobId", "")
            result.setdefault("reviewedRecordCount", 0)
            result.setdefault("suggestionCount", 0)

        self._review_last_run_result = result
        self._review_run_message = self._format_review_run_message(result)
        self.refreshReviewSuggestions()
        return result

    # ---- QML Properties ----

    @Property("QVariantList", notify=SettingsViewModelBase.changed)  # type: ignore[arg-type]
    def reviewSuggestions(self) -> list[dict[str, Any]]:
        return self._review_suggestions

    @Property("QVariantList", notify=SettingsViewModelBase.changed)  # type: ignore[arg-type]
    def reviewSuggestionGroups(self) -> list[dict[str, Any]]:
        return self._review_suggestion_groups

    @Property("QVariantList", notify=SettingsViewModelBase.changed)  # type: ignore[arg-type]
    def reviewCategorySummaries(self) -> list[dict[str, Any]]:
        return self._review_category_summaries

    @Property(str, notify=SettingsViewModelBase.changed)
    def reviewSelectedCategory(self) -> str:
        return self._review_selected_category

    @Property(str, notify=SettingsViewModelBase.changed)
    def reviewSelectedCategoryLabel(self) -> str:
        if self._review_selected_category == "all":
            return self.translate(
                "review_filter_all_categories",
                "All Categories",
            )
        return self._review_category_label(self._review_selected_category)

    @Property(bool, notify=SettingsViewModelBase.changed)
    def reviewCategoryFilterActive(self) -> bool:
        return self._review_selected_category != "all"

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
        if self._review_selected_category != "all":
            return self.translate(
                "no_review_suggestions_in_category",
                "No pending review suggestions in {category}.",
            ).format(category=self.reviewSelectedCategoryLabel)
        return self.translate(
            "no_review_suggestions",
            "No pending review suggestions",
        )

    @Property(str, notify=SettingsViewModelBase.changed)
    def reviewIgnoreScopeHint(self) -> str:
        return self.translate(
            "review_ignore_scope_hint",
            "Ignore Once dismisses only this card. Always Ignore Similar suppresses future similar suggestions.",
        )

    @Property(str, notify=SettingsViewModelBase.changed)
    def reviewSuggestionOverflowText(self) -> str:
        return self._review_suggestion_overflow_text

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
        return self._review_debug_export_message

    @Property(str, notify=SettingsViewModelBase.changed)
    def reviewDebugLastExportPath(self) -> str:
        return self._review_debug_last_export_path

    @Property(int, notify=SettingsViewModelBase.changed)
    def reviewJobCount(self) -> int:
        return len(self._review_jobs)

    @Property(str, notify=SettingsViewModelBase.changed)
    def reviewRunMessage(self) -> str:
        return self._review_run_message

    @Property("QVariantMap", notify=SettingsViewModelBase.changed)  # type: ignore[arg-type]
    def reviewLastRunResult(self) -> dict[str, Any]:
        return self._review_last_run_result

    # ---- QML Slots ----

    @Slot()
    def refreshReviewSuggestions(self) -> None:
        self._load_review_suggestions()
        self._load_lexicon_entries()
        self._load_review_jobs()
        self.changed.emit()

    @Slot(str, result=bool)
    def setReviewCategoryFilter(self, category: str) -> bool:
        normalized = str(category or "").strip() or "all"
        allowed = {
            "all",
            "boundary_violation",
            "content_distortion",
            "diagnostics",
            "lexicon_learning",
            "prompt_quality",
        }
        if normalized not in allowed:
            normalized = "all"
        if self._review_selected_category == normalized:
            return False

        self._review_selected_category = normalized
        self._load_review_suggestions()
        self.changed.emit()
        return True

    @Slot(str, result=bool)
    def toggleReviewSuggestionGroup(self, category: str) -> bool:
        normalized = str(category or "").strip()
        if not normalized:
            return False

        groups = {
            str(item.get("category", "") or ""): item
            for item in self._review_suggestion_groups
        }
        current = groups.get(normalized)
        if not current:
            return False

        return self.setReviewSuggestionGroupExpanded(
            normalized,
            not bool(current.get("isExpanded", False)),
        )

    @Slot(str, bool, result=bool)
    def setReviewSuggestionGroupExpanded(self, category: str, expanded: bool) -> bool:
        normalized = str(category or "").strip()
        if not normalized:
            return False

        all_categories = {
            str(item.get("category", "") or "")
            for item in self._review_category_summaries
        }
        if normalized not in all_categories:
            return False

        expanded_bool = bool(expanded)
        self._review_group_expanded_overrides[normalized] = expanded_bool
        self._load_review_suggestions()
        self.changed.emit()
        return True

    @Slot(result="QVariant")  # type: ignore[arg-type]
    def runReviewNow(self) -> dict[str, Any]:
        return self._run_review(("run_review_now", "run_idle_review_once"))

    @Slot(result="QVariant")  # type: ignore[arg-type]
    def runIdleReviewOnce(self) -> dict[str, Any]:
        return self._run_review(("run_idle_review_once", "run_review_now"))

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
        suggestion_id = str(suggestion_id or "").strip()
        if not suggestion_id:
            return False

        suggestion = next(
            (
                item
                for item in self._review_suggestions
                if str(item.get("id", "") or "") == suggestion_id
            ),
            None,
        )
        if not suggestion:
            return False

        if not bool(suggestion.get("canReprocessSample", False)):
            return False

        primary_source_record_id = str(
            suggestion.get("primarySourceRecordId", "") or ""
        ).strip()
        if not primary_source_record_id:
            return False

        history_service = self._get_history_service()
        if not history_service:
            self._history_action_stage = "failed"
            self._history_action_busy = False
            self._history_action_message = "Reprocessing requires history service."
            self.changed.emit()
            return False

        record = history_service.get_record_by_id(primary_source_record_id)
        if record is None:
            self._history_action_stage = "failed"
            self._history_action_busy = False
            self._history_action_message = "Unable to locate the source record."
            self.changed.emit()
            return False

        self._pending_review_reprocess_suggestion_id = suggestion_id
        self._retry_history_record(record)
        return True

    @Slot(str, result=bool)
    def revertReviewSuggestionToRaw(self, suggestion_id: str) -> bool:
        suggestion_id = str(suggestion_id or "").strip()
        if not suggestion_id:
            return False

        suggestion = next(
            (
                item
                for item in self._review_suggestions
                if str(item.get("id", "") or "") == suggestion_id
            ),
            None,
        )
        if not suggestion:
            return False

        if not bool(suggestion.get("canRevertToRaw", False)):
            return False

        primary_source_record_id = str(
            suggestion.get("primarySourceRecordId", "") or ""
        ).strip()
        if not primary_source_record_id:
            return False

        history_service = self._get_history_service()
        if not history_service:
            self._history_action_stage = "failed"
            self._history_action_busy = False
            self._history_action_message = "Rollback requires history service."
            self.changed.emit()
            return False

        record = self._get_history_record_by_id(primary_source_record_id)
        if record is None:
            self._history_action_stage = "failed"
            self._history_action_busy = False
            self._history_action_message = "Unable to locate the source record."
            self.changed.emit()
            return False

        raw_text = str(getattr(record, "transcription_text", "") or "")
        if not raw_text:
            return False

        record.final_text = raw_text
        update_record = getattr(history_service, "update_record", None)
        if not callable(update_record):
            self._history_action_stage = "failed"
            self._history_action_busy = False
            self._history_action_message = "Rollback requires history update support."
            self.changed.emit()
            return False

        success = bool(update_record(record))
        self.refreshHistory(self._history_query)
        if success:
            self._decide_review_suggestion(suggestion_id, "archived")
            if (
                self._selected_history_record is not None
                and getattr(self._selected_history_record, "id", "") == record.id
            ):
                self._selected_history_record = record
                self._selected_history_detail = self._record_to_history_detail(record)
                self._history_detail_visible = True
            self._history_action_stage = "complete"
            self._history_action_busy = False
            self._history_action_message = (
                "Review sample has been reverted to the raw transcript."
            )
            self.changed.emit()
            return True

        self._history_action_stage = "failed"
        self._history_action_busy = False
        self._history_action_message = "Failed to revert the sample to raw transcript."
        self.changed.emit()
        return False

    @Slot(str, result=bool)
    def openReviewSourceRecord(self, suggestion_id: str) -> bool:
        suggestion_id = str(suggestion_id or "").strip()
        if not suggestion_id:
            return False

        suggestion = next(
            (
                item
                for item in self._review_suggestions
                if str(item.get("id", "") or "") == suggestion_id
            ),
            None,
        )
        if not suggestion:
            return False

        source_record_id = str(suggestion.get("sourceRecordOpenId", "") or "").strip()
        if not source_record_id:
            source_record_ids = suggestion.get("sourceRecordIds", [])
            if not isinstance(source_record_ids, list):
                source_record_ids = (
                    [str(source_record_ids)] if source_record_ids else []
                )
            source_record_id = self._first_viewable_source_record_id(
                [str(value) for value in source_record_ids if str(value)]
            )
        if not source_record_id:
            return False

        return self._open_history_record_by_id(source_record_id)

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
        clear_learning_data = getattr(
            self._settings_service,
            "clear_review_learning_data",
            None,
        )
        if not callable(clear_learning_data):
            self._review_learning_data_message = self.translate(
                "clear_learning_data_failed",
                "Failed to clear local learning data.",
            )
            self.changed.emit()
            return False
        try:
            success = bool(clear_learning_data())
        except Exception:
            success = False
        self._review_learning_data_message = self.translate(
            "clear_learning_data_success" if success else "clear_learning_data_failed",
            "Local learning data has been cleared."
            if success
            else "Failed to clear local learning data.",
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
                raw = {
                    "success": False,
                    "path": "",
                    "count": 0,
                    "reason": str(exc),
                }
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
        export_report = getattr(
            self._settings_service,
            "export_review_debug_report",
            None,
        )
        if not callable(export_report):
            result: dict[str, Any] = {
                "success": False,
                "path": "",
                "count": 0,
                "reason": "export_unavailable",
            }
        else:
            try:
                raw = export_report(export_path or None)
            except Exception as exc:
                raw = {
                    "success": False,
                    "path": "",
                    "count": 0,
                    "reason": str(exc),
                }
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
        self._review_debug_last_export_path = str(result.get("path", "") or "")
        if result.get("success"):
            count = int(result.get("count", 0) or 0)
            target = self._review_debug_last_export_path or "local file"
            self._review_debug_export_message = self.translate(
                "review_debug_export_success",
                "Exported {count} fallback debug suggestions to {path}",
            ).format(count=count, path=target)
        else:
            reason = str(result.get("reason", "export_failed") or "export_failed")
            self._review_debug_export_message = self.translate(
                "review_debug_export_failed",
                "Prompt/validator debug export failed: {reason}",
            ).format(reason=reason)
        self.changed.emit()
        return result


__all__ = ["ReviewViewModelMixin"]
