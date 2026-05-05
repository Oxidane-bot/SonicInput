# 录音功能测试文档

## 概述

本文档描述了为 SonicInput 项目创建的录音功能测试套件。这些测试验证了录音启动、悬浮窗显示、状态转换和完整工作流程的正确性。

## 测试文件

### 1. `test_recording_basic.py` - 基础录音功能测试
**推荐使用** - 这个测试套件最稳定，专注于核心功能验证。

#### 测试用例：

1. **`test_recording_basic_workflow`** - 基础录音工作流程
   - 验证录音启动和停止
   - 检查状态转换
   - 验证事件触发

2. **`test_recording_state_transitions`** - 录音状态转换
   - IDLE → RECORDING → IDLE
   - 状态时间戳记录

3. **`test_multiple_recording_cycles`** - 多次录音循环
   - 连续录音/停止循环
   - 异步处理等待
   - 容错处理

4. **`test_audio_level_events_during_recording`** - 音频级别事件
   - 录音期间音频级别更新
   - 事件验证

5. **`test_recording_with_overlay_mock`** - 悬浮窗交互测试
   - Mock 悬浮窗对象
   - 方法存在性验证

6. **`test_error_handling_during_recording`** - 错误处理
   - 录音过程中异常处理
   - 应用稳定性验证

7. **`test_complete_recording_workflow`** - 完整工作流程
   - 端到端测试
   - 时间分析
   - 事件顺序验证

### 2. `tests/ui/test_fluent_qml_ui.py` - Fluent/QML 悬浮窗测试
验证当前唯一的 Fluent/QML 悬浮窗实现。

#### 测试用例：

- FluentRecordingOverlay host 初始化
- QML 录音悬浮窗加载
- 公共方法通过 Qt 信号队列派发
- 悬浮窗位置保存与屏幕元数据
- 音频级别显示更新

### 3. `test_recording_simple.py` - 简化录音功能测试
**备选方案** - 更简单的实现，依赖具体的 Mock 验证。

## 运行测试

### 运行基础录音测试（推荐）
```bash
uv run python -m pytest tests/test_recording_basic.py -v
```

### 运行特定测试
```bash
# 运行基础工作流程测试
uv run python -m pytest tests/test_recording_basic.py::TestRecordingBasic::test_recording_basic_workflow -v

# 运行完整工作流程测试
uv run python -m pytest tests/test_recording_basic.py::TestRecordingBasic::test_complete_recording_workflow -v
```

### 运行所有录音相关测试
```bash
uv run python -m pytest tests/test_recording_*.py -v
```

## 测试覆盖的核心功能

### ✅ 已验证功能

1. **录音启动/停止流程**
   - toggle_recording() 方法正常工作
   - 状态正确转换（IDLE ↔ RECORDING）

2. **事件系统**
   - RECORDING_STARTED 事件正确触发
   - RECORDING_STOPPED 事件正确触发
   - AUDIO_LEVEL_UPDATE 事件处理

3. **状态管理**
   - RecordingState 状态机正确
   - AppState 状态转换
   - 状态持久化和恢复

4. **异步处理**
   - 录音停止后的转录处理
   - AI 文本优化
   - 错误恢复机制

5. **多次录音循环**
   - 连续录音/停止操作
   - 状态清理和重置
   - 并发处理保护

6. **悬浮窗集成**
   - Mock 悬浮窗对象交互
   - 基本接口验证
   - 状态同步

## 测试环境配置

### 依赖注入容器
测试使用 DI 容器 (`DIContainer`)：
```python
from sonicinput.core.di_container import create_container
container = create_container()
```

### Mock 服务
关键服务被 Mock 替换：
- `ISpeechService` - Whisper 转录引擎
- `IAudioService` - 音频录制服务
- `IInputService` - 输入服务
- `GroqClient` - AI 优化客户端

### 异步处理等待
由于录音涉及异步处理，测试中使用适当的等待时间：
```python
time.sleep(0.1)  # 短暂等待
time.sleep(0.2)  # 中等等待
time.sleep(0.5)  # 长时间等待（确保处理完成）
```

## 测试结果解读

### 成功的测试输出示例
```
============================= test session starts =============================
collected 7 items

tests/test_recording_basic.py::TestRecordingBasic::test_recording_basic_workflow PASSED [ 14%]
tests/test_recording_basic.py::TestRecordingBasic::test_recording_state_transitions PASSED [ 28%]
tests/test_recording_basic.py::TestRecordingBasic::test_multiple_recording_cycles PASSED [ 42%]
tests/test_recording_basic.py::TestRecordingBasic::test_audio_level_events_during_recording PASSED [ 57%]
tests/test_recording_basic.py::TestRecordingBasic::test_recording_with_overlay_mock PASSED [ 71%]
tests/test_recording_basic.py::TestRecordingBasic::test_error_handling_during_recording PASSED [ 85%]
tests/test_recording_basic.py::TestRecordingBasic::test_complete_recording_workflow PASSED [100%]

============================== 7 passed in 15.46s ==============================
```

### 日志输出
测试期间会显示详细的应用日志，包括：
- 录音启动/停止事件
- 状态变化
- 转录处理
- AI 优化处理
- 错误信息（如果有）

## 已知问题和限制

### 1. 字符编码问题
测试环境中可能出现 `'charmap' codec can't encode characters` 错误，这是 Windows 控制台编码问题，不影响核心功能。

### 2. 异步处理时序
快速连续的录音操作可能因为异步处理而失败，测试中已通过适当的等待时间和容错处理来解决。

### 3. Qt UI 测试复杂性
完整的悬浮窗 UI 测试需要复杂的 Qt Mock 配置，当前版本提供了基础的 Mock 验证。

## 最佳实践

### 1. 使用基础测试套件
对于日常开发和 CI/CD，推荐使用 `test_recording_basic.py`。

### 2. 适当的等待时间
录音涉及音频处理、转录和 AI 优化，需要足够的等待时间。

### 3. 状态验证
始终验证录音状态和应用状态的正确性。

### 4. 事件监听
使用事件系统验证异步操作的正确性。

## 结论

录音功能测试套件成功验证了 SonicInput 的核心录音功能：

- ✅ 录音启动/停止机制正常
- ✅ 状态管理正确
- ✅ 事件系统工作正常
- ✅ 异步处理稳定
- ✅ 错误处理有效
- ✅ 多次录音循环支持

测试套件为持续集成和开发过程中的回归测试提供了可靠的基础。
