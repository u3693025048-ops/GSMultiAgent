# parameter_experience_best 工具参数错误诊断与修复

## 问题描述

运行系统时出现错误：

```
2026-06-09 23:21:39,252 - multi_agent.integration.hermes_integration - ERROR - Tool 'parameter_experience_best' arg error: ParameterExperienceBestTool.execute() missing 1 required positional argument: 'task_context'
```

## 根本原因

### 工具定义 vs LLM 调用的不匹配

**工具定义**（`parameter_experience_tool.py` 第196-201行）：

```python
async def execute(
    self,
    task_context: Dict[str, Any],  # ← 必需参数
    top_k: int = 5,
    param_ranges: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
```

**LLM 调用**：

```
Tool 1: parameter_experience_best(['top_k']) - {"top_k": 10}
                                    ↑
                                    只提供了 top_k
                                    没有提供 task_context
```

**问题**：
- `task_context` 被定义为必需参数
- 但 LLM 不知道应该提供什么值
- 导致工具调用失败

---

## 根本原因分析

### 为什么 LLM 不提供 task_context？

```
可能原因：

1. 工具定义不清楚
   - task_context 的描述不够具体
   - LLM 不知道应该从哪里获取

2. 工具设计不合理
   - task_context 应该是可选的
   - 或者应该从上下文自动推导

3. 工具注册不完整
   - task_context 没有被正确标记为必需
   - LLM 没有收到正确的参数要求
```

---

## 解决方案

### 方案1：使 task_context 可选（推荐）

**修改**：`parameter_experience_tool.py` 第196-201行

```python
async def execute(
    self,
    task_context: Optional[Dict[str, Any]] = None,  # ← 改为可选
    top_k: int = 5,
    param_ranges: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute ParameterExperience best retrieval with optional range filtering."""
    if not self.parameter_experience:
        return {"status": "error", "message": "ParameterExperience not initialized"}
    
    # 如果没有提供 task_context，使用空字典或默认值
    if task_context is None:
        task_context = {}
```

**修改**：`parameter_experience_tool.py` 第176行（input_schema）

```python
input_schema = {
    "type": "object",
    "properties": {
        "task_context": {"type": "object", "description": "Task context to match against"},
        "top_k": {
            "type": "integer",
            "description": "Number of best experiences to retrieve",
            "default": 5,
        },
        "param_ranges": {
            "type": "object",
            "description": "Optional parameter range constraints...",
        },
    },
    "required": [],  # ← 改为空列表，所有参数都是可选的
}
```

**理由**：
- LLM 可能无法提供 task_context
- 使其可选更灵活
- 可以使用默认值或从上下文推导

**效果**：
- ✅ 工具调用成功
- ✅ LLM 可以灵活使用
- ✅ 不破坏现有功能

---

### 方案2：从上下文自动推导 task_context

**修改**：`parameter_experience_tool.py` 第196-201行

```python
async def execute(
    self,
    task_context: Optional[Dict[str, Any]] = None,
    top_k: int = 5,
    param_ranges: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute ParameterExperience best retrieval with optional range filtering."""
    if not self.parameter_experience:
        return {"status": "error", "message": "ParameterExperience not initialized"}
    
    # 如果没有提供 task_context，尝试从工具的上下文推导
    if task_context is None:
        # 从最近的任务或工作流推导
        task_context = self._infer_task_context()
```

**新增方法**：

```python
def _infer_task_context(self) -> Dict[str, Any]:
    """Infer task context from current workflow or recent tasks."""
    # 可以从以下来源推导：
    # 1. 当前工作流的任务描述
    # 2. 最近的参数经验记录
    # 3. 用户输入的任务提示
    
    # 简单实现：返回空字典（表示"最通用的任务"）
    return {}
```

**理由**：
- 更智能的工具设计
- 不需要 LLM 显式提供参数
- 自动从上下文推导

**效果**：
- ✅ 工具更易用
- ✅ LLM 调用更简洁
- ✅ 用户体验更好

---

### 方案3：改进工具的 input_schema（最优）

**修改**：`parameter_experience_tool.py` 第157-177行

```python
input_schema = {
    "type": "object",
    "properties": {
        "task_context": {
            "type": "object",
            "description": (
                "Task context to match against experiences. "
                "Can include: mission_type, guidance_law, autopilot_params, etc. "
                "If not provided, retrieves best experiences across all tasks."
            ),
        },
        "top_k": {
            "type": "integer",
            "description": "Number of best experiences to retrieve (default: 5)",
            "default": 5,
        },
        "param_ranges": {
            "type": "object",
            "description": (
                "Optional parameter range constraints inferred from RAG knowledge. "
                "Format: {\"w1\": [min, max], \"zeta1\": [min, max], ...}. "
                "Only experiences whose parameters all fall within these ranges are returned. "
                "If no experience satisfies the ranges, falls back to unrestricted retrieval."
            ),
        },
    },
    "required": [],  # ← 所有参数都是可选的
}
```

**修改**：`parameter_experience_tool.py` 第196-201行

```python
async def execute(
    self,
    task_context: Optional[Dict[str, Any]] = None,
    top_k: int = 5,
    param_ranges: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute ParameterExperience best retrieval with optional range filtering."""
    if not self.parameter_experience:
        return {"status": "error", "message": "ParameterExperience not initialized"}
    
    # 使用提供的 task_context，或使用空字典作为默认值
    if task_context is None:
        task_context = {}
```

**理由**：
- 改进工具描述，让 LLM 更清楚
- 使所有参数都可选
- 提供合理的默认值

**效果**：
- ✅ 工具更易用
- ✅ LLM 理解更清楚
- ✅ 不破坏现有功能

---

## 实现建议

### 立即修复（5分钟）

实施方案3（最优）：

1. 修改 `input_schema`，将 `required` 改为 `[]`
2. 修改 `execute` 方法，使 `task_context` 可选
3. 添加默认值处理

### 代码修改

**修改1**：`parameter_experience_tool.py` 第176行

```python
"required": [],  # ← 改为空列表
```

**修改2**：`parameter_experience_tool.py` 第196-198行

```python
async def execute(
    self,
    task_context: Optional[Dict[str, Any]] = None,  # ← 改为可选
    top_k: int = 5,
    param_ranges: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
```

**修改3**：`parameter_experience_tool.py` 第203-204行

```python
if not self.parameter_experience:
    return {"status": "error", "message": "ParameterExperience not initialized"}

# 使用提供的 task_context，或使用空字典作为默认值
if task_context is None:
    task_context = {}
```

---

## 预期效果

| 方面 | 修复前 | 修复后 | 改进 |
|------|--------|--------|------|
| **工具调用成功率** | 0% | 100% | ✅ |
| **LLM 理解** | 困惑 | 清楚 | ✅ |
| **用户体验** | 失败 | 成功 | ✅ |

---

## 相关代码

| 文件 | 行号 | 说明 |
|------|------|------|
| `parameter_experience_tool.py` | 176 | input_schema required |
| `parameter_experience_tool.py` | 196-201 | execute 方法签名 |

---

## 总结

**问题**：
- `parameter_experience_best` 工具缺少必需参数 `task_context`
- LLM 不知道应该提供什么值

**原因**：
- 工具定义 `task_context` 为必需参数
- 但 LLM 无法自动推导

**解决方案**：
- ✅ 使 `task_context` 可选
- 改进工具描述
- 提供合理的默认值

**预期效果**：
- ✅ 工具调用成功
- ✅ LLM 可以灵活使用
- ✅ 优化流程继续进行

**立即实施**：
修改 `parameter_experience_tool.py` 的 `input_schema` 和 `execute` 方法
