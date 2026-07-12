# SonicInput v0.8.2 Release Notes

Release date: 2026-07-12

## Highlights

- Removed unused legacy plugins, compatibility layers, services, scripts, and direct dependencies identified by the repository cleanup. The supported application paths remain `sonicinput`, `python app.py`, and the Nuitka onefile executable.
- Added the formal `sonicinput` console entry point while keeping the repository-root `app.py` as a compatibility launcher for source checkouts and Nuitka.
- Corrected error-recovery reporting so a recovery result is only recorded after its action runs. Normal CLI exits, including `--help`, no longer create false crash evidence.
- Made package data explicit: wheels include the runtime assets, source distributions exclude local runtime/cache/build data, and packaged asset discovery works for source, wheel, and Nuitka layouts.
- Rebuilt the Nuitka release path around a locked local-ASR environment. Intermediate compiler output now lives in `build/nuitka`; versioned release artifacts live in `dist/release/v{version}`.
- Replaced full QML-tree copying with the verified Fluent UI runtime closure. This removes unused WebEngine, VirtualKeyboard, 3D, PDF, and extra style modules from staged data while retaining FluentWinUI3 plus Basic/Fusion fallback paths.
- Cached staged fonts, translations, and QML by input fingerprint. Repeat builds reuse staging and Nuitka intermediates instead of recopying or re-subsetting unchanged inputs.
- Removed an unsafe build-time mutation of `site-packages`; Windows-reserved `NUL` data paths are now excluded by Nuitka configuration.
- Offline bundles now stream files directly into the zip archive rather than copying the full model tree to a temporary directory first.
- Reduced staged QML data from 14.9 MiB to 6.64 MiB. The final executable is 68.32 MiB, about 3 MiB smaller than v0.8.1.
- Added a Nuitka report audit that rejects accidental WebEngine/VirtualKeyboard/cryptography/samplerate payloads, a recursive ONNX Runtime tools closure, or any SymPy inclusion. The final build contains 12 Python ONNX Runtime modules and no SymPy modules.
- Fixed the packaged local-ASR runtime to preload Sherpa's ABI-compatible ONNX Runtime DLL before the Python ONNX Runtime API. A real Zipformer model load and silent-audio decode now runs as an optional release gate.
- Hardened release integrity: formal builds remove same-version stale artifacts and reports, require a newly generated EXE, and apply timeouts to packaged CLI checks.

## Upgrade Notes

- This is a cleanup release. Unsupported imports of removed legacy/internal modules are intentionally not preserved; use the active service and entry-point APIs instead.
- The v0.8.1 review/lexicon schema behavior remains: incompatible obsolete review tables are rebuilt rather than migrated. Export old lexicon entries before upgrading if they are needed.
- Local ASR remains included in the Windows release. ONNX Runtime and Qt runtime libraries were kept until full model and GUI regression coverage confirms a smaller closure.

## Validation

- `uv lock --check`
- `uv run ruff check src tests app.py build_nuitka.py scripts`
- `uv run ruff format --check src tests app.py build_nuitka.py scripts`
- `uv run mypy src app.py build_nuitka.py scripts`
- `uv run pytest -m "not gui and not gpu and not e2e" -v`: 423 passed, 73 deselected
- Offscreen GUI/QML regression tests: 73 passed, 22 deselected
- `uv run bandit -r src -ll -ii -f json -o bandit-report.json`
- `uv build`, clean-environment wheel install, console-entrypoint smoke, and runtime asset checks
- Nuitka onefile `--help` and `--validate`
- Nuitka onefile `--package-smoke`: 6/6 checks passed for runtime assets, pypinyin dictionaries, ONNX Runtime CPU support, the sherpa native runtime, a real Zipformer model load/decode, and Settings/Overlay/About QML roots
- Isolated offscreen full-GUI startup remained alive for the 12-second release smoke window

## Artifact

- `SonicInput-v0.8.2-win64.exe`
- Size: 71,640,576 bytes (68.32 MiB)
- SHA-256: `678eb2b47b76bf34f12076ee5bb08900fae6f879d6e23ac717f5fd32b09669f8`
