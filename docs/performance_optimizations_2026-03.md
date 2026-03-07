# Performance Optimizations (2026-03)

This document summarizes the recent performance-focused refactor for transcription
and history workflows.

## Scope

- Chunked streaming stop-path timeout strategy
- History text search and aggregate query performance
- History list pagination performance
- Batch reprocessing database write efficiency

## Changes

### 1) Chunked stop-path timeout no longer scales linearly with chunk count

File:
- `src/sonicinput/core/services/transcription_service_refactored.py`

What changed:
- Replaced per-chunk sequential timeout waits with a shared timeout budget.
- Added polling-based completion checks with per-chunk timeout metadata.

User impact:
- In degraded scenarios (slow model, stalled tasks), stopping recording is more predictable.

### 2) History text search uses FTS5 with graceful fallback

File:
- `src/sonicinput/core/services/storage/history_storage_service.py`

What changed:
- Added FTS5 virtual table (`history_records_fts`) and triggers for insert/update/delete sync.
- Added startup reconciliation to backfill FTS rows when needed.
- Search/count/aggregate now share one condition builder and prefer FTS; fallback to `LIKE` when unavailable.

User impact:
- Search and statistics are significantly faster on larger history datasets.

### 3) History list switched from OFFSET pagination to keyset pagination

Files:
- `src/sonicinput/core/services/storage/history_storage_service.py`
- `src/sonicinput/ui/settings_tabs/history_tab.py`

What changed:
- Added keyset APIs (`get_records_keyset`, `search_records_keyset`).
- History table infinite scroll now uses `(timestamp, id)` cursor.
- Time ordering is stabilized with `id` tie-breakers.

User impact:
- Better scrolling consistency and lower latency for large history volumes.

### 4) History statistics query moved off UI thread

File:
- `src/sonicinput/ui/settings_tabs/history_tab.py`

What changed:
- Added `HistoryStatsWorker` to fetch aggregate stats asynchronously.
- Added request-id guard to ignore stale results.

User impact:
- Reduced UI stalls during refresh and search.

### 5) Batch reprocessing now uses keyset read + batch insert

File:
- `src/sonicinput/ui/settings_tabs/history_tab.py`

What changed:
- Batch worker reads source records via keyset (`ASC`) traversal.
- Successful reprocessed records are buffered and persisted with `save_records_batch`.

User impact:
- Lower database transaction overhead and better throughput on large batches.

### 6) History diagnostics moved out of crowded main columns

File:
- `src/sonicinput/ui/settings_tabs/history_tab.py`

What changed:
- Main history table is simplified to core columns only:
  - `Time`, `LEN`, `Transcription`, `Status`
- Diagnostic fields remain preserved in:
  - time-cell tooltip (provider/mode/transcribe/fallback)
  - detail dialog

User impact:
- Better readability in day-to-day history browsing.
- No loss of diagnostics when root-cause analysis is needed.

## Validation

Static checks:

```bash
uv run ruff check src tests
```

Targeted regression:

```bash
uv run pytest -q \
  tests/core/test_transcription_service_chunk_boundary_fix.py \
  tests/core/test_history_storage_schema_upgrade.py \
  tests/core/test_history_storage_keyset_pagination.py \
  tests/core/test_history_batch_reprocessing_worker.py \
  tests/core/test_history_storage_order_by.py \
  tests/core/test_transcription_controller_chunked_fallback.py \
  tests/core/test_transcription_history_diagnostics.py
```
