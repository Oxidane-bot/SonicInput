<div align="center">
  <img src="assets/icon.png" alt="SonicInput Icon" width="128" height="128">
  <h1>SonicInput</h1>
  <p>Lightweight Windows voice input powered by sherpa-onnx, with local/cloud ASR and optional AI post-processing.</p>
  <p><strong>Languages:</strong> <a href="README.md">中文</a> | <a href="README_EN.md">English</a></p>
</div>

## Highlights
- Ready to use: clipboard / text / GUI entry points
- No admin needed: Win32 RegisterHotKey (default Ctrl+Alt+Space, customizable), conflict prompts
- Two recording modes: Realtime (low latency) / Chunked (higher quality with AI)
- Cloud & local: Groq / OpenRouter / NVIDIA / OpenAI or local sherpa-onnx
- Local lexicon memory: user-confirmed entries are injected before later AI cleanup only when phonetically relevant
- Lexicon review: the settings page can ask the configured AI provider to mine raw ASR context for candidate terms

## What's New (v0.8.1)
- **Local lexicon memory is now a top-level settings page** with separate tabs and independently scrolling lists for candidates and saved vocabulary. The nested AI-page management entry has been removed.
- **History loads immediately** when entered, re-entered, or selected again. It also prefetches additional pages until the viewport is filled instead of waiting for a manual refresh.
- **Candidate extraction is more precise** and stores the smallest complete reusable term. For example, `小梗盖 -> 小梗概` in context is stored as `梗盖 -> 梗概`.
- **Homophone and controlled near-homophone correction** accepts exact phonetic matches or one conservative sound confusion while rejecting semantic jumps, cross-script pairs, and candidates without verifiable source records.
- **Lexicon storage and recall are corrected**: one canonical term can retain multiple mistaken forms, mutations invalidate the runtime cache immediately, and active entries are no longer truncated by a fixed limit.
- **The old review implementation is hard-cut**. Incompatible review/lexicon schemas are rebuilt, so old pending candidates and saved entries are not guaranteed to survive. Export the lexicon before upgrading.

## Performance Notes
- 2026-03 optimization summary (chunk-stop path, history search/pagination, batch reprocess):  
  [`docs/performance_optimizations_2026-03.md`](docs/performance_optimizations_2026-03.md)

## Requirements
- Windows 10/11 64-bit
- 4GB RAM+, ~500MB disk

## Quick Start
1. Download `SonicInput-v0.8.1-win64.exe` from [v0.8.1 Release](https://github.com/Oxidane-bot/SonicInput/releases/tag/v0.8.1)
2. Run the exe; default hotkey is Ctrl+Alt+Space (customize it in settings if it conflicts)
3. Enter cloud API keys in settings (optional) or use the local model

> Tip: keep hotkey backend on `win32` (no admin needed, fewer conflicts). Switch to `pynput` only if you must suppress key events.

## Lexicon Review & Local Learning
- Lexicon review reads only raw ASR text, not `ai_optimized_text` / `final_text`, so AI cleanup mistakes are not treated as ground truth.
- Local lexicon memory is a top-level settings page with separate candidate and saved-vocabulary views.
- The review model extracts the smallest complete term from full raw-sentence context. Every candidate must reference verifiable source records and enters local memory only after user acceptance.
- Before later AI cleanup, `LexiconMatcher` phonetic/near-phonetic filtering selects only entries relevant to the current raw text.
- Automatic lexicon review is disabled by default; it can be run manually from settings or enabled for idle scheduling.
- v0.8.1 does not retain a compatibility migration for obsolete review schemas. An incompatible review/lexicon schema is rebuilt; export from the old settings page before upgrading. Configuration and transcription history are unaffected.
- Local audit scripts omit transcript text by default and store metadata such as lengths, status, path, and anomaly labels for safe prompt/model comparisons.

## Dev Setup
```bash
git clone https://github.com/Oxidane-bot/SonicInput.git
cd SonicInput
uv sync          # install runtime deps
uv run python app.py --gui
```

## Ruff Automation
```powershell
# Install dev dependencies
uv sync --extra dev

# Install repository Git hooks (pre-commit / pre-push)
.\scripts\setup-git-hooks.ps1
```

Default behavior:
- `pre-commit`: runs `ruff format src tests` and `ruff check src tests --fix`.
- `pre-push`: runs `ruff check src tests` and `ruff format --check src tests`.

## AI Provider Notes
- `O​penAI Compatible` now treats `/models` from the current `base_url + A​PI k​ey` as the source of truth for model availability.
- During connection testing, if the selected `model_id` is not present in that list, the UI shows a clear validation error instead of issuing a doomed inference request.
- When using Cerebras or other O​penAI-compatible services, prefer the live `/models` response over the broader documentation overview pages.
- Relevant config keys live in `%AppData%/SonicInput/config.json` under `ai.o​penai_compatible.base_url`, `ai.o​penai_compatible.a​pi_k​ey`, and `ai.o​penai_compatible.model_id`.

## Paths
- Config: `%AppData%/SonicInput/config.json`
- Logs: `%AppData%/SonicInput/logs/app.log`
- History and Review data: `%AppData%/SonicInput/history/history.db`
- Local quality-audit output: `quality_audit/` (git-ignored by default)

## License
MIT License. See [LICENSE](LICENSE).
