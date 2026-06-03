# 证据门控节点规范

修改本文件时，必须同步修改 `evidence_gate.prompt.md`。

## 职责

评估检索结果是否有足够证据回答用户问题。

## 读写契约

- 读取：`retrieval.rag_context`, `retrieval.rag_found`
- 写入：`retrieval.gate_status`

## 门控规则

- rag_found=True 且上下文充分 → ACCEPT → answer_policy
- rag_found=False 或上下文不足 → REJECT → recovery

## 行为边界

- 硬性约束：无证据不通过，无论 LLM 多自信
