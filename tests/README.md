# 测试指南

## 测试分类

本项目的测试分为以下几类：

### 1. 单元测试（无需GUI）
- 不依赖Qt GUI环境
- 可以在无头环境/CI中运行
- 默认运行

```bash
# 运行所有非GUI测试
uv run pytest -m "not gui"

# 或者
uv run pytest --ignore=tests/ui/ --ignore=tests/test_recording_overlay.py
```

### 2. GUI测试
- 需要Qt GUI环境
- 需要显示器或虚拟显示
- 使用`@pytest.mark.gui`标记

```bash
# 只运行GUI测试
uv run pytest -m gui

# 运行特定GUI测试文件
uv run pytest tests/ui/test_recording_overlay.py -v
uv run pytest tests/test_recording_overlay.py -v
```

### 3. GPU测试
- 需要CUDA/GPU支持
- 使用`@pytest.mark.gpu`标记

```bash
# 只运行GPU测试
uv run pytest -m gpu
```

### 4. 慢速测试
- 运行时间较长（>2秒）
- 使用`@pytest.mark.slow`标记

```bash
# 跳过慢速测试
uv run pytest -m "not slow"
```

## 完整测试套件

### 运行所有测试（包括GUI）
```bash
uv run pytest -v
```

### 运行CI/CD测试（跳过GUI和GPU）
```bash
uv run pytest -m "not gui and not gpu and not e2e" -v
```

### 运行快速测试（跳过GUI、GPU、慢速）
```bash
uv run pytest -m "not gui and not gpu and not slow" -v
```

## GUI测试的特殊说明

### 为什么需要分离GUI测试？

1. **环境依赖**：GUI测试需要Qt GUI环境，在无头服务器/CI中无法运行
2. **执行速度**：GUI测试通常较慢，影响快速反馈
3. **稳定性**：GUI测试容易受到环境影响（分辨率、窗口管理器等）

### GUI测试文件

- `tests/ui/test_recording_overlay.py` - RecordingOverlay单元测试（27个测试）
- `tests/test_recording_overlay.py` - RecordingOverlay集成测试（11个测试）
- `tests/test_basic_functionality.py::test_recording_overlay_creation` - 基本创建测试

### 如何在CI中运行GUI测试

#### GitHub Actions示例
```yaml
- name: Install xvfb for GUI tests
  run: sudo apt-get install -y xvfb

- name: Run GUI tests
  run: xvfb-run -a uv run pytest -m gui -v
```

#### Windows CI
```bash
# Windows通常有GUI环境，可以直接运行
uv run pytest -m gui -v
```

## 代码质量检查

```bash
# Ruff 代码检查
uv run ruff check src tests

# Ruff 格式检查
uv run ruff format --check src tests
```

## 调试测试

```bash
# 详细输出 + 立即停止
uv run pytest -vv -x

# 显示print输出
uv run pytest -s

# 只运行失败的测试
uv run pytest --lf

# 运行特定测试
uv run pytest tests/test_basic_functionality.py::test_config_loading -v
```

## 常见问题

### Q: 为什么GUI测试卡住了？
A: GUI测试可能由于以下原因卡住：
- 缺少Qt GUI环境
- 窗口管理器冲突
- Mock配置不正确

解决方法：
```bash
# 跳过GUI测试
uv run pytest -m "not gui"

# 使用超时
uv run pytest -m gui --timeout=30
```

### Q: 如何只运行某个组件的测试？
A: 使用pytest的文件/目录选择：
```bash
# 测试overlay组件
uv run pytest tests/ui/test_recording_overlay.py

# 测试所有UI组件
uv run pytest tests/ui/

# 测试特定函数
uv run pytest tests/ui/test_recording_overlay.py::TestRecordingOverlayDisplay::test_display_capability
```

### Q: CI中如何跳过GUI测试？
A: 在CI配置中添加：
```bash
uv run pytest -m "not gui and not gpu and not e2e" -v
```

## 测试最佳实践

1. **本地开发**：快速反馈
   ```bash
   uv run pytest -m "not gui and not slow" -x
   ```

2. **提交前检查**：运行所有非GUI测试
   ```bash
   uv run pytest -m "not gui" -v
   ```

3. **完整验证**：定期运行包括GUI的所有测试
   ```bash
   uv run pytest -v
   ```

4. **性能测试**：只运行GPU测试
   ```bash
   uv run pytest -m gpu -v
   ```
