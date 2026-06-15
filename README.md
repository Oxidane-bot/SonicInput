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
- 质量护栏：AI 清理输出会被本地 validator 审查，越界时自动回退原始转写
- 模型审查：设置页可调用当前 AI 提供商生成审查建议；模型不可用时会回退到本地安全校验

## v0.8.0 更新
- 新增 **AI 输出安全门禁**：拦截 markdown/标签泄漏、助手式回答、翻译越界、低信息扩写、长文本过度压缩、异常重复等结果；失败时回退到原始转写，避免坏输出直接输入到目标窗口。
- 新增 **录音内 rolling context**：长语音在后续分块 AI 清理时会带上本次录音已出现的术语、路径和近期上下文，提高技术词、项目名和中英混合内容的一致性。
- 新增 **模型审查页面**：设置窗口中可查看模型审查发现的待处理建议，按边界越界、内容失真、诊断样本、词汇记忆和提示词问题分组处理；模型不可用时会回退到本地安全校验。
- 新增 **本地词汇记忆**：只有用户接受的术语候选才会进入本地记忆；支持导出、清空词汇记忆和清空学习数据。
- 新增长录音云转写路径：云端长录音默认优先走文件转写路径（阈值 90 秒），并在历史记录中记录 `transcription_path`、决策原因和 fallback 类型，便于诊断。
- 新增质量审计工具：`scripts/audit_transcript_quality.py`、`compare_quality_audits.py`、`evaluate_ai_prompt_profiles.py` 可在本地历史库上生成隐私安全的质量报告和 prompt profile 对比。
- 默认热键从旧示例切换为 `Ctrl+Alt+Space`，降低与常见编辑快捷键冲突的概率。

## 性能优化记录
- 2026-03：分块停止路径、历史搜索/分页、批量重处理等性能整理见  
  [`docs/performance_optimizations_2026-03.md`](docs/performance_optimizations_2026-03.md)

## 系统需求
- Windows 10/11 64 位
- 内存 4GB+，磁盘 500MB

## 快速开始
1. 下载 [v0.8.0 Release](https://github.com/Oxidane-bot/SonicInput/releases/tag/v0.8.0) 中的 `SonicInput-v0.8.0-win64.exe`
2. 双击运行，默认热键 Ctrl+Alt+Space（若冲突可在设置中自定义）
3. 在设置中填写需要的云端 API Key（可选），或直接使用本地模型

> 热键后端建议保持 `win32`（无需管理员，冲突率低）；需要按键抑制时再切换 `pynput`。

## 质量审查与本地学习
- AI 清理结果会先通过本地质量门禁；若疑似回答用户、翻译、输出 markdown、过度压缩或扩写噪声，系统会保留原始转写作为最终文本。
- 模型审查默认关闭自动调度；可在设置页手动运行模型审查，检查最近历史中的建议。
- 回退到本地安全校验时不会自动改写历史记录；接受词汇候选只会加入本地词汇记忆，后续 AI 清理会把它作为保守参考。
- 本地审计脚本默认不输出转写原文，只保存长度、状态、路径、异常标签等元数据，便于比较不同 prompt 或模型配置。

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
- 历史与 Review 数据：`%AppData%/SonicInput/history/history.db`
- 本地质量审计输出：`quality_audit/`（默认 git 忽略）

## 许可
MIT License，详见 [LICENSE](LICENSE)。
