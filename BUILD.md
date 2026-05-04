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
uv sync --extra local --group dev

# 构建
uv run python build_nuitka.py
```

**输出文件**：`dist/SonicInput-v{version}-win64.exe`
**可选离线包**:
- 设置 `SONICINPUT_OFFLINE_MODELS_DIR` 指向模型根目录（包含两个已解压的模型文件夹）
- 运行 `uv run python build_nuitka.py`
- 输出 `dist/SonicInput-v{version}-win64-offline.zip`（包含 exe + `models/`）

**特性**：
- 包含 sherpa-onnx C 扩展模块（~5MB）
- 支持本地 Paraformer/Zipformer 模型
- 无需互联网连接即可使用本地转录
- 文件大小：~66MB（v0.7.3，包含 PySide6 / Qt Quick / sherpa-onnx 运行时）

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
"--include-data-dir=assets=assets"  # UI assets (i18n, fonts)
"--include-data-dir=build/qml_staging=." # 精简 QML runtime staging
"--include-package-data=sherpa_onnx"# 包含 sherpa-onnx 数据文件和 C 扩展

# 排除项
"--nofollow-import-to=pytest"       # 排除测试依赖
"--nofollow-import-to=mypy"         # 排除类型检查依赖
"--nofollow-import-to=tests"        # 排除测试模块
"--nofollow-import-to=PySide6.QtWebEngine*" # 排除未使用的 WebEngine
```

Qt Quick / QML UI 使用 `build_nuitka.py` 中的 `stage_qml_runtime()` 精简复制必要 QML imports。不要重新启用 `--include-qt-plugins=qml` 作为默认构建参数；该参数会全量打包 `PySide6/qml`，容易把 `Qt6WebEngineCore.dll` 等未使用的大体积模块带入 exe。

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

- 模型在首次使用时自动下载到：`%APPDATA%/SonicInput/models/`
- Paraformer 模型：226MB
- Zipformer 模型：112MB

这种设计的优势：
- 减小 .exe 文件大小
- 用户可以选择下载需要的模型
- 模型更新无需重新构建应用

## 构建过程

### 1. 准备阶段

```bash
# 清理旧构建（可选）
rm -rf dist/ build/

# 验证环境
uv run python test_sherpa_import.py
```

## 常见问题

### Q1: 构建失败，提示找不到 sherpa-onnx

**原因**：未安装本地转录依赖

**解决**：
```bash
uv sync --extra local --group dev
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
2. 检查 `dist/app.dist` 是否包含 `Qt6WebEngineCore.dll`、`qt6webengine*.dll` 或 `PySide6/qml/QtWebEngine/`
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

```bash
# 使用缓存（第二次构建会快很多）
uv run python build_nuitka.py

# 使用 LTO（链接时优化，更小但更慢）
# 在 nuitka_cmd 中添加：
"--lto=yes"

# 使用并行编译
# 在 nuitka_cmd 中添加：
"--jobs=4"  # 使用 4 个 CPU 核心
```

### 减小文件大小

```bash
# 启用压缩（需要 Commercial 版本）
"--onefile-compress=yes"

# 移除调试符号
"--remove-output"  # 构建后删除临时文件
```

## 分发建议

### 本地版发布清单

- [ ] 测试本地转录功能（Paraformer/Zipformer）
- [ ] 测试首次启动模型下载
- [ ] 验证快捷键功能
- [ ] 检查系统托盘图标
- [ ] 测试 AI 文本优化（如启用）
- [ ] 在干净的 Windows 系统上测试


## 版本命名规范

```
SonicInput-v{version}-win64.exe        # 本地版（包含 sherpa-onnx）
```

示例：
```
SonicInput-v0.3.0-win64.exe
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
6. **压缩**：压缩最终的可执行文件（可选）

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
.\.venv\Lib\site-packages\PySide6\lupdate.exe -extensions py -recursive src app.py `
  -ts assets\i18n\sonicinput_en_US.ts assets\i18n\sonicinput_zh_CN.ts

# Compile .ts to .qm
.\.venv\Lib\site-packages\PySide6\lrelease.exe assets\i18n\sonicinput_en_US.ts `
  assets\i18n\sonicinput_zh_CN.ts
```

---

**最后更新**：2026-05-04
**适用版本**：v0.7.3+


## Release Script

Use the helper script to build the exe and (optionally) the offline bundle:

```powershell
# Build exe only
.\scripts\release.ps1

# Build exe + offline zip (models dir must contain both model folders)
.\scripts\release.ps1 -OfflineModelsDir "C:\path\to\models"

# Optional: build 7z (default off)
.\scripts\release.ps1 -OfflineModelsDir "C:\path\to\models" -Build7z -SevenZipPath "C:\Program Files\7-Zip\7z.exe"
```
