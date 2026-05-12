<div align="center">
  <img src="assets/icon.png" alt="SonicInput Icon" width="128" height="128">
  <h1>SonicInput</h1>
  <p>基于 sherpa-onnx 的 Windows 语音输入工具，支持本地/云端 ASR 与 AI 后处理</p>
  <p><strong>Languages:</strong> <a href="README.md">中文</a> | <a href="README_EN.md">English</a></p>
</div>

## 核心特性
- 即开即用：剪贴板 / 文本 / GUI 多入口
- 热键无管理员：Win32 RegisterHotKey（默认 F12，可自定义），冲突时会提示
- 双模式录制：Realtime 低延迟；Chunked 精度高（AI 后处理）
- 云端/本地切换：Groq / OpenRouter / NVIDIA / OpenAI / 本地 sherpa-onnx

## v0.7.7 更新
- 升级 Fluent 历史记录页面和详情面板，统一到最新设置窗口视觉规范
- 修正历史列表、统计栏和详情内容在窄窗口下的文字溢出与按钮挤压问题
- 让历史列表框体随窗口高度自适应，并补充中英文视觉审计截图覆盖

## 性能优化记录
- 2026-03：分块停止路径、历史搜索/分页、批量重处理等性能整理见  
  [`docs/performance_optimizations_2026-03.md`](docs/performance_optimizations_2026-03.md)

## 系统需求
- Windows 10/11 64 位
- 内存 4GB+，磁盘 500MB

## 快速开始
1. 下载 [v0.7.7 Release](https://github.com/Oxidane-bot/SonicInput/releases/tag/v0.7.7) 中的 `SonicInput-v0.7.7-win64.exe`
2. 双击运行，默认热键 F12（若冲突可改用 Alt+H 或自定义）
3. 在设置中填写需要的云端 API Key（可选），或直接使用本地模型

> 热键后端建议保持 `win32`（无需管理员，冲突率低）；需要按键抑制时再切换 `pynput`。

## 开发环境
```bash
git clone https://github.com/Oxidane-bot/SonicInput.git
cd SonicInput
uv sync          # 安装运行依赖
uv run python app.py --gui
```

## 代码质量自动化（Ruff）
```powershell
# 安装开发依赖
uv sync --extra dev

# 安装本仓库 Git hooks（pre-commit / pre-push）
.\scripts\setup-git-hooks.ps1
```

默认行为：
- `pre-commit`：自动执行 `ruff format src tests` 和 `ruff check src tests --fix`。
- `pre-push`：执行 `ruff check src tests` 与 `ruff format --check src tests`。

## AI Provider Notes
- `O​penAI Compatible` 会优先以当前 `base_url + A​PI k​ey` 请求 `/models` 作为真实可用模型列表。
- 测试连接时，如果填写的 `model_id` 不在该列表中，会直接提示“当前模型不在可用模型列表中”，而不是继续发起无效推理请求。
- 对接 Cerebras 这类 O​penAI-compatible 服务时，请以 `/models` 返回结果为准，不要只看文档总览页。
- 配置路径：`%AppData%/SonicInput/config.json`，对应字段为 `ai.o​penai_compatible.base_url`、`ai.o​penai_compatible.a​pi_k​ey`、`ai.o​penai_compatible.model_id`。

## 路径
- 配置：`%AppData%/SonicInput/config.json`
- 日志：`%AppData%/SonicInput/logs/app.log`

## 许可
MIT License，详见 [LICENSE](LICENSE)。
