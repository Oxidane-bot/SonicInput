import sys
import threading
import types

import numpy as np


def _ensure_pyaudio_importable() -> None:
    try:
        import pyaudio  # noqa: F401
    except ImportError:
        pyaudio_stub = types.ModuleType("pyaudio")
        pyaudio_stub.paInt16 = 8

        class PyAudio:  # pragma: no cover
            def __init__(self, *args, **kwargs):
                pass

        pyaudio_stub.PyAudio = PyAudio
        sys.modules["pyaudio"] = pyaudio_stub


_ensure_pyaudio_importable()

from sonicinput.audio.recorder import AudioRecorder  # noqa: E402


def test_get_remaining_audio_for_streaming_updates_accumulated_buffer() -> None:
    recorder = AudioRecorder.__new__(AudioRecorder)
    recorder._data_lock = threading.Lock()
    recorder.chunk_size = 4
    recorder._sample_rate = 4
    recorder._audio_data = [
        np.array([0, 1, 2, 3], dtype=np.float32),
        np.array([4, 5, 6, 7], dtype=np.float32),
        np.array([8, 9, 10, 11], dtype=np.float32),
    ]
    recorder._accumulated_audio = np.concatenate(
        recorder._audio_data[:2], axis=0
    ).flatten()
    recorder._chunked_samples_sent = len(recorder._accumulated_audio)

    remaining = recorder.get_remaining_audio_for_streaming()

    assert remaining.tolist() == [8.0, 9.0, 10.0, 11.0]


def test_chunk_ready_tracks_variable_size_chunks_without_duplicates() -> None:
    recorder = AudioRecorder.__new__(AudioRecorder)
    recorder._data_lock = threading.Lock()
    recorder.chunk_size = 4
    recorder.chunk_duration = 15.0
    recorder._sample_rate = 4
    recorder._recording = True
    recorder._audio_data = [
        np.array([0, 1, 2, 3], dtype=np.float32),
        np.array([4, 5], dtype=np.float32),
    ]
    recorder._accumulated_audio = None
    recorder._chunked_samples_sent = 0
    sent_chunks = []
    recorder.chunk_callback = lambda audio: sent_chunks.append(audio.copy())

    recorder._on_chunk_ready()
    recorder._audio_data.append(np.array([6, 7, 8, 9], dtype=np.float32))
    recorder._on_chunk_ready()

    assert [chunk.tolist() for chunk in sent_chunks] == [
        [0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
        [6.0, 7.0, 8.0, 9.0],
    ]


def test_remaining_audio_tracks_variable_size_chunks_without_duplicates() -> None:
    recorder = AudioRecorder.__new__(AudioRecorder)
    recorder._data_lock = threading.Lock()
    recorder.chunk_size = 4
    recorder._sample_rate = 4
    recorder._audio_data = [
        np.array([0, 1, 2, 3], dtype=np.float32),
        np.array([4, 5], dtype=np.float32),
        np.array([6, 7, 8, 9], dtype=np.float32),
    ]
    recorder._accumulated_audio = np.concatenate(
        recorder._audio_data[:2], axis=0
    ).flatten()
    recorder._chunked_samples_sent = len(recorder._accumulated_audio)

    remaining = recorder.get_remaining_audio_for_streaming()

    assert remaining.tolist() == [6.0, 7.0, 8.0, 9.0]


def test_record_audio_uses_stable_stream_reference_during_stop_race() -> None:
    recorder = AudioRecorder.__new__(AudioRecorder)
    recorder._data_lock = threading.Lock()
    recorder._recording = True
    recorder._audio_data = []
    recorder._callback = None
    recorder.chunk_size = 2
    recorder.chunk_duration = 999.0

    class RaceyStream:
        def __bool__(self) -> bool:
            recorder._stream = None
            return True

        def read(self, chunk_size, exception_on_overflow=False):
            recorder._recording = False
            return np.array([1, 2], dtype=np.int16).tobytes()

    recorder._stream = RaceyStream()

    recorder._record_audio()

    assert len(recorder._audio_data) == 1
    assert recorder._audio_data[0].tolist() == [1 / 32768.0, 2 / 32768.0]
