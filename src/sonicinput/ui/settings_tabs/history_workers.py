"""Background workers and helpers for history reprocessing flows."""

import time
import uuid
from datetime import datetime
from typing import List, Optional

from PySide6.QtCore import QCoreApplication, QThread, Signal

from ...core.interfaces import HistoryRecord


def build_reprocessed_record(
    source_record: HistoryRecord,
    transcription_text: str,
    transcription_provider: str,
    transcription_status: str,
    transcription_duration: float,
    ai_optimized_text: Optional[str],
    ai_provider: Optional[str],
    ai_status: str,
    ai_error: Optional[str],
    final_text: str,
    transcription_error: Optional[str] = None,
) -> HistoryRecord:
    """Create a new history record for a reprocessing attempt."""
    return HistoryRecord(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(),
        audio_file_path=source_record.audio_file_path,
        duration=source_record.duration,
        transcription_text=transcription_text,
        transcription_provider=transcription_provider,
        transcription_status=transcription_status,
        streaming_mode="disabled",
        transcription_duration=max(0.0, float(transcription_duration)),
        used_fallback=False,
        fallback_type="none",
        fallback_reason=None,
        diagnostics_collected=True,
        reprocess_parent_id=source_record.id,
        transcription_error=transcription_error,
        ai_optimized_text=ai_optimized_text,
        ai_provider=ai_provider,
        ai_status=ai_status,
        ai_error=ai_error,
        final_text=final_text,
    )


class ReprocessingWorker(QThread):
    """Background worker for reprocessing a single history record."""

    progress_updated = Signal(str)
    reprocessing_completed = Signal(dict)
    reprocessing_failed = Signal(str)

    def __init__(
        self,
        record_id: str,
        audio_file_path: str,
        transcription_service,
        ai_processing_controller,
        config_service,
        history_service,
    ):
        super().__init__()
        self.record_id = record_id
        self.audio_file_path = audio_file_path
        self.transcription_service = transcription_service
        self.ai_processing_controller = ai_processing_controller
        self.config_service = config_service
        self.history_service = history_service
        self.should_stop = False

    def run(self):
        """Execute the reprocessing flow in the background."""
        try:
            from ...audio.recorder import AudioRecorder
            from ...utils import app_logger

            self.progress_updated.emit(
                QCoreApplication.translate("HistoryTab", "Loading audio file...")
            )

            if not self.audio_file_path:
                self.reprocessing_failed.emit(
                    QCoreApplication.translate(
                        "HistoryTab", "Audio file path not found in record"
                    )
                )
                return

            try:
                audio_data = AudioRecorder.load_audio_from_file(self.audio_file_path)
                if audio_data is None or len(audio_data) == 0:
                    self.reprocessing_failed.emit(
                        QCoreApplication.translate(
                            "HistoryTab", "Failed to load audio data from file"
                        )
                    )
                    return
            except FileNotFoundError:
                self.reprocessing_failed.emit(
                    QCoreApplication.translate(
                        "HistoryTab", "Audio file not found: {path}"
                    ).format(path=self.audio_file_path)
                )
                return
            except Exception as e:
                self.reprocessing_failed.emit(
                    QCoreApplication.translate(
                        "HistoryTab", "Error loading audio file: {error}"
                    ).format(error=str(e))
                )
                return

            if self.should_stop:
                return

            self.progress_updated.emit(
                QCoreApplication.translate("HistoryTab", "Transcribing audio...")
            )

            try:
                transcription_provider = self.config_service.get_setting(
                    "transcription.provider", "local"
                )
                if transcription_provider == "local":
                    language = self.config_service.get_setting(
                        "transcription.local.language", "zh"
                    )
                else:
                    language = "auto"

                transcribe_start = time.time()
                transcription_result = self.transcription_service.transcribe_sync(
                    audio_data=audio_data,
                    language=language if language != "auto" else None,
                    temperature=0.0,
                )
                transcription_duration = time.time() - transcribe_start

                if not transcription_result.get("success", True):
                    error_msg = transcription_result.get(
                        "error",
                        QCoreApplication.translate(
                            "HistoryTab", "Unknown transcription error"
                        ),
                    )
                    self.reprocessing_failed.emit(
                        QCoreApplication.translate(
                            "HistoryTab", "Transcription failed: {error}"
                        ).format(error=error_msg)
                    )
                    return

                transcription_text = transcription_result.get("text", "")
                if not transcription_text.strip():
                    self.reprocessing_failed.emit(
                        QCoreApplication.translate(
                            "HistoryTab", "Transcription returned empty text"
                        )
                    )
                    return
            except Exception as e:
                app_logger.log_error(e, "reprocessing_transcription")
                self.reprocessing_failed.emit(
                    QCoreApplication.translate(
                        "HistoryTab", "Transcription error: {error}"
                    ).format(error=str(e))
                )
                return

            if self.should_stop:
                return

            ai_enabled = self.config_service.get_setting("ai.enabled", False)
            ai_optimized_text = None
            ai_provider = None
            ai_status = "skipped"
            ai_error = None

            if ai_enabled and transcription_text.strip():
                self.progress_updated.emit(
                    QCoreApplication.translate("HistoryTab", "Optimizing with AI...")
                )
                if not self.ai_processing_controller:
                    ai_status = "skipped"
                    ai_error = QCoreApplication.translate(
                        "HistoryTab", "AI processing controller not available"
                    )
                    ai_optimized_text = ""
                    app_logger.log_audio_event(
                        "Retry processing: AI controller not available, skipping AI optimization",
                        {"ai_enabled": ai_enabled},
                    )
                else:
                    try:
                        ai_optimized_text = (
                            self.ai_processing_controller.process_with_ai(
                                transcription_text,
                                record_id="",
                            )
                        )
                        ai_provider = self.config_service.get_setting(
                            "ai.provider", "groq"
                        )

                        if ai_optimized_text and ai_optimized_text.strip():
                            ai_status = "success"
                        else:
                            ai_status = "failed"
                            ai_error = QCoreApplication.translate(
                                "HistoryTab", "AI returned empty text"
                            )
                    except Exception as e:
                        app_logger.log_error(e, "reprocessing_ai_optimization")
                        ai_status = "failed"
                        ai_error = str(e)
                        ai_optimized_text = None

            if self.should_stop:
                return

            self.progress_updated.emit(
                QCoreApplication.translate("HistoryTab", "Saving reprocessed record...")
            )

            final_text = (
                ai_optimized_text
                if ai_status == "success" and ai_optimized_text
                else transcription_text
            )

            source_record = self.history_service.get_record_by_id(self.record_id)
            if not source_record:
                self.reprocessing_failed.emit(
                    QCoreApplication.translate(
                        "HistoryTab", "Record not found: {record_id}"
                    ).format(record_id=self.record_id)
                )
                return

            new_record = build_reprocessed_record(
                source_record=source_record,
                transcription_text=transcription_text,
                transcription_provider=transcription_provider,
                transcription_status="success",
                transcription_duration=transcription_duration,
                ai_optimized_text=ai_optimized_text,
                ai_provider=ai_provider,
                ai_status=ai_status,
                ai_error=ai_error,
                final_text=final_text,
                transcription_error=None,
            )

            try:
                if not self.history_service.save_record(new_record):
                    self.reprocessing_failed.emit(
                        QCoreApplication.translate(
                            "HistoryTab",
                            "Failed to save reprocessed record to history database",
                        )
                    )
                    return
            except Exception as e:
                app_logger.log_error(e, "reprocessing_update_record")
                self.reprocessing_failed.emit(
                    QCoreApplication.translate(
                        "HistoryTab",
                        "Failed to save reprocessed history record: {error}",
                    ).format(error=str(e))
                )
                return

            self.reprocessing_completed.emit(
                {
                    "transcription_text": transcription_text,
                    "ai_optimized_text": ai_optimized_text,
                    "final_text": final_text,
                    "ai_status": ai_status,
                    "transcription_provider": transcription_provider,
                    "streaming_mode": "disabled",
                    "transcription_duration": transcription_duration,
                    "used_fallback": False,
                    "fallback_type": "none",
                    "fallback_reason": None,
                    "diagnostics_collected": True,
                    "new_record_id": new_record.id,
                }
            )
        except Exception as e:
            from ...utils import app_logger

            app_logger.log_error(e, "reprocessing_worker")
            self.reprocessing_failed.emit(
                QCoreApplication.translate(
                    "HistoryTab", "Unexpected error: {error}"
                ).format(error=str(e))
            )

    def stop(self):
        """Request cancellation."""
        self.should_stop = True


class BatchReprocessingWorker(QThread):
    """Background worker for batch history reprocessing."""

    progress_updated = Signal(int, int, str)
    batch_completed = Signal(dict)
    record_processed = Signal(str, bool)

    def __init__(
        self,
        total_records: int,
        cd_seconds: int,
        transcription_service,
        ai_processing_controller,
        config_service,
        history_service,
        page_size: int = 500,
    ):
        super().__init__()
        self.total_records = total_records
        self.page_size = page_size
        self.cd_seconds = cd_seconds
        self.transcription_service = transcription_service
        self.ai_processing_controller = ai_processing_controller
        self.config_service = config_service
        self.history_service = history_service
        self.should_stop = False
        self.stats = {"total": 0, "success": 0, "skipped": 0, "failed": 0, "errors": []}

    def run(self):
        """Execute batch reprocessing."""
        from ...utils import app_logger

        total_records = max(int(self.total_records or 0), 0)
        self.stats["total"] = total_records

        processed = 0
        page_size = max(int(self.page_size or 0), 1)
        page_cursor_timestamp: Optional[datetime] = None
        page_cursor_id: Optional[str] = None
        pending_records: List[HistoryRecord] = []
        pending_source_ids: List[str] = []

        while not self.should_stop and processed < total_records:
            records = self.history_service.get_records_keyset(
                limit=page_size,
                cursor_timestamp=page_cursor_timestamp,
                cursor_id=page_cursor_id,
                order="ASC",
            )
            if not records:
                break

            last_seen_timestamp: Optional[datetime] = None
            last_seen_id: Optional[str] = None

            for record in records:
                if self.should_stop or processed >= total_records:
                    break

                processed += 1
                last_seen_timestamp = record.timestamp
                last_seen_id = record.id
                self.progress_updated.emit(processed, total_records, record.id)

                new_record = self._process_single_record(record)
                if new_record is None:
                    self.record_processed.emit(record.id, False)
                else:
                    pending_records.append(new_record)
                    pending_source_ids.append(record.id)
                    if len(pending_records) >= page_size:
                        self._flush_pending_records(pending_records, pending_source_ids)

                if processed < total_records and self.cd_seconds > 0:
                    time.sleep(self.cd_seconds)

            if last_seen_timestamp is None or last_seen_id is None:
                break
            page_cursor_timestamp = last_seen_timestamp
            page_cursor_id = last_seen_id

        self._flush_pending_records(pending_records, pending_source_ids)

        if self.should_stop:
            app_logger.log_audio_event(
                "Batch reprocessing cancelled by user",
                {"processed": processed, "total": total_records},
            )

        self.batch_completed.emit(self.stats)

    def _flush_pending_records(
        self, pending_records: List[HistoryRecord], pending_source_ids: List[str]
    ) -> None:
        """Flush buffered reprocessed records to storage."""
        if not pending_records:
            return

        from ...utils import app_logger

        try:
            saved_count = self.history_service.save_records_batch(pending_records)
            if saved_count == len(pending_records):
                self.stats["success"] += saved_count
                for source_id in pending_source_ids:
                    self.record_processed.emit(source_id, True)
            else:
                for source_id in pending_source_ids:
                    self.stats["failed"] += 1
                    self.stats["errors"].append(
                        QCoreApplication.translate(
                            "HistoryTab",
                            "[FAIL] {record_id}: Failed to save reprocessed record",
                        ).format(record_id=source_id)
                    )
                    self.record_processed.emit(source_id, False)
        except Exception as e:
            app_logger.log_error(e, "batch_reprocessing_batch_save")
            for source_id in pending_source_ids:
                self.stats["failed"] += 1
                self.stats["errors"].append(
                    QCoreApplication.translate(
                        "HistoryTab",
                        "[FAIL] {record_id}: Database save failed - {error}",
                    ).format(record_id=source_id, error=str(e))
                )
                self.record_processed.emit(source_id, False)
        finally:
            pending_records.clear()
            pending_source_ids.clear()

    def _process_single_record(self, record) -> Optional[HistoryRecord]:
        """Process a single history record."""
        from ...audio.recorder import AudioRecorder
        from ...utils import app_logger

        try:
            audio_file_path = record.audio_file_path
            if not audio_file_path:
                self.stats["skipped"] += 1
                self.stats["errors"].append(
                    QCoreApplication.translate(
                        "HistoryTab", "[SKIP] {record_id}: No audio file path"
                    ).format(record_id=record.id)
                )
                return None

            try:
                audio_data = AudioRecorder.load_audio_from_file(audio_file_path)
                if audio_data is None or len(audio_data) == 0:
                    self.stats["skipped"] += 1
                    self.stats["errors"].append(
                        QCoreApplication.translate(
                            "HistoryTab", "[SKIP] {record_id}: Failed to load audio"
                        ).format(record_id=record.id)
                    )
                    return None
            except FileNotFoundError:
                self.stats["skipped"] += 1
                self.stats["errors"].append(
                    QCoreApplication.translate(
                        "HistoryTab", "[SKIP] {record_id}: Audio file not found"
                    ).format(record_id=record.id)
                )
                return None
            except Exception as e:
                self.stats["skipped"] += 1
                self.stats["errors"].append(
                    QCoreApplication.translate(
                        "HistoryTab",
                        "[SKIP] {record_id}: Error loading audio - {error}",
                    ).format(record_id=record.id, error=str(e))
                )
                return None

            try:
                transcription_provider = self.config_service.get_setting(
                    "transcription.provider", "local"
                )
                if transcription_provider == "local":
                    language = self.config_service.get_setting(
                        "transcription.local.language", "zh"
                    )
                else:
                    language = "auto"

                transcribe_start = time.time()
                transcription_result = self.transcription_service.transcribe_sync(
                    audio_data=audio_data,
                    language=language if language != "auto" else None,
                    temperature=0.0,
                )
                transcription_duration = time.time() - transcribe_start

                if not transcription_result.get("success", True):
                    error_msg = transcription_result.get(
                        "error",
                        QCoreApplication.translate("HistoryTab", "Unknown error"),
                    )
                    self.stats["failed"] += 1
                    self.stats["errors"].append(
                        QCoreApplication.translate(
                            "HistoryTab",
                            "[FAIL] {record_id}: Transcription failed - {error}",
                        ).format(record_id=record.id, error=error_msg)
                    )
                    return None

                transcription_text = transcription_result.get("text", "")
                if not transcription_text.strip():
                    self.stats["failed"] += 1
                    self.stats["errors"].append(
                        QCoreApplication.translate(
                            "HistoryTab", "[FAIL] {record_id}: Empty transcription"
                        ).format(record_id=record.id)
                    )
                    return None
            except Exception as e:
                app_logger.log_error(e, "batch_reprocessing_transcription")
                self.stats["failed"] += 1
                self.stats["errors"].append(
                    QCoreApplication.translate(
                        "HistoryTab",
                        "[FAIL] {record_id}: Transcription error - {error}",
                    ).format(record_id=record.id, error=str(e))
                )
                return None

            ai_enabled = self.config_service.get_setting("ai.enabled", False)
            ai_optimized_text = None
            ai_provider = None
            ai_status = "skipped"
            ai_error = None

            if ai_enabled and transcription_text.strip():
                if not self.ai_processing_controller:
                    ai_status = "skipped"
                    ai_error = QCoreApplication.translate(
                        "HistoryTab", "AI controller not available"
                    )
                else:
                    try:
                        ai_optimized_text = (
                            self.ai_processing_controller.process_with_ai(
                                transcription_text, record_id=""
                            )
                        )
                        ai_provider = self.config_service.get_setting(
                            "ai.provider", "groq"
                        )

                        if ai_optimized_text and ai_optimized_text.strip():
                            ai_status = "success"
                        else:
                            ai_status = "failed"
                            ai_error = QCoreApplication.translate(
                                "HistoryTab", "AI returned empty text"
                            )
                    except Exception as e:
                        app_logger.log_error(e, "batch_reprocessing_ai")
                        ai_status = "failed"
                        ai_error = str(e)

            final_text = (
                ai_optimized_text
                if ai_status == "success" and ai_optimized_text
                else transcription_text
            )

            return build_reprocessed_record(
                source_record=record,
                transcription_text=transcription_text,
                transcription_provider=transcription_provider,
                transcription_status="success",
                transcription_duration=transcription_duration,
                ai_optimized_text=ai_optimized_text,
                ai_provider=ai_provider,
                ai_status=ai_status,
                ai_error=ai_error,
                final_text=final_text,
                transcription_error=None,
            )
        except Exception as e:
            from ...utils import app_logger

            app_logger.log_error(e, "batch_reprocessing_worker")
            self.stats["failed"] += 1
            self.stats["errors"].append(
                QCoreApplication.translate(
                    "HistoryTab",
                    "[FAIL] {record_id}: Unexpected error - {error}",
                ).format(record_id=record.id, error=str(e))
            )
            return None

    def stop(self):
        """Request cancellation."""
        self.should_stop = True


class HistoryStatsWorker(QThread):
    """Async history statistics query worker."""

    stats_ready = Signal(dict)
    stats_failed = Signal(dict)

    def __init__(self, history_service, query: Optional[str], request_id: int):
        super().__init__()
        self.history_service = history_service
        self.query = query
        self.request_id = request_id

    def run(self):
        try:
            if self.isInterruptionRequested():
                return

            total_count, total_duration, success_count = (
                self.history_service.get_aggregate_stats(query=self.query)
            )

            if self.isInterruptionRequested():
                return

            self.stats_ready.emit(
                {
                    "request_id": self.request_id,
                    "total_count": int(total_count),
                    "total_duration": float(total_duration),
                    "success_count": int(success_count),
                }
            )
        except Exception as e:
            if self.isInterruptionRequested():
                return
            self.stats_failed.emit({"request_id": self.request_id, "error": str(e)})
