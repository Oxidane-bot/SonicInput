<div align="center">
  <img src="assets/icon.png" alt="SonicInput Icon" width="128" height="128">
  <h1>SonicInput</h1>
  <p>Lightweight Windows voice input powered by sherpa-onnx, with local/cloud ASR and optional AI post-processing.</p>
  <p><strong>Languages:</strong> <a href="README.md">中文</a> | <a href="README_EN.md">English</a></p>
</div>

## Highlights
- Ready to use: clipboard / text / GUI entry points
- No admin needed: Win32 RegisterHotKey (default F12, customizable), conflict prompts
- Two recording modes: Realtime (low latency) / Chunked (higher quality with AI)
- Cloud & local: Groq / OpenRouter / NVIDIA / OpenAI or local sherpa-onnx

## What's New (v0.7.9)
- Fixed crashes in the Fluent settings window model load/test/unload flows (`QMessageBox`/`QProgressDialog` parent-type errors)
- Fixed sticky Win/Alt state after UAC/UIPI transitions that prevented hotkey matches
- Fixed clipboard restore on worker threads producing COM refusals (`0x8001010D`) and heap corruption (`0xC0000374`) after transcription
- Release the Fluent settings window's QML engine on process exit
- Hardened UI tests: CI now runs `tests/ui/` (offscreen), and dialog parent types are validated against PySide6's real contract

## Performance Notes
- 2026-03 optimization summary (chunk-stop path, history search/pagination, batch reprocess):  
  [`docs/performance_optimizations_2026-03.md`](docs/performance_optimizations_2026-03.md)

## Requirements
- Windows 10/11 64-bit
- 4GB RAM+, ~500MB disk

## Quick Start
1. Download `SonicInput-v0.7.9-win64.exe` from [v0.7.9 Release](https://github.com/Oxidane-bot/SonicInput/releases/tag/v0.7.9)
2. Run the exe; default hotkey is F12 (use Alt+H or customize if it conflicts)
3. Enter cloud API keys in settings (optional) or use the local model

> Tip: keep hotkey backend on `win32` (no admin needed, fewer conflicts). Switch to `pynput` only if you must suppress key events.

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

## License
MIT License. See [LICENSE](LICENSE).
