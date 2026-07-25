# SonicInput v0.8.6 Release Notes

Release date: 2026-07-25

## Highlights

- Consolidated the supported runtime around the `sonicinput` entry point and removed unused plugins, compatibility layers, services, scripts, and direct dependencies. The cleanup prepared after v0.8.1 removes more than 8,000 lines of obsolete code while retaining the source launcher and Windows executable paths.
- Reworked Python and Nuitka packaging around explicit runtime assets, a locked local-ASR build environment, a smaller verified Fluent/QML closure, cached staging, and payload audits that reject known accidental dependencies.
- Added a transcript-quality gate after normal AI provider completion. Long transcripts that are silently summarized or severely compressed now fall back to the original transcription; live streaming or grouped incremental text is reconciled in place instead of leaving a partial result or appending a duplicate.
- Moved local model loading from the GUI thread to a dedicated Qt worker. The settings window remains responsive while a model initializes or downloads, and duplicate load requests are ignored while a load is active.
- Moved manual and scheduled lexicon review to background Qt workers. The review UI exposes a busy state, and the shared settings service rejects concurrent review passes to protect the review cursor and storage.
- Removed GUI-thread waits from single-history-reprocess cancellation. Cancellation now updates immediately and lets the current operation finish at a safe checkpoint.
- Made the optional Sherpa runtime test robust against an uninstalled or orphaned namespace package without weakening the packaged local-ASR smoke gate.
- Pinned the official Windows release to `windows-2022` with the VS 2022 C++ x64 toolchain. The workflow uses `vswhere` and `vcvars64.bat` to initialize the compiler environment, then compiles and runs a minimal Nuitka preflight before the full build.
- Standardized the full build on Nuitka's explicit `--msvc=14.3` target. It includes Sherpa's ABI-compatible ONNX Runtime DLL and audits the packaged root DLL SHA-256 against the source runtime.
- Packaged command smoke failures now retain redirected stdout and stderr in the release log, so a failing executable can be diagnosed without rebuilding locally.
- Removed orphaned UI audio/GPU service registrations and the diagnostic import of a GPU module that no longer exists.
- Updated GitHub Actions to immutable current action revisions and a pinned uv release. CI now enforces locked installs, Ruff, mypy, Vulture, Bandit, non-GUI and offscreen GUI tests, and wheel/sdist construction.
- Added a Windows tag-release workflow that verifies the version, runs the locked release script, and publishes the executable plus SHA-256 sidecar. Nuitka compiler artifacts are cached and the clean-build timeout accounts for an empty C cache.

## Upgrade Notes

- No configuration or database migration is required for this release.
- v0.8.2 was prepared locally but never published. The v0.8.3 tag's clean-runner build was rejected before publication by a DLL collision; the v0.8.4 MinGW package was rejected by its CLI smoke test; and the v0.8.5 GitHub runner could not resolve an MSVC compiler before producing an artifact. v0.8.6 uses an explicit VS 2022 toolchain and preflight.
- A review that is already in progress now reports `review_already_running` instead of starting a second concurrent pass.

## Validation

- `uv lock --check`
- `uv run ruff check src tests app.py build_nuitka.py scripts`
- `uv run ruff format --check src tests app.py build_nuitka.py scripts`
- `uv run mypy src app.py build_nuitka.py scripts`
- `uv run vulture src app.py build_nuitka.py scripts --min-confidence 80`
- `uv run pytest -m "not gui and not gpu and not e2e" -v`: 428 passed, 77 deselected
- Offscreen GUI/QML regression suite: 77 passed, 22 deselected
- `uv run bandit -r src -ll -ii -f json -o bandit-report.json`
- `uv build` and the locked Nuitka release script with packaged CLI/QML/local-ASR smoke checks

## Artifacts

- `SonicInput-v0.8.6-win64.exe`
- `SonicInput-v0.8.6-win64.exe.sha256`
- Optional offline archives when release models are supplied

The GitHub Release attaches the generated SHA-256 sidecar; use it to verify the executable after download.
