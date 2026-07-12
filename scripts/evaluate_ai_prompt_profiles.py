"""Evaluate versioned AI cleanup prompt profiles on local history samples.

The output is privacy-safe by default: it stores metadata, lengths, latency, and
validator labels, but not transcript text or AI text.

Example:
    uv run python scripts/evaluate_ai_prompt_profiles.py --limit 20 \
      --profiles baseline strict_cleaner short_noise_safe
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, cast

from sonicinput.ai import AIClientFactory
from sonicinput.ai.prompt_profiles import get_prompt_profile, list_prompt_profile_names
from sonicinput.core.interfaces import IConfigService
from sonicinput.core.quality import TranscriptQualityValidator
from sonicinput.core.services.config import ConfigKeys


@dataclass(frozen=True)
class HistorySample:
    record_id: str
    timestamp: str
    transcription_text: str
    ai_status: str
    streaming_mode: str


class PromptEvaluationClient(Protocol):
    def refine_text(
        self,
        text: str,
        prompt_template: str,
        model: str,
        max_tokens: int = 1000,
    ) -> str: ...


class ConfigShim(IConfigService):
    def __init__(self, data: dict[str, Any]):
        self._data = data

    def get_setting(self, key: str, default: Any = None) -> Any:
        value: Any = self._data
        for part in key.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        return value

    def set_setting(self, key: str, value: Any) -> None:
        target = self._data
        parts = key.split(".")
        for part in parts[:-1]:
            nested = target.get(part)
            if not isinstance(nested, dict):
                nested = {}
                target[part] = nested
            target = nested
        target[parts[-1]] = value

    def get_all_settings(self) -> dict[str, Any]:
        return dict(self._data)

    def save_config(self) -> bool:
        return True


def _default_config_path() -> Path:
    return Path(os.environ.get("APPDATA", ".")) / "SonicInput" / "config.json"


def _default_history_db() -> Path:
    return (
        Path(os.environ.get("APPDATA", ".")) / "SonicInput" / "history" / "history.db"
    )


def _default_output_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("quality_audit") / f"prompt_profile_eval_{timestamp}.jsonl"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_samples(db_path: Path, limit: int, anomaly_only: bool) -> list[HistorySample]:
    where = "WHERE transcription_status = 'success' AND transcription_text != ''"
    if anomaly_only:
        where += """
        AND (
            ai_status != 'success'
            OR LENGTH(COALESCE(ai_optimized_text, '')) > LENGTH(transcription_text) * 3
            OR LENGTH(COALESCE(ai_optimized_text, '')) < LENGTH(transcription_text) * 0.5
        )
        """
    sql = f"""
    SELECT id, timestamp, transcription_text, ai_status, streaming_mode
    FROM history_records
    {where}
    ORDER BY timestamp DESC, id DESC
    LIMIT ?
    """
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(sql, (limit,)).fetchall()
    finally:
        conn.close()
    return [HistorySample(*row) for row in rows]


def _length_ratio(value: str, base: str) -> float | None:
    if not base:
        return None
    return round(len(value) / len(base), 4)


def evaluate_profiles(
    *,
    config_path: Path,
    history_db: Path,
    output_path: Path,
    profile_names: list[str],
    limit: int,
    anomaly_only: bool,
    include_text: bool,
) -> dict[str, Any]:
    config_data = _load_json(config_path)
    config = ConfigShim(config_data)
    baseline_prompt = str(config.get_setting(ConfigKeys.AI_PROMPT, "") or "")
    provider = str(config.get_setting(ConfigKeys.AI_PROVIDER, "unknown"))
    model = str(config.get_setting(f"ai.{provider}.model_id", "") or "")
    max_tokens = int(config.get_setting(ConfigKeys.AI_MAX_OUTPUT_TOKENS, 4096) or 4096)

    created_client = AIClientFactory.create_from_config(config)
    if not created_client:
        raise RuntimeError("Failed to create AI client from config")
    ai_client = cast(PromptEvaluationClient, created_client)

    samples = _load_samples(history_db, limit=limit, anomaly_only=anomaly_only)
    validator = TranscriptQualityValidator()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "config_path": str(config_path),
        "history_db": str(history_db),
        "output_path": str(output_path),
        "provider": provider,
        "model": model,
        "sample_count": len(samples),
        "profiles": profile_names,
        "profile_counts": {},
    }

    profile_counts: dict[str, dict[str, int]] = {
        name: {"ok": 0, "violation": 0, "error": 0} for name in profile_names
    }

    with output_path.open("w", encoding="utf-8") as fp:
        for sample in samples:
            for profile_name in profile_names:
                profile = get_prompt_profile(profile_name, baseline_prompt)
                start = time.perf_counter()
                error = ""
                refined_text = ""
                try:
                    refined_text = ai_client.refine_text(
                        sample.transcription_text,
                        profile.prompt,
                        model,
                        max_tokens=max_tokens,
                    )
                except Exception as exc:  # noqa: BLE001 - experiment report must continue
                    error = f"{type(exc).__name__}: {exc}"
                latency_s = round(time.perf_counter() - start, 4)

                validation = (
                    validator.validate(sample.transcription_text, refined_text)
                    if refined_text
                    else None
                )
                if error:
                    profile_counts[profile_name]["error"] += 1
                elif validation and validation.ok:
                    profile_counts[profile_name]["ok"] += 1
                else:
                    profile_counts[profile_name]["violation"] += 1

                row: dict[str, Any] = {
                    "record_id": sample.record_id,
                    "timestamp": sample.timestamp,
                    "profile": profile_name,
                    "profile_description": profile.description,
                    "provider": provider,
                    "model": model,
                    "streaming_mode": sample.streaming_mode,
                    "previous_ai_status": sample.ai_status,
                    "latency_s": latency_s,
                    "error": error,
                    "original_length": len(sample.transcription_text),
                    "refined_length": len(refined_text),
                    "length_ratio": _length_ratio(
                        refined_text, sample.transcription_text
                    ),
                    "validation_ok": bool(validation.ok) if validation else False,
                    "validation_reasons": list(validation.reasons)
                    if validation
                    else [],
                }
                if include_text:
                    row["original_text"] = sample.transcription_text
                    row["refined_text"] = refined_text
                fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary["profile_counts"] = profile_counts
    summary_path = output_path.with_suffix(".summary.json")
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary["summary_path"] = str(summary_path)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=_default_config_path())
    parser.add_argument("--db", type=Path, default=_default_history_db())
    parser.add_argument("--output", type=Path, default=_default_output_path())
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--profiles", nargs="+", default=["baseline", "strict_cleaner"])
    parser.add_argument("--anomaly-only", action="store_true", default=False)
    parser.add_argument(
        "--include-text",
        action="store_true",
        default=False,
        help="Write private transcript/refined text into the local report.",
    )
    args = parser.parse_args()

    unknown = set(args.profiles) - set(list_prompt_profile_names())
    if unknown:
        raise SystemExit(f"Unknown prompt profiles: {sorted(unknown)}")

    summary = evaluate_profiles(
        config_path=args.config,
        history_db=args.db,
        output_path=args.output,
        profile_names=args.profiles,
        limit=args.limit,
        anomaly_only=args.anomaly_only,
        include_text=args.include_text,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
