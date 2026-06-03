# 意图路由节点规范

修改本文件时，必须同步修改 `route_intent.prompt.md`。

## 职责

分析用户输入，判断意图类型和置信度，决定路由方向。

## 读写契约

- 读取：`user_input`
- 写入：`routing.intent`, `routing.intent_confidence`, `routing.intent_source`

## 路由映射

| 意图 | 目标节点 |
|------|---------|
| teach_loop | history_check |
| qa_direct | rag_first |
| replan | replan |
| review | summarize |

## 行为边界

- 规则优先匹配，LLM 兜底
- 置信度 < 0.5 时默认 teach_loop
- intent_source 记录来源：rule 或 llm
