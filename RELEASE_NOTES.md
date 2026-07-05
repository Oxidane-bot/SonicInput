# SonicInput v0.8.0 Release Notes

Release date: 2026-07-05

## Highlights

- Added local lexicon memory for user-confirmed ASR correction examples.
- Added raw-only lexicon review: the review model sees only raw ASR transcript snippets, uses full-sentence context, and proposes `old_form -> new_form` candidates for user approval.
- Injected accepted lexicon entries before AI cleanup using local phonetic/near-phonetic pre-filtering, so unrelated entries are not added to prompts.
- Removed the old broad review flow for profanity/content quality/boundary/prompt-failure cards. Existing legacy rows can remain in the local database but are no longer part of the active review flow.
- Removed the real-time AI-output rejection gate based on transcript quality validator rules; low-information skip behavior remains.
- Kept in-recording rolling context and long-recording cloud transcription diagnostics for better chunk consistency and observability.

## Lexicon Review Workflow

1. ASR produces raw transcript text.
2. Optional lexicon review scans raw text only. It does not read `ai_optimized_text` or `final_text`.
3. The model proposes candidate terms with short raw-context evidence.
4. The user accepts, rejects, or ignores each candidate.
5. Accepted terms are stored in `local_lexicon_entries`.
6. Future AI cleanup receives only phonetic/near-phonetic matches for the current raw text.

## Upgrade Notes

- `review.enabled` remains disabled by default to avoid silent API usage.
- `review.use_lexicon_memory` remains enabled by default, but only accepted local entries are injected.
- Legacy review tables and rows are preserved for compatibility; the new storage path filters active suggestions to lexicon candidates only.
- Existing pending legacy suggestions may still exist in old local databases. Reject, ignore, or clear learning data from Settings if needed.

## Validation

- `uv run --cache-dir .\.uv_cache ruff check src tests`
- `uv run --cache-dir .\.uv_cache pytest -m "not gui and not gpu and not e2e" -q`
- Targeted lexicon review/storage/UI tests were also run during development.

## Artifact

- `SonicInput-v0.8.0-win64.exe`
