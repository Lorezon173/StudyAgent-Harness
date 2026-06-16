# 诊断节点规范

修改本文件时，必须同步修改 `diagnose.prompt.md`。

## 职责

评估用户对主题的当前理解程度，定位认知差距。

## 读写契约

- 读取：`memory.topic`, `user_input`
- 写入：`teaching.diagnosis`

## 行为边界

- 只诊断，不讲解
- 定位"已理解"和"未理解"的边界
- 用户表述模糊时追问澄清而非猜测
