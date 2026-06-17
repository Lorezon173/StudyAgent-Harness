# StudyAgent 检索+记忆系统升级 · 现状 vs 开源方案 对比决策报告

> 报告日期：2026-06-16
> 前置文档：[`2026-06-15-rag-memory-frameworks-survey.md`](./2026-06-15-rag-memory-frameworks-survey.md)（7 个开源方案的设计 + 实时 star）
> 目的：把**当前 StudyAgent 的检索/记忆设计**与 7 个开源方案**逐维度对比**，供你决策升级路线。
> 你的场景已对齐：知识源四类全有（教材 PDF / 笔记 Markdown / 网页混合 / 题库问答）；记忆要**知识内容 + 学习者掌握轨迹两者都要**；存储后端待定；路线待对比后定。

---

## 一、当前设计现状（每条断言可溯源到 `file:line`）

> 方法论遵循：本节所有结论都来自实读源码，不臆测。读过的关键文件见末尾「已读源码清单」。

### 1.1 检索侧（RAG）

```
RetrieverAgent (机械层)  →  RAGCoordinator (多源聚合)  →  IndexProvider 协议
  retriever.py:54           coordinator.py:46              coordinator.py:24
                                    │
                ┌───────────────────┼───────────────────┐
          VectorProvider        OCRProvider          CodeIndexProvider
          coordinator.py:58     ocr.py:11            code_index.py:15
                │                   │                     │
          FakeRAGStore / RAGStore（store.py）——★ 底座是假的 ★
```

| 环节 | 现状 | 依据 |
|---|---|---|
| 检索协调 | `RAGCoordinator.search()` 聚合所有 provider → 按 content 去重（留高分）→ score 降序 → top_k | `coordinator.py:92-123` |
| 机械判定 | RetrieverAgent 只给 `retrieval_status` = empty / low_score(<0.3) / ok + 原始 score，**不自评语义质量**（语义归 Critic） | `retriever.py:79-85` |
| **向量底座** | `FakeRAGStore.query` = **字符级子串计数**（`sum(1 for w in query if w in content)`），不是向量检索 | `store.py:10-17` |
| **生产底座** | `RAGStore.query` = **空壳，直接 `return []`** | `store.py:34-36` |
| OCR 切块 | `OCRProvider` 用 pytesseract，按双换行分段 | `ocr.py:44-55` |
| 代码切块 | `CodeIndexProvider` 用 Python `ast`，按函数/类粒度 | `code_index.py:31-47` |
| **依赖** | pyproject **已装** llama-index、chromadb、llama-index-embeddings-openai、pgvector、sbert-rerank、ragas | `pyproject.toml` |

**一句话**：检索的**接口骨架完整、向量库依赖已就位，但 vector provider 没接线**——`RAGStore` 还是空壳。当前能跑通流程，但召回靠字符匹配，**没有真正的语义检索**。

### 1.2 记忆侧

当前记忆**不是一个统一系统，而是分裂的两半**：

**(A) 学习者状态侧 —— 成熟。** `MasteryGraph`（知识点掌握度图谱）

| 能力 | 现状 | 依据 |
|---|---|---|
| 节点 | mastery(0-100) / last_practiced_at / practice_count / confusion_with / rationale | `mastery_graph.py:22-31` |
| 边 | PREREQ / RELATED / CONFLICT + weight + **confidence** + source | `mastery_graph.py:34-42` |
| 边的置信度演化 | DOC_ORDER=0.5 → LLM_INFER=0.3 → 交互验证 INTERACTION=0.8 | `mastery_graph.py:97-125` |
| 前置薄弱检测 | `find_weak_prereqs`：低置信边阈值更严（adjusted threshold） | `mastery_graph.py:129-156` |
| 自动维护 | `Curator` Agent 订阅 MasteryAssessed/TopicEntered，自动更新图谱+画像、检测前置薄弱 | `curator.py:46-136` |
| L3 画像 | user_profile_l3：preferences/topics_active/topics_mastered/learning_streak/total_sessions | `mastery_graph_store.py:47-54` |
| 持久化 | 双轨：aiosqlite（`mastery_graph_store.py`）+ SQLAlchemy 表（`tables.py:58-82`），正在向 SQLAlchemy 统一 | git log: sqlalchemy_mastery_store |

**(B) 知识内容侧 —— 几乎空白。**

| 能力 | 现状 | 依据 |
|---|---|---|
| 知识库存储 | `KnowledgeStore` = **内存 dict 假实现**，无持久化、无检索 | `knowledge_store.py:1-24` |
| 知识表 | `KnowledgeTable`（scope/user_id/content/source/doc_ids）有定义，**但 store 没接它** | `tables.py:34-42` |
| 语义记忆 | **无**。没有"把学过的知识内容沉淀成可语义检索的长期记忆"这一层 | — |

> **关键区分**：`MasteryGraph` 节点是「知识点**掌握度**」（学习者状态），不是「知识**内容**本身」。
> 你要"两者都要" → **学习者状态侧已经有了**（且比一般框架还细），**真正缺的是知识内容侧**的语义沉淀与检索。

### 1.3 双栈并存（影响升级落点）

`chat.py:12` / `chat_stream.py:14` 仍 `from app_old.agent.graph import build_learning_graph`，由 `feature_flags` 灰度控制走新栈（`app/`，事件驱动 5 Agent）还是老栈（`app_old/`，LangGraph）。`app_old` 里有一套更完整的 `MemoryStore`（SQLite+FTS5 trigram+summaries+profiles，`app_old/.../memory_store.py`），但那是**老栈遗产，新栈不用**。

> **升级只针对新栈 `app/`**。老栈的 FTS5 记忆是历史包袱，不是可复用资产。

---

## 二、本次涉及的资产清单 + 三色血缘

| 名字 | 归属子系统 | 功能（干嘛） | 位置 | 三色 |
|---|---|---|---|---|
| RAGCoordinator | 检索 | 多源 Provider 聚合/去重/排序 | `app/infrastructure/rag/coordinator.py` | 🟡 改（接线真向量） |
| FakeRAGStore / RAGStore | 检索 | 向量存储底座（当前假/空壳） | `app/infrastructure/rag/store.py` | 🟡 改（接 chroma/llama-index） |
| OCRProvider / CodeIndexProvider | 检索 | OCR/代码切块索引 | `app/infrastructure/rag/{ocr,code_index}.py` | 🟢 保持（已可用） |
| RetrieverAgent | 检索 | 机械层检索 Agent | `app/agents/retriever.py` | 🟢 保持（接口不变） |
| MasteryGraph | 记忆 | 知识点掌握度图谱 | `app/harness/mastery_graph.py` | 🟢 保持/🟡 增强（可加时序） |
| Curator | 记忆 | 自动维护图谱+画像 | `app/agents/curator.py` | 🟢 保持 |
| KnowledgeStore | 记忆 | 知识库（当前假实现） | `app/infrastructure/storage/knowledge_store.py` | 🔴 重写（接知识内容记忆） |
| 知识内容记忆层 | 记忆 | 语义沉淀+检索（**全新**） | 待定 | 🔴 新建 |

> 🟢 保持现状 · 🟡 改动既有 · 🔴 新建/重写。
> 影响半径一眼可见：**检索是"接线"（改）、知识内容记忆是"新建"、学习者状态记忆基本"保持"**。

---

## 三、逐维度对比：当前设计 vs 7 方案

> 每个维度先给「你现在缺什么」，再给「哪个方案怎么解、代价是什么」。

### 维度 1：知识摄入与切块（对应你的四类知识源）

| 知识源 | 当前能力 | 最契合的方案 | 代价 |
|---|---|---|---|
| 教材 PDF（版面复杂） | ❌ 无 PDF 解析 | **ragflow** DeepDoc 版面级解析 / LightRAG 已并入 MinerU·Docling | ragflow 重（整套平台）；LightRAG 的解析较轻 |
| 笔记 Markdown | ⚠️ 仅字符匹配 | 任意向量 RAG（mem0/LightRAG/llama_index） | 低，装 embedding 即可 |
| 网页/混合 | ❌ 无摄入管线 | cognee 的 ECL 管线 / llama_index 的 reader 生态 | 中 |
| 题库问答对 | ❌ 无 | 直接条目级索引（任意向量库即可，不需要重型框架） | 低 |

**结论**：四类源里，**只有"教材 PDF 版面解析"需要重型能力**（ragflow / LightRAG-MinerU），其余三类装好 embedding + 基础切块就能覆盖。

### 维度 2：检索机制

| | 当前 | 纯向量（mem0/llama_index） | 图谱（LightRAG/graphrag/graphiti） |
|---|---|---|---|
| 召回方式 | 字符子串计数 | 语义向量（+可选 BM25/实体） | 双层：实体邻居 + 全局关系 |
| 概括性问题（"串一下这章脉络"） | ❌ 做不到 | ⚠️ 弱（只按 chunk 相似） | ✅ 强（global 模式/社区摘要） |
| 接入代价 | — | 低（依赖已装） | 中（要建图，LLM 抽取成本） |

**结论**：你的"知识高度集中"诉求 → 图谱检索价值大；但**图谱不必从零造**，因为你已有 `MasteryGraph` 的图基因（见维度 4）。

### 维度 3：知识内容记忆（语义沉淀）—— 你当前最大的空白

| 方案 | 怎么解 | 对你的适配 |
|---|---|---|
| **mem0** | ADD-only 抽取事实 + 多信号检索 + 时间推理 | 嵌入式库，侵入小；但它偏"对话事实"，对"教材知识"要自己喂 |
| **LightRAG** | 文档→实体关系图+向量双层 | 知识内容直接成图，契合"知识集中" |
| **cognee** | ECL：任意数据→知识图谱，session/永久双层 | 双层记忆现成，但较年轻 |

### 维度 4：学习者状态记忆（掌握轨迹/画像）—— 你当前最强的部分

> ⭐ **核心发现**：这一维度你**已经领先于大多数通用框架**。`MasteryGraph` 的 mastery+confidence+前置薄弱检测，是教育场景的专用设计，mem0/letta 的通用记忆反而没有。

| 方案 | 能补什么 | 是否需要 |
|---|---|---|
| **graphiti** | "事实带有效时间窗 + episode 溯源" | 💡 **借鉴其设计**到 MasteryGraph（让掌握度带时间版本、可回溯到哪次交互），**不必引入依赖** |
| mem0 时间推理 | 区分"当前/过去/未来"状态 | 💡 借鉴：复习节奏判断 |
| letta self-editing | agent 自主改写记忆块 | ⚠️ 你的 Curator 已经在做类似的事，letta 整套运行时耦合太重，不划算 |

### 维度 5：长期记忆的更新 / 淘汰 / 时间感知

| | 当前 | 方案参考 |
|---|---|---|
| 掌握度更新 | ✅ Curator 自动更新（observed/historical 双时机） | — |
| 知识内容更新 | ❌ 无 | LightRAG/graphiti 的**增量更新**（无需全量重算） |
| 记忆淘汰 | ❌ 无（mastery 只增不淘） | mem0 ADD-only（也不淘，需自己设计聚合） |
| 时间感知复习 | ⚠️ 有 last_practiced_at 字段但未用于检索 | mem0 时间推理 / graphiti 时间窗 |

### 维度 6：存储后端

| 方案要求 | 与你现状的契合 |
|---|---|
| 纯向量库（chroma/qdrant） | ✅ chromadb 已装；pgvector 已装（可走 PG 统一） |
| 图数据库（Neo4j） | ⚠️ 需新增依赖。graphrag/graphiti 原生偏好，但 LightRAG 支持 PG/Mongo 等，**可不引 Neo4j** |
| 你的现状 | aiosqlite + SQLAlchemy（study_agent.db），正在统一到 SQLAlchemy |

**结论**：**不引入 Neo4j 也能走通**——LightRAG 支持 PostgreSQL 存图，chroma 存向量，与你已装依赖一致。Neo4j 只在"想要重图遍历查询"时才需要。

### 维度 7：与现有架构（四层 + 事件驱动）的耦合代价

> 你的架构约束（`.claude/rules/agent-root.md`）：四层单向依赖（API→Orchestration→Harness→Infrastructure）、薄壳节点、事件驱动。

| 引入方式 | 耦合代价 | 说明 |
|---|---|---|
| **借鉴设计、自研嫁接** | 最低 | 检索接 chroma 进 `infrastructure/rag`，记忆增强 `harness/mastery_graph`，**完全贴合四层** |
| **mem0/LightRAG 作为库** | 中 | 作为 infrastructure 的一个 provider 引入，需适配它的数据模型；可控 |
| **letta/ragflow 作为平台** | 高 | 它们是"运行时/平台"，会和你的事件驱动 harness 抢主导权，违背"薄壳节点"约束 |

---

## 四、针对你场景的三条候选路线（摆判据，不替你拍板）

### 路线 A：最小接线（先把假底座变真）

把 `RAGStore` 接到已装的 chroma + llama-index embedding，知识内容记忆用向量库，`MasteryGraph` 保持不动。

| | 选它 | 不选的代价 |
|---|---|---|
| 工作量 | 最小（依赖已装，只接线） | — |
| 覆盖你的需求 | ✅ 真语义检索 ✅ 知识内容记忆 ⚠️ 无图谱概括检索 | 缺"知识集中/脉络串联" |
| 风险 | 极低 | — |

### 路线 B：向量 + 知识内容图谱（借鉴 LightRAG）

路线 A 之上，把知识内容也建成**实体关系图**（借鉴 LightRAG 双层检索），用 PG 存图（不引 Neo4j）。

| | 选它 | 不选的代价 |
|---|---|---|
| 工作量 | 中（要建图抽取管线） | — |
| 覆盖你的需求 | ✅ 全覆盖：语义检索 + 知识集中 + 脉络概括 | — |
| 风险 | 中（图抽取要调 prompt、有 LLM 成本） | — |

### 路线 C：双图谱统一（知识内容图谱 + 掌握度图谱打通）

路线 B 之上，把"知识内容图谱"与现有"掌握度图谱"**连起来**——知识点节点既挂内容（供检索）又挂掌握度（供教学决策），并借鉴 graphiti 给掌握度加时间版本。

| | 选它 | 不选的代价 |
|---|---|---|
| 工作量 | 大（两图谱对齐、时序改造） | — |
| 覆盖你的需求 | ✅✅ 最契合"学习辅助+长期回顾+知识集中"，检索与教学共用一张图 | — |
| 风险 | 较高（设计复杂，需充分规划） | 过度设计风险 |

**三条路线是递进的**：A 是 B 的前提，B 是 C 的前提。可以**分阶段走**，先 A 落地、再决定是否进 B/C。

---

## 五、待你决策的关键岔路

1. **先解决"假底座"还是直接上图谱？**（路线 A 起步，还是直奔 B）
   - 倾向建议：**先 A**（依赖已装，1 步把检索变真），再基于效果决定要不要 B。
2. **知识内容侧用"纯向量"还是"图谱"？**
   - 纯文本笔记/题库 → 向量够；教材的"章节脉络" → 图谱价值大。你四类源都有，可能要**混合**。
3. **掌握度图谱要不要时序化？**（借鉴 graphiti 给 mastery 加"有效时间窗 + 交互溯源"）
   - 这决定能不能做"掌握度随时间衰减→触发复习"。
4. **存储统一到 PG，还是继续 SQLite + chroma？**
   - 不引 Neo4j 的前提下：PG（pgvector 存向量 + 存图）可大一统；或 SQLite 存业务 + chroma 存向量。

---

## 已读源码清单（本报告事实依据）

- `app/infrastructure/rag/coordinator.py`（RAGCoordinator 全文）
- `app/infrastructure/rag/store.py`（FakeRAGStore/RAGStore 全文）
- `app/infrastructure/rag/ocr.py` · `code_index.py`（两 Provider 全文）
- `app/agents/retriever.py`（机械层检索链路）
- `app/harness/mastery_graph.py`（MasteryGraph 全部方法）
- `app/agents/curator.py`（图谱+画像自动维护，全文）
- `app/infrastructure/storage/mastery_graph_store.py`（三表持久化）
- `app/infrastructure/storage/knowledge_store.py`（确认为假实现）
- `app/models/tables.py`（KnowledgeTable/MasteryNodeTable/MasteryEdgeTable）
- `app/infrastructure/llm.py`（确认无 embedding 能力，仅 ChatOpenAI）
- `pyproject.toml`（确认 llama-index/chroma/pgvector/rerank/ragas 已装）
