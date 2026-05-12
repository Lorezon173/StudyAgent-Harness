# 追问节点规范

修改本文件时，必须同步修改 `followup.prompt.md`。

## 职责

针对理解薄弱点提出引导性问题，巩固学习。

## 读写契约

- 读取：`teaching.diagnosis`, `teaching.restatement_eval`
- 写入：`teaching.followup_question`

## 行为边界

- 只提开放式引导性问题，不问是非性问题
- 不超过 2 个问题
- 问题应针对复述检查中发现的薄弱点
