# Hermes Memory Tool 参数兼容性修复

## 问题

Hermes LLM 在调用 `agent_memory_recall` 工具时，使用了 `memory_id` 参数，但工具定义的参数是 `key`。

```
错误信息：
TypeError: AgentMemoryRecallTool.execute() got an unexpected keyword argument 'memory_id'
```

---

## 根本原因

不同的 LLM 模型可能生成不同的参数名：
- 某些模型使用 `key`
- 某些模型使用 `memory_id`
- 某些模型使用其他名称

工具只接受 `key` 参数，导致参数不匹配。

---

## 解决方案

### ✅ 已实施：参数兼容性

**修改**：`multi_agent/tools/memory_tools.py` 第94-109行

```python
async def execute(self, key: str = None, memory_id: str = None) -> str:
    # Accept both 'key' and 'memory_id' for compatibility with different LLM outputs
    recall_key = key or memory_id
    if not recall_key:
        return json.dumps({"status": "error", "message": "Either 'key' or 'memory_id' parameter is required"})
    
    if self._memory is None:
        logger.warning("[agent_memory_recall] Memory not initialized — skip.")
        return json.dumps({"status": "skipped", "value": None,
                           "message": "Memory not available in this session. Proceed without this memory."})
    try:
        result = self._memory.recall(recall_key)
        return json.dumps({"status": "success", "message": result})
    except Exception as exc:
        logger.error(f"[agent_memory_recall] {exc}")
        return json.dumps({"status": "error", "message": str(exc)})
```

### 更新 input_schema

```python
input_schema: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "key": {
            "type": "string",
            "description": "The key used when the memory was saved.",
        },
        "memory_id": {
            "type": "string",
            "description": "Alternative parameter name for the key (for compatibility).",
        },
    },
    "required": [],  # At least one of key or memory_id must be provided
}
```

---

## 工作原理

### 参数优先级

```python
recall_key = key or memory_id
```

**优先级**：
1. 如果提供了 `key`，使用 `key`
2. 否则，如果提供了 `memory_id`，使用 `memory_id`
3. 如果都没有提供，返回错误

### 兼容性

```
Hermes 调用方式1：
  agent_memory_recall(key='T4_MODIFY_LAW_result_20260611')
  ✅ 正常工作

Hermes 调用方式2：
  agent_memory_recall(memory_id='T4_MODIFY_LAW_result_20260611')
  ✅ 正常工作（修复后）

Hermes 调用方式3：
  agent_memory_recall()
  ❌ 返回错误信息
```

---

## 预期效果

| 场景 | 修复前 | 修复后 |
|------|--------|--------|
| **使用 `key` 参数** | ✅ 工作 | ✅ 工作 |
| **使用 `memory_id` 参数** | ❌ 错误 | ✅ 工作 |
| **两个参数都提供** | ❌ 错误 | ✅ 使用 `key` |
| **都不提供** | ❌ 错误 | ❌ 返回错误信息 |

---

## 类似的工具修复

如果其他工具也有类似的参数兼容性问题，可以应用相同的模式：

```python
async def execute(self, param1: str = None, param2: str = None, param3: str = None) -> str:
    # Accept multiple parameter names for compatibility
    value = param1 or param2 or param3
    if not value:
        return json.dumps({"status": "error", "message": "At least one parameter is required"})
    # ... rest of implementation
```

---

## 总结

**问题**：
- Hermes LLM 使用 `memory_id` 参数
- 工具只接受 `key` 参数
- 导致参数不匹配错误

**解决方案**：
- ✅ 接受两个参数名：`key` 和 `memory_id`
- ✅ 优先使用 `key`，回退到 `memory_id`
- ✅ 更新 `input_schema` 反映两个选项

**预期效果**：
- ✅ 兼容不同 LLM 的参数命名
- ✅ 提高工具的鲁棒性
- ✅ 避免参数不匹配错误
