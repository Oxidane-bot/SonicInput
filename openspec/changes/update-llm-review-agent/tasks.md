## 1. Spec

- [x] Add `ai-processing` requirements for an LLM-backed review suggestion
      pipeline.
- [x] Add `localize-ui` requirements for language that clearly distinguishes
      model-backed review from local heuristic fallback.
- [x] Add `code-quality` requirements for preserving a local safety gate only
      for contract violations and malformed output.

## 2. Implementation

- [x] Add an LLM-backed review service or adapter that consumes recent history
      and produces review suggestions.
- [x] Keep local heuristic validation only as a fallback gate for obvious unsafe
      or malformed AI output.
- [x] Wire the manual review button to the LLM-backed path.
- [x] Keep persisted review jobs and suggestion decisions compatible with
      existing storage.
- [x] Update docs and UI copy to describe the actual behavior.

## 3. Tests

- [x] Add/update tests covering LLM-backed review suggestion generation.
- [x] Add/update tests covering local fallback behavior when the LLM path is
      unavailable.
- [x] Add/update UI tests for the revised wording and manual review path.

## 4. Validation

- [x] Run targeted ruff checks.
- [x] Run targeted pytest coverage for review-related paths.
- [x] Run OpenSpec validation for `update-llm-review-agent`.
