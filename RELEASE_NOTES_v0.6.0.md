# v0.6.0 - 离线模型包 & I18N 完成

## 中文

### 亮点
**离线包**  
- exe 同目录 `models/` 自动识别，其次 `SONICINPUT_MODELS_DIR`，最后默认缓存；诊断报告显示 `model_cache_root` / `model_cache_source`。  
- 发布脚本默认只产 exe + 离线 zip；7z 改为显式 `-Build7z`（默认不生成）。

**I18N**  
- `error_messages.py`、模型描述、模型下载提示均可翻译；QM 已更新。

**健壮性**  
- 模型测试在引擎为空或未加载时弹窗提示，不再抛异常；修复 `whisper_engine` NameError。  
- 本地模型搜索优先 exe 同级 `models/`，离线包解压即用。

### 升级步骤
**从 v0.5.8 升级**  
1. 下载 `SonicInput-v0.6.0-win64.exe`。  
2. 需要离线使用时，另下 `SonicInput-v0.6.0-win64-offline.zip`，解压后直接运行同目录 exe。  
3. 诊断：`SonicInput-v0.6.0-win64.exe --diagnostics` 可查看模型缓存路径来源。  
4. 旧配置与历史保留，无需迁移。

### 系统要求
**最低**: Windows 10 64-bit，4GB RAM，500MB 磁盘  
**推荐**: Windows 11 64-bit，8GB RAM，1GB 磁盘（离线包额外约 2GB 解压空间）

### 支持
- 配置：`%AppData%/SonicInput/config.json`  
- 日志：`%AppData%/SonicInput/logs/app.log`  
- Issues：<https://github.com/Oxidane-bot/SonicInput/issues>

---

## English

### Highlights
**Offline bundle**  
- Runtime now prefers `models/` beside the exe, then `SONICINPUT_MODELS_DIR`, then the default cache; diagnostics show `model_cache_root` / `model_cache_source`.  
- Release script ships exe + offline zip by default; 7z is opt-in via `-Build7z`.

**I18N**  
- User-facing error messages, model descriptions, and download prompts are translatable; QM updated.

**Reliability**  
- Model-test button shows friendly prompts when engine is missing or not loaded; fixed `whisper_engine` NameError.  
- Offline bundle works out of the box: unzip, keep exe + `models/` together, run.

### Upgrade Steps
**From v0.5.8**  
1. Download `SonicInput-v0.6.0-win64.exe`.  
2. For offline use, also download `SonicInput-v0.6.0-win64-offline.zip`, unzip, run the exe in the same folder.  
3. Diagnostics: `SonicInput-v0.6.0-win64.exe --diagnostics` to see cache root/source.  
4. Config and history are preserved.

### System Requirements
**Minimum**: Windows 10 64-bit, 4GB RAM, 500MB disk  
**Recommended**: Windows 11 64-bit, 8GB RAM, 1GB disk (plus ~2GB to unpack offline bundle)

### Support
- Config: `%AppData%/SonicInput/config.json`  
- Logs: `%AppData%/SonicInput/logs/app.log`  
- Issues: <https://github.com/Oxidane-bot/SonicInput/issues>

---

**核心改进**: v0.6.0 提供可直接解压使用的离线模型包，补全 I18N，优化模型测试与诊断。  
**Core Improvements**: v0.6.0 ships an out-of-the-box offline bundle, completes I18N coverage, and hardens model testing/diagnostics.
