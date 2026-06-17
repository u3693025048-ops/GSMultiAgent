# LLM 指标解析空内容修复

## 问题

LLM 在解析 MATLAB 仿真输出时返回了空内容：

```
2026-06-11 09:45:03 - multi_agent.rl.matlab_rl_optimizer - WARNING - [LLM metric parse] LLM returned empty content
2026-06-11 09:45:03 - multi_agent.rl.matlab_rl_optimizer - WARNING -   [RL DIAG] Parse produced ALL defaults from 1820 chars.
```

**症状**：
- MATLAB 仿真成功（stdout=1820 chars）
- LLM 调用成功
- 但 LLM 返回的内容为空
- 导致指标解析失败，使用默认值

---

## 根本原因

可能的原因：

1. **LLM API 返回 None**
   - 网络问题导致响应为空
   - API 限流或超时

2. **LLM 返回空字符串**
   - 模型无法理解输入
   - 输入格式不正确

3. **响应处理问题**
   - Markdown 标记处理不当
   - 字符串清理过度

---

## ✅ 已实施的改进

### 改进1：更详细的日志

```python
content = resp.choices[0].message.content
if not content:
    logger.warning("[LLM metric parse] LLM returned None content")
    return {}

content = content.strip()
logger.debug(f"[LLM metric parse] Raw response (first 200 chars): {content[:200]}")
```

**效果**：
- 区分 None 和空字符串
- 记录原始响应内容（前 200 字符）
- 便于调试

### 改进2：更好的错误处理

```python
except json.JSONDecodeError as exc:
    logger.warning(f"[LLM metric parse] JSON decode failed: {exc}")
    return {}
except Exception as exc:
    logger.warning(f"[LLM metric parse] failed: {exc}")
    return {}
```

**效果**：
- 区分 JSON 解析错误和其他错误
- 更清晰的错误信息

### 改进3：更清晰的中间步骤

```python
content = content.strip()
if not content:
    logger.warning("[LLM metric parse] LLM returned empty content after stripping")
    return {}
```

**效果**：
- 明确指出在哪个步骤内容变为空
- 便于定位问题

---

## 工作流

### 原来的流程

```
1. LLM 调用
2. 获取响应内容
3. 清理 Markdown 标记
4. 解析 JSON
5. 如果失败 → 返回空字典
```

### 改进后的流程

```
1. LLM 调用
2. 获取响应内容
   ├─ 如果为 None → 记录警告，返回空字典
   └─ 否则继续
3. 清理空白
   └─ 记录原始响应（前 200 字符）
4. 清理 Markdown 标记
5. 清理空白
   ├─ 如果为空 → 记录警告，返回空字典
   └─ 否则继续
6. 解析 JSON
   ├─ 如果失败 → 记录 JSON 错误，返回空字典
   └─ 否则继续
7. 返回解析结果
```

---

## 调试步骤

如果再次遇到 LLM 返回空内容的问题，可以：

1. **查看日志**
   ```
   [LLM metric parse] LLM returned None content
   → LLM API 返回 None
   
   [LLM metric parse] LLM returned empty content after stripping
   → LLM 返回空字符串
   
   [LLM metric parse] JSON decode failed: ...
   → LLM 返回非 JSON 内容
   
   [LLM metric parse] Raw response (first 200 chars): ...
   → 查看实际返回内容
   ```

2. **检查 LLM 配置**
   - API Key 是否正确
   - Base URL 是否正确
   - 模型名称是否正确

3. **检查网络**
   - 是否能连接到 LLM API
   - 是否有超时问题

4. **检查输入**
   - MATLAB stdout 是否有效
   - 是否包含可解析的指标

---

## 回退机制

当 LLM 解析失败时，系统会：

1. **使用正则表达式解析**
   - 尝试从 stdout 中提取指标
   - 如果成功 → 使用提取的值

2. **使用默认值**
   - 如果正则表达式也失败
   - 使用硬编码的默认值
   - 标记为 `_parse_incomplete=True`

3. **记录警告**
   ```
   [parse_sim_stdout] hit_rate/SEP at sentinel defaults (0% / 50m)
   with no MC evidence in stdout — metrics unreliable for RL
   ```

---

## 预期效果

| 场景 | 改进前 | 改进后 |
|------|--------|--------|
| **LLM 返回 None** | ❌ 无日志 | ✅ 明确日志 |
| **LLM 返回空字符串** | ❌ 无日志 | ✅ 明确日志 |
| **LLM 返回非 JSON** | ❌ 通用错误 | ✅ JSON 错误 |
| **调试困难** | ❌ 无法定位 | ✅ 清晰的中间步骤 |

---

## 总结

**问题**：
- LLM 返回空内容
- 导致指标解析失败
- 使用默认值，影响 RL 优化

**解决方案**：
- ✅ 更详细的日志
- ✅ 更好的错误处理
- ✅ 更清晰的中间步骤

**预期效果**：
- ✅ 更容易调试
- ✅ 更清晰的错误信息
- ✅ 更好的问题定位
