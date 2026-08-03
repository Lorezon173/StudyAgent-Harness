# RAG 三段式增强（Query / 召回 / 重排）现状盘点与改进建议

> 创建：2026-07-07
> 状态：⏳ 待详细讨论
> 来源：2026-07-07 会话讨论；所有结论基于源码亲验，引用均给 `file:line`

---

## 0. 术语对齐

用户所说的"三级增强"在项目里**没有这个命名**。经澄清，所指为 RAG 标准三段式优化范式：

| 块 | 又名 | 典型手段 |
|---|---|---|
| **Query 输入优化** | 查询侧增强 | query rewrite / query expansion / HyDE / multi-query / 分解 |
| **召回增强** | 检索侧增强 | 混合检索（BM25+vector）/ 多路召回 / KG 召回 / MMR |
| **重排增强** | 后处理增强 | cross-encoder rerank / LLM rerank / 压缩 / 低分过滤 |

本文档按这三块盘点当前实现，并给出改进建议优先级。

---

## 1. 当前 RAG 设计逻辑（运转链路）

### 1.1 事件驱动链路

```
USER_MESSAGE / TOPIC_ENTERED / ACTION_REQUESTED(TUTOR_ASK)   ← assembly 种子事件
        │
        v
   run_collab_loop（单线程优先级事件总线）
        │
   ┌────┴────────────────────────────────────────────────┐
   │  Tutor  ─订阅→ ACTION_REQUESTED(target=tutor)       │
   │  Critic ─订阅→ USER_MESSAGE / RETRIEVED_EVIDENCE    │
   │  Retriever ─订阅→ ACTION_REQUESTED(target=retriever)│
   │  Orchestrator ─钩子→ 观察类事件 + Tick 屏障          │
   └─────────────────────────────────────────────────────┘
        │
   观察类事件（MasteryAssessed / ConfusionDetected / RAGQualityAssessed ...）
        │
        v
   Orchestrator 收集观察集 → RuleEngine 匹配 → 产生新 ACTION_REQUESTED
```

### 1.2 检索链路（当被触发时）

```
Orchestrator 发 ACTION_REQUESTED(action=retriever_*, target=retriever)
   payload = {"action": ..., "target": "retriever"}   ⚠ 不含 query
        │
        v
RetrieverAgent.handle (app/agents/retriever.py:36)
   query = payload.get("query", "")                    ⚠ 取到空串
   top_k = payload.get("top_k", 5)
        │
        v
RAGCoordinator.search (app/infrastructure/rag/coordinator.py:100)
   遍历 providers（vector / ocr / code）→ 各自 search(top_k)
        │
        v
PgVectorProvider.search (app/infrastructure/rag/pgvector_provider.py:111)
   embed_one(query) → SELECT ... ORDER BY embedding <=> query LIMIT top_k
   score = 1/(1+distance)                              ⚠ 无 WHERE scope/user_id
        │
        v
Coordinator 聚合：content 去重（留高分）→ score 降序 → top_k
        │
        v
RetrieverAgent 判 retrieval_status（empty / low_score / ok）
   发 RETRIEVED_EVIDENCE（含 chunks / scores / status）
        │
        v
CriticAgent（仅 purpose=teaching）─订阅→ 评 RAG 质量 → 发 RAGQualityAssessed
        │
        v
Orchestrator 收集 → rag_quality_low?(score<0.5) → 规则触发 retriever_expand_query
        │
        ⚠ 闭环断路（见 P0-②）
```

### 1.3 组件职责（设计意图）

| 组件 | 位置 | 职责 |
|---|---|---|
| `RAGCoordinator` | `coordinator.py:46` | 多 Provider 聚合 + 去重 + 排序 |
| `IndexProvider`（协议） | `coordinator.py:24` | 检索后端抽象（vector/ocr/code） |
| `PgVectorProvider` | `pgvector_provider.py:22` | 真向量检索（pgvector 余弦） |
| `EmbeddingService` | `embedding.py:17` | 文本→向量（doubao-embedding-vision 2048 维） |
| `RetrieverAgent` | `retriever.py:24` | 机械层检索 + retrieval_status 判定 |
| `CriticAgent._assess_rag_quality` | `critic.py:82` | 语义层 RAG 质量评估 |
| `Orchestrator` | `orchestrator.py:63` | 观察集 → 规则匹配 → action 路由 |

---

## 2. 三块现状（逐块带证据）

### 2.1 Query 输入优化：零优化 + expand_query 断路

**有的（极微弱）：**
- `RetrieverAgent` 取 `payload.query` 原样透传，零改写（`retriever.py:44`）
- `ActionKind.RETRIEVER_EXPAND_QUERY` 枚举存在（`enums.py:148`）——名义上的"扩展"，**实际断路**

**没有的：** rewrite / expansion / HyDE / multi-query / 分解 / step-back——全部 grep 确认不存在。

**🔴 断点 `retriever_expand_query` 断路（待 P0-② 修复）：**
1. Orchestrator 发 `ACTION_REQUESTED` 时 payload 只有 `action` + `target`，**没有 query**（`orchestrator.py:149-154`）
2. RetrieverAgent 取到空 query（`retriever.py:44`）
3. RetrieverAgent 不区分 action 类型，`retriever_search` 与 `retriever_expand_query` 走同一路径（`retriever.py:41`）
4. 空 query 进 `PgVectorProvider.search` → `if not query: return []`（`pgvector_provider.py:121`）→ 空检索

### 2.2 召回增强：仅多源聚合架构

**有的：**
- 多源 Provider 聚合：vector/ocr/code 并行 → 去重 → 排序（`coordinator.py:100-131`）
- `top_k` 可配（默认 5）、`sources` 过滤（`coordinator.py:103`）
- score 校准：`1/(1+distance)` 落 (0,1]（`pgvector_provider.py:149`）
- pgvector `<=>` 余弦近邻（`pgvector_provider.py:137`）

**没有的：** BM25 混合 / LightRAG KG 召回（B-1 未实现）/ MMR / 两段式召回 / 查询-文档异编码器。

**🔴 缺口 `search` 无 scope/user_id 过滤（待 P0-③ 修复）：**
- `index` 写入 `user_id` / `scope` 字段（`pgvector_provider.py:91-97`）
- 但 `search` SQL 无 `WHERE`（`pgvector_provider.py:135-143`）→ **全局检索所有用户的 chunk**

**多源聚合的真实成色：** 仅 vector provider 在用；ocr（`ocr.py`）、code（`code_index.py`）无生产数据（摄入管线未接通）。

### 2.3 重排增强：仅去重 + score 排序

**有的（都不是真正 rerank）：**
- content 去重（留高分）：`coordinator.py:119-126`
- score 降序排序：`coordinator.py:126`
- `retrieval_status` 机械阈值（`LOW_SCORE_THRESHOLD=0.3`）：`retriever.py:21,79-85`——**只打标签，不删 chunk、不重排**
- `CriticAgent` 语义质量评估：`critic.py:82-99`——**只发评分事件，不重排 chunks**

**没有的：** cross-encoder / LLM rerank / MMR / 上下文压缩 / 低分过滤。

**🔴 断点 语义评分→重检索闭环未闭合：** Critic 评分 → 规则触发 `retriever_expand_query`（`orchestrator_rules.yaml:50-54`）→ **断路见 P0-②**。`pyproject.toml` 声明的 `llama-index-postprocessor-sbert-rerank` 可选依赖**零调用**。

---

## 3. 三个 P0 断点（亲验，比三块优化更优先）

### P0-① 检索结果未进 Tutor prompt（且新栈默认不触发检索）

**证据：**
- `TutorAgent.subscriptions = [ACTION_REQUESTED]`（`tutor.py:19`）——**不订阅 `RETRIEVED_EVIDENCE`**
- `_ask` / `_explain` 调 LLM 时**只传 `ws.current_topic`**（`tutor.py:74-97`），无任何检索上下文字段
- 种子事件是 `ACTION_REQUESTED(TUTOR_ASK)`（`assembly.py:150-153`），**不含 `retriever_search`**——首轮必定走 Tutor
- `WorkspaceState.evidence_pool` 字段存在（`workspace_state.py:20`），但注释明说"Agent 不直接写"（`workspace_state.py:10-11`），**永为空**

**含义：** 检索优化做得再好，结果既不被 Tutor 消费、检索本身默认也不被调用——**当前新栈 RAG 链路实际是失效的**。这不是优化问题，是接线缺口。

**修复方向（三选一或组合）：**
- (a) Tutor 增订 `RETRIEVED_EVIDENCE`，从 payload 取 chunks 拼进 system_prompt
- (b) Orchestrator 在发 `TUTOR_EXPLAIN` 等 action 前，先发 `retriever_search`，把证据塞进 ACTION_REQUESTED payload
- (c) 让协作环把检索证据写进 `ws.evidence_pool`，Tutor 读取

### P0-② `retriever_expand_query` 闭环断路

**证据：** 见 §2.1 断点段。修复方向：Orchestrator 发 `ACTION_REQUESTED` 时填 `query` 字段（从 `ws.current_topic` 或上轮用户回答提取）；RetrieverAgent 按 action 区分处理。

### P0-③ `search` 加 scope/user_id 过滤

**证据：** 见 §2.2 缺口段。修复方向：`search` 方法签名加 `user_id` / `scope` 参数，SQL 加 `WHERE`。

---

## 4. 三块改进建议（锚定教学场景）

### 4.1 教学场景特性（建议的判据基底）

| 特性 | 对三块的含义 |
|---|---|
| 回合制（非一次性问答） | 单轮不需海量召回+精排，精准够用即可 |
| 主题驱动（query 多是主题词） | query 优化重心在"塞对 query"，不在"改写长查询" |
| 教学容错低（教错比没教糟） | 质量门禁 > 精排 |
| 概念脉络是核心 | KG 召回真匹配痛点（B-1 非为上而上） |
| 用户隔离刚需 | scope 过滤是底线，不是优化 |
| 素材给 LLM 非给人 | LLM 能容忍噪声，精排边际收益 < 门禁+闭环 |

**核心判断：教学场景下，"修断点"ROI 远高于"加增强"。**

### 4.2 Query 输入优化建议

| 建议 | 性质 | 判据 |
|---|---|---|
| ✅ 教学阶段感知的 query 构造 | 加小增强 | 不同 action 配不同 query 模板（`regress_to_prereq`→前置概念；`tutor_correct`→易混淆点） |
| ✅ 从教学状态正确提取 query | 修断点（P0-② 延伸） | query 来源规范化 |
| ❌ HyDE | 不建议 | 短主题词被长假设文档稀释信号；多一次 LLM 调用 |
| ❌ Multi-query | 不建议 | 回合制单轮不需海量召回 |
| ❌ Step-back | 不建议 | 前置关系归 Curator 图谱 + B-1 KG，不塞 query 层 |

### 4.3 召回增强建议

| 建议 | 性质 | 判据 |
|---|---|---|
| ✅ LightRAG dual retrieval（B-1） | 大增强（已规划） | 教学核心痛点=概念脉络，local 检索对症 |
| ✅ scope/user_id 过滤 | 修断点（P0-③） | 用户隔离底线 |
| ⚠️ BM25 混合 | 看数据量 | 术语/公式多则值得；数据量小则纯向量够 |
| ❌ 两段式召回 | 不建议 | 数据量级小，过度工程 |
| ❌ MMR 多样性 | 不建议 | 教学要聚焦不要多样 |

### 4.4 重排增强建议

| 建议 | 性质 | 判据 |
|---|---|---|
| ✅ 低分门禁 | 加小增强 | `low_score` 时不送 Tutor，改为坦白无把握——教错比没教糟 |
| ✅ 闭合 Critic→重检索闭环 | 修断点（P0-②） | 复用已有 Critic 评估，比外部 reranker 便宜 |
| ❌ Cross-encoder rerank | 不建议 | 部署额外模型；素材给 LLM 容忍噪声；除非实测 top-5 常夹不相关 |
| ❌ 上下文压缩 | 不建议 | 教学 chunk 本就短，收益小 |

---

## 5. 优先级总表

| 优先级 | 事项 | 块 | 性质 | 工作量 |
|---|---|---|---|---|
| **P0** | Tutor 吃检索结果（含触发检索） | 跨 | 修断点 | 小～中 |
| **P0** | 修 `retriever_expand_query` 闭环 | Query | 修断点 | 小 |
| **P0** | `search` 加 scope/user_id 过滤 | 召回 | 修断点 | 小 |
| **P1** | 低分门禁 | 重排 | 加小增强 | 小 |
| **P1** | 教学阶段感知 query 构造 | Query | 加小增强 | 小 |
| **P2** | B-1 KG 召回（local/global/hybrid） | 召回 | 大增强（已规划） | 大 |
| **P3** | BM25 混合检索 | 召回 | 看数据量 | 中 |

---

## 6. 与现有 B-1/B-2/B-3 计划的对齐

| 建议 | 是否已被计划覆盖 |
|---|---|
| KG 召回 | ✅ B-1 已规划 |
| 掌握度驱动复习检索 | ✅ B-2 已规划 |
| PDF 版面解析提升 chunk 质量 | ✅ B-3 已规划 |
| **P0-①②③ 三个断点** | ❌ **三个计划都没明确覆盖——计划盲区** |
| 教学阶段感知 query | ❌ 计划没有（P0-② 延伸） |
| 低分门禁 | ❌ 计划没有（教学特有） |
| BM25 混合 | ⚠️ B-1 hybrid 是 local+global+vector，**不含 BM25** |

---

## 7. 待讨论问题（open questions）

1. **P0-① 三条修复路径（a/b/c）选哪条？**——影响后续所有 RAG 改动的接入点。
2. **新栈是否应在种子事件里就发 `retriever_search`？**——当前首轮直接 Tutor 提问，是否需要"先检索再教学"的默认流程？
3. **BM25 是否值得引入？**——需先评估单用户平均文档量。
4. **低分门禁的 fallback 形态？**——Tutor 坦白无把握？降级到 Conductor？跳过该主题？
5. **B-1 的 hybrid 融合权重（local 0.5 / global 0.3 / vector 0.2）是否要为教学场景调参？**
6. **`retrieval_status` 当前是死字段（下游不用），是否应在 P0-① 修复时一并接入门禁逻辑？**

---

## 附录 A. 关键证据索引（file:line）

| 事实 | 位置 |
|---|---|
| Tutor 不订阅检索事件 | `app/agents/tutor.py:19` |
| Tutor 调 LLM 只用 current_topic | `app/agents/tutor.py:74-97` |
| Retriever 取 query 不改写 | `app/agents/retriever.py:44` |
| Retriever 不分 action 类型 | `app/agents/retriever.py:41` |
| LOW_SCORE_THRESHOLD=0.3 | `app/agents/retriever.py:21` |
| retrieval_status 机械判定 | `app/agents/retriever.py:79-85` |
| 多源聚合 + 去重 + 排序 | `app/infrastructure/rag/coordinator.py:100-131` |
| 旧接口 retrieve() 拼 context | `app/infrastructure/rag/coordinator.py:141-175` |
| search 无 WHERE | `app/infrastructure/rag/pgvector_provider.py:135-143` |
| score 校准 1/(1+d) | `app/infrastructure/rag/pgvector_provider.py:149` |
| 空 query 返回空 | `app/infrastructure/rag/pgvector_provider.py:121` |
| index 写 user_id/scope | `app/infrastructure/rag/pgvector_provider.py:91-97` |
| ACTION_REQUESTED 不带 query | `app/harness/orchestrator.py:149-154` |
| rag_quality_low 判定 | `app/harness/orchestrator.py:179` |
| retriever_expand_query 规则 | `app/orchestration/orchestrator_rules.yaml:50-54` |
| Critic 评 RAG 质量 | `app/agents/critic.py:82-99` |
| 种子事件 TUTOR_ASK（无 retriever_search） | `app/orchestration/assembly.py:144-154` |
| evidence_pool 永空 | `app/harness/workspace_state.py:10-11,20` |
