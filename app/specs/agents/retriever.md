# Retriever 角色规范（开发者文档）

知识检索，只做机械层（向量检索 + 原始 score + retrieval_status），不自评语义质量。

- 运行时 Prompt：`retriever.prompt.md`（当前不调 LLM，仅留存）
- 设计来源：design doc §2.1（Retriever 行）、§3.6 证据评判流程
- 实现：`app/agents/retriever.py`
- 修改本文件时必须同步修改 `retriever.prompt.md`
