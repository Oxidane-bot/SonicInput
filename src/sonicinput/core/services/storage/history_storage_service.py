"""历史记录存储服务实现"""

import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, List, Optional

from ....utils import app_logger
from ...base.lifecycle_component import LifecycleComponent
from ...interfaces import HistoryRecord, IConfigService
from ...services.config import ConfigKeys


class HistoryStorageService(LifecycleComponent):
    """历史记录存储服务

    负责管理录音历史记录的持久化存储和检索
    使用SQLite存储元数据，文件系统存储音频文件
    """

    def __init__(self, config_service: IConfigService):
        """初始化历史存储服务

        Args:
            config_service: 配置服务
        """
        super().__init__("HistoryStorageService")
        self._config_service = config_service
        self._db_path: Optional[Path] = None
        self._storage_path: Optional[Path] = None
        self._local = threading.local()  # 线程本地存储，每个线程独立的数据库连接

    def _do_start(self) -> bool:
        """Start history storage and initialize database"""
        try:
            # 获取存储路径
            storage_base = self._config_service.get_setting(
                ConfigKeys.HISTORY_STORAGE_PATH, "auto"
            )

            if storage_base == "auto":
                # 默认使用AppData/Roaming/SonicInput/history
                from ....utils.helpers import get_app_data_dir

                self._storage_path = get_app_data_dir() / "history"
            else:
                self._storage_path = Path(storage_base)

            # 创建存储目录
            self._storage_path.mkdir(parents=True, exist_ok=True)

            # 创建recordings子目录
            recordings_dir = self._storage_path / "recordings"
            recordings_dir.mkdir(exist_ok=True)

            # 数据库路径
            self._db_path = self._storage_path / "history.db"

            # 初始化数据库
            self._init_database()

            app_logger.log_audio_event("Database initialized successfully")

            # 清理孤立文件
            orphaned_count = self.cleanup_orphaned_files()

            if orphaned_count > 0:
                app_logger.log_audio_event(
                    "Cleaned up orphaned audio files", {"count": orphaned_count}
                )

            app_logger.log_audio_event(
                "HistoryStorageService started",
                {
                    "storage_path": str(self._storage_path),
                    "db_path": str(self._db_path),
                },
            )

            return True

        except Exception as e:
            app_logger.log_error(
                e,
                "HistoryStorageService_do_start",
                {
                    "storage_path_set": self._storage_path is not None,
                    "db_path_set": self._db_path is not None,
                },
            )
            # Reset state on failure to ensure consistent state
            self._storage_path = None
            self._db_path = None
            return False

    def _init_database(self) -> None:
        """初始化数据库表（使用临时连接）"""
        # 使用临时连接进行初始化，不保存到线程本地存储
        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.cursor()

        # 创建历史记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS history_records (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                audio_file_path TEXT NOT NULL,
                duration REAL NOT NULL,
                transcription_text TEXT NOT NULL,
                transcription_provider TEXT NOT NULL,
                transcription_status TEXT NOT NULL,
                transcription_error TEXT,
                ai_optimized_text TEXT,
                ai_provider TEXT,
                ai_status TEXT NOT NULL,
                ai_error TEXT,
                final_text TEXT NOT NULL
            )
        """)

        # 创建索引以提高查询性能
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp
            ON history_records(timestamp DESC)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_transcription_status
            ON history_records(transcription_status)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_ai_status
            ON history_records(ai_status)
        """)

        # 启用 WAL 模式以优化并发性能
        cursor.execute("PRAGMA journal_mode=WAL")

        conn.commit()
        conn.close()  # 关闭临时连接

        app_logger.log_audio_event("History database initialized", {"wal_mode": True})

    def _do_stop(self) -> bool:
        """Stop history storage and clean up resources"""
        # 关闭当前线程的数据库连接
        if hasattr(self._local, "conn") and self._local.conn is not None:
            try:
                self._local.conn.close()
                self._local.conn = None
                app_logger.log_audio_event(
                    "Thread-local DB connection closed",
                    {"thread_id": threading.get_ident()},
                )
            except Exception as e:
                app_logger.log_error(e, "close_database_connection_on_stop")
                return False
        return True

    def _get_connection(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接（线程安全）

        Returns:
            当前线程的 SQLite 连接对象
        """
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self._db_path))
            self._local.conn.row_factory = sqlite3.Row  # 启用列名访问

            app_logger.log_audio_event(
                "Thread-local DB connection created",
                {"thread_id": threading.get_ident()},
            )

        return self._local.conn

    @contextmanager
    def _transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        """Context manager for safe database transactions

        Provides automatic commit/rollback handling with proper error
        recovery. Ensures database integrity even if exceptions occur.

        Yields:
            Database cursor for executing queries

        Example:
            >>> with self._transaction() as cursor:
            >>>     cursor.execute("INSERT INTO ...")
            >>>     cursor.execute("UPDATE ...")
            # Automatic commit on success, rollback on exception

        Thread Safety:
            Uses thread-local connection from _get_connection()
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            yield cursor
            conn.commit()
            app_logger.log_audio_event(
                "Database transaction committed", {"thread_id": threading.get_ident()}
            )
        except sqlite3.IntegrityError as e:
            conn.rollback()
            app_logger.log_error(
                e,
                "database_integrity_error",
                {"thread_id": threading.get_ident(), "error_type": "IntegrityError"},
            )
            raise
        except sqlite3.OperationalError as e:
            conn.rollback()
            app_logger.log_error(
                e,
                "database_operational_error",
                {"thread_id": threading.get_ident(), "error_type": "OperationalError"},
            )
            raise
        except Exception as e:
            conn.rollback()
            app_logger.log_error(
                e,
                "database_transaction_error",
                {
                    "thread_id": threading.get_ident(),
                    "error_type": type(e).__name__,
                },
            )
            raise

    def save_record(self, record: HistoryRecord) -> bool:
        """Save history record with safe transaction handling

        Args:
            record: HistoryRecord object to save

        Returns:
            True if saved successfully, False otherwise
        """
        if not self._db_path:
            app_logger.log_audio_event(
                "HistoryStorageService not initialized (save_record)",
                {"_db_path": None, "message": "Service _do_start() may have failed"},
            )
            return False

        try:
            with self._transaction() as cursor:
                cursor.execute(
                    """
                    INSERT INTO history_records (
                        id, timestamp, audio_file_path, duration,
                        transcription_text, transcription_provider, transcription_status, transcription_error,
                        ai_optimized_text, ai_provider, ai_status, ai_error,
                        final_text
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        record.id,
                        record.timestamp.isoformat(),
                        record.audio_file_path,
                        record.duration,
                        record.transcription_text,
                        record.transcription_provider,
                        record.transcription_status,
                        record.transcription_error,
                        record.ai_optimized_text,
                        record.ai_provider,
                        record.ai_status,
                        record.ai_error,
                        record.final_text,
                    ),
                )

            app_logger.log_audio_event(
                "History record saved",
                {"record_id": record.id, "thread_id": threading.get_ident()},
            )
            return True

        except sqlite3.IntegrityError as e:
            # Duplicate ID or constraint violation
            app_logger.log_error(e, "save_record_duplicate", {"record_id": record.id})
            return False
        except Exception as e:
            app_logger.log_error(e, "save_record")
            return False

    def update_record(self, record: HistoryRecord) -> bool:
        """Update existing record with safe transaction handling

        Updates both transcription and AI-related fields

        Args:
            record: HistoryRecord object with updated fields

        Returns:
            True if updated successfully, False if record not found or error
        """
        try:
            with self._transaction() as cursor:
                cursor.execute(
                    """
                    UPDATE history_records
                    SET transcription_text = ?,
                        transcription_provider = ?,
                        transcription_status = ?,
                        transcription_error = ?,
                        ai_optimized_text = ?,
                        ai_provider = ?,
                        ai_status = ?,
                        ai_error = ?,
                        final_text = ?
                    WHERE id = ?
                """,
                    (
                        record.transcription_text,
                        record.transcription_provider,
                        record.transcription_status,
                        record.transcription_error,
                        record.ai_optimized_text,
                        record.ai_provider,
                        record.ai_status,
                        record.ai_error,
                        record.final_text,
                        record.id,
                    ),
                )

                # Check if any row was actually updated
                if cursor.rowcount == 0:
                    app_logger.log_audio_event(
                        "History record not found for update",
                        {"record_id": record.id},
                    )
                    return False

            app_logger.log_audio_event(
                "History record updated",
                {"record_id": record.id, "thread_id": threading.get_ident()},
            )
            return True

        except Exception as e:
            app_logger.log_error(e, "update_record")
            return False

    def save_records_batch(self, records: List[HistoryRecord]) -> int:
        """Save multiple records in a single transaction

        Args:
            records: List of HistoryRecord objects to save

        Returns:
            Number of records successfully saved

        Note:
            Uses a single transaction for atomic batch insert.
            If any record fails, entire batch is rolled back.
        """
        if not records:
            return 0

        try:
            with self._transaction() as cursor:
                saved_count = 0
                for record in records:
                    cursor.execute(
                        """
                        INSERT INTO history_records (
                            id, timestamp, audio_file_path, duration,
                            transcription_text, transcription_provider,
                            transcription_status, transcription_error,
                            ai_optimized_text, ai_provider, ai_status, ai_error,
                            final_text
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            record.id,
                            record.timestamp.isoformat(),
                            record.audio_file_path,
                            record.duration,
                            record.transcription_text,
                            record.transcription_provider,
                            record.transcription_status,
                            record.transcription_error,
                            record.ai_optimized_text,
                            record.ai_provider,
                            record.ai_status,
                            record.ai_error,
                            record.final_text,
                        ),
                    )
                    saved_count += 1

            app_logger.log_audio_event(
                "Batch records saved",
                {
                    "count": saved_count,
                    "total_records": len(records),
                    "thread_id": threading.get_ident(),
                },
            )
            return saved_count

        except Exception as e:
            app_logger.log_error(
                e, "save_records_batch", {"attempted_count": len(records)}
            )
            return 0

    def get_record_by_id(self, record_id: str) -> Optional[HistoryRecord]:
        """根据ID获取单条记录（线程安全）"""
        if not self._db_path:
            app_logger.log_audio_event(
                "HistoryStorageService not initialized (get_record_by_id)",
                {"_db_path": None, "message": "Service _do_start() may have failed"},
            )
            return None

        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM history_records WHERE id = ?", (record_id,))

            row = cursor.fetchone()
            if row:
                return self._row_to_record(row)

            return None

        except Exception as e:
            app_logger.log_error(e, "get_record_by_id")
            return None

    def get_records(
        self, limit: int = 50, offset: int = 0, order_by: str = "timestamp DESC"
    ) -> List[HistoryRecord]:
        """分页获取记录列表（线程安全）"""
        if not self._db_path:
            app_logger.log_audio_event(
                "HistoryStorageService not initialized (get_records)",
                {"_db_path": None, "message": "Service _do_start() may have failed"},
            )
            return []

        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # 验证 order_by，避免动态拼接任意 SQL
            allowed_fields = {
                "timestamp",
                "duration",
                "transcription_status",
                "ai_status",
            }
            allowed_orders = {"ASC", "DESC"}

            normalized_order = "timestamp DESC"
            order_parts = order_by.strip().split()
            if len(order_parts) == 2:
                field = order_parts[0].lower()
                direction = order_parts[1].upper()
                if field in allowed_fields and direction in allowed_orders:
                    normalized_order = f"{field} {direction}"

            query_by_order = {
                "timestamp ASC": (
                    "SELECT * FROM history_records "
                    "ORDER BY timestamp ASC LIMIT ? OFFSET ?"
                ),
                "timestamp DESC": (
                    "SELECT * FROM history_records "
                    "ORDER BY timestamp DESC LIMIT ? OFFSET ?"
                ),
                "duration ASC": (
                    "SELECT * FROM history_records "
                    "ORDER BY duration ASC LIMIT ? OFFSET ?"
                ),
                "duration DESC": (
                    "SELECT * FROM history_records "
                    "ORDER BY duration DESC LIMIT ? OFFSET ?"
                ),
                "transcription_status ASC": (
                    "SELECT * FROM history_records "
                    "ORDER BY transcription_status ASC LIMIT ? OFFSET ?"
                ),
                "transcription_status DESC": (
                    "SELECT * FROM history_records "
                    "ORDER BY transcription_status DESC LIMIT ? OFFSET ?"
                ),
                "ai_status ASC": (
                    "SELECT * FROM history_records "
                    "ORDER BY ai_status ASC LIMIT ? OFFSET ?"
                ),
                "ai_status DESC": (
                    "SELECT * FROM history_records "
                    "ORDER BY ai_status DESC LIMIT ? OFFSET ?"
                ),
            }
            query = query_by_order.get(
                normalized_order, query_by_order["timestamp DESC"]
            )

            cursor.execute(query, (limit, offset))

            rows = cursor.fetchall()
            return [self._row_to_record(row) for row in rows]

        except Exception as e:
            app_logger.log_error(e, "get_records")
            return []

    @staticmethod
    def _escape_like_pattern(value: str) -> str:
        """Escape LIKE wildcards so user queries behave like literal substring search."""
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def search_records(
        self,
        query: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        transcription_status: Optional[str] = None,
        ai_status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[HistoryRecord]:
        """搜索记录（线程安全）"""
        if not self._db_path:
            app_logger.log_audio_event(
                "HistoryStorageService not initialized (search_records)",
                {"_db_path": None, "message": "Service _do_start() may have failed"},
            )
            return []

        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # 构建查询条件
            conditions = []
            params = []

            if query:
                normalized_query = query.strip().lower()
                if normalized_query:
                    escaped_query = self._escape_like_pattern(normalized_query)
                    search_term = f"%{escaped_query}%"
                    conditions.append(
                        "("
                        "LOWER(transcription_text) LIKE ? ESCAPE '\\' OR "
                        "LOWER(ai_optimized_text) LIKE ? ESCAPE '\\' OR "
                        "LOWER(final_text) LIKE ? ESCAPE '\\'"
                        ")"
                    )
                    params.extend([search_term, search_term, search_term])

            if start_date:
                conditions.append("timestamp >= ?")
                params.append(start_date.isoformat())

            if end_date:
                conditions.append("timestamp <= ?")
                params.append(end_date.isoformat())

            if transcription_status:
                conditions.append("transcription_status = ?")
                params.append(transcription_status)

            if ai_status:
                conditions.append("ai_status = ?")
                params.append(ai_status)

            # 构建完整查询
            sql = "SELECT * FROM history_records"
            if conditions:
                sql += " WHERE " + " AND ".join(conditions)
            sql += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"

            params.extend([limit, offset])

            cursor.execute(sql, params)

            rows = cursor.fetchall()
            return [self._row_to_record(row) for row in rows]

        except Exception as e:
            app_logger.log_error(e, "search_records")
            return []

    def delete_record(self, record_id: str) -> bool:
        """删除记录（包括音频文件）"""
        try:
            # 获取数据库连接
            conn = self._get_connection()
            if not conn:
                return False

            # 先获取记录以找到音频文件路径
            record = self.get_record_by_id(record_id)
            if not record:
                return False

            # 删除音频文件
            audio_path = Path(record.audio_file_path)
            if audio_path.exists():
                audio_path.unlink()
                app_logger.log_audio_event(
                    "Audio file deleted", {"path": str(audio_path)}
                )

            # 删除数据库记录
            cursor = conn.cursor()
            cursor.execute("DELETE FROM history_records WHERE id = ?", (record_id,))
            conn.commit()

            app_logger.log_audio_event(
                "History record deleted", {"record_id": record_id}
            )

            return True

        except Exception as e:
            app_logger.log_error(e, "delete_record")
            return False

    def delete_records(self, record_ids: List[str]) -> int:
        """批量删除记录"""
        deleted_count = 0

        for record_id in record_ids:
            if self.delete_record(record_id):
                deleted_count += 1

        return deleted_count

    def get_total_count(
        self,
        query: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        transcription_status: Optional[str] = None,
        ai_status: Optional[str] = None,
    ) -> int:
        """获取记录总数（用于分页，线程安全）"""
        if not self._db_path:
            app_logger.log_audio_event(
                "HistoryStorageService not initialized (get_total_count)",
                {"_db_path": None, "message": "Service _do_start() may have failed"},
            )
            return 0

        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # 构建查询条件（与search_records相同）
            conditions = []
            params = []

            if query:
                normalized_query = query.strip().lower()
                if normalized_query:
                    escaped_query = self._escape_like_pattern(normalized_query)
                    search_term = f"%{escaped_query}%"
                    conditions.append(
                        "("
                        "LOWER(transcription_text) LIKE ? ESCAPE '\\' OR "
                        "LOWER(ai_optimized_text) LIKE ? ESCAPE '\\' OR "
                        "LOWER(final_text) LIKE ? ESCAPE '\\'"
                        ")"
                    )
                    params.extend([search_term, search_term, search_term])

            if start_date:
                conditions.append("timestamp >= ?")
                params.append(start_date.isoformat())

            if end_date:
                conditions.append("timestamp <= ?")
                params.append(end_date.isoformat())

            if transcription_status:
                conditions.append("transcription_status = ?")
                params.append(transcription_status)

            if ai_status:
                conditions.append("ai_status = ?")
                params.append(ai_status)

            # 构建完整查询
            sql = "SELECT COUNT(*) FROM history_records"
            if conditions:
                sql += " WHERE " + " AND ".join(conditions)

            cursor.execute(sql, params)

            result = cursor.fetchone()
            return result[0] if result else 0

        except Exception as e:
            app_logger.log_error(e, "get_total_count")
            return 0

    def get_aggregate_stats(
        self,
        query: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        transcription_status: Optional[str] = None,
        ai_status: Optional[str] = None,
    ) -> tuple[int, float, int]:
        """获取聚合统计信息（线程安全）

        Returns:
            (total_count, total_duration, success_count)
        """
        if not self._db_path:
            app_logger.log_audio_event(
                "HistoryStorageService not initialized (get_aggregate_stats)",
                {"_db_path": None, "message": "Service _do_start() may have failed"},
            )
            return (0, 0.0, 0)

        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            conditions = []
            params = []

            if query:
                normalized_query = query.strip().lower()
                if normalized_query:
                    escaped_query = self._escape_like_pattern(normalized_query)
                    search_term = f"%{escaped_query}%"
                    conditions.append(
                        "("
                        "LOWER(transcription_text) LIKE ? ESCAPE '\\' OR "
                        "LOWER(ai_optimized_text) LIKE ? ESCAPE '\\' OR "
                        "LOWER(final_text) LIKE ? ESCAPE '\\'"
                        ")"
                    )
                    params.extend([search_term, search_term, search_term])

            if start_date:
                conditions.append("timestamp >= ?")
                params.append(start_date.isoformat())

            if end_date:
                conditions.append("timestamp <= ?")
                params.append(end_date.isoformat())

            if transcription_status:
                conditions.append("transcription_status = ?")
                params.append(transcription_status)

            if ai_status:
                conditions.append("ai_status = ?")
                params.append(ai_status)

            sql = """
                SELECT
                    COUNT(*) AS total_count,
                    COALESCE(SUM(duration), 0) AS total_duration,
                    COALESCE(
                        SUM(
                            CASE
                                WHEN transcription_status = 'success'
                                    AND ai_status IN ('success', 'skipped')
                                THEN 1
                                ELSE 0
                            END
                        ),
                        0
                    ) AS success_count
                FROM history_records
            """

            if conditions:
                sql += " WHERE " + " AND ".join(conditions)

            cursor.execute(sql, params)
            row = cursor.fetchone()
            if not row:
                return (0, 0.0, 0)

            total_count = int(row[0] or 0)
            total_duration = float(row[1] or 0.0)
            success_count = int(row[2] or 0)
            return (total_count, total_duration, success_count)

        except Exception as e:
            app_logger.log_error(e, "get_aggregate_stats")
            return (0, 0.0, 0)

    def get_storage_path(self) -> Path:
        """获取存储路径"""
        if not self._storage_path:
            raise RuntimeError("Storage service not initialized")
        return self._storage_path

    def cleanup_orphaned_files(self) -> int:
        """清理孤立的音频文件（数据库中没有对应记录的文件，线程安全）"""
        if not self._storage_path:
            return 0

        try:
            # 获取所有数据库中的音频文件路径
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT audio_file_path FROM history_records")
            db_files = {row[0] for row in cursor.fetchall()}

            # 获取recordings目录中的所有wav文件
            recordings_dir = self._storage_path / "recordings"
            if not recordings_dir.exists():
                return 0

            disk_files = list(recordings_dir.glob("*.wav"))

            # 找出孤立文件并删除
            deleted_count = 0
            for file_path in disk_files:
                if str(file_path) not in db_files:
                    try:
                        file_path.unlink()
                        deleted_count += 1
                        app_logger.log_audio_event(
                            "Orphaned file deleted", {"path": str(file_path)}
                        )
                    except Exception as e:
                        app_logger.log_error(
                            e, f"delete_orphaned_file_{file_path.name}"
                        )

            return deleted_count

        except Exception as e:
            app_logger.log_error(e, "cleanup_orphaned_files")
            return 0

    def generate_audio_file_path(self) -> str:
        """生成新的音频文件路径

        Returns:
            音频文件的完整路径
        """
        if not self._storage_path:
            raise RuntimeError("Storage service not initialized")

        # 生成唯一文件名：timestamp_uuid.wav
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        filename = f"{timestamp}_{unique_id}.wav"

        recordings_dir = self._storage_path / "recordings"
        return str(recordings_dir / filename)

    def _row_to_record(self, row: sqlite3.Row) -> HistoryRecord:
        """将数据库行转换为HistoryRecord对象"""
        return HistoryRecord(
            id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            audio_file_path=row["audio_file_path"],
            duration=row["duration"],
            transcription_text=row["transcription_text"],
            transcription_provider=row["transcription_provider"],
            transcription_status=row["transcription_status"],
            transcription_error=row["transcription_error"],
            ai_optimized_text=row["ai_optimized_text"],
            ai_provider=row["ai_provider"],
            ai_status=row["ai_status"],
            ai_error=row["ai_error"],
            final_text=row["final_text"],
        )
