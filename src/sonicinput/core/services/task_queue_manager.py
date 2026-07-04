"""任务队列管理器 - 负责任务队列和线程管理"""

import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ...utils import app_logger
from ..base.lifecycle_component import LifecycleComponent


class TaskPriority(Enum):
    """任务优先级"""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class TaskStatus(Enum):
    """任务状态"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """任务对象"""

    task_id: str
    task_type: str
    data: Dict[str, Any] = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    callback: Optional[Callable] = None
    error_callback: Optional[Callable] = None
    timeout: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 0

    def __lt__(self, other):
        """用于优先队列排序"""
        if self.priority.value != other.priority.value:
            return self.priority.value > other.priority.value  # 高优先级在前
        return self.created_at < other.created_at  # 时间早的在前


class TaskQueueManager(LifecycleComponent):
    """任务队列管理器

    负责任务队列管理、工作线程管理和任务执行协调。
    与具体的业务逻辑解耦，专注于任务管理。
    """

    def __init__(self, worker_count: int = 1, event_service=None):
        """初始化任务队列管理器

        Args:
            worker_count: 工作线程数量
            event_service: 事件服务（可选）
        """
        super().__init__("TaskQueueManager")

        self.worker_count = worker_count
        self.event_service = event_service

        # 任务队列（优先队列）
        self._task_queue: queue.PriorityQueue[Task] = queue.PriorityQueue(maxsize=100)
        self._running_tasks: Dict[str, Task] = {}

        # 线程管理
        self._workers: List[threading.Thread] = []
        self._shutdown_event = threading.Event()

        # 统计信息
        self._stats = {
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "cancelled_tasks": 0,
            "average_execution_time": 0.0,
            "queue_size": 0,
            "active_workers": 0,
        }

        # 任务处理器注册表
        self._task_handlers: Dict[str, Callable] = {}

        # 锁
        self._stats_lock = threading.Lock()
        self._tasks_lock = threading.Lock()

        app_logger.log_audio_event(
            "TaskQueueManager initialized", {"worker_count": worker_count}
        )

    def register_task_handler(self, task_type: str, handler: Callable) -> None:
        """注册任务处理器

        Args:
            task_type: 任务类型
            handler: 处理器函数
        """
        self._task_handlers[task_type] = handler
        app_logger.log_audio_event("Task handler registered", {"task_type": task_type})

    def _do_start(self) -> bool:
        """启动任务队列管理器

        Returns:
            True if start successful
        """
        self._shutdown_event.clear()

        # 启动工作线程
        for i in range(self.worker_count):
            worker = threading.Thread(
                target=self._worker_loop, name=f"TaskWorker-{i}", daemon=True
            )
            worker.start()
            self._workers.append(worker)

        app_logger.log_audio_event(
            "TaskQueueManager started", {"worker_count": len(self._workers)}
        )

        # 发送启动事件
        self._emit_task_event(
            "task_queue_started", {"worker_count": len(self._workers)}
        )

        return True

    def _do_stop(self) -> bool:
        """停止任务队列管理器

        Returns:
            True if stop successful
        """
        timeout = 10.0
        app_logger.log_audio_event("TaskQueueManager stopping", {"timeout": timeout})

        # 设置关闭事件
        self._shutdown_event.set()

        # 等待工作线程结束
        for worker in self._workers:
            worker.join(timeout=timeout)

        # 清理资源
        with self._tasks_lock:
            self._running_tasks.clear()

        self._workers.clear()

        # 清空队列 (merged from cleanup())
        while not self._task_queue.empty():
            try:
                self._task_queue.get_nowait()
                self._task_queue.task_done()
            except queue.Empty:
                break

        # 清理注册的处理器 (merged from cleanup())
        self._task_handlers.clear()

        app_logger.log_audio_event("TaskQueueManager stopped", {})

        # 发送停止事件
        self._emit_task_event("task_queue_stopped", {})

        return True

    def submit_task(
        self,
        task_type: str,
        data: Optional[Dict[str, Any]] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        callback: Optional[Callable] = None,
        error_callback: Optional[Callable] = None,
        timeout: Optional[float] = None,
        max_retries: int = 0,
    ) -> str:
        """提交任务

        Args:
            task_type: 任务类型
            data: 任务数据
            priority: 任务优先级
            callback: 成功回调
            error_callback: 错误回调
            timeout: 超时时间
            max_retries: 最大重试次数

        Returns:
            任务ID
        """
        if not self.is_running:
            raise RuntimeError("TaskQueueManager is not running")

        if task_type not in self._task_handlers:
            raise ValueError(f"No handler registered for task type: {task_type}")

        # 创建任务
        task = Task(
            task_id=str(uuid.uuid4()),
            task_type=task_type,
            data=data or {},
            priority=priority,
            callback=callback,
            error_callback=error_callback,
            timeout=timeout,
            max_retries=max_retries,
        )

        try:
            # 添加到队列
            self._task_queue.put(task, timeout=1.0)

            # 更新统计
            with self._stats_lock:
                self._stats["total_tasks"] += 1

            app_logger.log_audio_event(
                "Task submitted",
                {
                    "task_id": task.task_id,
                    "task_type": task_type,
                    "priority": priority.name,
                    "queue_size": self._task_queue.qsize(),
                },
            )

            # 发送任务提交事件
            self._emit_task_event(
                "task_submitted", {"task_id": task.task_id, "task_type": task_type}
            )

            return task.task_id

        except queue.Full:
            raise RuntimeError("Task queue is full")

    def cancel_task(self, task_id: str) -> bool:
        """取消任务

        Args:
            task_id: 任务ID

        Returns:
            True如果成功取消
        """
        # 首先检查是否在运行中
        with self._tasks_lock:
            if task_id in self._running_tasks:
                task = self._running_tasks[task_id]
                task.status = TaskStatus.CANCELLED
                app_logger.log_audio_event(
                    "Running task cancelled", {"task_id": task_id}
                )
                return True

        # 尝试从队列中移除（这个比较困难，因为PriorityQueue不支持直接移除）
        # 这里简化处理，通过标记来取消
        app_logger.log_audio_event("Task cancel requested", {"task_id": task_id})

        return False

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态

        Args:
            task_id: 任务ID

        Returns:
            任务状态信息，如果任务不存在则返回None
        """
        with self._tasks_lock:
            if task_id in self._running_tasks:
                task = self._running_tasks[task_id]
                return self._task_to_dict(task)

        return None

    def get_queue_size(self) -> int:
        """获取队列大小

        Returns:
            队列中的任务数量
        """
        return self._task_queue.qsize()

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息

        Returns:
            统计信息字典
        """
        with self._stats_lock:
            stats = self._stats.copy()
            stats["queue_size"] = self._task_queue.qsize()
            stats["running_tasks"] = len(self._running_tasks)
            stats["is_running"] = self.is_running
            return stats

    def _worker_loop(self) -> None:
        """工作线程主循环"""
        worker_name = threading.current_thread().name
        app_logger.log_audio_event(
            "Worker thread started", {"worker_name": worker_name}
        )

        while not self._shutdown_event.is_set():
            try:
                # 获取任务（带超时）
                try:
                    task = self._task_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                # 执行任务
                self._execute_task(task)

            except Exception as e:
                app_logger.log_error(e, "worker_loop_error")

        app_logger.log_audio_event(
            "Worker thread stopped", {"worker_name": worker_name}
        )

    def _execute_task(self, task: Task) -> None:
        """执行任务

        Args:
            task: 任务对象
        """
        # 更新任务状态
        task.status = TaskStatus.RUNNING
        task.started_at = time.time()

        with self._tasks_lock:
            self._running_tasks[task.task_id] = task

        # Refactored to avoid try-finally with return for Nuitka compatibility
        retry_scheduled = False

        try:
            app_logger.log_audio_event(
                "Task execution started",
                {"task_id": task.task_id, "task_type": task.task_type},
            )

            # 获取处理器
            handler = self._task_handlers.get(task.task_type)
            if not handler:
                raise ValueError(f"No handler for task type: {task.task_type}")

            # 执行处理器
            if task.timeout:
                result = self._execute_with_timeout(handler, task.data, task.timeout)
            else:
                result = handler(task.data)

            # 任务成功
            task.status = TaskStatus.COMPLETED
            task.completed_at = time.time()
            task.result = result

            # 更新统计
            with self._stats_lock:
                self._stats["completed_tasks"] += 1
                self._update_execution_time_stats(task)

            app_logger.log_audio_event(
                "Task completed successfully",
                {
                    "task_id": task.task_id,
                    "execution_time": task.completed_at - task.started_at,
                },
            )

            # 执行成功回调
            if task.callback:
                try:
                    task.callback(result)
                except Exception as e:
                    app_logger.log_error(e, "task_callback_error")

            # 发送任务完成事件
            self._emit_task_event(
                "task_completed", {"task_id": task.task_id, "result": result}
            )

        except Exception as e:
            # 任务失败
            task.status = TaskStatus.FAILED
            task.completed_at = time.time()
            task.error = str(e)

            # 检查是否需要重试
            if task.retry_count < task.max_retries:
                task.retry_count += 1
                task.status = TaskStatus.PENDING
                task.started_at = None
                task.completed_at = None

                # 重新加入队列
                try:
                    self._task_queue.put(task, timeout=1.0)

                    app_logger.log_audio_event(
                        "Task retry scheduled",
                        {
                            "task_id": task.task_id,
                            "retry_count": task.retry_count,
                            "max_retries": task.max_retries,
                        },
                    )

                    retry_scheduled = True
                except queue.Full:
                    app_logger.log_error(
                        Exception("Queue full during retry"), "task_retry_failed"
                    )

            # Only continue with error handling if retry was not scheduled
            if not retry_scheduled:
                # 更新统计
                with self._stats_lock:
                    self._stats["failed_tasks"] += 1

                app_logger.log_error(e, f"task_execution_failed_{task.task_type}")

                # 执行错误回调
                if task.error_callback:
                    try:
                        task.error_callback(str(e))
                    except Exception as callback_error:
                        app_logger.log_error(
                            callback_error, "task_error_callback_error"
                        )

                # 发送任务失败事件
                self._emit_task_event(
                    "task_failed",
                    {
                        "task_id": task.task_id,
                        "error": str(e),
                        "retry_count": task.retry_count,
                    },
                )

        finally:
            # 清理运行任务记录
            with self._tasks_lock:
                self._running_tasks.pop(task.task_id, None)

            # 标记队列任务完成
            self._task_queue.task_done()

    def _execute_with_timeout(
        self, handler: Callable, data: Dict[str, Any], timeout: float
    ) -> Any:
        """带超时执行处理器

        Args:
            handler: 处理器函数
            data: 任务数据
            timeout: 超时时间

        Returns:
            处理结果

        Raises:
            TimeoutError: 如果执行超时
        """
        # 使用线程和Event来实现超时
        result_container = {}
        exception_container = {}
        completed_event = threading.Event()

        def target():
            try:
                result_container["result"] = handler(data)
            except Exception as e:
                exception_container["exception"] = e
            finally:
                completed_event.set()

        # 启动执行线程 - 设置daemon标志防止阻止进程退出
        thread = threading.Thread(target=target, daemon=True)
        thread.start()

        # 等待完成或超时
        if completed_event.wait(timeout=timeout):
            thread.join(timeout=5.0)  # 增加join超时时间到5秒

            if "exception" in exception_container:
                raise exception_container["exception"]

            return result_container.get("result")
        else:
            # 超时处理 - daemon线程会自动清理，不会阻止进程退出
            error_msg = f"Task execution timed out after {timeout}s"
            app_logger.log_error(TimeoutError(error_msg), "task_timeout")
            raise TimeoutError(error_msg)

    def _update_execution_time_stats(self, task: Task) -> None:
        """更新执行时间统计

        Args:
            task: 已完成的任务
        """
        if task.started_at and task.completed_at:
            execution_time = task.completed_at - task.started_at

            completed = self._stats["completed_tasks"]
            if completed == 1:
                self._stats["average_execution_time"] = execution_time
            else:
                # 计算移动平均
                current_avg = self._stats["average_execution_time"]
                self._stats["average_execution_time"] = (
                    current_avg * (completed - 1) + execution_time
                ) / completed

    def _task_to_dict(self, task: Task) -> Dict[str, Any]:
        """将任务对象转换为字典

        Args:
            task: 任务对象

        Returns:
            任务信息字典
        """
        return {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "priority": task.priority.name,
            "status": task.status.value,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "retry_count": task.retry_count,
            "max_retries": task.max_retries,
            "has_result": task.result is not None,
            "has_error": task.error is not None,
        }

    def _emit_task_event(self, event_name: str, data: Dict[str, Any]) -> None:
        """发送任务事件

        Args:
            event_name: 事件名称
            data: 事件数据
        """
        if self.event_service:
            try:
                self.event_service.emit(event_name, data)
            except Exception as e:
                app_logger.log_error(e, "emit_task_event")
