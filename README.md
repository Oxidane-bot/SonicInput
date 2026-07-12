<div align="center">
  <img src="assets/icon.png" alt="SonicInput Icon" width="128" height="128">
  <h1>SonicInput</h1>
  <p>基于 sherpa-onnx 的 Windows 语音输入工具，支持本地/云端 ASR 与 AI 后处理</p>
  <p><strong>Languages:</strong> <a href="README.md">中文</a> | <a href="README_EN.md">English</a></p>
</div>

## 核心特性
- 即开即用：剪贴板 / 文本 / GUI 多入口
- 热键无管理员：Win32 RegisterHotKey（默认 Ctrl+Alt+Space，可自定义），冲突时会提示
- 双模式录制：Realtime 低延迟；Chunked 精度高（AI 后处理）
- 云端/本地切换：Groq / OpenRouter / NVIDIA / OpenAI / 本地 sherpa-onnx
- 本地词汇记忆：用户确认后的词条会在后续 AI 清理前按同音/近音匹配注入
- 词汇审查：设置页可调用当前 AI 提供商从 raw 转写上下文中挖掘候选词条

## v0.8.2 更新
- **运行时代码清理**：移除了未被主程序使用的旧插件、兼容层、服务和依赖，保留现有公开入口；`app.py` 仍可用于源码和 Nuitka 构建，新增正式命令 `sonicinput`。
- **错误记录更可信**：异常恢复不再把未执行的动作记为成功，`--help` 等正常 CLI 路径也不会留下误导性的崩溃记录。
- **分发包可重复构建**：wheel/源码包明确包含 UI 资源并排除本机缓存与历史构建目录；Nuitka 发布物与编译中间产物分离。
- **更小、更快的打包**：QML 运行时按已验证的 Fluent UI 依赖闭包暂存，删除未使用的 WebEngine、VirtualKeyboard、3D、PDF 等模块；QML 暂存从 14.9 MiB 降到 6.64 MiB，最终 EXE 为 68.32 MiB，比 v0.8.1 小约 3 MiB。重复构建会复用资源、QML 暂存和 Nuitka 编译缓存。
- **本地词汇记忆与历史页改进**：一级词汇页、候选/已保存词汇独立滚动、历史页即时刷新，以及更严格的候选证据与同音纠错规则继续保留。

## 性能优化记录
- 2026-03：分块停止路径、历史搜索/分页、批量重处理等性能整理见  
  [`docs/performance_optimizations_2026-03.md`](docs/performance_optimizations_2026-03.md)

## 系统需求
- Windows 10/11 64 位
- 内存 4GB+，磁盘 500MB

## 快速开始
1. 从 [Releases](https://github.com/Oxidane-bot/SonicInput/releases) 下载 `SonicInput-v0.8.2-win64.exe`
2. 双击运行，默认热键 Ctrl+Alt+Space（若冲突可在设置中自定义）
3. 在设置中填写需要的云端 API Key（可选），或直接使用本地模型

> 热键后端建议保持 `win32`（无需管理员，冲突率低）；需要按键抑制时再切换 `pynput`。

## 词汇审查与本地学习
- 词汇审查只读取 raw ASR 转写，不读取 AI 清理后的 `ai_optimized_text` / `final_text`，避免把 AI 自己清错的结果固化进词库。
- 本地词汇记忆是设置窗口中的一级页面，候选词和已保存词汇可分别查看和滚动。
- 审查模型会根据整句 raw 上下文提取最小完整词组；候选必须带有可验证的原始记录证据，并由用户接受后才会进入本地词汇记忆。
- 后续 AI 清理前，系统用 `LexiconMatcher` 对当前 raw 文本做同音/近音预筛，只注入相关词条。
- 自动词汇审查默认关闭；可在设置页手动运行，也可开启空闲调度。
- v0.8.1 起不保留旧审查结构的兼容迁移；若检测到不兼容 schema，会重建 review/lexicon 表。升级前可从旧版本设置页导出词库；配置和历史记录不受影响。
- 本地审计脚本默认不输出转写原文，只保存长度、状态、路径、异常标签等元数据，便于比较不同 prompt 或模型配置。

## 开发环境
```bash
git clone https://github.com/Oxidane-bot/SonicInput.git
cd SonicInput
uv sync          # 安装运行依赖
uv run sonicinput --gui
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
- 历史与 Review 数据：`%AppData%/SonicInput/history/history.db`
- 本地质量审计输出：`quality_audit/`（默认 git 忽略）

## 许可
MIT License，详见 [LICENSE](LICENSE)。
