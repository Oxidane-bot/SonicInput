"""History detail dialog and retry/delete actions."""

from typing import Optional

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from .history_workers import ReprocessingWorker


class HistoryDetailDialog(QDialog):
    """历史记录详情对话框"""

    def __init__(
        self,
        record,
        parent_window,
        settings_service,
        history_service,
        parent=None,
    ):
        super().__init__(parent)
        self.record = record
        self.parent_window = parent_window
        self.settings_service = settings_service
        self.history_service = history_service
        self.reprocessing_worker = None
        self.progress_dialog = None
        self._language_listener_id: Optional[str] = None
        self.setup_ui()

        self._event_service = None
        if self.settings_service:
            from ...core.services.events import Events

            self._event_service = self.settings_service.get_event_service()
            if self._event_service:
                self._language_listener_id = self._event_service.on(
                    Events.UI_LANGUAGE_CHANGED, self._on_language_changed
                )

    def setup_ui(self):
        """设置对话框UI"""
        self.setWindowTitle(
            QCoreApplication.translate("HistoryDetailDialog", "Recording Details")
        )
        self.setMinimumSize(700, 600)

        layout = QVBoxLayout(self)

        info_layout = QVBoxLayout()

        self.basic_info_group = QGroupBox("Basic Information")
        basic_layout = QVBoxLayout(self.basic_info_group)

        self.time_label = QLabel(
            f"<b>Time:</b> {self.record.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        self.duration_label = QLabel(f"<b>Duration:</b> {self.record.duration:.2f}s")
        self.audio_path_label = QLabel(
            f"<b>Audio File:</b> {self.record.audio_file_path or 'N/A'}"
        )
        self.audio_path_label.setWordWrap(True)
        self.reprocess_parent_label = QLabel(
            f"<b>Reprocess Of:</b> {getattr(self.record, 'reprocess_parent_id', None) or 'N/A'}"
        )

        basic_layout.addWidget(self.time_label)
        basic_layout.addWidget(self.duration_label)
        basic_layout.addWidget(self.audio_path_label)
        basic_layout.addWidget(self.reprocess_parent_label)
        info_layout.addWidget(self.basic_info_group)

        transcription_status = self._status_display(self.record.transcription_status)
        self.trans_group = QGroupBox(
            QCoreApplication.translate(
                "HistoryDetailDialog", "Original Transcription ({status})"
            ).format(status=transcription_status)
        )
        trans_layout = QVBoxLayout(self.trans_group)

        self.trans_provider_label = QLabel(
            f"<b>Provider:</b> {self.record.transcription_provider or 'N/A'}"
        )
        trans_layout.addWidget(self.trans_provider_label)
        self.trans_diagnostics_label = QLabel(
            f"<b>Diagnostics:</b> {self._format_diagnostics_status()}"
        )
        trans_layout.addWidget(self.trans_diagnostics_label)
        self.trans_mode_label = QLabel(f"<b>Mode:</b> {self._display_mode()}")
        trans_layout.addWidget(self.trans_mode_label)
        self.trans_duration_label = QLabel(
            f"<b>Transcribe Time:</b> {self._display_transcribe_duration()}"
        )
        trans_layout.addWidget(self.trans_duration_label)
        self.trans_fallback_label = QLabel(
            f"<b>Fallback Used:</b> {self._display_fallback_used()}"
        )
        trans_layout.addWidget(self.trans_fallback_label)
        self.trans_fallback_type_label = QLabel(
            f"<b>Fallback Type:</b> {self._display_fallback_type()}"
        )
        trans_layout.addWidget(self.trans_fallback_type_label)
        self.trans_fallback_reason_label = QLabel(
            f"<b>Fallback Reason:</b> {self._display_fallback_reason()}"
        )
        trans_layout.addWidget(self.trans_fallback_reason_label)

        if self.record.transcription_error:
            self.trans_error_label = QLabel(
                f"<b>Error:</b> {self.record.transcription_error}"
            )
            self.trans_error_label.setStyleSheet("color: red;")
            trans_layout.addWidget(self.trans_error_label)
        else:
            self.trans_error_label = None

        self.trans_text_edit = QTextEdit()
        self.trans_text_edit.setPlainText(
            self.record.transcription_text
            or QCoreApplication.translate("HistoryDetailDialog", "(empty)")
        )
        self.trans_text_edit.setReadOnly(True)
        self.trans_text_edit.setMaximumHeight(150)
        trans_layout.addWidget(self.trans_text_edit)
        info_layout.addWidget(self.trans_group)

        if self.record.ai_status:
            ai_status_label = self._status_display(self.record.ai_status)
            ai_status_text = QCoreApplication.translate(
                "HistoryDetailDialog", "AI {status}"
            ).format(status=ai_status_label)
        else:
            ai_status_text = QCoreApplication.translate(
                "HistoryDetailDialog", "AI Status Unknown"
            )
        self.optimized_group = QGroupBox(
            QCoreApplication.translate(
                "HistoryDetailDialog", "Optimized Text ({status})"
            ).format(status=ai_status_text)
        )
        optimized_layout = QVBoxLayout(self.optimized_group)

        if self.record.ai_provider:
            self.ai_provider_label = QLabel(
                f"<b>AI Provider:</b> {self.record.ai_provider}"
            )
            optimized_layout.addWidget(self.ai_provider_label)
        else:
            self.ai_provider_label = None

        if self.record.ai_error:
            self.ai_error_label = QLabel(f"<b>Error:</b> {self.record.ai_error}")
            self.ai_error_label.setStyleSheet("color: red;")
            optimized_layout.addWidget(self.ai_error_label)
        else:
            self.ai_error_label = None

        self.optimized_text_edit = QTextEdit()
        if self.record.ai_status == "success" and self.record.ai_optimized_text:
            display_text = self.record.ai_optimized_text
        else:
            display_text = QCoreApplication.translate(
                "HistoryDetailDialog",
                "{text}\n\n(Using original transcription - AI {status})",
            ).format(text=self.record.transcription_text, status=self.record.ai_status)

        self.optimized_text_edit.setPlainText(
            display_text or QCoreApplication.translate("HistoryDetailDialog", "(empty)")
        )
        self.optimized_text_edit.setReadOnly(True)
        self.optimized_text_edit.setMaximumHeight(150)
        optimized_layout.addWidget(self.optimized_text_edit)
        info_layout.addWidget(self.optimized_group)

        layout.addLayout(info_layout)

        button_layout = QHBoxLayout()

        self.copy_button = QPushButton("Copy to Clipboard")
        self.copy_button.clicked.connect(self._copy_to_clipboard)
        button_layout.addWidget(self.copy_button)

        self.retry_button = QPushButton("Retry")
        self.retry_button.clicked.connect(self._retry_processing)
        button_layout.addWidget(self.retry_button)

        self.delete_button = QPushButton("Delete Record")
        self.delete_button.clicked.connect(self._delete_record)
        self.delete_button.setStyleSheet("background-color: #d32f2f; color: white;")
        button_layout.addWidget(self.delete_button)

        button_layout.addStretch()

        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)
        button_layout.addWidget(self.close_button)

        layout.addLayout(button_layout)
        self.retranslate_ui()

    def _get_runtime_transcription_service(self):
        if self.settings_service:
            return self.settings_service.get_transcription_service()
        return None

    def _get_runtime_ai_processing_controller(self):
        if self.settings_service:
            return self.settings_service.get_ai_processing_controller()
        return None

    def _status_display(self, status: Optional[str]) -> str:
        status_map = {
            "success": QCoreApplication.translate("HistoryDetailDialog", "Success"),
            "failed": QCoreApplication.translate("HistoryDetailDialog", "Failed"),
            "skipped": QCoreApplication.translate("HistoryDetailDialog", "Skipped"),
            "pending": QCoreApplication.translate("HistoryDetailDialog", "Pending"),
        }
        return status_map.get(
            status, QCoreApplication.translate("HistoryDetailDialog", "Unknown")
        )

    @staticmethod
    def _format_streaming_mode(mode: Optional[str]) -> str:
        if not mode:
            return "unknown"
        return str(mode)

    @staticmethod
    def _format_yes_no(value: bool) -> str:
        return (
            QCoreApplication.translate("HistoryDetailDialog", "Yes")
            if value
            else QCoreApplication.translate("HistoryDetailDialog", "No")
        )

    def _diagnostics_collected(self) -> bool:
        return bool(getattr(self.record, "diagnostics_collected", False))

    def _format_diagnostics_status(self) -> str:
        return (
            QCoreApplication.translate("HistoryDetailDialog", "Captured")
            if self._diagnostics_collected()
            else QCoreApplication.translate("HistoryDetailDialog", "Legacy Defaults")
        )

    def _display_mode(self) -> str:
        if not self._diagnostics_collected():
            return QCoreApplication.translate("HistoryDetailDialog", "N/A (legacy)")
        return self._format_streaming_mode(self.record.streaming_mode)

    def _display_transcribe_duration(self) -> str:
        if not self._diagnostics_collected():
            return QCoreApplication.translate("HistoryDetailDialog", "N/A (legacy)")
        return f"{self.record.transcription_duration:.2f}s"

    def _display_fallback_used(self) -> str:
        if not self._diagnostics_collected():
            return QCoreApplication.translate("HistoryDetailDialog", "N/A (legacy)")
        return self._format_yes_no(self.record.used_fallback)

    def _display_fallback_type(self) -> str:
        if not self._diagnostics_collected():
            return QCoreApplication.translate("HistoryDetailDialog", "N/A (legacy)")
        if not self.record.used_fallback:
            return QCoreApplication.translate("HistoryDetailDialog", "None")
        return getattr(self.record, "fallback_type", "unknown") or "unknown"

    def _display_fallback_reason(self) -> str:
        if not self._diagnostics_collected():
            return QCoreApplication.translate("HistoryDetailDialog", "N/A (legacy)")
        reason = getattr(self.record, "fallback_reason", None)
        if not reason:
            return QCoreApplication.translate("HistoryDetailDialog", "None")
        return str(reason)

    def _on_language_changed(self, data: object = None) -> None:
        self.retranslate_ui()

    def done(self, result: int) -> None:
        self._unsubscribe_language_listener()
        super().done(result)

    def _unsubscribe_language_listener(self) -> None:
        if (
            not self._event_service
            or not self._language_listener_id
            or not hasattr(self._event_service, "off")
        ):
            return

        from ...core.services.events import Events

        try:
            self._event_service.off(
                Events.UI_LANGUAGE_CHANGED, self._language_listener_id
            )
        finally:
            self._language_listener_id = None

    def retranslate_ui(self) -> None:
        self.setWindowTitle(
            QCoreApplication.translate("HistoryDetailDialog", "Recording Details")
        )
        self.basic_info_group.setTitle(
            QCoreApplication.translate("HistoryDetailDialog", "Basic Information")
        )

        timestamp_text = self.record.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        self.time_label.setText(
            QCoreApplication.translate(
                "HistoryDetailDialog", "<b>Time:</b> {time}"
            ).format(time=timestamp_text)
        )
        self.duration_label.setText(
            QCoreApplication.translate(
                "HistoryDetailDialog", "<b>Duration:</b> {duration:.2f}s"
            ).format(duration=self.record.duration)
        )
        audio_path = self.record.audio_file_path or QCoreApplication.translate(
            "HistoryDetailDialog", "N/A"
        )
        self.audio_path_label.setText(
            QCoreApplication.translate(
                "HistoryDetailDialog", "<b>Audio File:</b> {path}"
            ).format(path=audio_path)
        )
        self.reprocess_parent_label.setText(
            QCoreApplication.translate(
                "HistoryDetailDialog", "<b>Reprocess Of:</b> {record_id}"
            ).format(
                record_id=getattr(self.record, "reprocess_parent_id", None)
                or QCoreApplication.translate("HistoryDetailDialog", "N/A")
            )
        )

        transcription_status = self._status_display(self.record.transcription_status)
        self.trans_group.setTitle(
            QCoreApplication.translate(
                "HistoryDetailDialog", "Original Transcription ({status})"
            ).format(status=transcription_status)
        )
        self.trans_provider_label.setText(
            QCoreApplication.translate(
                "HistoryDetailDialog", "<b>Provider:</b> {provider}"
            ).format(
                provider=self.record.transcription_provider
                or QCoreApplication.translate("HistoryDetailDialog", "N/A")
            )
        )
        self.trans_diagnostics_label.setText(
            QCoreApplication.translate(
                "HistoryDetailDialog", "<b>Diagnostics:</b> {value}"
            ).format(value=self._format_diagnostics_status())
        )
        self.trans_mode_label.setText(
            QCoreApplication.translate(
                "HistoryDetailDialog", "<b>Mode:</b> {mode}"
            ).format(mode=self._display_mode())
        )
        self.trans_duration_label.setText(
            QCoreApplication.translate(
                "HistoryDetailDialog", "<b>Transcribe Time:</b> {value}"
            ).format(value=self._display_transcribe_duration())
        )
        self.trans_fallback_label.setText(
            QCoreApplication.translate(
                "HistoryDetailDialog", "<b>Fallback Used:</b> {value}"
            ).format(value=self._display_fallback_used())
        )
        self.trans_fallback_type_label.setText(
            QCoreApplication.translate(
                "HistoryDetailDialog", "<b>Fallback Type:</b> {value}"
            ).format(value=self._display_fallback_type())
        )
        self.trans_fallback_reason_label.setText(
            QCoreApplication.translate(
                "HistoryDetailDialog", "<b>Fallback Reason:</b> {value}"
            ).format(value=self._display_fallback_reason())
        )
        if self.trans_error_label:
            self.trans_error_label.setText(
                QCoreApplication.translate(
                    "HistoryDetailDialog", "<b>Error:</b> {error}"
                ).format(error=self.record.transcription_error)
            )

        transcription_text = self.record.transcription_text or ""
        self.trans_text_edit.setPlainText(
            transcription_text
            or QCoreApplication.translate("HistoryDetailDialog", "(empty)")
        )

        if self.record.ai_status:
            ai_status_label = self._status_display(self.record.ai_status)
            ai_status_text = QCoreApplication.translate(
                "HistoryDetailDialog", "AI {status}"
            ).format(status=ai_status_label)
        else:
            ai_status_text = QCoreApplication.translate(
                "HistoryDetailDialog", "AI Status Unknown"
            )

        self.optimized_group.setTitle(
            QCoreApplication.translate(
                "HistoryDetailDialog", "Optimized Text ({status})"
            ).format(status=ai_status_text)
        )

        if self.ai_provider_label:
            self.ai_provider_label.setText(
                QCoreApplication.translate(
                    "HistoryDetailDialog", "<b>AI Provider:</b> {provider}"
                ).format(provider=self.record.ai_provider)
            )
        if self.ai_error_label:
            self.ai_error_label.setText(
                QCoreApplication.translate(
                    "HistoryDetailDialog", "<b>Error:</b> {error}"
                ).format(error=self.record.ai_error)
            )

        if self.record.ai_status == "success" and self.record.ai_optimized_text:
            display_text = self.record.ai_optimized_text
        else:
            display_text = QCoreApplication.translate(
                "HistoryDetailDialog",
                "{text}\n\n(Using original transcription - AI {status})",
            ).format(
                text=self.record.transcription_text or "",
                status=self.record.ai_status
                or QCoreApplication.translate("HistoryDetailDialog", "Unknown"),
            )

        self.optimized_text_edit.setPlainText(
            display_text or QCoreApplication.translate("HistoryDetailDialog", "(empty)")
        )

        self.copy_button.setText(
            QCoreApplication.translate("HistoryDetailDialog", "Copy to Clipboard")
        )
        self.retry_button.setText(
            QCoreApplication.translate("HistoryDetailDialog", "Retry")
        )
        self.delete_button.setText(
            QCoreApplication.translate("HistoryDetailDialog", "Delete Record")
        )
        self.close_button.setText(
            QCoreApplication.translate("HistoryDetailDialog", "Close")
        )

    def _copy_to_clipboard(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.optimized_text_edit.toPlainText())
        QMessageBox.information(
            self,
            QCoreApplication.translate("HistoryDetailDialog", "Success"),
            QCoreApplication.translate(
                "HistoryDetailDialog", "Text copied to clipboard!"
            ),
        )

    def _retry_processing(self):
        from ...utils import app_logger

        transcription_service = self._get_runtime_transcription_service()
        ai_processing_controller = self._get_runtime_ai_processing_controller()

        app_logger.log_audio_event(
            "Retry processing requested",
            {
                "has_transcription_service": transcription_service is not None,
                "has_config_service": self.settings_service is not None,
                "has_ai_controller": ai_processing_controller is not None,
                "transcription_service_type": type(transcription_service).__name__
                if transcription_service
                else "None",
            },
        )

        if not transcription_service or not self.settings_service:
            QMessageBox.warning(
                self,
                QCoreApplication.translate(
                    "HistoryDetailDialog", "Service Unavailable"
                ),
                QCoreApplication.translate(
                    "HistoryDetailDialog",
                    "Retry processing requires transcription service.\n\n"
                    "This feature may not be available in this context.",
                ),
            )
            return

        reply = QMessageBox.question(
            self,
            QCoreApplication.translate("HistoryDetailDialog", "Retry Processing"),
            QCoreApplication.translate(
                "HistoryDetailDialog",
                "This will reprocess the recording using current configuration.\n\n"
                "- Transcription will use current provider/model\n"
                "- AI optimization will use current settings\n\n"
                "A new history record will be created.\n"
                "The original record will be kept for comparison.\n\n"
                "Continue?",
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        self.progress_dialog = QProgressDialog(
            QCoreApplication.translate(
                "HistoryDetailDialog", "Initializing reprocessing..."
            ),
            QCoreApplication.translate("HistoryDetailDialog", "Cancel"),
            0,
            0,
            self,
        )
        self.progress_dialog.setWindowTitle(
            QCoreApplication.translate("HistoryDetailDialog", "Reprocessing Recording")
        )
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setValue(0)
        self.progress_dialog.show()

        self.reprocessing_worker = ReprocessingWorker(
            record_id=self.record.id,
            audio_file_path=self.record.audio_file_path,
            transcription_service=transcription_service,
            ai_processing_controller=ai_processing_controller,
            config_service=self.settings_service,
            history_service=self.history_service,
        )

        self.reprocessing_worker.progress_updated.connect(self._on_progress_updated)
        self.reprocessing_worker.reprocessing_completed.connect(
            self._on_reprocessing_completed
        )
        self.reprocessing_worker.reprocessing_failed.connect(
            self._on_reprocessing_failed
        )
        self.progress_dialog.canceled.connect(self._on_reprocessing_canceled)
        self.reprocessing_worker.start()

    def _on_progress_updated(self, message: str):
        if self.progress_dialog:
            self.progress_dialog.setLabelText(message)

    def _on_reprocessing_completed(self, result: dict):
        from ...utils import app_logger

        if not self.isVisible():
            app_logger.log_audio_event(
                "Reprocessing completed but dialog no longer visible",
                {"result": result},
            )
            return

        try:
            if self.progress_dialog:
                try:
                    self.progress_dialog.canceled.disconnect(
                        self._on_reprocessing_canceled
                    )
                except RuntimeError:
                    pass
                self.progress_dialog.close()
                self.progress_dialog = None

            transcription_text = result.get("transcription_text", "")
            ai_optimized_text = result.get("ai_optimized_text", "")
            final_text = result.get("final_text", "")
            ai_status = result.get("ai_status", "skipped")
            new_record_id = result.get("new_record_id")

            if new_record_id:
                fresh_record = self.history_service.get_record_by_id(new_record_id)
                if fresh_record:
                    self.record = fresh_record

            if self.reprocessing_worker:
                if self.reprocessing_worker.isRunning():
                    self.reprocessing_worker.wait(1000)
                self.reprocessing_worker = None

            if not new_record_id or self.record.id != new_record_id:
                self.record.transcription_text = transcription_text
                self.record.ai_optimized_text = ai_optimized_text
                self.record.final_text = final_text
                self.record.ai_status = ai_status
                self.record.transcription_provider = result.get(
                    "transcription_provider", self.record.transcription_provider
                )
                self.record.streaming_mode = result.get(
                    "streaming_mode", self.record.streaming_mode
                )
                self.record.transcription_duration = result.get(
                    "transcription_duration", self.record.transcription_duration
                )
                self.record.used_fallback = result.get(
                    "used_fallback", self.record.used_fallback
                )
                self.record.fallback_type = result.get(
                    "fallback_type", self.record.fallback_type
                )
                self.record.fallback_reason = result.get(
                    "fallback_reason", self.record.fallback_reason
                )
                self.record.diagnostics_collected = result.get(
                    "diagnostics_collected", self.record.diagnostics_collected
                )
            self.retranslate_ui()

            QMessageBox.information(
                self,
                QCoreApplication.translate(
                    "HistoryDetailDialog", "Reprocessing Complete"
                ),
                QCoreApplication.translate(
                    "HistoryDetailDialog",
                    "Recording has been successfully reprocessed!\n\n"
                    "New Record ID: {record_id}\n"
                    "Transcription Provider: {provider}\n"
                    "AI Status: {status}\n\n"
                    "Original record was preserved for diagnostics.",
                ).format(
                    record_id=(new_record_id or self.record.id)[:12],
                    provider=result.get(
                        "transcription_provider",
                        QCoreApplication.translate("HistoryDetailDialog", "N/A"),
                    ),
                    status=ai_status,
                ),
            )
        except Exception as e:
            app_logger.log_error(e, "reprocessing_completed_handler")

    def _on_reprocessing_failed(self, error_message: str):
        from ...utils import app_logger

        if not self.isVisible():
            app_logger.log_audio_event(
                "Reprocessing failed but dialog no longer visible",
                {"error": error_message},
            )
            return

        try:
            if self.progress_dialog:
                try:
                    self.progress_dialog.canceled.disconnect(
                        self._on_reprocessing_canceled
                    )
                except RuntimeError:
                    pass
                self.progress_dialog.close()
                self.progress_dialog = None

            if self.reprocessing_worker:
                if self.reprocessing_worker.isRunning():
                    self.reprocessing_worker.wait(1000)
                self.reprocessing_worker = None

            QMessageBox.critical(
                self,
                QCoreApplication.translate(
                    "HistoryDetailDialog", "Reprocessing Failed"
                ),
                QCoreApplication.translate(
                    "HistoryDetailDialog",
                    "Failed to reprocess the recording:\n\n{error}\n\n"
                    "Please check the logs for more details.",
                ).format(error=error_message),
            )
        except Exception as e:
            app_logger.log_error(e, "reprocessing_failed_handler")

    def _on_reprocessing_canceled(self):
        if self.reprocessing_worker:
            self.reprocessing_worker.stop()
            self.reprocessing_worker.wait(2000)

            if self.reprocessing_worker.isRunning():
                self.reprocessing_worker.terminate()
                self.reprocessing_worker.wait()

            self.reprocessing_worker = None

        QMessageBox.information(
            self,
            QCoreApplication.translate("HistoryDetailDialog", "Reprocessing Canceled"),
            QCoreApplication.translate(
                "HistoryDetailDialog", "Reprocessing operation has been canceled."
            ),
        )

    def _delete_record(self):
        reply = QMessageBox.question(
            self,
            QCoreApplication.translate("HistoryDetailDialog", "Delete Record"),
            QCoreApplication.translate(
                "HistoryDetailDialog",
                "Are you sure you want to delete this record?\n\nTime: {time}",
            ).format(time=self.record.timestamp.strftime("%Y-%m-%d %H:%M:%S")),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                success = self.history_service.delete_record(self.record.id)
                if success:
                    QMessageBox.information(
                        self,
                        QCoreApplication.translate("HistoryDetailDialog", "Success"),
                        QCoreApplication.translate(
                            "HistoryDetailDialog", "Record deleted successfully!"
                        ),
                    )
                    self.accept()
                else:
                    QMessageBox.warning(
                        self,
                        QCoreApplication.translate("HistoryDetailDialog", "Warning"),
                        QCoreApplication.translate(
                            "HistoryDetailDialog", "Failed to delete record."
                        ),
                    )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    QCoreApplication.translate("HistoryDetailDialog", "Error"),
                    QCoreApplication.translate(
                        "HistoryDetailDialog", "Error deleting record: {error}"
                    ).format(error=str(e)),
                )
