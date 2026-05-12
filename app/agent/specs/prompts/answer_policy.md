# 回答策略节点规范

修改本文件时，必须同步修改 `answer_policy.prompt.md`。

## 职责

基于 RAG 证据生成回答。

## 读写契约

- 读取：`retrieval.rag_context`, `user_input`
- 写入：`teaching.reply`, `meta.stage`(EXPLAINING)

## 行为边界

- 仅基于 RAG 上下文回答
- 上下文不足时标注"部分信息"
- 回答需附引用来源
