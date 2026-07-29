# SonicInput v0.8.8 Release Notes

Release date: 2026-07-29

## Highlights

- Removed the legacy `ConfigService` and `EventBus` compatibility modules. Supported integrations now import `RefactoredConfigService` from `sonicinput.core.services.config` and `DynamicEventSystem` from `sonicinput.core.services.dynamic_event_system`.
- Removed the old `--test` and `--diagnostics` command-line harness, its model tester, and the EventBus compatibility tests. Default startup still performs the GUI preflight, while `--gui`, `--validate`, and packaged `--package-smoke` remain supported.
- Removed orphaned constant modules, legacy `ConfigKeys`, dependency diagnostics, unused exception types, an unused QML page, and obsolete recording tray images. Existing Whisper configuration files remain supported by the configuration migrator.
- Narrowed unused service and interface APIs across hotkeys, logging, events, transcription, recording, AI clients, state management, queues, and caches. Active internal methods and runtime behavior remain intact.
- Replaced the final legacy configuration startup path with direct `RefactoredConfigService` construction and standardized current service imports.
- Moved the manual settings visual audit from the pytest tree to `scripts/settings_visual_audit.py`. Its Qt object types are explicit, and the offscreen audit generates 34 non-empty screenshots.
- Retired the eight temporary Stage 6 transcription observability scripts and their 38 script tests. Production `transcription_path` and `transcription_decision_reason` fields, database migrations, runtime log events, and quality-audit path statistics are unchanged.
- Removed more than 14,000 lines across 74 files while retaining the supported desktop application, local Sherpa ASR, SOCKS support, quality tooling, and release pipeline.

## Upgrade Notes

- No configuration or database migration is required.
- This release intentionally removes obsolete public Python APIs without a deprecation period. SonicInput is maintained as a desktop application rather than a general-purpose Python SDK.
- Replace old service imports with `sonicinput.core.services.config.RefactoredConfigService` and `sonicinput.core.services.dynamic_event_system.DynamicEventSystem`.
- Replace `dependency_diagnostics` with the retained startup diagnostics and `create_app_icon()` with `get_app_icon()`.
- The removed `--test` and `--diagnostics` options now produce the standard argparse exit code 2.

## Validation

- `uv run ruff check src tests app.py build_nuitka.py scripts`
- `uv run ruff format --check src tests app.py build_nuitka.py scripts`
- `uv run mypy src app.py build_nuitka.py scripts`: 137 source files checked
- `uv run vulture src tests app.py build_nuitka.py scripts --min-confidence 80`
- `uv run pytest -m "not gui and not gpu and not e2e" -v`: 393 passed, 77 deselected
- Offscreen GUI/QML regression suite: 69 passed, 401 deselected
- Settings visual audit: 34 non-empty PNG files
- Bandit medium/high severity scan: no findings
- `uv build`, source CLI smoke, and source package smoke
- Local Nuitka 2.8.4/MSVC 14.3 onefile build: 68.23 MiB; packaged runtime smoke passed

## Artifacts

- `SonicInput-v0.8.8-win64.exe`
- `SonicInput-v0.8.8-win64.exe.sha256`
- Optional offline archives when release models are supplied

The GitHub Release attaches the generated SHA-256 sidecar; use it to verify the executable after download.
