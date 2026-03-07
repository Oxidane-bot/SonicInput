from datetime import datetime
from unittest.mock import Mock, patch

import numpy as np

from sonicinput.core.interfaces import HistoryRecord
from sonicinput.ui.settings_tabs.history_tab import BatchReprocessingWorker


class _DummyConfigService:
    def get_setting(self, key, default=None):
        values = {
            "transcription.provider": "local",
            "transcription.local.language": "zh",
            "ai.enabled": False,
        }
        return values.get(key, default)


class _FakeHistoryService:
    def __init__(self, records):
        self._records = records
        self._returned = False
        self.keyset_calls = []
        self.saved_batches = []

    def get_records_keyset(
        self, limit, cursor_timestamp=None, cursor_id=None, order="DESC"
    ):
        self.keyset_calls.append(
            {
                "limit": limit,
                "cursor_timestamp": cursor_timestamp,
                "cursor_id": cursor_id,
                "order": order,
            }
        )
        if self._returned:
            return []
        self._returned = True
        return self._records[:limit]

    def save_records_batch(self, records):
        self.saved_batches.append(list(records))
        return len(records)


def _make_record(record_id: str, ts: datetime) -> HistoryRecord:
    return HistoryRecord(
        id=record_id,
        timestamp=ts,
        audio_file_path=f"C:/{record_id}.wav",
        duration=1.0,
        transcription_text="old",
        transcription_provider="local",
        transcription_status="success",
        streaming_mode="chunked",
        transcription_duration=0.1,
        used_fallback=False,
        fallback_type="none",
        fallback_reason=None,
        diagnostics_collected=True,
        reprocess_parent_id=None,
        transcription_error=None,
        ai_optimized_text=None,
        ai_provider=None,
        ai_status="skipped",
        ai_error=None,
        final_text="old",
    )


def test_batch_reprocessing_worker_uses_keyset_and_batch_save():
    records = [
        _make_record("r1", datetime(2026, 3, 8, 10, 0, 0)),
        _make_record("r2", datetime(2026, 3, 8, 11, 0, 0)),
    ]
    history_service = _FakeHistoryService(records)
    transcription_service = Mock()
    transcription_service.transcribe_sync.return_value = {"success": True, "text": "new"}

    worker = BatchReprocessingWorker(
        total_records=2,
        cd_seconds=0,
        transcription_service=transcription_service,
        ai_processing_controller=None,
        config_service=_DummyConfigService(),
        history_service=history_service,
        page_size=100,
    )

    with patch(
        "sonicinput.audio.recorder.AudioRecorder.load_audio_from_file",
        return_value=np.array([0.1, 0.2], dtype=np.float32),
    ):
        worker.run()

    assert history_service.keyset_calls
    assert history_service.keyset_calls[0]["order"] == "ASC"
    assert len(history_service.saved_batches) == 1
    assert len(history_service.saved_batches[0]) == 2
    assert worker.stats["success"] == 2
    assert worker.stats["failed"] == 0
