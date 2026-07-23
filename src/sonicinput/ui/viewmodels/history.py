"""历史记录领域 mixin — 分页加载、统计、详情与单条重处理"""

from typing import Any

from PySide6.QtCore import Property, Slot
from PySide6.QtWidgets import QApplication

from ..history_formatters import (
    build_diagnostic_tooltip,
    format_fallback_for_table,
    format_mode_for_table,
    format_transcription_path_for_display,
    format_transcribe_for_table,
    get_ai_status_display,
    get_status_display,
)
from ..history_workers import ReprocessingWorker
from .base import SettingsViewModelBase


class HistoryViewModelMixin(SettingsViewModelBase):
    """历史列表/详情/统计 + 单条记录重试(ReprocessingWorker)。"""

    # ---- 统计与格式化 ----

    def _set_history_stats(
        self, total_count: int, total_duration: float, success_count: int
    ) -> None:
        success_rate = (success_count / total_count * 100) if total_count > 0 else 0.0
        self._history_total_text = self.translate(
            "total_records_format", "Total Records: {count}"
        ).format(count=total_count)
        self._history_duration_text = self.translate(
            "total_duration_format", "Total Duration: {duration:.1f}s"
        ).format(duration=total_duration)
        self._history_success_rate_text = self.translate(
            "success_rate_format", "Success Rate: {rate:.1f}%"
        ).format(rate=success_rate)

    def _update_history_stats(self) -> None:
        service = self._get_history_service()
        if not service:
            self._set_history_stats(0, 0.0, 0)
            return

        try:
            query = self._history_query or None
            total_count, total_duration, success_count = service.get_aggregate_stats(
                query=query
            )
            self._set_history_stats(
                int(total_count),
                float(total_duration),
                int(success_count),
            )
        except Exception:
            self._set_history_stats(0, 0.0, 0)

    @staticmethod
    def _history_status_display(record: Any) -> str:
        return get_ai_status_display(record)

    @staticmethod
    def _history_primary_text(record: Any) -> str:
        final_text = getattr(record, "final_text", "") or ""
        if final_text:
            return final_text
        ai_text = getattr(record, "ai_optimized_text", "") or ""
        if getattr(record, "ai_status", "") == "success" and ai_text:
            return ai_text
        return getattr(record, "transcription_text", "") or ""

    def _record_to_history_row(self, record: Any) -> dict[str, Any]:
        timestamp = getattr(record, "timestamp", None)
        if timestamp is not None and hasattr(timestamp, "strftime"):
            display_time = timestamp.strftime("%m-%d %H:%M")
            full_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        else:
            display_time = ""
            full_time = ""

        duration = float(getattr(record, "duration", 0.0) or 0.0)
        transcription_text = getattr(record, "transcription_text", "") or ""
        primary_text = self._history_primary_text(record)
        return {
            "id": getattr(record, "id", ""),
            "displayTime": display_time,
            "fullTime": full_time,
            "durationText": f"{duration:.1f}s",
            "transcriptionText": transcription_text,
            "primaryText": primary_text,
            "statusText": self._history_status_display(record),
            "aiStatus": getattr(record, "ai_status", "") or "",
            "tooltip": build_diagnostic_tooltip(record),
        }

    def _record_to_history_detail(self, record: Any) -> dict[str, Any]:
        row = self._record_to_history_row(record)
        ai_text = getattr(record, "ai_optimized_text", "") or ""
        transcription_error = getattr(record, "transcription_error", None) or ""
        ai_error = getattr(record, "ai_error", None) or ""
        reprocess_parent_id = getattr(record, "reprocess_parent_id", None) or ""
        return {
            **row,
            "audioPath": getattr(record, "audio_file_path", "") or "N/A",
            "reprocessParentId": reprocess_parent_id or "N/A",
            "transcriptionProvider": getattr(record, "transcription_provider", "")
            or "N/A",
            "transcriptionStatusText": get_status_display(
                str(getattr(record, "transcription_status", "") or "")
            ),
            "streamingMode": format_mode_for_table(record),
            "transcriptionPath": format_transcription_path_for_display(record),
            "transcriptionDecisionReason": getattr(
                record, "transcription_decision_reason", None
            )
            or "N/A",
            "transcribeTime": format_transcribe_for_table(record),
            "fallbackUsed": format_fallback_for_table(record),
            "fallbackType": getattr(record, "fallback_type", None) or "none",
            "fallbackReason": getattr(record, "fallback_reason", None) or "None",
            "transcriptionError": transcription_error,
            "aiOptimizedText": ai_text,
            "aiProvider": getattr(record, "ai_provider", None) or "N/A",
            "aiError": ai_error,
            "diagnosticsText": "Captured"
            if getattr(record, "diagnostics_collected", False)
            else "Legacy defaults",
        }

    def _clear_history_detail(self) -> None:
        self._selected_history_index = -1
        self._selected_history_record = None
        self._selected_history_detail = {}
        self._history_detail_visible = False

    def _sync_selected_history_detail(self) -> None:
        """Keep an open detail panel bound to its record across list refreshes."""
        if self._selected_history_record is None:
            return

        selected_id = str(getattr(self._selected_history_record, "id", "") or "")
        for index, record in enumerate(self._history_records):
            if str(getattr(record, "id", "") or "") != selected_id:
                continue
            self._selected_history_index = index
            self._selected_history_record = record
            self._selected_history_detail = self._record_to_history_detail(record)
            return

        self._clear_history_detail()

    def _load_history_page(self, append: bool) -> None:
        service = self._get_history_service()
        if not service:
            if not append:
                self._history_records = []
                self._history_rows = []
                self._set_history_stats(0, 0.0, 0)
                self.changed.emit()
            return

        query = self._history_query
        if query:
            page_records = service.search_records_keyset(
                query=query,
                limit=self._history_page_size,
                cursor_timestamp=self._history_page_cursor_timestamp,
                cursor_id=self._history_page_cursor_id,
            )
        else:
            page_records = service.get_records_keyset(
                limit=self._history_page_size,
                cursor_timestamp=self._history_page_cursor_timestamp,
                cursor_id=self._history_page_cursor_id,
            )

        if not page_records:
            self._history_has_more_pages = False
            if not append:
                self._history_records = []
                self._history_rows = []
                self._sync_selected_history_detail()
            return

        if append:
            self._history_records.extend(page_records)
            self._history_rows.extend(
                self._record_to_history_row(record) for record in page_records
            )
        else:
            self._history_records = list(page_records)
            self._history_rows = [
                self._record_to_history_row(record) for record in page_records
            ]
            self._sync_selected_history_detail()

        last_record = page_records[-1]
        self._history_page_cursor_timestamp = getattr(last_record, "timestamp", None)
        self._history_page_cursor_id = getattr(last_record, "id", None)
        self._history_has_more_pages = len(page_records) >= self._history_page_size

    # ---- 单条重试(ReprocessingWorker) ----

    def _retry_history_record(self, record: Any) -> None:
        from ...utils import app_logger

        get_transcription_service = getattr(
            self._settings_service, "get_transcription_service", None
        )
        get_ai_processing_controller = getattr(
            self._settings_service, "get_ai_processing_controller", None
        )
        transcription_service = (
            get_transcription_service() if callable(get_transcription_service) else None
        )
        ai_processing_controller = (
            get_ai_processing_controller()
            if callable(get_ai_processing_controller)
            else None
        )
        history_service = self._get_history_service()

        app_logger.log_audio_event(
            "Fluent history retry requested",
            {
                "has_transcription_service": transcription_service is not None,
                "has_ai_controller": ai_processing_controller is not None,
                "record_id": getattr(record, "id", ""),
            },
        )

        if not transcription_service or not history_service:
            self._history_action_stage = "failed"
            self._history_action_busy = False
            self._history_action_message = (
                "Retry processing requires transcription service."
            )
            self.changed.emit()
            return

        self._retry_worker = ReprocessingWorker(
            record_id=getattr(record, "id", ""),
            audio_file_path=getattr(record, "audio_file_path", ""),
            transcription_service=transcription_service,
            ai_processing_controller=ai_processing_controller,
            config_service=self._settings_service,
            history_service=history_service,
        )
        self._retry_worker.progress_updated.connect(self._on_retry_progress_updated)
        self._retry_worker.reprocessing_completed.connect(
            self._on_retry_reprocessing_completed
        )
        self._retry_worker.reprocessing_failed.connect(
            self._on_retry_reprocessing_failed
        )
        self._retry_worker.finished.connect(self._on_retry_worker_finished)
        self._history_action_stage = "running"
        self._history_action_busy = True
        self._history_action_message = "Initializing reprocessing..."
        self.changed.emit()
        self._retry_worker.start()

    def _on_retry_progress_updated(self, message: str) -> None:
        self._history_action_message = message
        self.changed.emit()

    def _on_retry_reprocessing_completed(self, result: dict) -> None:
        new_record_id = result.get("new_record_id")
        history_service = self._get_history_service()
        if new_record_id and history_service:
            fresh_record = history_service.get_record_by_id(new_record_id)
            if fresh_record:
                self._selected_history_record = fresh_record
                self._selected_history_detail = self._record_to_history_detail(
                    fresh_record
                )
                self._history_detail_visible = True

        self.refreshHistory(self._history_query)
        self._history_action_stage = "complete"
        self._history_action_busy = False
        self._history_action_message = "Recording has been successfully reprocessed."
        self.changed.emit()

    def _on_retry_reprocessing_failed(self, error_message: str) -> None:
        if self._history_action_stage == "canceling":
            return

        self._history_action_stage = "failed"
        self._history_action_busy = False
        self._history_action_message = (
            f"Failed to reprocess the recording: {error_message}"
        )
        self.changed.emit()

    @Slot()
    def _on_retry_reprocessing_canceled(self) -> None:
        if self._retry_worker:
            self._retry_worker.stop()
            self._history_action_stage = "canceling"
            self._history_action_busy = True
            self._history_action_message = (
                "Cancel requested. Waiting for the current operation to stop safely..."
            )
            self.changed.emit()
            return

        self._history_action_stage = "canceled"
        self._history_action_busy = False
        self._history_action_message = "Reprocessing operation has been canceled."
        self.changed.emit()

    def _on_retry_worker_finished(self) -> None:
        worker = self.sender()
        if isinstance(worker, ReprocessingWorker):
            worker.deleteLater()
            if self._retry_worker is worker:
                self._retry_worker = None

        if self._history_action_stage == "canceling":
            self._history_action_stage = "canceled"
            self._history_action_busy = False
            self._history_action_message = "Reprocessing operation has been canceled."
            self.changed.emit()

    # ---- QML Properties ----

    @Property("QVariantList", notify=SettingsViewModelBase.changed)  # type: ignore[arg-type]
    def historyRecords(self) -> list[dict[str, Any]]:
        return self._history_rows

    @Property(str, notify=SettingsViewModelBase.changed)
    def historyTotalText(self) -> str:
        return self._history_total_text

    @Property(str, notify=SettingsViewModelBase.changed)
    def historyDurationText(self) -> str:
        return self._history_duration_text

    @Property(str, notify=SettingsViewModelBase.changed)
    def historySuccessRateText(self) -> str:
        return self._history_success_rate_text

    @Property(bool, notify=SettingsViewModelBase.changed)
    def historyDetailVisible(self) -> bool:
        return self._history_detail_visible

    @Property("QVariantMap", notify=SettingsViewModelBase.changed)  # type: ignore[arg-type]
    def selectedHistoryDetail(self) -> dict[str, Any]:
        return self._selected_history_detail

    @Property(bool, notify=SettingsViewModelBase.changed)
    def historyActionBusy(self) -> bool:
        return self._history_action_busy

    @Property(str, notify=SettingsViewModelBase.changed)
    def historyActionMessage(self) -> str:
        return self._history_action_message

    @Property(str, notify=SettingsViewModelBase.changed)
    def historyActionStage(self) -> str:
        return self._history_action_stage

    @Property(bool, notify=SettingsViewModelBase.changed)
    def historyHasMore(self) -> bool:
        return self._history_has_more_pages

    # ---- QML Slots ----

    @Slot(str)
    def refreshHistory(self, query: str = "") -> None:
        self._history_query = str(query or "").strip()
        self._history_page_cursor_timestamp = None
        self._history_page_cursor_id = None
        self._history_has_more_pages = True
        self._load_history_page(append=False)
        self._update_history_stats()
        self.changed.emit()

    @Slot()
    def loadMoreHistory(self) -> None:
        if not self._history_has_more_pages:
            return
        self._load_history_page(append=True)
        self.changed.emit()

    @Slot(int)
    def openHistoryDetail(self, index: int) -> None:
        if index < 0 or index >= len(self._history_records):
            return

        self._selected_history_index = index
        self._selected_history_record = self._history_records[index]
        self._selected_history_detail = self._record_to_history_detail(
            self._selected_history_record
        )
        self._history_detail_visible = True
        self.changed.emit()

    @Slot()
    def closeHistoryDetail(self) -> None:
        self._clear_history_detail()
        self.changed.emit()

    @Slot(int)
    def retryHistoryRecord(self, index: int) -> None:
        if index < 0 or index >= len(self._history_records):
            return
        self._retry_history_record(self._history_records[index])

    @Slot()
    def retrySelectedHistoryRecord(self) -> None:
        if self._selected_history_record is None:
            return
        self._retry_history_record(self._selected_history_record)

    @Slot(int, result=bool)
    def deleteHistoryRecord(self, index: int) -> bool:
        if index < 0 or index >= len(self._history_records):
            return False

        service = self._get_history_service()
        if not service:
            return False

        record = self._history_records[index]
        success = bool(service.delete_record(getattr(record, "id", "")))
        if success:
            self.refreshHistory(self._history_query)
        return success

    @Slot(result=bool)
    def deleteSelectedHistoryRecord(self) -> bool:
        record = self._selected_history_record
        if record is None:
            return False

        service = self._get_history_service()
        if not service:
            return False

        record_id = str(getattr(record, "id", "") or "")
        if not record_id:
            return False

        success = bool(service.delete_record(record_id))
        if success:
            self.refreshHistory(self._history_query)
            self._clear_history_detail()
            self.changed.emit()
        return success

    @Slot()
    def copySelectedHistoryText(self) -> None:
        if not self._selected_history_detail:
            return
        text = str(self._selected_history_detail.get("primaryText", ""))
        QApplication.clipboard().setText(text)

    @Slot()
    def cancelHistoryAction(self) -> None:
        if self._retry_worker:
            self._on_retry_reprocessing_canceled()
            return
        self._history_action_stage = "idle"
        self._history_action_busy = False
        self._history_action_message = ""
        self.changed.emit()


__all__ = ["HistoryViewModelMixin"]
