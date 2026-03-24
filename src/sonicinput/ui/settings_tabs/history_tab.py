"""历史记录标签页"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QCoreApplication, QThread, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .base_tab import BaseSettingsTab
from .history_detail_dialog import HistoryDetailDialog
from .history_workers import (
    BatchReprocessingWorker,
    HistoryStatsWorker,
)


class HistoryTab(BaseSettingsTab):
    """历史记录标签页

    显示所有录音历史记录，包括：
    - 录音时间
    - 时长
    - 转录结果
    - AI优化状态
    - 最终文本

    功能：
    - 查看详情
    - 删除记录
    - 搜索过滤
    - 刷新列表
    - 重新处理录音
    """

    def __init__(
        self,
        config_manager,
        parent_window,
    ):
        super().__init__(config_manager, parent_window)
        self.history_service = None  # 延迟初始化
        self.current_records: List[Any] = []  # 当前显示的记录列表
        self.batch_worker = None  # 批量处理Worker
        self.batch_progress_dialog = None  # 批量处理进度对话框
        self._search_debounce_timer: Optional[QTimer] = None
        self._stats_worker: Optional[HistoryStatsWorker] = None
        self._stats_request_id = 0

        # History pagination (keeps UI responsive for large history)
        self._page_size = 200
        self._page_cursor_timestamp: Optional[datetime] = None
        self._page_cursor_id: Optional[str] = None
        self._has_more_pages = True
        self._is_loading_page = False
        self._active_query = ""

        from ...utils import app_logger

        app_logger.log_audio_event(
            "HistoryTab initialized with UISettingsService facade",
            {},
        )

    def _setup_ui(self) -> None:
        """设置UI"""
        layout = QVBoxLayout(self.widget)

        # 顶部工具栏
        toolbar_layout = QHBoxLayout()

        # 搜索框
        self.search_label = QLabel("Search:")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search in transcription or AI text...")
        self.search_input.textChanged.connect(self._on_search_changed)
        toolbar_layout.addWidget(self.search_label)
        toolbar_layout.addWidget(self.search_input, stretch=1)

        # 刷新按钮
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self._load_history)
        toolbar_layout.addWidget(self.refresh_button)

        # 批量重新处理按钮
        self.batch_reprocess_button = QPushButton("Batch Reprocess")
        self.batch_reprocess_button.clicked.connect(self._on_batch_reprocess_clicked)
        self.batch_reprocess_button.setToolTip(
            "Re-transcribe all history records with customizable cooldown delay"
        )
        toolbar_layout.addWidget(self.batch_reprocess_button)

        layout.addLayout(toolbar_layout)

        # 历史记录表格
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(4)
        self.history_table.setHorizontalHeaderLabels(
            [
                "Time",
                "LEN",
                "Transcription",
                "Status",
            ]
        )

        # 表格设置
        self.history_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.history_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.setAlternatingRowColors(True)

        # 双击打开详情
        self.history_table.doubleClicked.connect(self._on_row_double_clicked)
        self.history_table.verticalScrollBar().valueChanged.connect(
            self._on_history_table_scrolled
        )

        # 列宽设置
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)  # Time
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)  # Length
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # Transcription
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)  # AI Status

        # 设置固定列宽
        self.history_table.setColumnWidth(0, 110)  # Time: MM-DD HH:MM 格式
        self.history_table.setColumnWidth(1, 70)  # Length
        self.history_table.setColumnWidth(3, 90)  # Status

        layout.addWidget(self.history_table)

        # 底部统计信息
        stats_group = QGroupBox("Statistics")
        stats_layout = QHBoxLayout(stats_group)
        self.stats_group = stats_group

        self.total_records_label = QLabel("Total Records: 0")
        self.total_duration_label = QLabel("Total Duration: 0.0s")
        self.success_rate_label = QLabel("Success Rate: 0%")

        stats_layout.addWidget(self.total_records_label)
        stats_layout.addWidget(self.total_duration_label)
        stats_layout.addWidget(self.success_rate_label)
        stats_layout.addStretch()

        layout.addWidget(stats_group)

        # Debounce search to avoid querying on every keypress
        self._search_debounce_timer = QTimer(self.widget)
        self._search_debounce_timer.setSingleShot(True)
        self._search_debounce_timer.setInterval(250)
        self._search_debounce_timer.timeout.connect(self._load_history)
        self.retranslate_ui()

        # 保存控件引用
        self.controls = {
            "history_table": self.history_table,
            "search_input": self.search_input,
            "refresh_button": self.refresh_button,
        }

    def retranslate_ui(self) -> None:
        """Update UI text for the current language."""
        self.search_label.setText(QCoreApplication.translate("HistoryTab", "Search:"))
        self.search_input.setPlaceholderText(
            QCoreApplication.translate(
                "HistoryTab", "Search in transcription or AI text..."
            )
        )
        self.refresh_button.setText(QCoreApplication.translate("HistoryTab", "Refresh"))
        self.batch_reprocess_button.setText(
            QCoreApplication.translate("HistoryTab", "Batch Reprocess")
        )
        self.batch_reprocess_button.setToolTip(
            QCoreApplication.translate(
                "HistoryTab",
                "Re-transcribe all history records with customizable cooldown delay",
            )
        )
        self.history_table.setHorizontalHeaderLabels(
            [
                QCoreApplication.translate("HistoryTab", "Time"),
                QCoreApplication.translate("HistoryTab", "LEN"),
                QCoreApplication.translate("HistoryTab", "Transcription"),
                QCoreApplication.translate("HistoryTab", "Status"),
            ]
        )
        self.stats_group.setTitle(
            QCoreApplication.translate("HistoryTab", "Statistics")
        )
        self._update_statistics()

    def _get_history_service(self):
        """获取HistoryStorageService实例

        通过UISettingsService facade访问
        """
        if self.history_service is None:
            try:
                self.history_service = self.config_manager.get_history_service()
                if self.history_service is None:
                    from ...utils import app_logger

                    app_logger.warning(
                        "HistoryStorageService not available from config_manager"
                    )
            except Exception as e:
                from ...utils import app_logger

                app_logger.log_error(e, "Failed to get HistoryStorageService")
                return None

        return self.history_service

    def _load_history(self) -> None:
        """加载历史记录（分页，支持无限滚动）"""
        service = self._get_history_service()
        if not service:
            QMessageBox.warning(
                self.parent_window,
                QCoreApplication.translate("HistoryTab", "Error"),
                QCoreApplication.translate(
                    "HistoryTab",
                    "History service not available. Please restart the application.",
                ),
            )
            return

        try:
            self._reset_pagination()

            # Load first page
            self._load_next_page()

            # 更新统计信息（基于数据库全量数据）
            self._update_statistics()

        except Exception as e:
            QMessageBox.critical(
                self.parent_window,
                QCoreApplication.translate("HistoryTab", "Error"),
                QCoreApplication.translate(
                    "HistoryTab", "Failed to load history: {error}"
                ).format(error=str(e)),
            )

    def _reset_pagination(self) -> None:
        """重置分页状态并清空表格"""
        self._page_cursor_timestamp = None
        self._page_cursor_id = None
        self._has_more_pages = True
        self._is_loading_page = False
        self._active_query = self.search_input.text().strip()

        self.current_records = []
        self.history_table.setRowCount(0)
        self.history_table.scrollToTop()

    def _load_next_page(self) -> None:
        """加载下一页并追加到表格"""
        if self._is_loading_page or not self._has_more_pages:
            return

        service = self._get_history_service()
        if not service:
            return

        self._is_loading_page = True
        try:
            query = self._active_query
            if query:
                page_records = service.search_records_keyset(
                    query=query,
                    limit=self._page_size,
                    cursor_timestamp=self._page_cursor_timestamp,
                    cursor_id=self._page_cursor_id,
                )
            else:
                page_records = service.get_records_keyset(
                    limit=self._page_size,
                    cursor_timestamp=self._page_cursor_timestamp,
                    cursor_id=self._page_cursor_id,
                )

            if not page_records:
                self._has_more_pages = False
                return

            self.current_records.extend(page_records)
            self._append_rows(page_records)

            last_record = page_records[-1]
            self._page_cursor_timestamp = last_record.timestamp
            self._page_cursor_id = last_record.id
            self._has_more_pages = len(page_records) >= self._page_size

        finally:
            self._is_loading_page = False

        # If the view isn't scrollable yet, auto-fetch more pages (until it is or no more data)
        QTimer.singleShot(0, self._ensure_table_scrollable)

    def _ensure_table_scrollable(self) -> None:
        if self._is_loading_page or not self._has_more_pages:
            return

        if self.history_table.verticalScrollBar().maximum() == 0:
            self._load_next_page()

    def _on_history_table_scrolled(self, value: int) -> None:
        """滚动接近底部时自动加载更多"""
        if self._is_loading_page or not self._has_more_pages:
            return

        scrollbar = self.history_table.verticalScrollBar()
        if value >= scrollbar.maximum() - 50:
            self._load_next_page()

    def _append_rows(self, records: List[Any]) -> None:
        """向表格追加多行"""
        if not records:
            return

        start_row = self.history_table.rowCount()
        self.history_table.setUpdatesEnabled(False)
        try:
            self.history_table.setRowCount(start_row + len(records))

            for row_offset, record in enumerate(records):
                row = start_row + row_offset

                # Time - 短格式：MM-DD HH:MM
                time_str = record.timestamp.strftime("%m-%d %H:%M")
                time_item = QTableWidgetItem(time_str)
                time_item.setToolTip(self._build_diagnostic_tooltip(record))
                self.history_table.setItem(row, 0, time_item)

                # Duration
                duration_str = f"{record.duration:.1f}s"
                self.history_table.setItem(row, 1, QTableWidgetItem(duration_str))

                # Transcription (full text with auto-ellipsis)
                trans_text = record.transcription_text or ""
                trans_item = QTableWidgetItem(trans_text)
                trans_item.setToolTip(trans_text)
                self.history_table.setItem(row, 2, trans_item)

                # AI Status - 居中对齐
                ai_status = self._get_ai_status_display(record)
                ai_item = QTableWidgetItem(ai_status)
                ai_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)  # 居中对齐
                if record.ai_status == "success":
                    ai_item.setForeground(Qt.GlobalColor.darkGreen)
                elif record.ai_status == "failed":
                    ai_item.setForeground(Qt.GlobalColor.red)
                elif record.ai_status == "skipped":
                    ai_item.setForeground(Qt.GlobalColor.gray)
                self.history_table.setItem(row, 3, ai_item)
        finally:
            self.history_table.setUpdatesEnabled(True)

    def _on_row_double_clicked(self, index) -> None:
        """双击行打开详情对话框"""
        row = index.row()
        if 0 <= row < len(self.current_records):
            record = self.current_records[row]
            self._show_detail_dialog(record)

    def _show_detail_dialog(self, record) -> None:
        """打开记录详情对话框"""
        service = self._get_history_service()
        if not service:
            QMessageBox.warning(
                self.parent_window,
                QCoreApplication.translate("HistoryTab", "Error"),
                QCoreApplication.translate(
                    "HistoryTab", "History service not available."
                ),
            )
            return

        dialog = HistoryDetailDialog(
            record=record,
            parent_window=self.parent_window,
            settings_service=self.config_manager,
            history_service=service,
            parent=self.parent_window,
        )

        result = dialog.exec()

        # 如果删除了记录或者进行了重处理，刷新列表
        if result == QDialog.DialogCode.Accepted:
            self._load_history()

    def _on_search_changed(self, text: str) -> None:
        """搜索文本变化时触发"""
        if self._search_debounce_timer is None:
            self._load_history()
            return

        # 重新加载（分页 + DB查询）
        self._search_debounce_timer.start()

    def _update_statistics(self) -> None:
        """异步更新统计信息，避免阻塞 UI 主线程。"""
        service = self._get_history_service()
        if not service:
            self._set_statistics_labels(0, 0.0, 0.0)
            return

        query = self._active_query or self.search_input.text().strip()
        query = query if query else None

        self._stats_request_id += 1
        request_id = self._stats_request_id

        if self._stats_worker and self._stats_worker.isRunning():
            self._stats_worker.requestInterruption()

        worker = HistoryStatsWorker(
            history_service=service,
            query=query,
            request_id=request_id,
        )
        worker.stats_ready.connect(self._on_statistics_ready)
        worker.stats_failed.connect(self._on_statistics_failed)
        worker.finished.connect(
            lambda _=None, finished_worker=worker: self._on_statistics_worker_finished(
                finished_worker
            )
        )
        self._stats_worker = worker
        worker.start()

    def _set_statistics_labels(
        self, total_count: int, total_duration: float, success_rate: float
    ) -> None:
        self.total_records_label.setText(
            QCoreApplication.translate("HistoryTab", "Total Records: {count}").format(
                count=total_count
            )
        )
        self.total_duration_label.setText(
            QCoreApplication.translate(
                "HistoryTab", "Total Duration: {seconds:.1f}s"
            ).format(seconds=total_duration)
        )
        self.success_rate_label.setText(
            QCoreApplication.translate(
                "HistoryTab", "Success Rate: {rate:.1f}%"
            ).format(rate=success_rate)
        )

    def _on_statistics_ready(self, payload: dict) -> None:
        request_id = int(payload.get("request_id", -1))
        if request_id != self._stats_request_id:
            return

        total_count = int(payload.get("total_count", 0))
        total_duration = float(payload.get("total_duration", 0.0))
        success_count = int(payload.get("success_count", 0))
        success_rate = (success_count / total_count * 100) if total_count > 0 else 0

        self._set_statistics_labels(total_count, total_duration, success_rate)

    def _on_statistics_failed(self, payload: dict) -> None:
        request_id = int(payload.get("request_id", -1))
        if request_id != self._stats_request_id:
            return
        self._set_statistics_labels(0, 0.0, 0.0)

    def _on_statistics_worker_finished(self, worker: QThread) -> None:
        if worker is self._stats_worker:
            self._stats_worker = None
        worker.deleteLater()

    @staticmethod
    def _truncate_text(text: str, max_length: int) -> str:
        """截断文本"""
        if not text:
            return ""
        if len(text) <= max_length:
            return text
        return text[:max_length] + "..."

    @staticmethod
    def _diagnostics_collected(record: Any) -> bool:
        return bool(getattr(record, "diagnostics_collected", False))

    @classmethod
    def _format_mode_for_table(cls, record: Any) -> str:
        if not cls._diagnostics_collected(record):
            return QCoreApplication.translate("HistoryTab", "Legacy")
        return str(getattr(record, "streaming_mode", "unknown") or "unknown")

    @classmethod
    def _format_transcribe_for_table(cls, record: Any) -> str:
        if not cls._diagnostics_collected(record):
            return QCoreApplication.translate("HistoryTab", "Legacy")
        seconds = float(getattr(record, "transcription_duration", 0.0) or 0.0)
        return f"{seconds:.2f}s"

    @classmethod
    def _format_fallback_for_table(cls, record: Any) -> str:
        if not cls._diagnostics_collected(record):
            return QCoreApplication.translate("HistoryTab", "Legacy")
        used_fallback = bool(getattr(record, "used_fallback", False))
        if not used_fallback:
            return QCoreApplication.translate("HistoryTab", "No")
        fallback_type = str(getattr(record, "fallback_type", "unknown") or "unknown")
        return QCoreApplication.translate("HistoryTab", "Yes ({type})").format(
            type=fallback_type
        )

    @classmethod
    def _build_diagnostic_tooltip(cls, record: Any) -> str:
        diagnostics_label = (
            QCoreApplication.translate("HistoryTab", "Captured")
            if cls._diagnostics_collected(record)
            else QCoreApplication.translate("HistoryTab", "Legacy defaults")
        )
        fallback_reason = getattr(
            record, "fallback_reason", None
        ) or QCoreApplication.translate("HistoryTab", "None")
        return (
            f"{record.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Provider: {record.transcription_provider or 'N/A'}\n"
            f"Diagnostics: {diagnostics_label}\n"
            f"Mode: {cls._format_mode_for_table(record)}\n"
            f"Transcribe: {cls._format_transcribe_for_table(record)}\n"
            f"Fallback: {cls._format_fallback_for_table(record)}\n"
            f"Fallback Reason: {fallback_reason}"
        )

    @staticmethod
    def _get_ai_status_display(record) -> str:
        """获取AI状态显示文本"""
        status_map = {
            "success": QCoreApplication.translate("HistoryTab", "Success"),
            "failed": QCoreApplication.translate("HistoryTab", "Failed"),
            "skipped": QCoreApplication.translate("HistoryTab", "Skipped"),
            "pending": QCoreApplication.translate("HistoryTab", "Pending"),
        }
        return status_map.get(
            record.ai_status, QCoreApplication.translate("HistoryTab", "Unknown")
        )

    def load_config(self, config: Dict[str, Any]) -> None:
        """从配置加载UI状态

        历史记录页面不需要从配置加载状态，
        而是在显示时动态加载数据
        """
        # 加载历史记录
        self._load_history()

    def save_config(self) -> Dict[str, Any]:
        """保存UI状态到配置

        历史记录页面不需要保存配置
        """
        return {}

    def _on_batch_reprocess_clicked(self) -> None:
        """处理批量重新处理按钮点击"""
        from ..dialogs.batch_reprocess_dialog import BatchReprocessDialog

        # 获取所有历史记录
        service = self._get_history_service()
        if not service:
            QMessageBox.warning(
                self.parent_window,
                QCoreApplication.translate("HistoryTab", "Error"),
                QCoreApplication.translate(
                    "HistoryTab",
                    "History service not available. Please restart the application.",
                ),
            )
            return

        try:
            total_records = service.get_total_count()
            if total_records <= 0:
                QMessageBox.information(
                    self.parent_window,
                    QCoreApplication.translate("HistoryTab", "No Records"),
                    QCoreApplication.translate(
                        "HistoryTab", "No history records found to reprocess."
                    ),
                )
                return

            # 显示配置对话框
            dialog = BatchReprocessDialog(total_records, self.parent_window)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return

            cd_seconds = dialog.get_cd_seconds()

            # 确认操作
            reply = QMessageBox.question(
                self.parent_window,
                QCoreApplication.translate("HistoryTab", "Confirm Batch Reprocessing"),
                QCoreApplication.translate(
                    "HistoryTab",
                    "You are about to re-transcribe {total} records.\n\n"
                    "Cooldown: {cooldown} seconds between records\n"
                    "Each successful retry will create a new history record.\n"
                    "Original records will be preserved.\n"
                    "This operation may take a long time and consume API quota.\n\n"
                    "Are you sure you want to continue?",
                ).format(total=total_records, cooldown=cd_seconds),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if reply != QMessageBox.StandardButton.Yes:
                return

            # 启动批量处理
            self._start_batch_reprocessing(total_records, cd_seconds)

        except Exception as e:
            QMessageBox.critical(
                self.parent_window,
                QCoreApplication.translate("HistoryTab", "Error"),
                QCoreApplication.translate(
                    "HistoryTab", "Failed to start batch reprocessing: {error}"
                ).format(error=str(e)),
            )

    def _start_batch_reprocessing(self, total_records: int, cd_seconds: int) -> None:
        """启动批量重新处理流程

        Args:
            total_records: 要处理的记录总数
            cd_seconds: CD时间（秒）
        """
        # 获取必要的服务
        transcription_service = self.config_manager.get_transcription_service()
        ai_processing_controller = self.config_manager.get_ai_processing_controller()
        history_service = self._get_history_service()

        if not transcription_service or not history_service:
            QMessageBox.critical(
                self.parent_window,
                QCoreApplication.translate("HistoryTab", "Error"),
                QCoreApplication.translate(
                    "HistoryTab",
                    "Required services not available. Please restart the application.",
                ),
            )
            return

        # 创建进度对话框
        self.batch_progress_dialog = QProgressDialog(
            QCoreApplication.translate("HistoryTab", "Starting batch reprocessing..."),
            QCoreApplication.translate("HistoryTab", "Cancel"),
            0,
            total_records,
            self.parent_window,
        )
        self.batch_progress_dialog.setWindowTitle(
            QCoreApplication.translate("HistoryTab", "Batch Reprocessing")
        )
        self.batch_progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.batch_progress_dialog.setMinimumDuration(0)
        self.batch_progress_dialog.setValue(0)

        # 创建Worker线程
        self.batch_worker = BatchReprocessingWorker(
            total_records=total_records,
            cd_seconds=cd_seconds,
            transcription_service=transcription_service,
            ai_processing_controller=ai_processing_controller,
            config_service=self.config_manager,
            history_service=history_service,
        )

        # 连接信号
        self.batch_worker.progress_updated.connect(self._on_batch_progress_updated)
        self.batch_worker.batch_completed.connect(self._on_batch_completed)
        self.batch_progress_dialog.canceled.connect(self._on_batch_canceled)

        # 启动Worker
        self.batch_worker.start()

    def _on_batch_progress_updated(
        self, current: int, total: int, record_id: str
    ) -> None:
        """批量处理进度更新

        Args:
            current: 当前处理的索引（1-based）
            total: 总记录数
            record_id: 当前记录ID
        """
        if self.batch_progress_dialog:
            self.batch_progress_dialog.setValue(current)
            self.batch_progress_dialog.setLabelText(
                QCoreApplication.translate(
                    "HistoryTab",
                    "Processing {current}/{total} records...\n"
                    "Current record: {record_id}...",
                ).format(current=current, total=total, record_id=record_id[:16])
            )

    def _on_batch_completed(self, stats: dict) -> None:
        """批量处理完成

        Args:
            stats: 统计结果字典
        """
        # 关闭进度对话框
        if self.batch_progress_dialog:
            self.batch_progress_dialog.close()
            self.batch_progress_dialog = None

        # 清理Worker
        if self.batch_worker:
            self.batch_worker.wait()
            self.batch_worker = None

        # 刷新历史记录列表
        self._load_history()

        # 显示完成报告
        total = stats.get("total", 0)
        success = stats.get("success", 0)
        skipped = stats.get("skipped", 0)
        failed = stats.get("failed", 0)
        errors = stats.get("errors", [])

        # 构建报告消息
        report_lines = [
            QCoreApplication.translate("HistoryTab", "Batch Reprocessing Complete!"),
            "",
            QCoreApplication.translate("HistoryTab", "Total records: {total}").format(
                total=total
            ),
            QCoreApplication.translate("HistoryTab", "Successful: {success}").format(
                success=success
            ),
            QCoreApplication.translate("HistoryTab", "Skipped: {skipped}").format(
                skipped=skipped
            ),
            QCoreApplication.translate("HistoryTab", "Failed: {failed}").format(
                failed=failed
            ),
        ]

        if errors:
            report_lines.append("")
            report_lines.append(
                QCoreApplication.translate(
                    "HistoryTab", "First {count} errors:"
                ).format(count=min(5, len(errors)))
            )
            report_lines.extend([f"  {error}" for error in errors[:5]])
            if len(errors) > 5:
                report_lines.append(
                    QCoreApplication.translate(
                        "HistoryTab", "... and {count} more errors"
                    ).format(count=len(errors) - 5)
                )

        QMessageBox.information(
            self.parent_window,
            QCoreApplication.translate("HistoryTab", "Batch Reprocessing Complete"),
            "\n".join(report_lines),
        )

    def _on_batch_canceled(self) -> None:
        """用户取消批量处理"""
        if self.batch_worker:
            self.batch_worker.stop()
            self.batch_worker.wait(5000)  # 等待最多5秒

            # 强制终止（如果还在运行）
            if self.batch_worker.isRunning():
                self.batch_worker.terminate()
                self.batch_worker.wait()

            self.batch_worker = None

        QMessageBox.information(
            self.parent_window,
            QCoreApplication.translate("HistoryTab", "Batch Reprocessing Canceled"),
            QCoreApplication.translate(
                "HistoryTab", "Batch reprocessing operation has been canceled."
            ),
        )
