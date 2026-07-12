"""Benchmark first AI output latency using the real chunk-triggered chain.

This script replays existing history audio through:
1. Current configured ASR provider, chunked by `audio.streaming.chunk_duration`
2. The real `AIProcessingController` first-chunk-output path
3. Event timing based on the first emitted AI text event

Metric:
- `first_visible_vs_stop_s`: first visible AI output minus recording stop time, can be negative
- `wait_after_stop_s`: `max(0, first_visible_vs_stop_s)`, used for main P50/P95
- `total_to_first_visible_s`: simulated time from recording start to first AI text visible

Filtering rules:
- exclude 429 / rate limit / timeout errors
- exclude `tps_avg <= min_tps`
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from statistics import mean
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from sonicinput.ai.factory import AIClientFactory
from sonicinput.core.controllers.ai_processing_controller import AIProcessingController
from sonicinput.core.interfaces import (
    EventPriority,
    HistoryRecord,
    IConfigService,
    IEventService,
)
from sonicinput.core.services.config import ConfigKeys
from sonicinput.core.services.events import Events
from sonicinput.core.services.state_manager import StateManager
from sonicinput.core.services.storage.history_storage_service import (
    HistoryStorageService,
)
from sonicinput.speech.speech_service_factory import SpeechServiceFactory

SAMPLE_RATE = 16000


@dataclass
class Sample:
    record_id: str
    timestamp: str
    audio_file_path: str
    duration: float


class ConfigShim(IConfigService):
    def __init__(self, config: Dict[str, Any]):
        self._config = config

    def get_setting(self, key: str, default: Any = None) -> Any:
        value: Any = self._config
        for part in key.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        return value

    def set_setting(self, key: str, value: Any) -> None:
        target = self._config
        parts = key.split(".")
        for part in parts[:-1]:
            nested = target.get(part)
            if not isinstance(nested, dict):
                nested = {}
                target[part] = nested
            target = nested
        target[parts[-1]] = value

    def get_all_settings(self) -> Dict[str, Any]:
        return dict(self._config)

    def save_config(self) -> bool:
        return True


class DummyHistoryService(HistoryStorageService):
    def get_record_by_id(self, record_id: str) -> Optional[HistoryRecord]:
        del record_id
        return None


class BenchmarkEventService(IEventService):
    def __init__(self) -> None:
        self._phase_start: Optional[float] = None
        self.first_output_runtime_s: Optional[float] = None
        self.first_output_event: str = ""

    def begin_phase(self) -> None:
        self._phase_start = time.perf_counter()

    def end_phase(self) -> float:
        if self._phase_start is None:
            return 0.0
        return time.perf_counter() - self._phase_start

    def emit(
        self,
        event_name: str,
        data: Any = None,
        priority: EventPriority = EventPriority.NORMAL,
    ) -> None:
        del priority
        if (
            self._phase_start is not None
            and self.first_output_runtime_s is None
            and event_name
            in {Events.AI_INCREMENTAL_TEXT_UPDATED, Events.AI_PROCESSED_TEXT}
        ):
            self.first_output_runtime_s = time.perf_counter() - self._phase_start
            self.first_output_event = event_name

    def on(
        self,
        event_name: str,
        handler: Callable,
        priority: EventPriority = EventPriority.NORMAL,
    ) -> str:
        del handler, priority
        return f"{event_name}-noop"

    def once(
        self,
        event_name: str,
        handler: Callable,
        priority: EventPriority = EventPriority.NORMAL,
    ) -> str:
        return self.on(event_name, handler, priority)

    def subscribe(
        self,
        event_name: str,
        handler: Callable[[Any], None],
        priority: EventPriority = EventPriority.NORMAL,
        is_once: bool = False,
        namespace: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        del is_once, namespace, metadata
        return self.on(event_name, handler, priority)

    def off(self, event_name: str, listener_id: str) -> bool:
        del event_name, listener_id
        return True


def _default_config_path() -> Path:
    return Path(os.environ.get("APPDATA", ".")) / "SonicInput" / "config.json"


def _default_history_db_path() -> Path:
    return (
        Path(os.environ.get("APPDATA", ".")) / "SonicInput" / "history" / "history.db"
    )


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_recent_samples(history_db: Path, limit: int) -> List[Sample]:
    sql = """
    SELECT id, timestamp, audio_file_path, duration
    FROM history_records
    WHERE transcription_status = 'success'
      AND audio_file_path IS NOT NULL
      AND duration > 0
    ORDER BY timestamp DESC
    LIMIT ?
    """
    conn = sqlite3.connect(str(history_db))
    try:
        rows = conn.execute(sql, (limit * 3,)).fetchall()
    finally:
        conn.close()

    samples: List[Sample] = []
    for row in rows:
        sample = Sample(*row)
        if Path(sample.audio_file_path).exists():
            samples.append(sample)
        if len(samples) >= limit:
            break
    return samples


def load_sample_by_id(history_db: Path, record_id: str) -> Sample:
    sql = """
    SELECT id, timestamp, audio_file_path, duration
    FROM history_records
    WHERE id = ?
      AND transcription_status = 'success'
      AND audio_file_path IS NOT NULL
      AND duration > 0
    LIMIT 1
    """
    conn = sqlite3.connect(str(history_db))
    try:
        row = conn.execute(sql, (record_id,)).fetchone()
    finally:
        conn.close()

    if not row:
        raise RuntimeError(f"Sample not found: {record_id}")
    sample = Sample(*row)
    if not Path(sample.audio_file_path).exists():
        raise FileNotFoundError(f"Audio not found: {sample.audio_file_path}")
    return sample


def load_wav_as_float32(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        framerate = wav_file.getframerate()
        frames = wav_file.readframes(wav_file.getnframes())

    if sample_width == 2:
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif sample_width == 4:
        audio = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported sample width: {sample_width}")

    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1).astype(np.float32)

    if framerate != SAMPLE_RATE:
        audio = resample_linear(audio, framerate, SAMPLE_RATE)

    return audio.astype(np.float32)


def resample_linear(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate or len(audio) == 0:
        return audio.astype(np.float32)
    ratio = dst_rate / float(src_rate)
    target_len = max(1, int(len(audio) * ratio))
    x_old = np.linspace(0.0, 1.0, len(audio), endpoint=False)
    x_new = np.linspace(0.0, 1.0, target_len, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)


def split_chunks(audio: np.ndarray, chunk_duration: float) -> List[np.ndarray]:
    step = int(chunk_duration * SAMPLE_RATE)
    if step <= 0:
        raise ValueError("chunk_duration must be > 0")
    chunks: List[np.ndarray] = []
    for start in range(0, len(audio), step):
        end = min(len(audio), start + step)
        chunk = audio[start:end]
        if len(chunk) > 0:
            chunks.append(chunk)
    return chunks


def percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    if pct <= 0:
        return min(values)
    if pct >= 100:
        return max(values)
    values_sorted = sorted(values)
    k = (len(values_sorted) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(values_sorted) - 1)
    if f == c:
        return values_sorted[f]
    return values_sorted[f] + (values_sorted[c] - values_sorted[f]) * (k - f)


def classify_error(err: Optional[str]) -> str:
    if not err:
        return ""
    err_lower = err.lower()
    if "429" in err_lower or "rate limit" in err_lower:
        return "rate_limit"
    if "timeout" in err_lower:
        return "timeout"
    return "other"


def get_language(config: ConfigShim) -> Optional[str]:
    language = config.get_setting(ConfigKeys.TRANSCRIPTION_LOCAL_LANGUAGE, "auto")
    if language == "auto":
        return None
    return language


def run_sample(
    sample: Sample,
    config: ConfigShim,
    speech_service: Any,
    ai_client: Any,
    chunk_duration: float,
    language: Optional[str],
) -> Dict[str, Any]:
    audio = load_wav_as_float32(Path(sample.audio_file_path))
    chunks = split_chunks(audio, chunk_duration=chunk_duration)

    events = BenchmarkEventService()
    controller = AIProcessingController(
        config_service=config,
        event_service=events,
        state_manager=StateManager(events),
        history_service=DummyHistoryService(config),
    )
    controller._get_current_ai_service = lambda: ai_client  # type: ignore[method-assign]
    controller._on_transcription_request(
        {
            "record_id": sample.record_id,
            "audio_duration": sample.duration,
            "recording_stop_time": 0.0,
        }
    )

    chunk_texts: List[str] = []
    tps_values: List[float] = []
    worker_available_s = 0.0
    total_to_first_visible_s: Optional[float] = None
    error: Optional[str] = None

    try:
        for index, chunk in enumerate(chunks):
            chunk_ready_s = min(sample.duration, (index + 1) * chunk_duration)
            asr_start_s = max(chunk_ready_s, worker_available_s)

            asr_begin = time.perf_counter()
            result = speech_service.transcribe(chunk, language=language)
            asr_runtime_s = time.perf_counter() - asr_begin
            chunk_text = str((result or {}).get("text", "") or "")
            chunk_texts.append(chunk_text)

            asr_finish_s = asr_start_s + asr_runtime_s
            events.begin_phase()
            controller._on_streaming_chunk_completed(
                {
                    "chunk_id": index,
                    "result": {
                        "success": True,
                        "text": chunk_text,
                    },
                }
            )
            phase_elapsed_s = events.end_phase()
            worker_available_s = asr_finish_s + phase_elapsed_s

            last_tps = getattr(ai_client, "_last_tps", 0.0)
            if last_tps:
                tps_values.append(float(last_tps))

            if (
                total_to_first_visible_s is None
                and events.first_output_runtime_s is not None
            ):
                total_to_first_visible_s = asr_finish_s + events.first_output_runtime_s

        final_text = controller._merge_chunk_texts_with_boundary_dedup(chunk_texts)
        final_trigger_s = max(sample.duration, worker_available_s)

        events.begin_phase()
        controller._on_transcription_completed(
            {
                "record_id": sample.record_id,
                "text": final_text,
                "streaming_mode": "chunked",
                "audio_duration": sample.duration,
                "recording_stop_time": 0.0,
            }
        )
        final_phase_elapsed_s = events.end_phase()
        worker_available_s = final_trigger_s + final_phase_elapsed_s

        last_tps = getattr(ai_client, "_last_tps", 0.0)
        if last_tps:
            tps_values.append(float(last_tps))

        if (
            total_to_first_visible_s is None
            and events.first_output_runtime_s is not None
        ):
            total_to_first_visible_s = final_trigger_s + events.first_output_runtime_s
    except Exception as exc:
        error = str(exc)

    tps_avg = mean(tps_values) if tps_values else 0.0
    total_to_first_visible_s = total_to_first_visible_s or 0.0
    first_visible_vs_stop_s = total_to_first_visible_s - sample.duration
    wait_after_stop_s = max(0.0, first_visible_vs_stop_s)
    return {
        "record_id": sample.record_id,
        "duration_s": sample.duration,
        "chunk_count": len(chunks),
        "first_visible_vs_stop_s": first_visible_vs_stop_s,
        "wait_after_stop_s": wait_after_stop_s,
        "total_to_first_visible_s": total_to_first_visible_s,
        "first_output_event": events.first_output_event,
        "tps_avg": tps_avg,
        "error": error or "",
    }


def run_single_sample_mode(args: argparse.Namespace) -> int:
    config_path = Path(args.config_path)
    history_db = Path(args.history_db)
    config_dict = load_json(config_path)
    config_dict.setdefault("ai", {}).setdefault("sentence_split", {})["enabled"] = True
    config_dict.setdefault("ai", {}).setdefault("first_chunk_output", {})["enabled"] = (
        True
    )
    config = ConfigShim(config_dict)

    sample = load_sample_by_id(history_db, args.record_id)
    speech_service = SpeechServiceFactory.create_from_config(config)
    if not speech_service:
        raise RuntimeError("Failed to create speech service from config")
    if (
        hasattr(speech_service, "is_model_loaded")
        and not speech_service.is_model_loaded
    ):
        if not speech_service.load_model():
            raise RuntimeError("Failed to load speech service model")

    ai_client = AIClientFactory.create_from_config(config)
    if not ai_client:
        raise RuntimeError("Failed to create AI client from config")

    record = run_sample(
        sample=sample,
        config=config,
        speech_service=speech_service,
        ai_client=ai_client,
        chunk_duration=float(
            config.get_setting(ConfigKeys.AUDIO_STREAMING_CHUNK_DURATION, 15.0)
        ),
        language=get_language(config),
    )
    Path(args.sample_output).write_text(
        json.dumps(record, ensure_ascii=False),
        encoding="utf-8",
    )
    return 0


def run_worker_mode(args: argparse.Namespace) -> int:
    config_path = Path(args.config_path)
    history_db = Path(args.history_db)
    config_dict = load_json(config_path)
    config_dict.setdefault("ai", {}).setdefault("sentence_split", {})["enabled"] = True
    config_dict.setdefault("ai", {}).setdefault("first_chunk_output", {})["enabled"] = (
        True
    )
    config = ConfigShim(config_dict)

    speech_service = SpeechServiceFactory.create_from_config(config)
    if not speech_service:
        raise RuntimeError("Failed to create speech service from config")
    if (
        hasattr(speech_service, "is_model_loaded")
        and not speech_service.is_model_loaded
    ):
        if not speech_service.load_model():
            raise RuntimeError("Failed to load speech service model")

    ai_client = AIClientFactory.create_from_config(config)
    if not ai_client:
        raise RuntimeError("Failed to create AI client from config")

    chunk_duration = float(
        config.get_setting(ConfigKeys.AUDIO_STREAMING_CHUNK_DURATION, 15.0)
    )
    language = get_language(config)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if payload.get("cmd") == "stop":
            break

        record_id = payload.get("record_id", "")
        index = int(payload.get("index", 0))
        try:
            sample = load_sample_by_id(history_db, record_id)
            record = run_sample(
                sample=sample,
                config=config,
                speech_service=speech_service,
                ai_client=ai_client,
                chunk_duration=chunk_duration,
                language=language,
            )
        except Exception as exc:
            record = {
                "record_id": record_id,
                "duration_s": 0.0,
                "chunk_count": 0,
                "first_visible_vs_stop_s": 0.0,
                "wait_after_stop_s": 0.0,
                "total_to_first_visible_s": 0.0,
                "first_output_event": "",
                "tps_avg": 0.0,
                "error": str(exc),
            }

        record["index"] = index
        sys.stdout.write(json.dumps(record, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    return 0


def run_sample_subprocess(
    sample: Sample,
    index: int,
    config_path: Path,
    history_db: Path,
    output_dir: Path,
    sample_timeout_seconds: int,
) -> Dict[str, Any]:
    sample_output_path = output_dir / f"{sample.record_id}.sample.json"
    if sample_output_path.exists():
        sample_output_path.unlink()

    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--record-id",
        sample.record_id,
        "--sample-output",
        str(sample_output_path),
        "--config-path",
        str(config_path),
        "--history-db",
        str(history_db),
    ]

    try:
        subprocess.run(
            cmd,
            check=True,
            timeout=sample_timeout_seconds,
            cwd=str(Path.cwd()),
        )
        if not sample_output_path.exists():
            raise RuntimeError("Sample output file missing")
        record = json.loads(sample_output_path.read_text(encoding="utf-8"))
    except subprocess.TimeoutExpired:
        record = {
            "record_id": sample.record_id,
            "duration_s": sample.duration,
            "chunk_count": 0,
            "first_visible_vs_stop_s": 0.0,
            "wait_after_stop_s": 0.0,
            "total_to_first_visible_s": 0.0,
            "first_output_event": "",
            "tps_avg": 0.0,
            "error": f"sample_timeout_{sample_timeout_seconds}s",
        }
    except Exception as exc:
        record = {
            "record_id": sample.record_id,
            "duration_s": sample.duration,
            "chunk_count": 0,
            "first_visible_vs_stop_s": 0.0,
            "wait_after_stop_s": 0.0,
            "total_to_first_visible_s": 0.0,
            "first_output_event": "",
            "tps_avg": 0.0,
            "error": str(exc),
        }
    finally:
        if sample_output_path.exists():
            sample_output_path.unlink()

    record["index"] = index
    return record


def start_worker_process(config_path: Path, history_db: Path) -> subprocess.Popen[str]:
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--config-path",
        str(config_path),
        "--history-db",
        str(history_db),
    ]
    return subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        text=True,
        bufsize=1,
        cwd=str(Path.cwd()),
    )


def worker_process_samples(
    worker_id: int,
    samples: List[tuple[int, Sample]],
    config_path: Path,
    history_db: Path,
    output_queue: Queue[Dict[str, Any]],
) -> None:
    if not samples:
        return

    proc = start_worker_process(config_path, history_db)
    remaining = list(samples)
    try:
        while remaining:
            index, sample = remaining[0]
            payload = {"record_id": sample.record_id, "index": index}
            assert proc.stdin is not None
            proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            proc.stdin.flush()

            assert proc.stdout is not None
            line = proc.stdout.readline()
            if not line:
                raise RuntimeError(f"worker_{worker_id} exited unexpectedly")
            record = json.loads(line)
            output_queue.put(record)
            remaining.pop(0)

        if proc.stdin:
            proc.stdin.write(json.dumps({"cmd": "stop"}) + "\n")
            proc.stdin.flush()
    except Exception as exc:
        for index, sample in remaining:
            output_queue.put(
                {
                    "record_id": sample.record_id,
                    "duration_s": sample.duration,
                    "chunk_count": 0,
                    "first_visible_vs_stop_s": 0.0,
                    "wait_after_stop_s": 0.0,
                    "total_to_first_visible_s": 0.0,
                    "first_output_event": "",
                    "tps_avg": 0.0,
                    "error": str(exc),
                    "index": index,
                }
            )
    finally:
        if proc.poll() is None:
            proc.kill()


def _handle_record(
    record: Dict[str, Any],
    index: int,
    args: argparse.Namespace,
    chunk_duration: float,
    error_counts: Dict[str, int],
    results: List[Dict[str, Any]],
    out: Any,
) -> None:
    err_class = classify_error(record["error"])
    if err_class:
        error_counts[err_class] += 1

    record.update(
        {
            "eligible": not record["error"] and record["tps_avg"] > args.min_tps,
            "chunk_duration_s": chunk_duration,
        }
    )
    results.append(record)
    out.write(json.dumps(record, ensure_ascii=False) + "\n")
    out.flush()

    print(
        f"[{index}/{args.limit}] first_visible_vs_stop_s={record['first_visible_vs_stop_s']:.2f} "
        f"wait_after_stop_s={record['wait_after_stop_s']:.2f} "
        f"event={record['first_output_event'] or 'none'} "
        f"tps_avg={record['tps_avg']:.1f} eligible={record['eligible']}"
    )

    if len(results) < args.limit and args.sleep_seconds > 0:
        time.sleep(args.sleep_seconds)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    parser.add_argument("--min-tps", type=float, default=100.0)
    parser.add_argument("--config-path", type=str, default=str(_default_config_path()))
    parser.add_argument(
        "--history-db", type=str, default=str(_default_history_db_path())
    )
    parser.add_argument("--output", type=str, default="")
    parser.add_argument("--resume", action="store_true", default=False)
    parser.add_argument("--record-id", type=str, default="")
    parser.add_argument("--sample-output", type=str, default="")
    parser.add_argument("--sample-timeout-seconds", type=int, default=600)
    parser.add_argument("--max-concurrency", type=int, default=1)
    parser.add_argument("--isolate-samples", action="store_true", default=False)
    parser.add_argument("--worker", action="store_true", default=False)
    args = parser.parse_args()

    if args.worker:
        raise SystemExit(run_worker_mode(args))

    if args.record_id:
        raise SystemExit(run_single_sample_mode(args))

    config_path = Path(args.config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    history_db = Path(args.history_db)
    if not history_db.exists():
        raise FileNotFoundError(f"History DB not found: {history_db}")

    config_dict = load_json(config_path)
    chunk_duration = (
        config_dict.get("audio", {}).get("streaming", {}).get("chunk_duration", 15.0)
    )

    samples = load_recent_samples(history_db, args.limit)
    if not samples:
        raise RuntimeError("No eligible samples found in history DB")

    results: List[Dict[str, Any]] = []
    processed_ids: set[str] = set()
    error_counts: Dict[str, int] = {"rate_limit": 0, "timeout": 0, "other": 0}

    output_path = Path(args.output) if args.output else None
    if output_path is None:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_path = (
            Path("artifacts") / f"ai_first_output_real_chain_{timestamp}.jsonl"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and args.resume:
        for line in output_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            results.append(item)
            processed_ids.add(item.get("record_id", ""))
        print(f"resume: loaded {len(results)} existing results from {output_path}")

    pending_samples: List[tuple[int, Sample]] = []
    next_index = len(results) + 1
    for sample in samples:
        if sample.record_id in processed_ids:
            continue
        if len(pending_samples) >= args.limit - len(results):
            break
        pending_samples.append((next_index, sample))
        next_index += 1

    with output_path.open("a", encoding="utf-8") as out:
        if args.isolate_samples:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=max(1, args.max_concurrency)
            ) as executor:
                future_to_meta = {
                    executor.submit(
                        run_sample_subprocess,
                        sample=sample,
                        index=index,
                        config_path=config_path,
                        history_db=history_db,
                        output_dir=output_path.parent,
                        sample_timeout_seconds=args.sample_timeout_seconds,
                    ): (index, sample.record_id)
                    for index, sample in pending_samples
                }

                for future in concurrent.futures.as_completed(future_to_meta):
                    index, _record_id = future_to_meta[future]
                    record = future.result()
                    _handle_record(
                        record=record,
                        index=index,
                        args=args,
                        chunk_duration=chunk_duration,
                        error_counts=error_counts,
                        results=results,
                        out=out,
                    )
        else:
            worker_count = max(1, args.max_concurrency)
            buckets: List[List[tuple[int, Sample]]] = [[] for _ in range(worker_count)]
            for idx, item in enumerate(pending_samples):
                buckets[idx % worker_count].append(item)

            output_queue: Queue[Dict[str, Any]] = Queue()
            threads: List[threading.Thread] = []
            for worker_id, bucket in enumerate(buckets):
                thread = threading.Thread(
                    target=worker_process_samples,
                    args=(worker_id, bucket, config_path, history_db, output_queue),
                    daemon=True,
                )
                threads.append(thread)
                thread.start()

            total_expected = len(pending_samples)
            received = 0
            while received < total_expected:
                record = output_queue.get()
                received += 1
                index = int(record.get("index", 0))
                _handle_record(
                    record=record,
                    index=index,
                    args=args,
                    chunk_duration=chunk_duration,
                    error_counts=error_counts,
                    results=results,
                    out=out,
                )

            for thread in threads:
                thread.join()

    def summarize(limit: int) -> None:
        subset = sorted(
            [r for r in results if r["index"] <= limit],
            key=lambda item: item["index"],
        )
        eligible = [r for r in subset if r["eligible"]]
        values = [r["wait_after_stop_s"] for r in eligible]
        negative_count = sum(1 for r in eligible if r["first_visible_vs_stop_s"] < 0)
        print("")
        print(f"summary_limit={limit}")
        print(f"total={len(subset)} eligible={len(eligible)}")
        print(
            f"wait_after_stop_s_p50={percentile(values, 50):.2f} "
            f"wait_after_stop_s_p95={percentile(values, 95):.2f}"
        )
        print(f"first_visible_before_stop={negative_count}")

    summarize(min(500, len(results)))
    summarize(len(results))

    print("")
    print("error_counts:", error_counts)
    print("output:", output_path)


if __name__ == "__main__":
    main()
