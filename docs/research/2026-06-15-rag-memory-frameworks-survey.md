# RAG 与长期记忆开源方案调研

> 调研日期：2026-06-15
> 目的：为 StudyAgent 升级检索系统、支持长期记忆做选型依据。后续基于本文档讨论 RAG + 记忆的搭建。
> 场景定位：**学习辅助** —— 注重长期记忆回顾、知识高度集中（知识点之间有强关联结构，而非松散文档）。

## 0. star 数核实说明

所有 star 数均通过 GitHub API（`api.github.com/repos/<owner>/<repo>`）于 **2026-06-15 当天实时拉取**，
非来自我的训练记忆或二手榜单文章（那些会过时）。下表按 star 降序。

| 排名 | 项目 | star | 定位 | 类别 |
|---|---|---|---|---|
| 1 | infiniflow/ragflow | ⭐ 82,816 | 生产级 RAG 引擎（深度文档解析） | RAG |
| 2 | mem0ai/mem0 | ⭐ 58,619 | 通用 AI 记忆层 | 记忆 |
| 3 | HKUDS/LightRAG | ⭐ 36,603 | 轻量图谱+向量双层 RAG | RAG/图谱 |
| 4 | microsoft/graphrag | ⭐ 33,761 | 图谱化 RAG（社区摘要） | RAG/图谱 |
| 5 | getzep/graphiti | ⭐ 27,456 | 时序知识图谱记忆引擎 | 记忆/图谱 |
| 6 | letta-ai/letta (原 MemGPT) | ⭐ 23,340 | 有状态 Agent + 分层记忆 | 记忆 |
| 7 | topoteretes/cognee | ⭐ 17,838 | AI 记忆平台（图谱+向量） | 记忆/图谱 |

> 补充候选（同样 >10k，但与本场景相关性略低，未展开）：
> run-llama/llama_index ⭐ 50,142、deepset-ai/haystack ⭐ 25,571、
> qdrant/qdrant ⭐ 32,316（纯向量库）、chroma-core/chroma ⭐ 28,439（纯向量库）、
> supermemoryai/supermemory ⭐ 27,043、NevaMind-AI/memU ⭐ 13,859。

本文档详述 **7 个核心项目**（全部 >10k，最高 82.8k），满足"至少 5 个"要求。

---
## 1. infiniflow/ragflow ⭐ 82,816

- **地址**：https://github.com/infiniflow/ragflow
- **一句话**：把 RAG 与 Agent 能力融合的生产级检索引擎，核心卖点是**深度文档理解**（DeepDoc）。
- **设计方案**（据官方仓库描述）：
  - **深度文档解析**：不止按字数切块，而是对 PDF/PPT/表格/扫描件做版面分析，按文档真实结构（标题、段落、表格、图）切块，减少"切坏语义"的问题。
  - **基于模板的分块**：针对不同文档类型（论文、简历、法律、手册）提供可解释、可干预的切块模板。
  - **引用可溯源**：检索结果带原文出处，降低幻觉、便于人工核对。
  - **融合 Agent**：在 RAG 之上叠加 agentic workflow，把"检索"作为 LLM 的上下文层。
- **存储/部署**：自带 Web 服务，`docker compose` 起栈，工程化最完整。
- **对学习场景的价值**：如果你的知识来源是**结构复杂的教材/讲义 PDF**，它的版面级解析能显著提升切块质量。
- **代价**：重。是一个完整平台（前后端+多个依赖服务），不是嵌入式库；自建运维成本高。

---

## 2. mem0ai/mem0 ⭐ 58,619

- **地址**：https://github.com/mem0ai/mem0
- **一句话**：通用"记忆层"，给 AI 助手加可个性化、可长期积累的记忆。论文 arXiv:2504.19413。
- **核心设计**（据 2026-04 README 公布的新算法）：
  - **多层记忆（Multi-Level Memory）**：区分 **User / Session / Agent** 三种状态，分别承载长期用户画像、当前会话、agent 自身确认的事实。
  - **单遍 ADD-only 抽取**：一次 LLM 调用从对话抽取事实，**只新增不覆盖**（记忆累积，不删旧）。这是它把 token 压到 ~7K、延迟 ~1s 的关键。
  - **实体链接**：抽取实体并 embed，跨记忆链接以增强检索召回。
  - **多信号检索融合**：语义向量 + BM25 关键词 + 实体匹配三路并行打分融合。
  - **时间推理**：时间感知检索，能区分"当前状态/过去事件/未来计划"，对同一实体的不同时间版本排序。
- **基础用法**：`memory.search(query, filters={user_id})` 召回 → 拼进 system prompt → `memory.add(messages, user_id)` 回写。一个极简的"检索-生成-回写"闭环。
- **存储/部署**：库（`pip install mem0ai`）/ 自建 server（docker）/ 云三档。可选 `[nlp]` 装 BM25+实体抽取。
- **对学习场景的价值**：**最贴近"长期记忆回顾"**。User 层天然适合存"学习者画像/易错点/偏好"，时间推理适合"上次学到哪、隔多久该复习"。
- **代价**：抽取/检索依赖 LLM 调用（有成本）；ADD-only 不删意味着需要自己设计记忆淘汰/聚合策略。

---

## 3. HKUDS/LightRAG ⭐ 36,603

- **地址**：https://github.com/HKUDS/LightRAG（论文 arXiv:2410.05779，港大数据智能实验室）
- **一句话**：轻量级、把**知识图谱 + 向量嵌入双层**同时管理的 RAG，定位为 Microsoft GraphRAG 的高效替代。
- **核心设计**（据 README 原文 line 219-258）：
  - **双层检索（Dual-Level Retrieval）**：
    - **low-level（local 模式）**：召回**具体实体**及其邻居关系 —— 回答细节事实。
    - **high-level（global 模式）**：召回**全局关系/抽象概念** —— 回答跨文档、概括性问题。
  - **四种查询模式**：`naive`（纯向量切块，不用图谱）/ `local` / `global` / `hybrid`（local+global）/ `mix`（local+global+naive，默认，效果最佳，延迟略高于 naive）。
  - **增量更新**：新增文档自动增量建图，**无需全量重算**（直击 GraphRAG 的增量成本痛点）。
  - **token 预算可控**：`MAX_ENTITY_TOKENS / MAX_RELATION_TOKENS / MAX_TOTAL_TOKENS` 三个旋钮控制送进 LLM 上下文的 entities/relations/text chunks 长度。
  - **多后端**：PostgreSQL / Neo4j / MongoDB / OpenSearch 等可作统一存储；2026-05 已并入多模态解析（MinerU/Docling）和 4 种切块策略。
- **对学习场景的价值**：**最契合"知识高度集中"**。知识点之间的 PREREQ/RELATED 关系正是图谱的强项；global 模式天然支持"帮我串一下这一章的脉络"这类概括性回顾。
- **代价**：建图需要 LLM 抽取实体关系（首次索引有成本）；图质量依赖抽取 prompt 调优。

---

## 4. microsoft/graphrag ⭐ 33,761

- **地址**：https://github.com/microsoft/graphrag（论文 arXiv:2404.16130，微软研究院）
- **一句话**：用 LLM 从非结构化文本抽取结构化知识图谱，并预生成**社区摘要**来增强全局问答。
- **核心设计**（据 README + 论文背景）：
  - **图谱抽取**：LLM 抽取实体、关系，构建知识图谱。
  - **社区检测 + 分层摘要**：用图聚类（Leiden）把实体分成社区，对每个社区**预先生成摘要**。回答"全局性问题"时聚合社区摘要，而非逐块检索 —— 这是它相对传统 RAG 的核心差异。
  - **Prompt Tuning**：强调要针对自己的数据微调抽取 prompt，否则开箱效果一般。
- **对学习场景的价值**：社区摘要 ≈ "章节/主题级概览"，适合生成"知识地图"式的回顾材料。
- **代价**：官方明确警告 **indexing 很贵**（大量 LLM 调用）；**增量更新弱**（小版本升级要 `--force` 重建，大版本要迁移）。是"方法论演示"，非生产框架。**LightRAG 基本就是冲着解决它的成本/增量问题而来**，两者要二选一时优先看 LightRAG。

---
## 5. getzep/graphiti ⭐ 27,456

- **地址**：https://github.com/getzep/graphiti（论文 arXiv:2501.13956 "Zep: A Temporal Knowledge Graph Architecture for Agent Memory"）
- **一句话**：构建并查询**时序上下文图谱（temporal context graph）**的记忆引擎，是 Zep 商业平台的开源内核。
- **核心设计**（据 README 原文 line 42-93）：
  - **时序图谱**：与静态知识图谱不同，**每条事实带"有效时间窗"** —— 何时成立、何时被取代。能查"现在为真"和"过去为真"两种状态。
  - **四类组件**：
    - **Entities（节点）**：人/概念，summary 随时间演化。
    - **Facts/Relationships（边）**：实体三元组，带时间有效性窗口。
    - **Episodes（溯源）**：原始数据流，每条派生事实都能回溯到来源。
    - **Custom Types（本体）**：用 Pydantic 模型自定义实体/边类型。
  - **增量更新**：持续把新交互整合进图，**无需重算整图**。
  - **混合检索**：语义 + 关键词 + 图遍历三路。
  - **MCP server**：可直接作为 Claude/Cursor 的记忆后端。
- **对学习场景的价值**：时间窗 + episode 溯源非常适合记录"学习者对某知识点的掌握随时间变化"，且每次评分都能溯源到具体交互。**与本项目已有的 mastery_graph（掌握度图谱）理念高度同构**。
- **代价**：需要图数据库（Neo4j 等）；OSS 版只给引擎，用户/会话管理、生产级低延迟检索要么自建、要么上 Zep 云。

---

## 6. letta-ai/letta（原 MemGPT）⭐ 23,340

- **地址**：https://github.com/letta-ai/letta
- **一句话**：构建**有状态 Agent** 的平台，核心是 MemGPT 提出的"把 LLM 上下文当操作系统内存来管理"。
- **核心设计**（据 MemGPT 论文 + README memory_blocks 示例）：
  - **memory blocks**：把记忆组织成带 `label` 的块（如 `human` 存用户画像、`persona` 存 agent 人设），常驻在上下文里。
  - **分层记忆（操作系统类比）**：
    - **core memory**：常驻上下文的高频信息（memory blocks），容量有限。
    - **archival / recall memory**：上下文外的长期存储，需要时检索调入。
  - **self-editing memory**：agent 通过工具调用**自主改写自己的记忆块**（决定什么该记进 core、什么归档），并在上下文逼近上限时自主搬运 —— 这是 MemGPT 的标志性机制。
  - **模型无关**，提供 Python/TS SDK 与 agents API。
- **对学习场景的价值**：self-editing + core/archival 分层适合做"学习者长期画像"的自动维护（agent 自己决定把哪些易错点提升到常驻记忆）。
- **代价**：README 极简，能力集中在托管平台/SDK，自建程度低；偏"有状态 agent 框架"，不是纯检索库，引入它等于引入一套 agent 运行时，对已有自研 harness 的本项目耦合较重。

---

## 7. topoteretes/cognee ⭐ 17,838

- **地址**：https://github.com/topoteretes/cognee（论文 arXiv:2505.24478）
- **一句话**：开源 AI 记忆平台，把任意格式数据持续构建成**自托管知识图谱**，给 agent 跨会话长期记忆。
- **核心设计**（据 README 原文 line 40-202）：
  - **ECL 管线**：Extract（抽取）→ Cognify（构图）→ Load（加载）。`cognee.remember()` 一次跑完 add+cognify+improve，永久存进知识图谱。
  - **双存储 + 自动路由**：**session memory（快缓存，后台同步到图）** + 永久知识图谱；`search` 自动选最优检索策略，可先查 session 再回落到图。
  - **图谱+向量+本体融合**：向量 embedding 负责"按语义搜"，图推理负责"按关系连"，认知科学本体生成负责结构化。
  - **Claude Code 插件**：通过 hooks 接入 Claude Code 生命周期 —— `SessionStart` 初始化、`PostToolUse` 捕获动作、`UserPromptSubmit` 注入相关上下文、`PreCompact` 在上下文重置前保住记忆、`SessionEnd` 把会话桥接进永久图。
- **对学习场景的价值**：session/permanent 双层 + 自动路由，天然对应"短期会话"与"长期知识"分离；ECL 管线适合把学习材料持续沉淀成图。
- **代价**：相对年轻；图谱质量同样依赖抽取与本体设计。

---

## 8. 横向对比与对本项目（StudyAgent）的适配建议

### 8.1 三类技术路线对比

| | 纯向量 RAG | 图谱 RAG | 记忆层 |
|---|---|---|---|
| 代表 | ragflow / llama_index | LightRAG / graphrag / graphiti | mem0 / letta / cognee |
| 擅长 | 文档级语义检索 | 知识点关系、概括性回顾 | 跨会话长期记忆、用户画像 |
| 短板 | 不懂知识点关系 | 建图有 LLM 成本 | 需配检索后端 |
| 对应你的需求 | 基础检索 | **知识高度集中** | **长期记忆回顾** |

### 8.2 本项目现状（已读代码确认）

| 资产 | 位置 | 现状 | 三色 |
|---|---|---|---|
| RetrieverAgent | `app/agents/retriever.py` | 机械检索层，委托 RAGCoordinator，只给原始 similarity score | 🟢 已有 |
| RAGCoordinator | `app/infrastructure/rag/coordinator.py` | 检索协调入口 | 🟢 已有 |
| rag/ 子模块 | `app/infrastructure/rag/`（code_index/extractors/ocr/store） | 已有抽取+索引雏形 | 🟢 已有 |
| mastery_graph | `app/harness/mastery_graph.py` | **知识点掌握度图谱**：节点含 mastery(0-100)、last_practiced_at、confusion_with；边含 PREREQ/RELATED/CONFLICT + confidence | 🟢 已有 |
| mastery_graph_store | `app/infrastructure/storage/` | 图谱持久化（SQLAlchemy） | 🟢 已有 |

> 关键发现：**你已经有一个 mastery_graph，结构上和 graphiti 的"时序上下文图谱"高度同构**
> （都是 节点+带 confidence/时间的边）。升级方向不是推倒重来，而是给它补上"检索"和"长期记忆回写"两条能力。

### 8.3 初步选型倾向（待与你讨论）

结合"学习辅助 + 长期记忆回顾 + 知识高度集中"+ 已有 mastery_graph：

| | 倾向方案 | 备选 | 不选的理由 |
|---|---|---|---|
| 图谱检索 | **LightRAG** | graphrag | graphrag 索引贵、增量弱；LightRAG 双层检索 + 增量更新 + 多后端，且理念可直接嫁接到现有 mastery_graph |
| 长期记忆 | **mem0** | letta / cognee | mem0 是嵌入式库，User/Session/Agent 分层 + 时间推理最贴"复习"语义，对自研 harness 侵入最小；letta 是整套 agent 运行时，耦合重 |
| 时序图谱（可选参考） | graphiti 的设计 | — | 不一定引入依赖，但其"事实带有效时间窗 + episode 溯源"思路值得搬到 mastery_graph |

**核心判断**：本项目的图谱底子已经具备，更可能的路径是
**"借鉴 LightRAG 的双层检索 + mem0 的多层记忆/时间推理思路，嫁接到现有 mastery_graph 与 RAGCoordinator"**，
而非整体替换为某个框架。具体方案在下一轮讨论确定。

### 8.4 待你拍板的关键问题

1. 知识来源主要是什么形态？（结构化教材 PDF → ragflow 解析价值大；纯文本/笔记 → LightRAG 够用）
2. 长期记忆要记的是**知识内容本身**，还是**学习者画像/掌握轨迹**？（前者偏图谱，后者偏 mem0 风格）
3. 是否接受引入图数据库（Neo4j）？还是希望继续用现有 SQLite/PG？
4. 倾向"引入成熟框架"还是"借鉴设计、自研嫁接到现有 harness"？

---

## 参考来源

- ragflow: https://github.com/infiniflow/ragflow
- mem0: https://github.com/mem0ai/mem0 · 论文 https://arxiv.org/abs/2504.19413
- LightRAG: https://github.com/HKUDS/LightRAG · 论文 https://arxiv.org/abs/2410.05779
- graphrag: https://github.com/microsoft/graphrag · 论文 https://arxiv.org/abs/2404.16130
- graphiti: https://github.com/getzep/graphiti · 论文 https://arxiv.org/abs/2501.13956
- letta: https://github.com/letta-ai/letta
- cognee: https://github.com/topoteretes/cognee · 论文 https://arxiv.org/abs/2505.24478
- 榜单参考：https://ossinsight.io/blog/agent-memory-race-2026 · https://www.firecrawl.dev/blog/best-open-source-rag-frameworks
