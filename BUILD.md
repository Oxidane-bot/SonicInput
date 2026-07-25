# SonicInput 构建指南

本文档说明如何使用 Nuitka 构建 SonicInput 的可执行文件。

## 环境要求

- Python 3.10+
- uv 包管理器
- Visual Studio Build Tools (Windows C++ 编译器)
- 硬盘空间：至少 2GB 用于构建缓存

## 构建类型

### 1. 本地版（包含 sherpa-onnx）

本地版包含完整的离线语音识别功能，支持 sherpa-onnx 本地转录。

```bash
# 安装依赖（包含本地转录支持）
uv sync --locked --extra local --extra dev --group dev

# 构建
uv run --locked --extra local --extra dev --group dev python build_nuitka.py
```

本地和 GitHub Release 均使用 MSVC，并显式加入 Sherpa ABI 对应的根 `onnxruntime.dll`。GitHub Release 固定运行在 `windows-2022`，用 `vswhere` 定位 VS 2022 C++ x64 工具链并在完整构建前运行最小 Nuitka 编译预检。打包后会校验该 DLL 的 SHA-256 与 Sherpa 源文件完全一致。`SONICINPUT_NUITKA_COMPILER=mingw64` 仅保留给诊断性构建，不作为正式 Windows 发布路径。

**输出文件**：`dist/release/v{version}/SonicInput-v{version}-win64.exe`
**可选离线包**:
- 设置 `SONICINPUT_OFFLINE_MODELS_DIR` 指向模型根目录（包含两个已解压的模型文件夹）
- 运行 `uv run --locked --extra local --extra dev --group dev python build_nuitka.py`
- 输出 `dist/release/v{version}/SonicInput-v{version}-win64-offline.zip`（包含 exe + `models/`）

**特性**：
- 包含 sherpa-onnx C 扩展模块（~5MB）
- 支持本地 Paraformer/Zipformer 模型
- 无需互联网连接即可使用本地转录
- 文件大小会随 PySide6、ONNX Runtime 与编译器版本变化；发布后以 GitHub Release 附带的 `.sha256` 文件校验实际产物

v0.8.2 基线实测结果：QML 暂存目录由 14.9 MiB 降至 6.64 MiB；Nuitka 报告中的 Python ONNX Runtime 闭包为 12 个模块且未引入 SymPy；最终 onefile EXE 为 68.32 MiB，比 v0.8.1 小约 3 MiB。每个新版本的实际大小与 SHA-256 以 GitHub Release 附带的 `.sha256` 文件为准。

## 构建说明

### Nuitka 配置详解

```python
# 核心参数
"--standalone"                      # 创建独立分发包（包含所有依赖）
"--onefile"                         # 打包成单个 .exe 文件
"--windows-console-mode=attach"     # 从命令行启动时附着控制台，双击时保持 GUI 体验

# 插件和包含
"--enable-plugin=pyside6"           # 启用 PySide6 插件（Qt 支持）
"--include-package=sonicinput"      # 包含主应用包
"--include-package=sherpa_onnx"     # 包含 sherpa-onnx 包（本地版）
"--include-data-dir=build/staging/assets=assets"  # 已暂存的 UI assets (i18n, subset fonts)
"--include-data-dir=build/staging/qml=."           # 已验证的 QML runtime closure
"--include-package-data=sherpa_onnx"# 包含 sherpa-onnx 数据文件和 C 扩展
"--include-package-data=pypinyin"   # 包含词汇匹配所需的拼音词典 JSON

# 排除项
"--nofollow-import-to=pytest"       # 排除测试依赖
"--nofollow-import-to=mypy"         # 排除类型检查依赖
"--nofollow-import-to=tests"        # 排除测试模块
"--nofollow-import-to=PySide6.QtWebEngine*" # 排除未使用的 WebEngine
```

Qt Quick / QML UI 使用 `build_nuitka.py` 中的 `stage_qml_runtime()` 复制经过 `qmlimportscanner` 和离屏窗口验证的运行时闭包：QtQml Models/WorkerScript、QtQuick Controls（FluentWinUI3、Basic、Fusion 回退链）、Templates、Layouts、Effects 和 Window。不要重新启用 `--include-qt-plugins=qml` 作为默认构建参数；该参数会全量打包 `PySide6/qml`，容易把 `Qt6WebEngineCore.dll`、VirtualKeyboard、3D 等未使用模块带入 exe。
构建脚本会对 staging 内的 QML module plugin DLL 使用显式 `--include-data-file`，确保 `QtQuick.Controls`、`QtQuick.Layouts` 和 FluentWinUI3 style 在 onefile 解包后可加载。资源和 QML 暂存按输入文件指纹缓存，重复构建无需重复字体子集化或复制同一批 QML 文件。

### sherpa-onnx C 扩展处理

sherpa-onnx 包含一个大型 C 扩展模块（`_sherpa_onnx.cp310-win_amd64.pyd`，~5MB）：

- `--include-package=sherpa_onnx`：确保包被完整包含
- `--include-package-data=sherpa_onnx`：包含所有包数据文件，包括 .pyd 文件

Nuitka 会自动：
1. 检测并包含 C 扩展模块（.pyd）
2. 链接所需的 DLL 依赖
3. 在打包的 .exe 中正确设置模块路径

### 模型文件说明

**重要**：ONNX 模型文件**不需要**打包到 .exe 中！

- 默认模型缓存：`%USERPROFILE%\.sonicinput\sherpa_models_v2\`
- 若 EXE 同目录已有 `models\`，优先使用该目录；也可用 `SONICINPUT_MODELS_DIR` 指定缓存目录
- Paraformer 模型：226MB
- Zipformer 模型：112MB

这种设计的优势：
- 减小 .exe 文件大小
- 用户可以选择下载需要的模型
- 模型更新无需重新构建应用

## 构建过程

### 1. 准备阶段

```bash
# `build/nuitka/` 保存增量编译缓存；常规重复构建不要删除它。
# 只在编译器/依赖升级或缓存异常时清理：
Remove-Item -Recurse -Force build\nuitka
```

## 常见问题

### Q1: 构建失败，提示找不到 sherpa-onnx

**原因**：未安装本地转录依赖

**解决**：
```bash
uv sync --locked --extra local --extra dev --group dev
```

### Q2: 构建成功但运行时无法导入 sherpa-onnx

**原因**：Nuitka 未正确包含 C 扩展模块

**解决**：
1. 确保 `build_nuitka.py` 包含 `--include-package-data=sherpa_onnx`
2. 检查构建日志中是否有 "Including package data for 'sherpa_onnx'"
3. 使用 `--verbose` 模式重新构建查看详细信息

### Q3: 可执行文件过大（>100MB）

**原因**：可能包含了不必要的依赖

**解决**：
1. 检查是否意外包含了测试依赖
2. 检查 `build/nuitka/app.dist` 是否包含 `Qt6WebEngineCore.dll`、`qt6webengine*.dll` 或 `PySide6/qml/QtWebEngine/`
3. 确认没有启用 `--include-qt-plugins=qml`，并使用 `stage_qml_runtime()` 生成的精简 QML runtime
4. 添加更多 `--nofollow-import-to` / `--noinclude-dlls` 排除项
5. 考虑构建云端版（不包含 sherpa-onnx）

### Q4: 运行时提示缺少 DLL

**原因**：某些依赖的 DLL 未被 Nuitka 自动检测

**解决**：
1. 使用 Dependency Walker 检查缺少的 DLL
2. 手动添加 `--include-data-files` 包含缺失的 DLL
3. 查看 Nuitka 插件文档，可能需要特定插件

## 构建性能优化

### 加速构建

- 保留 `build/nuitka/`：Nuitka 会复用 C 编译和链接中间结果。
- 保留 `build/staging/`：资源和 QML 暂存会在输入文件与 PySide6 版本不变时复用。
- Nuitka 2.8 默认让 `--jobs` 使用可用 CPU，并将 LTO 设为 `auto`；不要为了“优化”硬编码较小并行度或强制 LTO。
- 构建报告位于 `build/nuitka/nuitka-report.xml`，可用于比较后续依赖和数据文件变化。

### 减小文件大小

- onefile 在当前 Nuitka 版本中默认压缩；`--onefile-compress=yes` 不是本项目的有效优化项。
- 不要把 `--remove-output` 当作体积优化。它只会丢弃能加速下次构建的中间产物。
- 默认构建已排除测试、WebEngine、PDF 和未使用 QML 模块。进一步删除 ONNX Runtime、Qt DLL 或 QML 模块前，必须用本地 ASR、设置窗口、录音悬浮窗、关于窗口做运行时回归。

## 分发建议

### 本地版发布清单

- [ ] 测试本地转录功能（Paraformer/Zipformer）
- [ ] 测试首次启动模型下载
- [ ] 验证快捷键功能
- [ ] 检查系统托盘图标
- [ ] 测试 AI 文本优化（如启用）
- [ ] 验证本地词汇一级页面、候选/已保存 Tab 与独立滚动
- [ ] 验证进入和重新进入历史页会自动加载记录
- [ ] 在干净的 Windows 系统上测试


## 版本命名规范

```
SonicInput-v{version}-win64.exe        # 本地版（包含 sherpa-onnx）
```

示例：
```
SonicInput-v0.8.6-win64.exe
```

## 技术细节

### sherpa-onnx 包结构

```
sherpa_onnx/
├── __init__.py                          # Python 接口
├── lib/
│   └── _sherpa_onnx.cp310-win_amd64.pyd # C 扩展（4.9MB）
├── online_recognizer.py                 # 在线识别器
└── offline_recognizer.py                # 离线识别器
```

### Nuitka 打包流程

1. **依赖分析**：扫描 import 语句，构建依赖图
2. **代码编译**：将 Python 代码编译为 C 代码
3. **C 编译**：使用 MSVC 编译 C 代码为二进制
4. **链接**：链接所有对象文件和依赖库
5. **打包**：将所有文件打包到单个 .exe
6. **压缩**：Nuitka 默认压缩 onefile 可执行文件

### 与 PyInstaller 的区别

| 特性 | Nuitka | PyInstaller |
|------|--------|-------------|
| 方法 | 编译为 C | 打包解释器 |
| 性能 | 更快（编译优化） | 原始性能 |
| 启动速度 | 快 | 较慢（解压） |
| 文件大小 | 较小 | 较大 |
| 兼容性 | 需要 C 编译器 | 无需编译器 |
| C 扩展 | 原生支持 | 可能需要额外配置 |

## Localization (i18n)

Update UI translations with Qt tools (PySide6 bundle):

```bash
# Extract/update source strings
.\.venv\Lib\site-packages\PySide6\lupdate.exe -extensions py -recursive src `
  -ts assets\i18n\sonicinput_en_US.ts assets\i18n\sonicinput_zh_CN.ts

# Compile .ts to .qm
.\.venv\Lib\site-packages\PySide6\lrelease.exe assets\i18n\sonicinput_en_US.ts `
  assets\i18n\sonicinput_zh_CN.ts
```

---

**最后更新**：2026-07-25
**适用版本**：v0.8.6+


## Release Script

Use the helper script to build the exe and (optionally) the offline bundle:

```powershell
# Run locked checks, build the exe, and write a SHA-256 sidecar
.\scripts\release.ps1

# Build exe + offline zip (models dir must contain both model folders)
.\scripts\release.ps1 -OfflineModelsDir "C:\path\to\models"

# Optional: build 7z (default off)
.\scripts\release.ps1 -OfflineModelsDir "C:\path\to\models" -Build7z -SevenZipPath "C:\Program Files\7-Zip\7z.exe"

# Also load a cached model and run a real packaged decode before release
.\scripts\release.ps1 -NoOffline -ModelSmokeDir "C:\path\to\model-cache" -ModelSmokeName "zipformer-small"

# Iterate on Nuitka only; skips locked sync and source checks
.\scripts\release.ps1 -SkipChecks

# Skip packaged CLI/offscreen-startup smoke only when diagnosing an iteration
.\scripts\release.ps1 -SkipSmoke
```

The script uses `uv sync --locked --extra local --extra dev --group dev`, runs the same Ruff/mypy scope as CI, both non-GUI and offscreen GUI/QML suites, then packaged `--help`, `--validate`, `--package-smoke`, and an isolated 12-second offscreen GUI-startup smoke by default. `--package-smoke` verifies packaged assets, pypinyin dictionaries, ONNX Runtime, the sherpa native runtime, and the Settings/Overlay/About QML roots. When `-ModelSmokeDir` is provided, it additionally loads the named cached model and decodes one second of silent audio without downloading or modifying the model cache. Packaged CLI checks have a 180-second timeout, and a formal build removes same-version stale artifacts before compiling. The script writes the executable, optional offline archive, and `.sha256` file under `dist/release/v{version}/`. Close any running SonicInput process before invoking it so `uv sync` can update the environment.

## GitHub Release

The `.github/workflows/release.yml` workflow is the authoritative publisher. After the local release script has passed, commit the versioned source and release notes, create an annotated `v{version}` tag at that commit, and push the tag. The workflow rebuilds on `windows-2022`, initializes the VS 2022 C++ x64 environment, compiles a minimal Nuitka preflight, reruns locked validation and packaged smoke checks, then creates the GitHub Release with the exe and SHA-256 sidecar. It refuses a tag whose name does not match `pyproject.toml`.
