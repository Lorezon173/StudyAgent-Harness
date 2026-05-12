# 评估节点规范

修改本文件时，必须同步修改 `evaluate.prompt.md`。

## 职责

评估用户对知识的掌握程度，输出分数和等级。

## 读写契约

- 读取：`teaching.diagnosis`, `teaching.restatement_eval`
- 写入：`evaluation.mastery_score`, `evaluation.mastery_level`, `evaluation.mastery_rationale`, `meta.stage`

## 分级规则

- ≥ 80 → MASTERED
- ≥ 50 → PARTIAL
- < 50 → WEAK

## 行为边界

- 必须输出 0-100 数值分数
- level 由分数自动推导，不允许手动设置不一致的等级
- LLM 返回非 JSON 时按 mastery_score=50 / PARTIAL 处理
