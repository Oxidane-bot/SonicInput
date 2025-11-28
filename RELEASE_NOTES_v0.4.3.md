# v0.4.3 - 热键热重载修复

## 中文

v0.4.3 - 热键热重载修复

### 主要改进

**热键系统稳定性**
- 修复热键后端切换时的注册失败问题
- 解决 Win32 后端热重载超时卡死
- 支持 pynput ↔ win32 后端无缝切换
- 热键配置变更即时生效，无需重启

**问题修复**
- 修复 Win32 热键注册超时返回成功的并发 bug
- 修复消息循环线程 ID 获取错误导致的唤醒失败
- 修复 Pynput 后端无热键时初始化失败
- 修复后端切换顺序导致的注册时序问题

**配置验证**
- 新增热键后端配置验证（仅允许 pynput/win32）
- 配置保存前自动检查，防止无效配置

### 使用方法

**切换热键后端**
1. 打开设置窗口
2. 选择"热键设置"标签
3. 切换"热键后端"（pynput/win32）
4. 点击"应用"按钮
5. 立即生效，无需重启

**支持的后端**
- pynput：跨平台热键库（推荐）
- win32：Windows 原生 RegisterHotKey API

### 升级步骤

**从 v0.4.2 升级**
1. 下载 SonicInput-v0.4.3-win64.exe
2. 关闭旧版本，替换可执行文件
3. 启动应用（配置自动生效）

**注意事项**
- 完全兼容 v0.4.2 配置
- 无需手动调整任何设置
- 直接替换即可使用

### 系统要求

**最低配置**
- Windows 10 64-bit
- Intel Core i3 或同等 CPU
- 4GB RAM
- 500MB 磁盘空间

**推荐配置**
- Windows 11 64-bit
- Intel Core i5 或 AMD Ryzen 5
- 8GB RAM
- 1GB 磁盘空间

### 技术支持

**配置和日志**
- 配置：`%AppData%\SonicInput\config.json`
- 日志：`%AppData%\SonicInput\logs\app.log`
- 模型：`%AppData%\SonicInput\models/`

**问题反馈**
- GitHub Issues: [提交 Issue](https://github.com/Oxidane-bot/SonicInput/issues)

---

## English

v0.4.3 - Hotkey Hot Reload Fix

### Key Improvements

**Hotkey System Stability**
- Fix hotkey registration failure during backend switching
- Resolve Win32 backend hot reload timeout freeze
- Support seamless pynput ↔ win32 backend switching
- Instant hotkey configuration changes without app restart

**Bug Fixes**
- Fix Win32 hotkey registration timeout returning success (concurrency bug)
- Fix message loop thread ID retrieval error causing wakeup failure
- Fix Pynput backend initialization failure without hotkeys
- Fix backend switching order causing registration timing issues

**Configuration Validation**
- Add hotkey backend configuration validation (only allow pynput/win32)
- Auto-check before saving config to prevent invalid configurations

### Usage

**Switch Hotkey Backend**
1. Open Settings window
2. Select "Hotkey Settings" tab
3. Switch "Hotkey Backend" (pynput/win32)
4. Click "Apply" button
5. Takes effect immediately, no restart needed

**Supported Backends**
- pynput: Cross-platform hotkey library (recommended)
- win32: Windows native RegisterHotKey API

### Upgrade Steps

**From v0.4.2**
1. Download SonicInput-v0.4.3-win64.exe
2. Close old version, replace executable
3. Launch app (config auto-applied)

**Notes**
- Fully compatible with v0.4.2 config
- No manual settings adjustment needed
- Direct replacement ready to use

### System Requirements

**Minimum**
- Windows 10 64-bit
- Intel Core i3 or equivalent CPU
- 4GB RAM
- 500MB disk space

**Recommended**
- Windows 11 64-bit
- Intel Core i5 or AMD Ryzen 5
- 8GB RAM
- 1GB disk space

### Technical Support

**Configuration and Logs**
- Config: `%AppData%\SonicInput\config.json`
- Logs: `%AppData%\SonicInput\logs\app.log`
- Models: `%AppData%\SonicInput\models/`

**Issue Reporting**
- GitHub Issues: [Submit Issue](https://github.com/Oxidane-bot/SonicInput/issues)

---

**核心改进总结**: v0.4.3 修复热键热重载卡死问题，支持后端无缝切换，提升系统稳定性。

**Core Improvements**: v0.4.3 fixes hotkey hot reload freeze, supports seamless backend switching, improves system stability.
