import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np

from sonicinput.core.base.lifecycle_component import ComponentState
from sonicinput.core.services.transcription_service_refactored import (
    RefactoredTranscriptionService,
)


def _make_chunk(chunk_id: int, audio: np.ndarray, text: str) -> SimpleNamespace:
    event = threading.Event()
    event.set()
    return SimpleNamespace(
        chunk_id=chunk_id,
        audio_data=audio,
        result_event=event,
        result_container={"success": True, "text": text},
    )


def test_stop_streaming_chunked_adds_context_overlap_and_dedupes_text() -> None:
    service = RefactoredTranscriptionService.__new__(RefactoredTranscriptionService)
    service.task_queue_manager = Mock()
    service.streaming_coordinator = Mock()

    chunk1_audio = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    chunk2_audio = np.array([4.0, 5.0], dtype=np.float32)
    chunk1 = _make_chunk(0, chunk1_audio, "你好世界")
    chunk2 = _make_chunk(1, chunk2_audio, "世界和平")

    service.streaming_coordinator.get_streaming_mode.return_value = "chunked"
    service.streaming_coordinator.get_pending_chunks.return_value = [chunk1, chunk2]
    service.streaming_coordinator.get_completed_chunks.return_value = []
    service.streaming_coordinator.stop_streaming.return_value = {"mode": "chunked"}

    result = service.stop_streaming()

    assert result["text"] == "你好世界和平"
    assert service.task_queue_manager.submit_task.call_count == 2

    first_call_data = service.task_queue_manager.submit_task.call_args_list[0].kwargs[
        "data"
    ]
    second_call_data = service.task_queue_manager.submit_task.call_args_list[1].kwargs[
        "data"
    ]

    assert np.array_equal(first_call_data["audio_data"], chunk1_audio)
    assert np.array_equal(
        second_call_data["audio_data"], np.concatenate([chunk1_audio, chunk2_audio])
    )


def test_stop_streaming_chunked_includes_chunks_completed_before_stop() -> None:
    service = RefactoredTranscriptionService.__new__(RefactoredTranscriptionService)
    service.task_queue_manager = Mock()
    service.streaming_coordinator = Mock()

    completed_chunk1 = _make_chunk(0, np.array([1.0], dtype=np.float32), "第一段。")
    completed_chunk2 = _make_chunk(1, np.array([2.0], dtype=np.float32), "第二段。")
    pending_chunk = _make_chunk(2, np.array([3.0], dtype=np.float32), "第三段。")

    service.streaming_coordinator.get_streaming_mode.return_value = "chunked"
    service.streaming_coordinator.get_completed_chunks.return_value = [
        completed_chunk1,
        completed_chunk2,
    ]
    service.streaming_coordinator.get_pending_chunks.return_value = [pending_chunk]
    service.streaming_coordinator.stop_streaming.return_value = {"mode": "chunked"}

    result = service.stop_streaming()

    assert result["text"] == "第一段。第二段。第三段。"
    assert service.task_queue_manager.submit_task.call_count == 1
    submitted_data = service.task_queue_manager.submit_task.call_args.kwargs["data"]
    assert submitted_data["chunk_id"] == 2


def test_merge_chunk_texts_with_boundary_dedup_handles_overlap_and_plain_concat() -> (
    None
):
    service = RefactoredTranscriptionService.__new__(RefactoredTranscriptionService)
    service._TEXT_OVERLAP_MAX_CHARS = 60
    service._TEXT_NORMALIZED_OVERLAP_MIN_CHARS = 8

    merged_overlap = service._merge_chunk_texts_with_boundary_dedup(
        ["abc123", "123xyz"]
    )
    assert merged_overlap == "abc123xyz"

    merged_plain = service._merge_chunk_texts_with_boundary_dedup(["hello", "world"])
    assert merged_plain == "hello world"

    merged_normalized = service._merge_chunk_texts_with_boundary_dedup(
        [
            "reference 的这些东西",
            "reference的这些东西 你就不需要提取出来",
        ]
    )
    assert merged_normalized == "reference 的这些东西 你就不需要提取出来"


def test_normalized_suffix_prefix_overlap_skip_ignores_spacing_and_punctuation() -> None:
    service = RefactoredTranscriptionService.__new__(RefactoredTranscriptionService)

    skip = service._normalized_suffix_prefix_overlap_skip(
        "review agent 的边界",
        "review agent的边界，然后再跑回归",
        max_chars=60,
        min_chars=8,
    )

    assert skip == len("review agent的边界")


def test_wait_for_chunk_results_uses_shared_timeout_budget() -> None:
    service = RefactoredTranscriptionService.__new__(RefactoredTranscriptionService)
    service._CHUNK_RESULT_MIN_TIMEOUT_SECONDS = 0.05
    service._CHUNK_WAIT_POLL_INTERVAL_SECONDS = 0.005

    chunk1 = SimpleNamespace(
        chunk_id=0,
        audio_data=np.array([1.0], dtype=np.float32),
        result_event=threading.Event(),
    )
    chunk2 = SimpleNamespace(
        chunk_id=1,
        audio_data=np.array([2.0], dtype=np.float32),
        result_event=threading.Event(),
    )

    started = time.perf_counter()
    timed_out = service._wait_for_chunk_results([chunk1, chunk2])
    elapsed = time.perf_counter() - started

    assert sorted(timed_out) == [0, 1]
    # 若按串行超时，耗时会接近 0.10s；共享预算应明显低于该值
    assert elapsed < 0.085


def test_add_streaming_chunk_submits_immediate_transcription_task() -> None:
    service = RefactoredTranscriptionService.__new__(RefactoredTranscriptionService)
    service._state = ComponentState.RUNNING
    service._CHUNK_CONTEXT_OVERLAP_SECONDS = 0.6
    service._streaming_chunk_prev_tail = np.array([8.0, 9.0], dtype=np.float32)
    service.task_queue_manager = Mock()
    service.streaming_coordinator = Mock()
    service.streaming_coordinator.add_streaming_chunk.return_value = 7

    audio = np.array([1.0, 2.0, 3.0], dtype=np.float32)

    chunk_id = service.add_streaming_chunk(audio)

    assert chunk_id == 7
    submitted = service.task_queue_manager.submit_task.call_args.kwargs
    assert submitted["task_type"] == "process_streaming_chunk"
    assert submitted["priority"].name == "HIGH"
    assert submitted["data"]["chunk_id"] == 7
    assert np.array_equal(
        submitted["data"]["audio_data"],
        np.array([8.0, 9.0, 1.0, 2.0, 3.0], dtype=np.float32),
    )
    assert np.array_equal(service._streaming_chunk_prev_tail, audio)
