"""ASR chunk boundary experiment runner.

Compare three paths on existing history audio:
1) Cloud full-file transcription (configured providers with API keys)
2) Current local chunked strategy (no overlap + naive join)
3) Improved local chunked strategy (overlap + boundary dedup merge)

Also includes local full-file transcription as a reference baseline.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
import wave
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from sonicinput.speech.speech_service_factory import SpeechServiceFactory

SAMPLE_RATE = 16000


@dataclass
class Sample:
    record_id: str
    timestamp: str
    audio_file_path: str
    duration: float
    transcription_provider: str
    transcription_status: str


def _default_config_path() -> Path:
    return Path(os.environ.get("APPDATA", ".")) / "SonicInput" / "config.json"


def _default_history_db_path() -> Path:
    return Path(os.environ.get("APPDATA", ".")) / "SonicInput" / "history" / "history.db"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_recent_samples(history_db: Path, min_duration: float, limit: int) -> List[Sample]:
    sql = """
    SELECT id, timestamp, audio_file_path, duration, transcription_provider, transcription_status
    FROM history_records
    WHERE audio_file_path IS NOT NULL
      AND duration >= ?
      AND transcription_status = 'success'
    ORDER BY timestamp DESC
    LIMIT ?
    """
    conn = sqlite3.connect(str(history_db))
    try:
        rows = conn.execute(sql, (min_duration, limit * 4)).fetchall()
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


def load_wav_as_float32(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        framerate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())

    if sample_width == 2:
        arr = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif sample_width == 4:
        arr = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported sample width: {sample_width}")

    if channels > 1:
        arr = arr.reshape(-1, channels).mean(axis=1).astype(np.float32)

    if framerate != SAMPLE_RATE:
        arr = resample_linear(arr, framerate, SAMPLE_RATE)

    return arr.astype(np.float32)


def resample_linear(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate or len(audio) == 0:
        return audio.astype(np.float32)
    ratio = dst_rate / float(src_rate)
    target_len = max(1, int(len(audio) * ratio))
    x_old = np.linspace(0.0, 1.0, len(audio), endpoint=False)
    x_new = np.linspace(0.0, 1.0, target_len, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)


def seq_ratio(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def split_chunks_current(audio: np.ndarray, chunk_duration: float) -> List[np.ndarray]:
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


def split_chunks_with_overlap(
    audio: np.ndarray, chunk_duration: float, overlap_seconds: float
) -> List[np.ndarray]:
    step = int(chunk_duration * SAMPLE_RATE)
    overlap = int(overlap_seconds * SAMPLE_RATE)
    if step <= 0:
        raise ValueError("chunk_duration must be > 0")
    if overlap < 0:
        overlap = 0

    chunks: List[np.ndarray] = []
    for base_start in range(0, len(audio), step):
        start = max(0, base_start - overlap)
        end = min(len(audio), base_start + step + overlap)
        chunk = audio[start:end]
        if len(chunk) > 0:
            chunks.append(chunk)
    return chunks


def smart_concat(a: str, b: str) -> str:
    if not a:
        return b
    if not b:
        return a
    if a[-1].isalnum() and b[0].isalnum():
        return a + " " + b
    return a + b


def longest_suffix_prefix_overlap(a: str, b: str, max_chars: int = 60) -> int:
    a = a.strip()
    b = b.strip()
    limit = min(len(a), len(b), max_chars)
    for k in range(limit, 0, -1):
        if a[-k:] == b[:k]:
            return k
    return 0


def merge_texts_with_dedup(parts: List[str], max_overlap_chars: int = 60) -> str:
    merged = ""
    for raw in parts:
        part = raw.strip()
        if not part:
            continue
        if not merged:
            merged = part
            continue

        overlap = longest_suffix_prefix_overlap(merged, part, max_chars=max_overlap_chars)
        if overlap > 0:
            merged = merged + part[overlap:]
        else:
            merged = smart_concat(merged, part)
    return merged.strip()


def transcribe_chunks(service: Any, chunks: List[np.ndarray], language: Optional[str]) -> List[str]:
    texts: List[str] = []
    for chunk in chunks:
        result = service.transcribe(chunk, language=language)
        text = result.get("text", "") if isinstance(result, dict) else ""
        if text is None:
            text = ""
        texts.append(str(text))
    return texts


def current_strategy_text(texts: List[str]) -> str:
    parts = [t for t in texts if t]
    return " ".join(parts).strip()


def boundary_pairs(texts: List[str], preview_chars: int = 12) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for i in range(len(texts) - 1):
        left = texts[i].strip()
        right = texts[i + 1].strip()
        rows.append(
            {
                "idx": str(i),
                "left_tail": left[-preview_chars:] if left else "",
                "right_head": right[:preview_chars] if right else "",
            }
        )
    return rows


def configured_cloud_providers(config: Dict[str, Any]) -> List[str]:
    t = config.get("transcription", {})
    providers: List[str] = []
    for p in ("groq", "siliconflow", "qwen"):
        api_key = t.get(p, {}).get("api_key", "")
        if isinstance(api_key, str) and api_key.strip():
            providers.append(p)
    return providers


def create_cloud_service(config: Dict[str, Any], provider: str) -> Any:
    t = config["transcription"][provider]
    kwargs: Dict[str, Any] = {
        "provider": provider,
        "api_key": t.get("api_key", ""),
        "model": t.get("model", ""),
        "base_url": t.get("base_url"),
    }
    if provider == "qwen":
        kwargs["enable_itn"] = t.get("enable_itn", True)
    service = SpeechServiceFactory.create_service(**kwargs)
    service.load_model()
    return service


def run_experiment(
    config_path: Path,
    history_db: Path,
    sample_count: int,
    min_duration: float,
    overlap_seconds: float,
    output_dir: Path,
) -> Dict[str, Any]:
    config = load_json(config_path)
    transcription = config.get("transcription", {})
    local_model = transcription.get("local", {}).get("model", "paraformer")
    language = transcription.get("local", {}).get("language", "auto")
    if language == "auto":
        language = None
    chunk_duration = float(
        config.get("audio", {}).get("streaming", {}).get("chunk_duration", 30.0)
    )

    samples = load_recent_samples(history_db, min_duration=min_duration, limit=sample_count)
    if not samples:
        raise RuntimeError("No eligible audio samples found in history.db")

    local_service = SpeechServiceFactory.create_service(provider="local", model=local_model)
    local_service.load_model()

    clouds = {}
    for provider in configured_cloud_providers(config):
        clouds[provider] = create_cloud_service(config, provider)

    run_started = time.time()
    report: Dict[str, Any] = {
        "meta": {
            "run_at": datetime.now().isoformat(),
            "config_path": str(config_path),
            "history_db": str(history_db),
            "chunk_duration_seconds": chunk_duration,
            "overlap_seconds": overlap_seconds,
            "sample_count": len(samples),
            "cloud_providers": list(clouds.keys()),
            "local_model": local_model,
            "language": language or "auto",
        },
        "samples": [],
    }

    for idx, sample in enumerate(samples, start=1):
        print(f"[{idx}/{len(samples)}] processing {sample.audio_file_path}")
        audio = load_wav_as_float32(Path(sample.audio_file_path))

        local_full_result = local_service.transcribe(audio, language=language)
        local_full_text = str(local_full_result.get("text", "") or "")

        chunks_current = split_chunks_current(audio, chunk_duration=chunk_duration)
        chunk_texts_current = transcribe_chunks(local_service, chunks_current, language=language)
        local_chunked_current_text = current_strategy_text(chunk_texts_current)

        chunks_improved = split_chunks_with_overlap(
            audio, chunk_duration=chunk_duration, overlap_seconds=overlap_seconds
        )
        chunk_texts_improved = transcribe_chunks(local_service, chunks_improved, language=language)
        local_chunked_improved_text = merge_texts_with_dedup(chunk_texts_improved)

        cloud_results: Dict[str, Dict[str, Any]] = {}
        for provider, service in clouds.items():
            r = service.transcribe(audio, language=language)
            cloud_results[provider] = {
                "text": str(r.get("text", "") or ""),
                "error": r.get("error"),
            }

        sample_report: Dict[str, Any] = {
            "record_id": sample.record_id,
            "timestamp": sample.timestamp,
            "audio_file_path": sample.audio_file_path,
            "duration_seconds": sample.duration,
            "source_provider": sample.transcription_provider,
            "local_full": {
                "text": local_full_text,
            },
            "local_chunked_current": {
                "chunk_count": len(chunks_current),
                "text": local_chunked_current_text,
                "chunks_text": chunk_texts_current,
                "boundaries": boundary_pairs(chunk_texts_current),
            },
            "local_chunked_improved": {
                "chunk_count": len(chunks_improved),
                "text": local_chunked_improved_text,
                "chunks_text": chunk_texts_improved,
                "boundaries": boundary_pairs(chunk_texts_improved),
            },
            "cloud_full": cloud_results,
            "metrics": {
                "current_vs_local_full_ratio": seq_ratio(
                    local_chunked_current_text, local_full_text
                ),
                "improved_vs_local_full_ratio": seq_ratio(
                    local_chunked_improved_text, local_full_text
                ),
            },
        }

        for provider, cdata in cloud_results.items():
            if cdata.get("error"):
                continue
            ctext = cdata.get("text", "")
            sample_report["metrics"][f"current_vs_{provider}_ratio"] = seq_ratio(
                local_chunked_current_text, ctext
            )
            sample_report["metrics"][f"improved_vs_{provider}_ratio"] = seq_ratio(
                local_chunked_improved_text, ctext
            )
            sample_report["metrics"][f"local_full_vs_{provider}_ratio"] = seq_ratio(
                local_full_text, ctext
            )

        report["samples"].append(sample_report)

    report["meta"]["elapsed_seconds"] = round(time.time() - run_started, 3)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"asr_chunk_experiment_{stamp}.json"
    md_path = output_dir / f"asr_chunk_experiment_{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(build_markdown_summary(report), encoding="utf-8")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {md_path}")
    return report


def build_markdown_summary(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    meta = report["meta"]
    lines.append("# ASR Chunk Experiment Report")
    lines.append("")
    lines.append(f"- Run at: {meta['run_at']}")
    lines.append(f"- Chunk duration: {meta['chunk_duration_seconds']}s")
    lines.append(f"- Overlap (improved): {meta['overlap_seconds']}s")
    lines.append(f"- Sample count: {meta['sample_count']}")
    lines.append(f"- Cloud providers: {', '.join(meta['cloud_providers']) if meta['cloud_providers'] else 'none'}")
    lines.append(f"- Elapsed: {meta['elapsed_seconds']}s")
    lines.append("")

    for i, sample in enumerate(report["samples"], start=1):
        lines.append(f"## Sample {i}")
        lines.append(f"- Audio: `{sample['audio_file_path']}`")
        lines.append(f"- Duration: {sample['duration_seconds']}s")
        lines.append(f"- Source provider: {sample['source_provider']}")
        lines.append("- Metrics:")
        for k, v in sample["metrics"].items():
            if isinstance(v, float):
                lines.append(f"  - {k}: {v:.4f}")
            else:
                lines.append(f"  - {k}: {v}")
        lines.append("")
        lines.append("- Current chunked preview:")
        lines.append(f"  - {sample['local_chunked_current']['text'][:240]}")
        lines.append("- Improved chunked preview:")
        lines.append(f"  - {sample['local_chunked_improved']['text'][:240]}")
        lines.append("- Local full preview:")
        lines.append(f"  - {sample['local_full']['text'][:240]}")
        for provider, data in sample["cloud_full"].items():
            err = data.get("error")
            if err:
                lines.append(f"- {provider} error: {err}")
            else:
                lines.append(f"- {provider} full preview:")
                lines.append(f"  - {data.get('text', '')[:240]}")
        lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run chunk boundary ASR experiment")
    parser.add_argument("--config-path", type=Path, default=_default_config_path())
    parser.add_argument("--history-db", type=Path, default=_default_history_db_path())
    parser.add_argument("--sample-count", type=int, default=3)
    parser.add_argument("--min-duration", type=float, default=35.0)
    parser.add_argument("--overlap-seconds", type=float, default=0.6)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts") / "experiments",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_experiment(
        config_path=args.config_path,
        history_db=args.history_db,
        sample_count=args.sample_count,
        min_duration=args.min_duration,
        overlap_seconds=args.overlap_seconds,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
