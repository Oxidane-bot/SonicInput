"""Review recent SonicInput history and write local suggestion cards.

This is the first non-UI Review Agent prototype. It does not modify history and
does not update lexicon memory. It only writes pending suggestions for later
inspection.

Example:
    uv run python scripts/review_recent_history.py --limit 20
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from sonicinput.core.quality import HistoryReviewAgent
from sonicinput.core.services.storage import ReviewStorageService


def _default_history_db() -> Path:
    return Path(os.environ.get("APPDATA", ".")) / "SonicInput" / "history" / "history.db"


def _default_output_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("quality_audit") / f"review_suggestions_{timestamp}.json"


def _load_recent_records(db_path: Path, limit: int) -> list[dict[str, Any]]:
    sql = """
    SELECT
        id,
        timestamp,
        transcription_text,
        transcription_status,
        ai_optimized_text,
        ai_status,
        final_text,
        streaming_mode
    FROM history_records
    ORDER BY timestamp DESC, id DESC
    LIMIT ?
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(sql, (limit,)).fetchall()]
    finally:
        conn.close()


def _strip_private_text(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record.get("id"),
        "timestamp": record.get("timestamp"),
        "transcription_status": record.get("transcription_status"),
        "ai_status": record.get("ai_status"),
        "streaming_mode": record.get("streaming_mode"),
        "transcription_length": len(record.get("transcription_text") or ""),
        "ai_length": len(record.get("ai_optimized_text") or ""),
        "final_length": len(record.get("final_text") or ""),
    }


def run_review(
    db_path: Path,
    output_path: Path,
    limit: int,
    include_excerpts: bool,
    persist: bool,
) -> dict[str, Any]:
    if not db_path.exists():
        raise FileNotFoundError(f"History database not found: {db_path}")

    records = _load_recent_records(db_path, limit)
    agent = HistoryReviewAgent()
    suggestions = agent.analyze_records(records)

    payload: dict[str, Any] = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "db_path": str(db_path),
        "reviewed_record_count": len(records),
        "suggestion_count": len(suggestions),
        "records": records if include_excerpts else [_strip_private_text(r) for r in records],
        "suggestions": [suggestion.to_dict() for suggestion in suggestions],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    job_id = None
    if persist:
        storage = ReviewStorageService(db_path)
        job_id = storage.save_review_run(
            suggestions,
            record_limit=limit,
            reviewed_count=len(records),
        )

    return {
        "output_path": str(output_path),
        "review_job_id": job_id,
        "reviewed_record_count": len(records),
        "suggestion_count": len(suggestions),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=_default_history_db())
    parser.add_argument("--output", type=Path, default=_default_output_path())
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument(
        "--include-excerpts",
        action="store_true",
        default=False,
        help="Include private transcript text in the local report.",
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        default=False,
        help="Persist review job and pending suggestions into the history DB.",
    )
    args = parser.parse_args()

    summary = run_review(
        db_path=args.db,
        output_path=args.output,
        limit=args.limit,
        include_excerpts=args.include_excerpts,
        persist=args.persist,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
