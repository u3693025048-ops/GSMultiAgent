# Python async 关键字冲突修复

## 问题描述

在Python 3.14+中，`async`被保留为关键字，不能用作模块名。

**错误信息**：
```
SyntaxError: invalid syntax
  File "multi_agent/async/__init__.py", line 3
    from multi_agent.async.task_queue import (
                     ^^^^^
```

## 根本原因

`async`是Python的保留关键字（用于异步函数定义），不能作为包名。

```python
# ❌ 错误：async是保留关键字
from multi_agent.async.task_queue import ...

# ✅ 正确：使用非保留字名称
from multi_agent.asynctask.task_queue import ...
```

## 解决方案

将包名从`async`改为`asynctask`。

### 修改清单

**新建文件**：
- ✅ `multi_agent/asynctask/__init__.py` - 新包初始化
- ✅ `multi_agent/asynctask/task_queue.py` - 任务队列模块
- ✅ `multi_agent/asynctask/http_server.py` - HTTP服务器模块

**修改文件**：
- ✅ `cli_agent.py` 第39-41行 - 更新导入路径

### 代码变更

**cli_agent.py**：
```python
# 修改前
def _async_module(name: str):
    """Import submodules under multi_agent.async (Py 3.14+ reserves ``async``)."""
    return importlib.import_module(f"multi_agent.async.{name}")

# 修改后
def _async_module(name: str):
    """Import submodules under multi_agent.asynctask (async is reserved in Py 3.14+)."""
    return importlib.import_module(f"multi_agent.asynctask.{name}")
```

## 数据流

```
cli_agent.py
    ↓
_async_module("task_queue")
    ↓
importlib.import_module("multi_agent.asynctask.task_queue")
    ↓
multi_agent/asynctask/task_queue.py ✅
```

## 兼容性

- ✅ Python 3.12 - 完全兼容
- ✅ Python 3.13 - 完全兼容
- ✅ Python 3.14+ - 完全兼容（避免了async关键字冲突）

## 功能验证

所有功能保持不变：
- ✅ `AsyncTaskQueue` - 异步任务队列
- ✅ `AsyncTaskRecord` - 任务记录
- ✅ `AsyncTaskStore` - 任务存储
- ✅ `TaskProgress` - 进度跟踪
- ✅ HTTP服务器 - 任务状态查询

## 总结

通过将包名从`async`改为`asynctask`，避免了Python保留关键字冲突，确保系统在Python 3.14+中也能正常运行。

**关键点**：
- ✅ 简单的包重命名
- ✅ 无功能改变
- ✅ 完全向后兼容
- ✅ 面向未来的Python版本
