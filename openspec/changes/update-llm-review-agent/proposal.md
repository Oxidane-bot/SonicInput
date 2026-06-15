# Update Local Review to LLM-backed Review Suggestions

## Why

The current "Review" feature is a local heuristic scanner, but the UI and
workflow imply that it is a model-backed review step. That mismatch is
misleading.

We need a real LLM-backed review path so the system can:

- inspect recent history with the configured AI provider
- generate actionable suggestions from a model instead of only regex/heuristics
- keep a lightweight local fallback only for obvious contract violations or
  when the LLM path is unavailable

## What Changes

- Replace the current local heuristic review path with an LLM-backed review
  pipeline.
- Keep local heuristics as a fallback gate for clearly unsafe or malformed
  AI output, not as the primary review engine.
- Update the UI and documentation so they describe the feature as LLM-backed
  review suggestions instead of the previous local-only review abstraction.
- Preserve storage of review jobs, suggestions, and lexicon decisions, but make
  the primary suggestion source the selected AI provider.

## Impact

- Affected specs:
  - `ai-processing`
  - `localize-ui`
  - `code-quality`
- Affected code:
  - `src/sonicinput/core/quality/*`
  - `src/sonicinput/core/services/review_scheduler_service.py`
  - `src/sonicinput/core/services/storage/review_storage_service.py`
  - `src/sonicinput/core/services/ui_services.py`
  - `src/sonicinput/ui/qml_bridge.py`
  - `src/sonicinput/ui/qml/FluentSettingsWindow.qml`
  - related tests
