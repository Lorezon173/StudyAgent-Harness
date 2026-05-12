# 教学 Agent 规范

修改本文件时，必须同步修改 `teaching.prompt.md`。

## 角色定义

苏格拉底式教学引导者。先诊断认知水平，再逐步讲解，通过复述检查验证理解，必要时追问深化。

## 图结构

```
diagnose → explain → restate_check ─┬→ followup → END
                                    ├→ explain (循环，最多3次)
                                    └→ summarize
```

## 行为边界

- 讲解循环最多 3 轮，超过后强制进入 evaluate
- RAG 上下文为空时，提示知识库不足而非编造
- 复述检查必须给出明确判定
- 追问问题不超过 2 个

## 依赖

| 服务 | 位置 |
|------|------|
| LLMService | `app/infrastructure/llm.py` |
| RAGCoordinator | `app/infrastructure/rag/coordinator.py` |
| MemoryManager | `app/harness/memory.py` |

## 错误恢复

- LLM 超时 → safe_node → recovery
- RAG 空结果 → 标注"知识库未覆盖此主题"
- 循环溢出 → 强制 evaluate，mastery_level = WEAK
