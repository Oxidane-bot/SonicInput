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
- Quality guardrails: AI cleanup is locally validated and falls back to raw transcription when it crosses product boundaries
- Local learning: the Review Agent can find terminology candidates and quality issues from history; only user-accepted terms enter local memory

## What's New (v0.8.0)
- Added an **AI output quality gate** that rejects markdown/label leaks, assistant-style answers, translation leaks, low-information expansion, over-compressed long dictation, and abnormal repetition; rejected AI output falls back to the raw transcript.
- Added **in-recording rolling context** so later chunk cleanup can reuse terms, paths, and recent context heard in the same recording, improving consistency for technical and mixed-language dictation.
- Added a **Quality Review page** in settings with grouped local suggestions for boundary violations, content distortion, diagnostic samples, lexicon learning, and prompt-quality issues.
- Added **local lexicon memory**: only accepted terminology candidates are reused; users can export, clear lexicon entries, or clear learning data.
- Added a long-recording cloud path: cloud recordings over the default 90-second threshold prefer file transcription and record `transcription_path`, decision reason, and fallback type for diagnostics.
- Added privacy-safe quality tools: `scripts/audit_transcript_quality.py`, `compare_quality_audits.py`, and `evaluate_ai_prompt_profiles.py` for local audit reports and prompt-profile comparisons.
- Changed the default hotkey to `Ctrl+Alt+Space` to reduce collisions with common editing shortcuts.

## Performance Notes
- 2026-03 optimization summary (chunk-stop path, history search/pagination, batch reprocess):  
  [`docs/performance_optimizations_2026-03.md`](docs/performance_optimizations_2026-03.md)

## Requirements
- Windows 10/11 64-bit
- 4GB RAM+, ~500MB disk

## Quick Start
1. Download `SonicInput-v0.8.0-win64.exe` from [v0.8.0 Release](https://github.com/Oxidane-bot/SonicInput/releases/tag/v0.8.0)
2. Run the exe; default hotkey is Ctrl+Alt+Space (customize it in settings if it conflicts)
3. Enter cloud API keys in settings (optional) or use the local model

> Tip: keep hotkey backend on `win32` (no admin needed, fewer conflicts). Switch to `pynput` only if you must suppress key events.

## Quality Review & Local Learning
- AI cleanup output is validated locally before insertion. If it looks like an answer, translation, markdown, over-compression, or noise expansion, SonicInput keeps the raw transcript as final text.
- Idle scheduling for Quality Review is disabled by default; you can manually run review from settings to inspect recent-history suggestions.
- The Review Agent does not rewrite history automatically. Accepted lexicon suggestions become local memory and are used only as conservative context for later AI cleanup.
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
