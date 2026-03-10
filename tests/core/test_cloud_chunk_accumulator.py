from concurrent.futures import Future
import time
from unittest.mock import Mock

import numpy as np
import pytest

import sonicinput.speech.cloud_chunk_accumulator as accumulator_module
from sonicinput.speech.cloud_chunk_accumulator import CloudChunkAccumulator


def _ready_future(result):
    future = Future()
    future.set_result(result)
    return future


def test_transcribe_chunk_retries_and_raises_on_error_payload(monkeypatch):
    speech_service = Mock()
    speech_service.transcribe.return_value = {
        "error": "Internal Server Error",
        "error_code": 500,
    }
    accumulator = CloudChunkAccumulator(speech_service)
    monkeypatch.setattr(
        accumulator_module.time, "sleep", lambda *_args, **_kwargs: None
    )

    with pytest.raises(RuntimeError, match="Cloud transcription error"):
        accumulator._transcribe_chunk(0, np.zeros(1600, dtype=np.float32))

    assert speech_service.transcribe.call_count == 3
    accumulator.shutdown()


def test_get_results_filters_whitespace_only_chunk_text(monkeypatch):
    accumulator = CloudChunkAccumulator(Mock())
    monkeypatch.setattr(accumulator, "_flush_chunk", lambda: None)

    accumulator._chunks = [
        (0, _ready_future((0, "")), 1600),
        (1, _ready_future((1, "   ")), 1600),
        (2, _ready_future((2, "hello")), 1600),
        (3, _ready_future((3, " world ")), 1600),
    ]
    accumulator._chunk_counter = len(accumulator._chunks)

    result = accumulator.get_results(timeout=0.01)

    assert result["text"] == "hello world"
    assert result["stats"]["successful_chunks"] == 4
    assert result["stats"]["non_empty_chunks"] == 2
    assert result["stats"]["empty_chunks"] == 2
    accumulator.shutdown()


def test_get_results_uses_shared_deadline_for_parallel_futures(monkeypatch):
    accumulator = CloudChunkAccumulator(Mock(), sample_rate=16000)
    monkeypatch.setattr(accumulator, "_flush_chunk", lambda: None)

    future_a = Future()
    future_b = Future()
    accumulator._chunks = [
        (0, future_a, 1600),
        (1, future_b, 1600),
    ]
    accumulator._chunk_counter = len(accumulator._chunks)

    started = time.perf_counter()
    result = accumulator.get_results(timeout=0.05)
    elapsed = time.perf_counter() - started

    assert result["text"] == ""
    assert sorted(result["stats"]["failed_chunk_ids"]) == [0, 1]
    # 单块动态超时约 0.20s，若串行等待两块应接近 0.40s
    assert elapsed < 0.32
    accumulator.shutdown()
