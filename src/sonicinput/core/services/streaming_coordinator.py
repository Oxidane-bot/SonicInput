"""流式转录协调器 - 负责流式转录的协调和管理

支持两种流式模式：
- chunked: 30秒分块处理模式（带AI优化）
- realtime: 边到边流式转录模式（利用sherpa-onnx流式API）
"""

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

import numpy as np

from ...utils import app_logger
from ..base.lifecycle_component import LifecycleComponent
from .events import Events

# 流式模式类型
StreamingMode = Literal["chunked", "realtime"]


@dataclass
class StreamingChunk:
    """流式转录块（仅用于chunked模式）"""

    chunk_id: int
    audio_data: np.ndarray
    timestamp: float
    result_event: threading.Event
    result_container: Dict[str, Any]


class StreamingCoordinator(LifecycleComponent):
    """流式转录协调器

    支持双模式：
    - chunked: 30秒分块处理，支持AI文本优化
    - realtime: 边到边流式转录，最低延迟

    与具体的转录逻辑和模型管理解耦。

    Lifecycle vs Context Manager:
    - Lifecycle (start/stop): 管理协调器的总体可用性
    - Context Manager (__enter__/__exit__): 管理单个流式会话
    """

    def __init__(self, event_service=None, streaming_mode: StreamingMode = "chunked"):
        """初始化流式协调器

        Args:
            event_service: 事件服务（可选）
            streaming_mode: 流式模式，"chunked" 或 "realtime"
        """
        super().__init__("StreamingCoordinator")

        self.event_service = event_service

        # 流式模式配置
        self._streaming_mode_type: StreamingMode = streaming_mode
        self._streaming_active = False
        self._streaming_lock = threading.RLock()
        self._streaming_condition = threading.Condition(self._streaming_lock)

        # chunked 模式：流式块管理
        with self._streaming_lock:
            self._streaming_chunks_by_id: Dict[int, StreamingChunk] = {}
            self._pending_chunk_ids: "OrderedDict[int, None]" = OrderedDict()
            self._completed_chunks_by_id: Dict[int, StreamingChunk] = {}
            self._next_chunk_id = 0

        # realtime 模式：流式会话管理
        self._realtime_session = None
        self._realtime_finalized_text = ""
        self._realtime_partial_text = ""
        self._realtime_last_update = time.time()
        self._realtime_debug_last_log = 0.0
        self._realtime_debug_log_interval = 2.0

        # 流式统计（异构字典：mode 为字符串，其余为数值，_get_stats 还会追加 bool/str 键）
        self._streaming_stats: Dict[str, Any] = {
            "mode": streaming_mode,
            "total_chunks": 0,
            "completed_chunks": 0,
            "failed_chunks": 0,
            "total_audio_duration": 0.0,
            "average_chunk_time": 0.0,
            "realtime_updates": 0,  # realtime 模式统计
        }

        app_logger.log_audio_event(
            "StreamingCoordinator initialized", {"mode": streaming_mode}
        )

    def _do_start(self) -> bool:
        """启动协调器（Lifecycle层）

        初始化协调器状态，准备接受流式会话。
        不会启动实际的流式会话（由__enter__负责）。

        Returns:
            True 如果启动成功
        """
        with self._streaming_lock:
            # 重置统计数据
            self._reset_stats()
            self._clear_chunk_state()

            app_logger.log_audio_event(
                "StreamingCoordinator lifecycle started",
                {"mode": self._streaming_mode_type},
            )

            return True

    def _do_stop(self) -> bool:
        """停止协调器（Lifecycle层）

        停止任何活动的流式会话并清理资源。

        Returns:
            True 如果停止成功
        """
        try:
            # 停止任何活动的流式会话
            if self._streaming_active:
                self.stop_streaming()

            # 清理所有资源
            with self._streaming_lock:
                self._clear_chunk_state()
                self._realtime_session = None
                self._streaming_condition.notify_all()

            app_logger.log_audio_event(
                "StreamingCoordinator lifecycle stopped",
                {"mode": self._streaming_mode_type},
            )

            return True

        except Exception as e:
            app_logger.log_error(e, "streaming_coordinator_stop")
            return False

    def start_streaming(self, streaming_session=None) -> None:
        """开始流式转录模式

        Args:
            streaming_session: realtime模式下的流式会话对象（可选）
        """
        with self._streaming_lock:
            if self._streaming_active:
                return

            self._streaming_active = True
            self._reset_stats()
            self._clear_chunk_state()

            # realtime 模式初始化
            if self._streaming_mode_type == "realtime":
                self._realtime_session = streaming_session
                self._realtime_finalized_text = ""
                self._realtime_partial_text = ""
                self._realtime_last_update = time.time()

            app_logger.log_audio_event(
                "Streaming mode started", {"mode": self._streaming_mode_type}
            )

            # 发送流式开始事件
            self._emit_streaming_event(
                Events.STREAMING_STARTED, {"mode": self._streaming_mode_type}
            )

    def stop_streaming(self) -> Dict[str, Any]:
        """停止流式转录模式

        Returns:
            流式转录统计信息
        """
        with self._streaming_lock:
            if not self._streaming_active:
                return self._get_stats()

            self._streaming_active = False

            # chunked 模式：处理剩余的块
            if self._streaming_mode_type == "chunked":
                pending_chunks = len(self._streaming_chunks_by_id)
                if pending_chunks > 0:
                    app_logger.log_audio_event(
                        "Cleaning up pending chunks", {"pending_count": pending_chunks}
                    )

                    # 标记剩余块为失败
                    for chunk in self._streaming_chunks_by_id.values():
                        chunk.result_container.update(
                            {
                                "success": False,
                                "error": "Streaming stopped before processing",
                                "error_type": "streaming_stopped",
                            }
                        )
                        chunk.result_event.set()

                    self._streaming_chunks_by_id.clear()
                    self._pending_chunk_ids.clear()

            # realtime 模式：仅清理session，不获取最终结果
            # 重要：realtime 模式文本已在录音过程中逐字输入，
            # 不应该再调用 get_final_result()，否则会导致文本重复
            elif self._streaming_mode_type == "realtime":
                if self._realtime_session:
                    app_logger.log_audio_event(
                        "Realtime mode: keeping partial text, not calling get_final_result",
                        {"partial_text_length": len(self.get_realtime_text())},
                    )

                    # 显式清理sherpa-onnx streaming session
                    try:
                        if (
                            hasattr(self._realtime_session, "is_active")
                            and self._realtime_session.is_active
                        ):
                            if (
                                hasattr(self._realtime_session, "stream")
                                and self._realtime_session.stream
                            ):
                                self._realtime_session.stream.input_finished()
                            self._realtime_session.is_active = False
                            app_logger.log_audio_event(
                                "Realtime session explicitly cleaned up", {}
                            )
                    except Exception as e:
                        app_logger.log_error(e, "realtime_session_cleanup")

                    self._realtime_session = None

            self._streaming_condition.notify_all()
            stats = self._get_stats()

            app_logger.log_audio_event(
                "Streaming mode stopped",
                {"mode": self._streaming_mode_type, "stats": stats},
            )

            # 发送流式结束事件
            self._emit_streaming_event(Events.STREAMING_STOPPED, stats)

            return stats

    def add_streaming_chunk(self, audio_data: np.ndarray) -> int:
        """添加流式转录块（仅chunked模式）

        Args:
            audio_data: 音频数据

        Returns:
            块ID（chunked模式）或 -1（不适用）
        """
        if self._streaming_mode_type != "chunked":
            app_logger.log_audio_event(
                "add_streaming_chunk called in non-chunked mode",
                {"mode": self._streaming_mode_type},
            )
            return -1

        with self._streaming_lock:
            if not self._streaming_active:
                return -1

            chunk_id = self._next_chunk_id
            self._next_chunk_id += 1

            # 创建结果容器和事件
            result_container = {
                "success": False,
                "text": "",
                "error": None,
                "error_type": None,
                "processing_time": 0.0,
                "timestamp": time.time(),
            }

            result_event = threading.Event()

            # 创建流式块
            chunk = StreamingChunk(
                chunk_id=chunk_id,
                audio_data=audio_data.copy(),  # 复制数据避免引用问题
                timestamp=time.time(),
                result_event=result_event,
                result_container=result_container,
            )

            self._streaming_chunks_by_id[chunk_id] = chunk
            self._pending_chunk_ids[chunk_id] = None
            self._streaming_stats["total_chunks"] += 1
            self._streaming_stats["total_audio_duration"] += (
                len(audio_data) / 16000
            )  # 假设16kHz

            app_logger.log_audio_event(
                "Streaming chunk added",
                {
                    "chunk_id": chunk_id,
                    "audio_length": len(audio_data),
                    "queue_size": len(self._pending_chunk_ids),
                },
            )
            self._streaming_condition.notify()

            return chunk_id

    def add_realtime_audio(self, audio_data: np.ndarray) -> Optional[str]:
        """添加实时音频数据（仅realtime模式）

        Args:
            audio_data: 音频数据

        Returns:
            部分转录结果（如有更新）或 None
        """
        if self._streaming_mode_type != "realtime":
            app_logger.log_audio_event(
                "add_realtime_audio called in non-realtime mode",
                {"mode": self._streaming_mode_type},
            )
            return None

        with self._streaming_lock:
            now = time.time()
            should_log_debug = (
                now - self._realtime_debug_last_log
            ) >= self._realtime_debug_log_interval
            if should_log_debug:
                self._realtime_debug_last_log = now
                app_logger.log_audio_event(
                    "add_realtime_audio called",
                    {
                        "streaming_active": self._streaming_active,
                        "has_session": self._realtime_session is not None,
                        "audio_length": len(audio_data),
                    },
                )

            if not self._streaming_active or not self._realtime_session:
                if should_log_debug:
                    app_logger.log_audio_event(
                        "add_realtime_audio: streaming inactive or no session",
                        {
                            "streaming_active": self._streaming_active,
                            "has_session": self._realtime_session is not None,
                        },
                    )
                return None

            try:
                # 向流式会话添加音频样本
                self._realtime_session.add_samples(audio_data)

                # 获取部分结果
                partial_result = self._realtime_session.get_partial_result()

                if should_log_debug:
                    app_logger.log_audio_event(
                        "add_realtime_audio: got partial result",
                        {
                            "partial_result": partial_result[:50]
                            if partial_result
                            else ""
                        },
                    )

                # sherpa realtime session 在 endpoint 后可能从新片段重新开始计数。
                # 这里保留已完成片段，并将当前片段作为可修正的尾部文本。
                if partial_result != self._realtime_partial_text:
                    previous_partial = self._realtime_partial_text
                    if self._should_finalize_realtime_partial(
                        previous_partial, partial_result
                    ):
                        self._realtime_finalized_text = self._merge_realtime_text(
                            self._realtime_finalized_text, previous_partial
                        )
                    self._realtime_partial_text = partial_result
                    self._realtime_last_update = time.time()
                    self._streaming_stats["realtime_updates"] += 1
                    display_text = self.get_realtime_text()

                    # 发送实时更新事件
                    self._emit_streaming_event(
                        Events.REALTIME_TEXT_UPDATED,
                        {
                            "text": display_text,
                            "timestamp": self._realtime_last_update,
                        },
                    )

                    return display_text

                return None

            except Exception as e:
                app_logger.log_error(e, "add_realtime_audio")
                return None

    def get_realtime_text(self) -> str:
        """获取当前实时转录文本（仅realtime模式）

        Returns:
            当前转录文本
        """
        with self._streaming_lock:
            return self._merge_realtime_text(
                self._realtime_finalized_text, self._realtime_partial_text
            )

    @staticmethod
    def _common_prefix_length(left: str, right: str) -> int:
        prefix_length = 0
        for left_char, right_char in zip(left, right):
            if left_char != right_char:
                break
            prefix_length += 1
        return prefix_length

    @staticmethod
    def _merge_realtime_text(prefix: str, current: str) -> str:
        if not prefix:
            return current
        if not current:
            return prefix
        if current.startswith(prefix):
            return current
        return f"{prefix}{current}"

    def _should_finalize_realtime_partial(
        self, previous_partial: str, current_partial: str
    ) -> bool:
        if not previous_partial or not current_partial:
            return False
        if current_partial.startswith(previous_partial):
            return False

        common_prefix_length = self._common_prefix_length(
            previous_partial, current_partial
        )
        min_length = min(len(previous_partial), len(current_partial))
        restart_threshold = max(1, min_length // 3)
        return common_prefix_length <= restart_threshold

    def get_pending_chunks(self) -> List[StreamingChunk]:
        """获取所有待处理的流式块

        Returns:
            待处理的流式块列表
        """
        with self._streaming_lock:
            # 返回所有待处理块的副本
            return sorted(
                self._streaming_chunks_by_id.values(), key=lambda chunk: chunk.chunk_id
            )

    def get_next_chunk(
        self, timeout: Optional[float] = None
    ) -> Optional[StreamingChunk]:
        """获取下一个待处理的流式块

        Args:
            timeout: 超时时间（秒）

        Returns:
            流式块对象，如果没有块则返回None
        """
        deadline = None if timeout is None else (time.monotonic() + timeout)

        with self._streaming_condition:
            while True:
                if self._pending_chunk_ids:
                    chunk_id, _ = self._pending_chunk_ids.popitem(last=False)
                    chunk = self._streaming_chunks_by_id.get(chunk_id)
                    if chunk and not chunk.result_event.is_set():
                        return chunk

                # 检查是否仍在流式模式
                if not self._streaming_active:
                    return None

                if deadline is None:
                    self._streaming_condition.wait()
                    continue

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._streaming_condition.wait(timeout=remaining)

    def complete_chunk(self, chunk_id: int, result: Dict[str, Any]) -> None:
        """标记流式块处理完成

        Args:
            chunk_id: 块ID
            result: 处理结果
        """
        with self._streaming_lock:
            chunk = self._streaming_chunks_by_id.pop(chunk_id, None)
            if not chunk:
                return

            # 更新结果容器
            chunk.result_container.update(result)
            chunk.result_container["chunk_id"] = chunk_id
            chunk.result_container["completed_at"] = time.time()

            # 计算处理时间
            processing_time = time.time() - chunk.timestamp
            chunk.result_container["processing_time"] = processing_time

            # 更新统计
            self._update_stats(processing_time, result.get("success", False))

            # 设置事件标志
            chunk.result_event.set()
            self._pending_chunk_ids.pop(chunk_id, None)
            self._completed_chunks_by_id[chunk_id] = chunk
            self._streaming_condition.notify_all()

            app_logger.log_audio_event(
                "Streaming chunk completed",
                {
                    "chunk_id": chunk_id,
                    "success": result.get("success", False),
                    "processing_time": processing_time,
                    "text_length": len(result.get("text", "")),
                    "queue_size": len(self._pending_chunk_ids),
                },
            )

            # 发送块完成事件
            self._emit_streaming_event(
                Events.STREAMING_CHUNK_COMPLETED,
                {"chunk_id": chunk_id, "result": result},
            )

    def get_chunk_result(
        self, chunk_id: int, timeout: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """获取流式块的处理结果

        Args:
            chunk_id: 块ID
            timeout: 超时时间（秒）

        Returns:
            处理结果，如果超时则返回None
        """
        with self._streaming_lock:
            chunk = self._streaming_chunks_by_id.get(chunk_id)
            if not chunk:
                chunk = self._completed_chunks_by_id.get(chunk_id)

        if not chunk:
            return None

        # 等待结果
        if chunk.result_event.wait(timeout=timeout):
            return chunk.result_container.copy()
        else:
            return None

    def get_pending_chunk_count(self) -> int:
        """获取待处理的块数量

        Returns:
            待处理块数量
        """
        with self._streaming_lock:
            return len(self._pending_chunk_ids)

    def is_streaming(self) -> bool:
        """检查是否在流式模式

        Returns:
            True如果在流式模式
        """
        return self._streaming_active

    def get_streaming_mode(self) -> StreamingMode:
        """获取当前流式模式类型

        Returns:
            "chunked" 或 "realtime"
        """
        return self._streaming_mode_type

    def set_streaming_mode(self, mode: StreamingMode) -> bool:
        """设置流式模式类型（仅在非活动状态下可更改）

        Args:
            mode: "chunked" 或 "realtime"

        Returns:
            True 如果设置成功
        """
        with self._streaming_lock:
            if self._streaming_active:
                app_logger.log_audio_event(
                    "Cannot change streaming mode while active",
                    {"current_mode": self._streaming_mode_type, "requested_mode": mode},
                )
                return False

            if mode not in ("chunked", "realtime"):
                app_logger.log_audio_event(
                    "Invalid streaming mode", {"requested_mode": mode}
                )
                return False

            self._streaming_mode_type = mode
            self._streaming_stats["mode"] = mode

            app_logger.log_audio_event("Streaming mode changed", {"new_mode": mode})

            return True

    def get_stats(self) -> Dict[str, Any]:
        """获取流式转录统计信息

        Returns:
            统计信息字典
        """
        with self._streaming_lock:
            return self._get_stats().copy()

    def get_completed_chunks(self) -> List[StreamingChunk]:
        """获取所有已完成的转录块

        Returns:
            已完成的转录块列表
        """
        with self._streaming_lock:
            return list(self._completed_chunks_by_id.values())

    def _get_stats(self) -> Dict[str, Any]:
        """获取统计信息（内部方法，需要持有锁）"""
        stats = self._streaming_stats.copy()
        stats.update(
            {
                "is_streaming": self._streaming_active,
                "mode": self._streaming_mode_type,
                "pending_chunks": len(self._pending_chunk_ids),
                "next_chunk_id": self._next_chunk_id,
                "success_rate": (
                    stats["completed_chunks"] / max(stats["total_chunks"], 1) * 100
                )
                if stats["total_chunks"] > 0
                else 0.0,
            }
        )

        # realtime 模式额外统计
        if self._streaming_mode_type == "realtime":
            stats.update(
                {
                    "current_text": self._realtime_partial_text,
                    "text_length": len(self._realtime_partial_text),
                    "last_update": self._realtime_last_update,
                    "has_session": self._realtime_session is not None,
                }
            )

        return stats

    def _reset_stats(self) -> None:
        """重置统计信息"""
        self._streaming_stats = {
            "mode": self._streaming_mode_type,
            "total_chunks": 0,
            "completed_chunks": 0,
            "failed_chunks": 0,
            "total_audio_duration": 0.0,
            "average_chunk_time": 0.0,
            "realtime_updates": 0,
        }
        self._next_chunk_id = 0

        # realtime 模式重置
        if self._streaming_mode_type == "realtime":
            self._realtime_partial_text = ""
            self._realtime_last_update = time.time()

    def _clear_chunk_state(self) -> None:
        """清理分块状态（需在持锁状态下调用）。"""
        self._streaming_chunks_by_id.clear()
        self._pending_chunk_ids.clear()
        self._completed_chunks_by_id.clear()

    def _update_stats(self, processing_time: float, success: bool) -> None:
        """更新统计信息

        Args:
            processing_time: 处理时间
            success: 是否成功
        """
        if success:
            self._streaming_stats["completed_chunks"] += 1
        else:
            self._streaming_stats["failed_chunks"] += 1

        # 更新平均处理时间
        completed = self._streaming_stats["completed_chunks"]
        if completed > 0:
            current_avg = self._streaming_stats["average_chunk_time"]
            self._streaming_stats["average_chunk_time"] = (
                current_avg * (completed - 1) + processing_time
            ) / completed

    def _emit_streaming_event(self, event_name: str, data: Dict[str, Any]) -> None:
        """发送流式转录事件

        Args:
            event_name: 事件名称
            data: 事件数据
        """
        if self.event_service:
            try:
                self.event_service.emit(event_name, data)
            except Exception as e:
                app_logger.log_error(e, "emit_streaming_event")

    def __enter__(self) -> "StreamingCoordinator":
        """进入上下文管理器 - 启动流式转录

        Returns:
            self (StreamingCoordinator实例)
        """
        self.start_streaming()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> Literal[False]:
        """退出上下文管理器 - 停止流式转录并清理资源

        保证sherpa-onnx会话被正确释放，即使发生异常。

        Args:
            exc_type: 异常类型（如果有）
            exc_val: 异常值（如果有）
            exc_tb: 异常回溯（如果有）

        Returns:
            False（不抑制异常，让异常继续传播）
        """
        try:
            # 停止流式转录（内部已有session清理逻辑）
            self.stop_streaming()

            # 显式额外清理realtime session（防御性编程）
            with self._streaming_lock:
                if self._realtime_session is not None:
                    app_logger.log_audio_event(
                        "Context manager explicitly releasing realtime session", {}
                    )
                    self._realtime_session = None

        except Exception as e:
            app_logger.log_error(e, "context_manager_exit")

        # 不抑制异常 - 让调用者处理
        return False
