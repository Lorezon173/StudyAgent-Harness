# 工作交接：retriever agent 教学场景改进讨论

> 创建：2026-07-14
> 会话目标：讨论 retriever agent 针对**教学场景**的改进（query / 召回 / 重排 三方面）
> 状态：⏳ 讨论中——已完成现状摸清 + 教学场景刻画 + 记忆系统答疑，等待用户两项决策后进入改进方案讨论
> 约束：处于 `superpowers:brainstorming` skill 的 HARD-GATE 下（设计未批准前不写代码）
> 说明：与同目录 `2026-07-14-工作内容.md`（另一会话：Retriever 职责梳理 + 用户画像设计全貌）互补，本文件聚焦"教学场景改进讨论 + 长期记忆系统答疑"

---

## 1. 本次会话的来龙去脉

用户提出：基于当前 retriever agent 设计，针对 query / 召回 / 重排三方面，讨论教学场景的改进。明确要求"先详细描述教学场景特点，再说改进"。

讨论中途，用户延伸出关于**长期记忆系统**的四个问题（retriever 是否可承担长期记忆 / 长期记忆如何实现及依托什么框架 / 知识图谱画像与记忆系统的关系 / 在 Agent 运行中的地位），已基于代码事实逐一回答。

本会话**未改动任何代码或文件**，全部为只读探索 + 讨论性输出。

---

## 2. 已完成的工作（按步骤）

1. 加载 `superpowers:brainstorming` skill，按其流程组织讨论
2. 派 Explore agent 摸清 retriever agent 在 query / 召回 / 重排三方面的真实实现
3. 派 Explore agent 读取教学场景相关文件（TeachingMode / ObservationSet / MasteryGraph / UserProfile / Curator / orchestrator_rules / WorkspaceState）
4. 在会话中输出"教学场景六维度特点刻画"（待用户确认）
5. 派 Explore agent 穷举项目记忆系统实现，回答用户关于长期记忆的四个问题

---

## 3. 关键事实索引（按主题，仅给 file:line，内容自查原文）

### 3.1 retriever agent 现状

| 事实 | 索引位置 |
|---|---|
| RetrieverAgent 实现（事件驱动，非 LangGraph 节点） | `app/agents/retriever.py:24` |
| retriever spec（声明不调 LLM，仅留存） | `app/specs/agents/retriever.md` + `retriever.prompt.md` |
| Query 原样透传，无改写/扩展/意图识别 | `app/agents/retriever.py:44` |
| 不读 action 字段（只判 target=="retriever"） | `app/agents/retriever.py:41` |
| 不读任何教学 state 字段（grep profile/current_topic/current_mode 无命中） | `app/agents/retriever.py` 全文 |
| 召回入口：RAGCoordinator.search | `app/infrastructure/rag/coordinator.py:100` |
| 唯一 provider：vector | `app/infrastructure/rag/coordinator.py:52` |
| embedding 配置（doubao-embedding-vision / 2048 维） | `app/config.py:22-23` |
| top_k=5 / LOW_SCORE_THRESHOLD=0.3（仅打标签不过滤） | `app/agents/retriever.py:45` / `:21` |
| search 无 WHERE user_id/scope | `app/infrastructure/rag/pgvector_provider.py:135-143` |
| 重排未实现；sbert-rerank 依赖零调用 | `pyproject.toml:29`（grep rerank 无命中） |
| retriever_expand_query 闭环断路 | `app/orchestration/orchestrator_rules.yaml:50-54` + `app/harness/orchestrator.py:149-154` |

### 3.2 已有 RAG 三段式回顾文档（本次讨论的延续基础，必读）

- `docs/designs/2026-07-07-rag-three-stage-enhancement-review.md`
  - §1 现状链路 / §2 三块现状带证据 / §3 三个 P0 断点 / §4 三块改进建议（锚定教学场景）/ §4.1 教学场景特性表 / §5 优先级总表 / §6 与 B-1/B-2/B-3 计划对齐 / §7 六个 open questions

### 3.3 教学场景相关

| 事实 | 索引位置 |
|---|---|
| TeachingMode 四模式（Socratic/Feynman/Analogy/Regress） | `app/harness/enums.py:137-142` |
| 模式语义/转移逻辑 | `app/harness/teaching_policy.py`（TeachingPolicy._decide） |
| 8 种教学动作 + 规则优先级表 | `app/orchestration/orchestrator_rules.yaml`（全文） |
| Tutor 动作指令定义 | `app/specs/agents/tutor.prompt.md` |
| ObservationSet（mastery/confusion/contradiction/prereq_weak/rag_quality_low/repeat_count/...） | `app/harness/teaching_policy.py:6-17` |
| MasteryGraph 主类 | `app/harness/mastery_graph.py:45` |
| MasteryNode / EdgeType / EdgeSource | `app/harness/mastery_graph.py:22-31` / `:8-12` / `:15-19` |
| find_weak_prereqs（前置薄弱检测） | `app/harness/mastery_graph.py:127-156` |
| UserProfile（preferences: explanation_style/pace/depth） | `app/harness/user_profile.py:13-67` |
| Curator（唯一维护 MasteryGraph+UserProfile，只判结构层） | `app/agents/curator.py:9-23` |
| WorkspaceState（会话内共享状态） | `app/harness/workspace_state.py:6-22` |
| 全局教学底线 | `app/specs/_root.prompt.md` |

### 3.4 记忆系统（本次新增调查）

| 事实 | 索引位置 |
|---|---|
| 三层记忆设计定义（L1 工作记忆 / L2 会话记忆 / L3 画像记忆） | `docs/superpowers/specs/2026-05-29-multi-agent-redesign-design.md:786-796` |
| 设计-实现断裂关键行（"memory.py [复用]"——但 memory.py 不存在） | 同上 `:830` |
| L1/L2 重写设计（未落地） | `docs/designs/2026-05-13-memory-redesign.md` |
| Plan B（L3 落地计划） | `docs/superpowers/plans/2026-06-01-plan-b-memory-profile.md` |
| 记忆框架调研（7 个框架，结论：嫁接不替换） | `docs/research/2026-06-15-rag-memory-frameworks-survey.md` |
| "分裂两半"交接文档（L3 成熟 vs L2+知识库空白） | `docs/claude-chat/2026-06-16-rag-memory-handoff.md` |
| MemoryScope 枚举（5 级，无消费方） | `app/harness/enums.py:68-74` |
| L3 持久化（aiosqlite） | `app/infrastructure/storage/mastery_graph_store.py:7` |
| L3 持久化（备选，SQLAlchemy） | `app/infrastructure/storage/sqlalchemy_mastery_store.py:7` |
| EventStore（按 session_id 全量回放，不可内容检索；当前 `:memory:`） | `app/infrastructure/storage/event_store.py:9` |
| MessageStore | `app/infrastructure/storage/message_store.py:9` |
| graph.save() 时机（persist_turn 内） | `app/api/_persist.py:42-43` |
| graph 未 load 历史（db_path=":memory:"，空图启动） | `app/orchestration/assembly.py:115` |
| profile_snapshot 未填充 | `app/orchestration/assembly.py:142-143` |
| 假摘要方法 | `app/infrastructure/llm.py:206-211` |
| LangGraph MemorySaver（非项目记忆系统） | `app/orchestration/graph.py:116` |
| vector_chunks 表（retriever 检索对象，存教材知识非历史交互） | `app/models/tables.py:92-112` |
| retriever 无记忆检索路径（只调 RAGCoordinator.search） | `app/agents/retriever.py` 全文 |
| 协作环数据流 | `app/orchestration/collab_loop.py:31-78` + `app/orchestration/assembly.py:100-168` |
| 框架依赖（无 mem0/letta/graphiti/cognee/LightRAG；无 langchain.memory） | `pyproject.toml` |

---

## 4. 关键发现（本次会话产出）

1. **retriever 与教学上下文完全脱节**：state 有 4 层教学信号（模式 / 观察集 / 图谱 / 画像）、8 种差异化教学动作，retriever 一个都不读、一个都不区分。改进核心抓手是"接进来"而非"加增强"。
2. **设计-实现断裂**：设计文档说"复用现有 memory.py（L1+L2）"，但 `app/harness/memory.py` 在代码库中不存在。L1 实际由 `WorkspaceState` 临时顶替，L2 完全空白。
3. **记忆系统现状**：只有 L3 画像记忆（MasteryGraph + UserProfile）落地且由 Curator 维护；L2 文本检索式记忆（跨会话对话历史召回）完全没实现。
4. **画像与记忆的关系**：UserProfile + MasteryGraph 不是独立于记忆系统的组件，它们**就是**记忆系统的 L3 层本身（设计文档 §6.2 明确）。
5. **与 2026-07-07 回顾文档互相印证**：本次独立摸清的现状，与该回顾文档的结论一致（三个 P0 断点、修断点 ROI > 加增强）。

---

## 5. 待决策的开放问题（等待用户）

### 决策点 1：教学场景六维度刻画是否准确
会话中已输出六维度刻画（交互结构 / 教学动作驱动 / 四层教学状态 / 检索目的与职能边界 / 概念脉络 / 用户隔离）。**用户尚未确认或补充**。

### 决策点 2：L2 文本记忆路线选择（A/B/C）
- (A) 按原设计独立实现 memory.py（MemoryManager 路线，与 retriever 平行）
- (B) 让 retriever 兼并 L2 职责（统一检索层，知识库 + 历史记忆都走 retriever，scope/source 区分）
- (C) 暂不补 L2，本次只聚焦"把已有 L3 信号接进 retriever + 修三块断点"

> 此决策直接决定 retriever 改进讨论是否纳入"长期记忆检索"。

### 决策点 3：2026-07-07 回顾文档 §7 的 6 个 open questions
特别是 P0-①（Tutor 吃检索结果的三条路径 a/b/c 选哪条）、新栈是否应在种子事件就发 retriever_search。

---

## 6. 下一步行动

1. 等用户确认 / 修正教学场景六维度刻画
2. 等用户选 L2 路线（A/B/C）
3. 确认后，按 brainstorming skill 流程进入"query / 召回 / 重排三块改进方案"讨论：
   - 引用 `docs/designs/2026-07-07-rag-three-stage-enhancement-review.md` §4 已有建议（不重写）
   - 逐块讨论选型与取舍（带两列对照判据）
   - 范围是否纳入 L2 记忆检索，取决于决策点 2
4. 方案敲定后 → 写 design doc（`docs/superpowers/specs/`）→ spec self-review → 用户审 → `writing-plans` skill

---

## 7. 约束提醒（接手者必看）

- 本会话处于 `superpowers:brainstorming` skill 的 HARD-GATE 下：设计未批准前不写代码
- 全程中文沟通（项目规范）
- 引用即读：所有结论基于 `file:line` 事实，不脑补
- 后续若进入 spec / plan 编写，须先载入 `spec-plan-writer` skill
- 后续若进入编码，须先载入 `andrej-karpathy-skills:karpathy-guidelines` skill
- 方案呈现须遵循 `.claude/rules/solution-presentation.md`（资产清单 + 三色血缘 + 决策判据）
- 模块开发须遵循三层规划（`.claude/rules/dev-standards.md`）
