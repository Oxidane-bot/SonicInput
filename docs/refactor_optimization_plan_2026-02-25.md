# SonicInput 多-Agent 重构与优化计划（2026-02-25）

## 审计范围
- Agent A: 架构与依赖边界（Controller / Service / UI）
- Agent B: 并发与性能（录音、转录、队列、UI 线程）
- Agent C: 可维护性（大文件、重复逻辑、死代码候选）
- Agent D: 工程化（CI、测试基线、打包链路）
- Agent E: Ruff 自动化（本地与 CI 质量门）

## 结论摘要
- 建议重构：`是`。当前代码可运行，但在 UI 大文件、云端客户端复用、启动编排复杂度方面有明显维护成本。
- 优先策略：先做低风险高收益项，再做结构性重构，避免一次性大改。

## 立刻做（高收益、低风险）
1. Ruff 自动化三层质量门
- 本地 `pre-commit` 自动 format + fix
- 本地 `pre-push` 执行 Ruff check + format check
- CI 对齐到 `src + tests`（避免本地/CI规则漂移）

2. 文档与基线命令对齐
- 测试文档统一到 `pytest -m "not gui and not gpu and not e2e" -v`
- 补充本地 hook 安装与团队约定

## 应当做（中期）
1. 拆分超大 UI 文件
- `src/sonicinput/ui/settings_window.py`
- `src/sonicinput/ui/settings_tabs/history_tab.py`
- `src/sonicinput/ui/settings_tabs/transcription_tab.py`
- `src/sonicinput/ui/settings_tabs/ai_tab.py`

2. 云端客户端共性抽象
- 收敛重复的重试、超时、错误映射、模型列表获取逻辑
- 统一 provider 级别能力描述（是否支持稳定 list endpoint）

3. 启动编排简化
- 降低 `app.py` + `voice_input_app.py` 初始化路径复杂度
- 固化初始化顺序与失败回滚策略

## 可延后（低优先级）
1. 系统化死代码治理（以调用链和测试覆盖为依据，分批删除）
2. 日志结构统一（减少噪声日志，补关键链路指标）
3. 可选的本地 pre-push 快速回归（按团队节奏开启）

## 执行与验收
- 风格：`uv run ruff check src tests` 与 `uv run ruff format --check src tests` 通过
- 回归：`uv run pytest -m "not gui and not gpu and not e2e" -v` 通过
- 安全：`uv run bandit -r src -ll -ii -f json -o bandit-report.json` 通过
- 打包：`.\scripts\release.ps1` 能产出目标 exe（必要时加离线包参数）
