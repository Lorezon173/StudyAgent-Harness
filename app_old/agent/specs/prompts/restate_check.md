# 复述检查节点规范

修改本文件时，必须同步修改 `restate_check.prompt.md`。

## 职责

评估用户对讲解内容的理解程度，决定是否需要重新讲解或追问。

## 读写契约

- 读取：`teaching.explanation`, `user_input`
- 写入：`teaching.restatement_eval`

## 路由关键词

- "已理解"/"准确"/"完整" → summarize
- "错误"/"混淆"/"误解" 且循环 < 3 → explain
- 其他 → followup

## 行为边界

- 必须给出明确判定，不能含糊
- 区分"完全理解"、"部分理解"、"误解"三档
