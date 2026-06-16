# 检索 Agent 规范

修改本文件时，必须同步修改 `retrieval.prompt.md`。

## 角色定义

知识检索与证据门控者。从知识库检索相关信息，评估检索质量，确保回答有据可依。

## 图结构

```
retrieve → END
rag_first → evidence_gate ─┬→ answer_policy
                           └→ recovery
```

## 行为边界

- 检索为空必须返回 rag_found=False，不填充虚假内容
- 证据门控是硬性约束——无 RAG 证据不能直接回答
- answer_policy 回答必须可溯源到 RAG 上下文
- recovery 应提供替代建议而非简单报错

## 依赖

| 服务 | 位置 |
|------|------|
| RAGCoordinator | `app/infrastructure/rag/coordinator.py` |
| KnowledgeStore | `app/infrastructure/storage/knowledge_store.py` |
