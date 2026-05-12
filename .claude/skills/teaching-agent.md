---
name: teaching-agent
description: 教学 Agent 行为规范 — 当处理 teach_loop 分支（诊断、讲解、复述、追问）时调用
---

# Teaching Agent 行为规范

## 角色定义

教学 Agent 负责引导用户理解知识点，采用苏格拉底式教学法：先诊断认知水平，再逐步讲解，通过复述检查验证理解，必要时追问深化。

## 图结构

```
diagnose → explain → restate_check ─┬→ followup → END
                                    ├→ explain (循环，最多3次)
                                    └→ summarize (理解通过)
```

## 节点职责

### diagnose（诊断）
- **读取**：`memory.topic`, `user_input`
- **写入**：`teaching.diagnosis`
- **行为**：分析用户对主题的当前理解程度，输出诊断描述
- **禁止**：不要直接给出答案，诊断目的是定位认知差距

### explain（讲解）
- **读取**：`teaching.diagnosis`, `retrieval.rag_context`
- **写入**：`teaching.explanation`, `teaching.explain_loop_count`
- **行为**：根据诊断结果和 RAG 上下文生成针对性讲解
- **循环控制**：`explain_loop_count` 每次 +1，达到 3 次必须退出循环

### restate_check（复述检查）
- **读取**：`teaching.explanation`
- **写入**：`teaching.restatement_eval`
- **行为**：评估用户的复述是否准确
- **路由关键词**：
  - "已理解"/"准确"/"完整" → summarize
  - "错误"/"混淆"/"误解" 且循环 < 3 → explain（重新讲解）
  - 其他 → followup（追问深化）

### followup（追问）
- **读取**：`teaching.diagnosis`, `teaching.restatement_eval`
- **写入**：`teaching.followup_question`
- **行为**：针对理解薄弱点提出引导性问题
- **禁止**：不要问是非性问题，应该是开放式的引导性提问

## 行为边界

- 讲解循环最多 **3 轮**，超过后强制进入 evaluate
- 如果 RAG 上下文为空（`retrieval.rag_context == ""`），讲解应提示知识库不足而非编造内容
- 复述检查必须给出明确判定（"已理解"/"错误"/"部分理解"），不能含糊
- 追问问题不超过 2 个，避免信息过载

## 依赖服务

| 服务 | 用途 | 位置 |
|------|------|------|
| LLMService | 生成诊断/讲解/复述评估 | `app/infrastructure/llm.py` |
| RAGCoordinator | 提供知识上下文 | `app/infrastructure/rag/coordinator.py` |
| MemoryManager | 读取历史学习记忆 | `app/harness/memory.py` |

## 错误恢复

- LLM 调用超时 → safe_node 捕获 → recovery 节点处理
- RAG 返回空结果 → 讲解中标注"知识库未覆盖此主题"
- 循环溢出（3轮后仍未理解）→ 强制进入 evaluate，mastery_level 设为 WEAK

## 测试场景

1. 完整教学循环：诊断→讲解→复述通过→追问→评估
2. 循环重试：复述失败→重新讲解→复述通过
3. 循环溢出：3轮复述失败→强制评估
4. 空知识库：RAG 无结果时的降级处理
