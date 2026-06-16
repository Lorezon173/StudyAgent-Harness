# 总结节点规范

修改本文件时，必须同步修改 `summarize.prompt.md`。

## 职责

汇总本次学习会话的整体结果，生成学习总结和复习建议。

## 读写契约

- 读取：`memory.topic`, `evaluation.mastery_level`, `evaluation.mastery_score`, `evaluation.mastery_rationale`
- 写入：`teaching.summary`, `meta.stage`(COMPLETE)

## 行为边界

- 总结必须包含：学习主题、掌握程度、建议下一步
- 复习建议应针对 mastery_level 给出差异化建议
