# v0.6.4 - 历史诊断与性能体验升级

## 中文

### 亮点

**历史记录体验**
- 历史主表恢复为核心列（Time / LEN / Transcription / Status），避免诊断字段挤占阅读空间。
- provider / mode / transcribe 耗时 / fallback 等诊断信息继续保留在 tooltip 与详情页，便于问题复盘。

**性能优化**
- 分块模式停止路径优化，减少在边界场景的等待抖动。
- 历史搜索与统计优化：启用 FTS5 + 异步统计查询，降低大历史量下的卡顿。
- 历史分页切换为 keyset 分页，滚动加载更稳定。
- 批量重处理改为 keyset 读取 + 批量写入，吞吐更好。

**数据可追踪性**
- 批量/单条重处理默认新增历史记录并保留原记录，方便横向对比与回滚排查。

### 兼容性
- 配置文件与历史数据库保持兼容。
- 旧记录会按 “Legacy defaults” 显示诊断状态，不影响使用。

### 发布产物
- `SonicInput-v0.6.4-win64.exe`

---

## English

### Highlights

**History UX**
- The history main table is simplified back to core columns (Time / LEN / Transcription / Status).
- Diagnostics (provider/mode/transcribe duration/fallback) are still preserved in tooltip and detail view for troubleshooting.

**Performance**
- Improved chunk-stop path behavior to reduce boundary-case wait jitter.
- Faster history search and stats using FTS5 + async aggregate queries.
- Keyset pagination replaces offset pagination for smoother large-history scrolling.
- Batch reprocess now uses keyset reads + batch writes for better throughput.

**Traceability**
- Reprocessing now creates new history records while preserving originals for side-by-side comparison.

### Compatibility
- Config and history DB remain backward-compatible.
- Legacy entries are marked as diagnostic defaults without breaking behavior.

### Artifact
- `SonicInput-v0.6.4-win64.exe`
