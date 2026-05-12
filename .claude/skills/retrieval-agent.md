---
name: retrieval-agent
description: 检索 Agent 行为规范 — 当处理 QA_DIRECT 分支或知识检索时调用
---

# Retrieval Agent 行为规范

## 角色定义

检索 Agent 负责从知识库中检索与用户问题相关的信息，并评估检索结果的质量。它是 QA_DIRECT 分支的核心，也为 teach_loop 分支提供知识上下文。

## 图结构

```
retrieve → END
```

## 节点职责

### retrieve / knowledge_retrieval（知识检索）
- **读取**：`memory.topic`, `user_input`
- **写入**：`retrieval.rag_context`, `retrieval.rag_found`
- **行为**：根据用户输入检索相关知识，返回文本片段
- **输出**：
  - `rag_found=True`：检索到相关内容，`rag_context` 为非空文本
  - `rag_found=False`：未检索到内容，`rag_context` 为空字符串

### rag_first（RAG 优先检索）
- **读取**：`user_input`
- **写入**：`retrieval.rag_context`, `retrieval.rag_found`
- **行为**：QA_DIRECT 分支的入口，直接以用户问题为查询检索
- **注意**：与 knowledge_retrieval 逻辑相同，但在 QA_DIRECT 分支中使用

### evidence_gate（证据门控）
- **读取**：`retrieval.rag_context`, `retrieval.rag_found`
- **写入**：`retrieval.gate_status`
- **行为**：评估检索结果是否有足够证据回答用户问题
- **门控规则**：
  - `rag_found=True` 且上下文充分 → `GateStatus.ACCEPT` → 进入 answer_policy
  - `rag_found=False` 或上下文不足 → `GateStatus.REJECT` → 进入 recovery
- **禁止**：不要在证据不足时强行通过门控

### answer_policy（回答策略）
- **读取**：`retrieval.rag_context`, `user_input`
- **写入**：`retrieval.answer`
- **行为**：基于检索到的证据生成回答
- **原则**：
  - 仅基于 RAG 上下文回答，不编造信息
  - 上下文不足以完整回答时，明确标注"部分信息"
  - 回答需附引用来源（如果有）

## 行为边界

- 检索结果为空时，必须诚实返回 `rag_found=False`，不能填充虚假内容
- 证据门控是硬性约束——无论 LLM 多么自信，没有 RAG 证据就不能直接回答
- answer_policy 的回答必须可溯源到 RAG 上下文中的具体段落
- recovery 节点应提供替代建议（如推荐相关主题），而非简单报错

## 依赖服务

| 服务 | 用途 | 位置 |
|------|------|------|
| RAGCoordinator | 知识检索 | `app/infrastructure/rag/coordinator.py` |
| FakeRAGStore | 测试用模拟存储 | `app/infrastructure/rag/store.py` |
| KnowledgeStore | 知识库 CRUD | `app/infrastructure/storage/knowledge_store.py` |

## 错误恢复

- RAG 服务不可用 → `rag_found=False`, `gate_status=REJECT` → recovery
- 检索超时 → safe_node 捕获 → recovery
- 向量存储连接失败 → 同上

## 测试场景

1. 成功检索：输入有匹配知识 → rag_found=True → 门控通过 → 生成回答
2. 检索无结果：输入无匹配知识 → rag_found=False → 门控拒绝 → recovery
3. 部分匹配：检索到但不充分 → 门控需判断
4. QA_DIRECT 完整流程：rag_first → evidence_gate → answer_policy → evaluate
5. 门控拒绝流程：rag_first → evidence_gate(REJECT) → recovery → answer_policy
