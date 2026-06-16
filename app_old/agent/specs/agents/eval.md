# 评估 Agent 规范

修改本文件时，必须同步修改 `eval.prompt.md`。

## 角色定义

双重评估者：用户掌握程度（mastery）和 RAG 检索质量（ragas）。

## 图结构

```
evaluate_mastery → evaluate_ragas → END
```

## 行为边界

- 掌握度评估必须给出 0-100 数值分数
- mastery_level 由分数自动推导：≥80 MASTERED, ≥50 PARTIAL, <50 WEAK
- 分数与等级不允许不一致
- ragas 为可选——retrieval 为空时三个指标返回 0.0
- 评估结果写入 meta.stage = EVALUATE

## 依赖

| 服务 | 位置 |
|------|------|
| LLMService | `app/infrastructure/llm.py` |
| EvalStore | `app/infrastructure/storage/eval_store.py` |
| ragas (可选) | 外部依赖 |
