"""批量重处理领域 mixin — BatchReprocessingWorker 状态机"""

from typing import Any

from PySide6.QtCore import Property, Slot

from ..history_workers import BatchReprocessingWorker
from .base import SettingsViewModelBase


class BatchReprocessViewModelMixin(SettingsViewModelBase):
    """批量重新转写的确认/进度/取消/结果流程。"""

    # ---- QML Properties ----

    @Property(bool, notify=SettingsViewModelBase.changed)
    def batchReprocessVisible(self) -> bool:
        return self._batch_reprocess_visible

    @Property(str, notify=SettingsViewModelBase.changed)
    def batchReprocessStage(self) -> str:
        return self._batch_reprocess_stage

    @Property(bool, notify=SettingsViewModelBase.changed)
    def batchReprocessRunning(self) -> bool:
        return self._batch_reprocess_stage == "running"

    @Property(int, notify=SettingsViewModelBase.changed)
    def batchReprocessTotal(self) -> int:
        return self._batch_reprocess_total

    @Property(int, notify=SettingsViewModelBase.changed)
    def batchReprocessCooldownSeconds(self) -> int:
        return self._batch_reprocess_cooldown_seconds

    @Property(int, notify=SettingsViewModelBase.changed)
    def batchReprocessProgressValue(self) -> int:
        return self._batch_reprocess_progress_value

    @Property(int, notify=SettingsViewModelBase.changed)
    def batchReprocessProgressTotal(self) -> int:
        return self._batch_reprocess_progress_total

    @Property(str, notify=SettingsViewModelBase.changed)
    def batchReprocessMessage(self) -> str:
        return self._batch_reprocess_message

    @Property("QVariantMap", notify=SettingsViewModelBase.changed)  # type: ignore[arg-type]
    def batchReprocessResult(self) -> dict[str, Any]:
        return self._batch_reprocess_result

    # ---- QML Slots ----

    @Slot()
    def startBatchReprocess(self) -> None:
        service = self._get_history_service()
        if not service:
            self._set_batch_message(
                "failed",
                "History service not available. Please restart the application.",
                visible=True,
            )
            return

        try:
            total_records = int(service.get_total_count())
            if total_records <= 0:
                self._set_batch_message(
                    "empty",
                    "No history records found to reprocess.",
                    visible=True,
                )
                return

            self._batch_reprocess_visible = True
            self._batch_reprocess_stage = "confirm"
            self._batch_reprocess_total = total_records
            self._batch_reprocess_progress_value = 0
            self._batch_reprocess_progress_total = 0
            self._batch_reprocess_message = (
                f"You are about to re-transcribe {total_records} records."
            )
            self._batch_reprocess_result = {}
            self.changed.emit()
        except Exception as exc:
            self._set_batch_message(
                "failed",
                f"Failed to start batch reprocessing: {exc}",
                visible=True,
            )

    @Slot(int)
    def confirmBatchReprocess(self, cd_seconds: int = 0) -> None:
        total_records = self._batch_reprocess_total
        if total_records <= 0:
            return
        self._start_batch_reprocessing(total_records, max(0, int(cd_seconds or 0)))

    @Slot()
    def closeBatchReprocess(self) -> None:
        if self._batch_reprocess_stage in {"running", "canceling"}:
            return
        self._batch_reprocess_visible = False
        self._batch_reprocess_stage = "idle"
        self._batch_reprocess_message = ""
        self._batch_reprocess_result = {}
        self.changed.emit()

    @Slot()
    def cancelBatchReprocess(self) -> None:
        self._batch_cancel_requested = True
        self._batch_reprocess_stage = "canceling"
        self._batch_reprocess_message = (
            "Cancel requested...\nWaiting for the current record to finish safely."
        )
        if self._batch_worker:
            self._batch_worker.stop()
        self.changed.emit()

    # ---- 内部实现 ----

    def _set_batch_message(self, stage: str, message: str, visible: bool) -> None:
        self._batch_reprocess_visible = visible
        self._batch_reprocess_stage = stage
        self._batch_reprocess_message = message
        self.changed.emit()

    def _start_batch_reprocessing(self, total_records: int, cd_seconds: int) -> None:
        self._batch_cancel_requested = False
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

        if not transcription_service or not history_service:
            self._set_batch_message(
                "failed",
                "Required services not available. Please restart the application.",
                visible=True,
            )
            return

        self._batch_worker = BatchReprocessingWorker(
            total_records=total_records,
            cd_seconds=cd_seconds,
            transcription_service=transcription_service,
            ai_processing_controller=ai_processing_controller,
            config_service=self._settings_service,
            history_service=history_service,
        )
        self._batch_worker.progress_updated.connect(self._on_batch_progress_updated)
        self._batch_worker.batch_completed.connect(self._on_batch_completed)
        self._batch_reprocess_visible = True
        self._batch_reprocess_stage = "running"
        self._batch_reprocess_total = total_records
        self._batch_reprocess_cooldown_seconds = cd_seconds
        self._batch_reprocess_progress_value = 0
        self._batch_reprocess_progress_total = total_records
        self._batch_reprocess_message = "Starting batch reprocessing..."
        self._batch_reprocess_result = {}
        self.changed.emit()
        self._batch_worker.start()

    def _on_batch_progress_updated(
        self, current: int, total: int, record_id: str
    ) -> None:
        self._batch_reprocess_progress_value = int(current)
        self._batch_reprocess_progress_total = int(total)
        self._batch_reprocess_message = f"Processing {current}/{total} records...\nCurrent record: {record_id[:16]}..."
        self.changed.emit()

    def _on_batch_completed(self, stats: dict) -> None:
        if self._batch_worker:
            self._batch_worker.wait()
            self._batch_worker = None

        self.refreshHistory(self._history_query)
        self._batch_reprocess_result = dict(stats)

        if self._batch_cancel_requested:
            self._batch_cancel_requested = False
            self._set_batch_message(
                "canceled",
                "Batch reprocessing was canceled. Completed work has been kept, and remaining records were skipped.",
                visible=True,
            )
            return

        report_lines = [
            "Batch Reprocessing Complete!",
            f"Total records: {stats.get('total', 0)}",
            f"Successful: {stats.get('success', 0)}",
            f"Skipped: {stats.get('skipped', 0)}",
            f"Failed: {stats.get('failed', 0)}",
        ]
        errors = stats.get("errors", [])
        if errors:
            report_lines.append("")
            report_lines.append(f"First {min(5, len(errors))} errors:")
            report_lines.extend(f"  {error}" for error in errors[:5])
            if len(errors) > 5:
                report_lines.append(f"... and {len(errors) - 5} more errors")

        self._set_batch_message("complete", "\n".join(report_lines), visible=True)


__all__ = ["BatchReprocessViewModelMixin"]
