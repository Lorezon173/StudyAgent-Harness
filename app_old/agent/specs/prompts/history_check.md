# 历史检查节点规范

修改本文件时，必须同步修改 `history_check.prompt.md`。

## 职责

检查用户是否有学习历史记录，决定后续路径。

## 读写契约

- 读取：`memory.user_id`, `memory.topic`
- 写入：`memory.has_history`, `memory.history_summary`

## 行为边界

- 有历史：记录摘要，继续到 diagnose
- 无历史：标记 has_history=False，仍然继续到 diagnose（诊断时会从头开始）
