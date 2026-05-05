import threading
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from sonicinput.core.base.lifecycle_component import ComponentState
from sonicinput.core.services.task_queue_manager import TaskPriority
from sonicinput.core.services.transcription_service import (
    TranscriptionService,
)


def _make_running_service() -> TranscriptionService:
    service = TranscriptionService.__new__(TranscriptionService)
    service._state = ComponentState.RUNNING
    service.task_queue_manager = Mock()
    service.streaming_coordinator = Mock()
    return service


def test_start_streaming_processing_requires_running_state() -> None:
    service = TranscriptionService.__new__(TranscriptionService)
    service._state = ComponentState.STOPPED
    service.task_queue_manager = Mock()
    service.streaming_coordinator = Mock()

    with pytest.raises(RuntimeError, match="not started"):
        service.start_streaming_processing()


def test_start_streaming_processing_skips_when_no_pending_chunks() -> None:
    service = _make_running_service()
    service.streaming_coordinator.get_pending_chunks.return_value = []

    service.start_streaming_processing()

    service.task_queue_manager.submit_task.assert_not_called()


def test_start_streaming_processing_submits_only_unfinished_chunks() -> None:
    service = _make_running_service()

    pending_event = threading.Event()
    completed_event = threading.Event()
    completed_event.set()
    pending_audio = np.array([0.1, 0.2], dtype=np.float32)

    pending_chunk = SimpleNamespace(
        chunk_id=101,
        audio_data=pending_audio,
        result_event=pending_event,
    )
    completed_chunk = SimpleNamespace(
        chunk_id=102,
        audio_data=np.array([0.3], dtype=np.float32),
        result_event=completed_event,
    )
    service.streaming_coordinator.get_pending_chunks.return_value = [
        pending_chunk,
        completed_chunk,
    ]

    service.start_streaming_processing()

    assert service.task_queue_manager.submit_task.call_count == 1
    call_kwargs = service.task_queue_manager.submit_task.call_args.kwargs
    assert call_kwargs["task_type"] == "process_streaming_chunk"
    assert call_kwargs["priority"] == TaskPriority.HIGH
    assert call_kwargs["max_retries"] == 0
    assert call_kwargs["data"]["chunk_id"] == 101
    assert np.array_equal(call_kwargs["data"]["audio_data"], pending_audio)
