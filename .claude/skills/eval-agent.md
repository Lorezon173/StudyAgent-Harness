---
name: eval-agent
description: 评估 Agent 行为规范 — 当处理掌握度评估或 RAG 质量评估时调用
---

# Eval Agent 行为规范

## 角色定义

评估 Agent 负责双重评估：用户对知识的掌握程度（mastery）和 RAG 检索质量（ragas）。它是学习循环的收尾环节，决定是否需要重新学习。

## 图结构

```
evaluate_mastery → evaluate_ragas → END
```

## 节点职责

### evaluate_mastery（掌握度评估）
- **读取**：`teaching.diagnosis`, `teaching.restatement_eval`
- **写入**：`evaluation.mastery_score`, `evaluation.mastery_level`, `evaluation.mastery_rationale`
- **行为**：根据诊断和复述评估结果，输出 0-100 的掌握度分数
- **分级规则**：
  - ≥ 80 → `MasteryLevel.MASTERED`
  - ≥ 50 → `MasteryLevel.PARTIAL`
  - < 50 → `MasteryLevel.WEAK`
- **输出格式**：必须返回 JSON `{"mastery_score": int, "mastery_rationale": str}`

### evaluate_ragas（RAG 质量评估）
- **读取**：`retrieval.rag_context`, 上下文相关性数据
- **写入**：`evaluation.ragas_faithfulness`, `evaluation.ragas_relevancy`, `evaluation.ragas_context_precision`
- **行为**：评估 RAG 检索结果的质量（忠实度、相关性、上下文精度）
- **范围**：三个指标均为 0.0-1.0 的浮点数
- **注意**：当前为存根实现，实际评估需要 ragas 库

## 行为边界

- 掌握度评估必须给出明确的数值分数，不能仅给定性描述
- mastery_level 由分数自动推导，不允许手动设置与分数不一致的等级
- ragas 评估是可选的——如果 retrieval 为空，三个指标均返回 0.0
- 评估结果写入 `meta.stage = Stage.EVALUATE`

## 依赖服务

| 服务 | 用途 | 位置 |
|------|------|------|
| LLMService | 生成掌握度评估 JSON | `app/infrastructure/llm.py` |
| EvalStore | 持久化评估结果 | `app/infrastructure/storage/eval_store.py` |
| ragas (可选) | RAG 质量评估 | 外部依赖 |

## 错误恢复

- LLM 返回非 JSON → 按 mastery_score=50 / PARTIAL 处理
- ragas 库不可用 → 三个指标返回 0.0，不影响掌握度评估
- 分数超出范围 → 钳位到 [0, 100]

## 测试场景

1. 高掌握度：mastery_score=90 → MASTERED
2. 中等掌握度：mastery_score=60 → PARTIAL
3. 低掌握度：mastery_score=30 → WEAK
4. 边界值：mastery_score=80/50 恰好在分界线
5. LLM 返回异常：非 JSON 响应的降级处理
6. 空 RAG 上下文：ragas 指标全部为 0.0
