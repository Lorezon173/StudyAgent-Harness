# StudyAgent 重构阶段 — 全栈脚本清单

> **生成日期**：2026-06-01
> **用途**：项目整体整理时的脚本对照地图，列出本轮重构涉及的全部新建脚本及其依赖的老脚本
> **当前状态**：Wave 0（Plan 0）✅ 完成 · Wave 1（Plan A/B）✅ 完成 · Plan C 进行中 · Wave 2（Plan D/E）待开始

---

## 0. 总览：四层架构 + 新旧分布

```
┌────────────────────────────────────────────────────────────────────┐
│  API 层（FastAPI）— 老栈，待 Plan D 加 feature flag                │
│  app/api/{auth, chat, chat_multi, chat_stream, errors, eval,       │
│           knowledge, profile, sessions}.py                          │
├────────────────────────────────────────────────────────────────────┤
│  Orchestration 层                                                   │
│   🆕 app/orchestration/ — 新栈骨架（Plan 0）                       │
│   📛 app/agent/ — 老栈（14 节点 + multi_agent + system_eval, 只读）│
├────────────────────────────────────────────────────────────────────┤
│  Harness 层 — 混合：Plan 0/B 新增 + 老文件复用                     │
│  app/harness/{events, eventbus, workspace_state,                    │
│               mastery_graph, user_profile}.py  🆕                  │
│  app/harness/{enums(扩展), memory, observability, intent_router,    │
│               error_handler, guardrails, tool_registry,             │
│               state_manager, state/}.py  📛 复用                   │
├────────────────────────────────────────────────────────────────────┤
│  Infrastructure 层 — 混合：Plan 0/A/B 新增 + 扩展 + 老复用          │
│  storage: event_store, mastery_graph_store  🆕                      │
│  rag: coordinator(扩展) + ocr/code_index/extractors/  🔄🆕         │
│  其余存储 + llm.py + external/  📛 复用                            │
└────────────────────────────────────────────────────────────────────┘

图例：🆕 全新建 · 🔄 扩展老文件 · 📛 老栈/复用不改
```

---

## 1. Wave 0：Plan 0 核心契约地基（已冻结）

**用途**：建立事件驱动新栈的所有契约接口，所有 Wave 1/2 都依赖这些不可改动的签名。

### 1.1 新建文件

| 路径 | 职责 | 依赖 |
|------|------|------|
| 🆕 [app/harness/events.py](app/harness/events.py) | `Event` 数据类 + `new_event_id`（时序 ULID）+ `EVENT_OWNERSHIP` 白名单 + `check_ownership` + `EmitViolationError` + `EVENT_PRIORITY` + `priority_of` | enums.py |
| 🆕 [app/harness/eventbus.py](app/harness/eventbus.py) | `EventBus.publish/subscribe/subscribers_of/replay`，publish 时校验白名单 | events, enums, event_store |
| 🆕 [app/harness/workspace_state.py](app/harness/workspace_state.py) | `WorkspaceState` dataclass（session_id, user_id, current_topic, current_mode, turn_count, event_ids, evidence_pool, critic_state, profile_snapshot） | enums.TeachingMode |
| 🆕 [app/agents/base.py](app/agents/base.py) | `AgentBase` ABC：source/subscriptions/emittable_types/handle/emit/evaluate | events, enums, workspace_state |
| 🆕 [app/infrastructure/storage/event_store.py](app/infrastructure/storage/event_store.py) | 同步 sqlite3 事件持久化 + 全序回放（按 id 升序）| events, enums |
| 🆕 [app/orchestration/collab_loop.py](app/orchestration/collab_loop.py) | 单线程事件循环 + 优先级队列 + 回合屏障骨架（`run_collab_loop`） | events, eventbus, workspace_state |
| 🆕 [app/orchestration/graph.py](app/orchestration/graph.py) | 4 节点主图骨架（ingest/route/collab_loop/wrap_up，Plan C 接入 _collab_loop_node） | — |

### 1.2 扩展文件

| 路径 | 改动 |
|------|------|
| 🔄 [app/harness/enums.py](app/harness/enums.py) | **新增**：`EventType`（25 种）/ `EventSource`（7 角色）/ `TeachingMode`（4 模式）/ `ActionKind`（13 种）。**保留**：Stage/Intent/GateStatus/MasteryLevel/ErrorKind/RecoveryAction/RetrievalMode/MemoryScope/AgentRole/EvalMetric（老栈用） |

### 1.3 测试文件

| 路径 | 数量 |
|------|------|
| 🆕 [tests/unit/harness/test_events.py](tests/unit/harness/test_events.py) | ID + 优先级 + 所有权白名单 |
| 🆕 [tests/unit/harness/test_eventbus.py](tests/unit/harness/test_eventbus.py) | 订阅/发布/回放/越权拦截 |
| 🆕 [tests/unit/harness/test_workspace_state.py](tests/unit/harness/test_workspace_state.py) | 状态字段 |
| 🆕 [tests/unit/agents/test_agent_base.py](tests/unit/agents/test_agent_base.py) | 4 测试 |
| 🆕 [tests/unit/infrastructure/test_event_store.py](tests/unit/infrastructure/test_event_store.py) | 持久化往返 + 全序回放 |
| 🆕 [tests/unit/orchestration/test_collab_loop.py](tests/unit/orchestration/test_collab_loop.py) | 优先级队列 + 屏障 |
| 🆕 [tests/unit/orchestration/test_graph.py](tests/unit/orchestration/test_graph.py) | 4 节点骨架 |

---

## 2. Wave 1 · Plan A：检索与知识库（已完成）

**用途**：Retriever Agent + RAG 多 Provider 协调器（OCR / 代码 AST / 文件提取）。

### 2.1 新建文件

| 路径 | 职责 | 依赖 |
|------|------|------|
| 🆕 [app/agents/retriever.py](app/agents/retriever.py) | RetrieverAgent：只做机械层（向量检索+相似度+retrieval_status），不评语义质量；evaluate() 实现 §5.2 RAG 三件套 | base.py, events, enums, workspace_state, rag.coordinator |
| 🆕 [app/infrastructure/rag/ocr.py](app/infrastructure/rag/ocr.py) | OCRProvider 实现 IndexProvider 协议，pytesseract 可选依赖 | rag.coordinator, rag.store |
| 🆕 [app/infrastructure/rag/code_index.py](app/infrastructure/rag/code_index.py) | CodeIndexProvider，Python AST 按函数/类切片 | rag.coordinator, rag.store |
| 🆕 [app/infrastructure/rag/extractors/__init__.py](app/infrastructure/rag/extractors/__init__.py) | 工厂导出 |
| 🆕 [app/infrastructure/rag/extractors/base.py](app/infrastructure/rag/extractors/base.py) | Extractor 协议 + 文件路由 |
| 🆕 [app/infrastructure/rag/extractors/pdf_extractor.py](app/infrastructure/rag/extractors/pdf_extractor.py) | PDF 提取（pypdf 可选） |
| 🆕 [app/infrastructure/rag/extractors/docx_extractor.py](app/infrastructure/rag/extractors/docx_extractor.py) | DOCX 提取（python-docx 可选） |
| 🆕 [app/infrastructure/rag/extractors/text_extractor.py](app/infrastructure/rag/extractors/text_extractor.py) | TXT/MD 提取 |

### 2.2 扩展文件

| 路径 | 改动 |
|------|------|
| 🔄 [app/infrastructure/rag/coordinator.py](app/infrastructure/rag/coordinator.py) | 从单 FakeRAGStore 重写为 **多 Provider 协调器**：IndexProvider 协议 + Chunk/SearchResult 数据类 + 去重排序聚合 |

### 2.3 复用（不改）

| 路径 | 用途 |
|------|------|
| 📛 [app/infrastructure/rag/store.py](app/infrastructure/rag/store.py) | FakeRAGStore — Plan A 各 Provider 内部仍使用 |
| 📛 [app/infrastructure/llm.py](app/infrastructure/llm.py) | LLMService（Plan A 不直接用，Plan C/D 会用） |
| 📛 [app/infrastructure/external/](app/infrastructure/external/) | OCR / Web 搜索 / Redis（Plan A 的 OCR 在 rag/ocr.py 独立实现） |

### 2.4 测试文件

| 路径 | 覆盖 |
|------|------|
| 🆕 [tests/unit/agents/test_retriever.py](tests/unit/agents/test_retriever.py) | RetrieverAgent 契约 + 机械门槛 + evaluate |
| 🆕 [tests/unit/infrastructure/test_rag.py](tests/unit/infrastructure/test_rag.py) | Coordinator 多 Provider 聚合 |
| 🆕 [tests/unit/infrastructure/test_ocr.py](tests/unit/infrastructure/test_ocr.py) | OCRProvider |
| 🆕 [tests/unit/infrastructure/test_code_index.py](tests/unit/infrastructure/test_code_index.py) | AST 切片 |
| 🆕 [tests/unit/infrastructure/test_extractors.py](tests/unit/infrastructure/test_extractors.py) | PDF/DOCX/TXT |

---

## 3. Wave 1 · Plan B：记忆与画像（已完成）

**用途**：Curator Agent + L3 画像记忆（MasteryGraph + UserProfile）+ 持久化。

### 3.1 新建文件

| 路径 | 职责 | 依赖 |
|------|------|------|
| 🆕 [app/infrastructure/storage/mastery_graph_store.py](app/infrastructure/storage/mastery_graph_store.py) | aiosqlite 持久化：3 张表（mastery_nodes/mastery_edges/user_profile_l3）+ CRUD 8 方法 | aiosqlite, json |
| 🆕 [app/harness/mastery_graph.py](app/harness/mastery_graph.py) | MasteryNode/MasteryEdge + EdgeType/EdgeSource StrEnum + MasteryGraph 引擎（冷启动三来源 + 置信度加权 find_weak_prereqs） | mastery_graph_store |
| 🆕 [app/harness/user_profile.py](app/harness/user_profile.py) | UserProfile dataclass（preferences/topics_active/topics_mastered/learning_streak/total_sessions） | mastery_graph_store |
| 🆕 [app/agents/curator.py](app/agents/curator.py) | Curator Agent：双时机（MasteryAssessed→observed / TopicEntered→historical，渐进启用）+ evaluate | base.py, events, enums, workspace_state, mastery_graph, mastery_graph_store |

### 3.2 复用（不改）

| 路径 | 关系 |
|------|------|
| 📛 [app/harness/memory.py](app/harness/memory.py) | L1（ShortTermStore LRU+TTL）+ L2（LongTermStore SQLite+FTS5）— L3 画像与 L1/L2 **并列**而非扩展，由 mastery_graph + user_profile 实现 |
| 📛 [app/infrastructure/storage/memory_store.py](app/infrastructure/storage/memory_store.py) | L2 后端，Plan B 的 store 是独立的 aiosqlite |

### 3.3 测试文件

| 路径 | 数量 |
|------|------|
| 🆕 [tests/unit/infrastructure/test_mastery_graph_store.py](tests/unit/infrastructure/test_mastery_graph_store.py) | 5 测试 |
| 🆕 [tests/unit/harness/test_mastery_graph.py](tests/unit/harness/test_mastery_graph.py) | 12 测试 |
| 🆕 [tests/unit/harness/test_user_profile.py](tests/unit/harness/test_user_profile.py) | 5 测试 |
| 🆕 [tests/unit/agents/test_curator.py](tests/unit/agents/test_curator.py) | 13 测试 |

---

## 4. Wave 1 · Plan C：教学与编排（进行中）

**用途**：Tutor/Critic/Conductor Agent + Orchestrator 规则引擎 + 回合屏障 + TeachingPolicy + 主图接入。

### 4.1 已落地文件（截至本盘点时）

| 路径 | 职责 |
|------|------|
| 🆕 [app/agents/tutor.py](app/agents/tutor.py) | Tutor Agent：教学生成（讲解/提问/发起复述/类比） |
| 🆕 [app/agents/critic.py](app/agents/critic.py) | Critic Agent：只判文本语义（MasteryAssessed/ConfusionDetected/...） |
| 🆕 [tests/unit/agents/test_tutor.py](tests/unit/agents/test_tutor.py) | Tutor 单测 |
| 🆕 [tests/unit/agents/test_critic.py](tests/unit/agents/test_critic.py) | Critic 单测 |
| 🆕 [tests/unit/agents/test_mock_llm_fixture.py](tests/unit/agents/test_mock_llm_fixture.py) | LLM Mock 公用 fixture |

### 4.2 计划但未落地（Plan C 待补）

| 路径 | 职责 |
|------|------|
| ⏳ `app/agents/conductor.py` | Conductor Agent：规则未覆盖时 LLM 兜底，只能基于已有观察路由 |
| ⏳ `app/harness/orchestrator.py` | 事件路由器（RuleEngine + Conductor 召唤 + 回合屏障实现） |
| ⏳ `app/harness/teaching_policy.py` | 融合循环状态机（§4.2 转移表） |
| ⏳ `app/orchestration/orchestrator_rules.yaml` | 规则 DSL |
| ⏳ `app/orchestration/graph.py` 的 `_collab_loop_node` 实装 | 接入 EventBus + 5 Agent |

---

## 5. Wave 2（待开始）

### 5.1 Plan D 集成与灰度（待开始）

修改：
- `app/api/chat.py` / `chat_stream.py` — feature flag 切换新/老栈
- `app/orchestration/graph.py` 的 `_collab_loop_node` — 装配 EventBus + 5 Agent + Orchestrator

### 5.2 Plan E 评估体系（待开始）

新建目录：
- `app/eval/{kernel, component_bench, system_bench, collaboration_bench, ab_controller, selection_reporter}.py`
- `app/eval/scenarios/` — 场景 YAML
- `app/eval/fixtures/` — 部件测试用例
- `tests/golden/` — 黄金集（双人标注 + Cohen's κ）
- `tests/eval/` — 评估体系 TDD

---

## 6. 老栈 — 全部待下线（P9 删除），重构期严禁修改

### 6.1 老编排（app/agent/）

```
app/agent/
├── graph.py              — 14 节点主图（旧）
├── routers.py            — 条件边
├── node_wrapper.py       — safe_node 装饰器
├── spec_decorator.py     — @with_spec 装饰器
├── spec_loader.py        — 渐进式 prompt 加载（保留至 specs 体系迁移）
├── nodes/                — 14 个薄壳节点（参考改造源）
│   ├── route_intent.py   → 改造为 orchestration/routers.py
│   ├── history_check.py  → 进 Tutor/Curator
│   ├── knowledge_retrieval.py + evidence_gate.py + rag_first.py
│   │                     → 改造为 agents/retriever.py（已完成）
│   ├── diagnose.py + explain.py + restate_check.py + followup.py + answer_policy.py
│   │                     → 改造为 agents/tutor.py + agents/critic.py（进行中）
│   ├── evaluate.py       → 进 agents/critic.py（进行中）
│   ├── summarize.py      → 进 graph.wrap_up
│   ├── recovery.py       → 错误回退（暂留）
│   └── replan.py         → 主题切换（→ 进 Orchestrator）
├── multi_agent/          — 4 个 SubGraph（全部废弃）
│   ├── orchestrator_graph.py  → 已被 harness/orchestrator.py 取代（Plan C）
│   ├── teaching_graph.py      → 已被 5 Agent 取代
│   ├── retrieval_graph.py     → 已被 agents/retriever.py 取代
│   ├── eval_graph.py          → 已被 Plan E 取代
│   ├── routers.py / state.py  → 废弃
└── system_eval/          — 旧评估子图（全部废弃，Plan E 重写）
    └── eval_graph.py / orchestrator_eval.py / teaching_eval.py
```

### 6.2 老规范（app/agent/specs/，保留参考）

```
specs/
├── _root.md / .prompt.md      — 全局规则（迁移到新栈待 Plan C 完成后）
├── intent_map.yaml            — 待重写为 event_map.yaml
├── agents/                    — teaching/eval/retrieval/orchestrator (4 个，需重写为 5 个新角色)
└── prompts/                   — 14 个节点指令（需对应新栈 Agent 内部 step 重写）
```

### 6.3 老 harness 文件（保留复用）

| 路径 | 是否新栈使用 | 说明 |
|------|-------------|------|
| 📛 [app/harness/memory.py](app/harness/memory.py) | ✅ 复用 L1/L2 | 三层记忆的下两层，新栈直接复用 |
| 📛 [app/harness/observability.py](app/harness/observability.py) | ⏳ Plan D 扩展 EventSink | 现有 trace/llm_span/metric/session_summary 保留 |
| 📛 [app/harness/intent_router.py](app/harness/intent_router.py) | ⏳ orchestration/routers.py 可调用 | 规则优先 + LLM 兜底，新栈 route 节点可复用 |
| 📛 [app/harness/error_handler.py](app/harness/error_handler.py) | ✅ 复用 | 错误分类与恢复策略，全栈通用 |
| 📛 [app/harness/guardrails.py](app/harness/guardrails.py) | ✅ 复用 | 输入/工具/输出护栏 |
| 📛 [app/harness/tool_registry.py](app/harness/tool_registry.py) | ✅ 复用 | 工具注册 |
| 📛 [app/harness/state_manager.py](app/harness/state_manager.py) | ⚠️ 评估 | 老的 LearningState 管理器，新栈用 WorkspaceState，待评估去留 |
| 📛 [app/harness/state/](app/harness/state/) | ⛔ 待下线 | 老的分层状态模型（LearningState/RoutingState/TeachingState/...），随 P9 删除 |

### 6.4 老 infrastructure（大多保留）

| 路径 | 状态 |
|------|------|
| 📛 [app/infrastructure/llm.py](app/infrastructure/llm.py) | ✅ 复用 — LLMService 已就绪，Plan C 各 Agent 直接调用 |
| 📛 [app/infrastructure/storage/session_store.py](app/infrastructure/storage/session_store.py) | ✅ 复用 — 会话存储 |
| 📛 [app/infrastructure/storage/user_store.py](app/infrastructure/storage/user_store.py) | ✅ 复用 — 用户存储 |
| 📛 [app/infrastructure/storage/eval_store.py](app/infrastructure/storage/eval_store.py) | ⚠️ Plan E 评估 — 老评估存储，Plan E 可能取代 |
| 📛 [app/infrastructure/storage/knowledge_store.py](app/infrastructure/storage/knowledge_store.py) | ✅ 复用 — 知识库元数据 |
| 📛 [app/infrastructure/storage/memory_store.py](app/infrastructure/storage/memory_store.py) | ✅ 复用 — L2 文本记忆后端 |
| 📛 [app/infrastructure/extraction/](app/infrastructure/extraction/) | ⚠️ 与 rag/extractors/ 重叠 — Plan A 在 rag/ 下重新实现了 PDF/DOCX/TXT，老的可考虑下线 |
| 📛 [app/infrastructure/external/](app/infrastructure/external/) | ⚠️ OCR 重叠 — Plan A 在 rag/ocr.py 重新实现，老的 external/ocr.py 可下线 |

### 6.5 老 API（待 Plan D 切换）

```
app/api/
├── auth.py            — 认证，不动
├── chat.py            — ⏳ 待 feature flag 切新栈
├── chat_stream.py     — ⏳ 待 feature flag 切新栈
├── chat_multi.py      — ⛔ 老 multi_agent 路由，待 P8/P9 下线
├── eval.py            — ⏳ Plan E 重写
├── knowledge.py       — ✅ 保留，可能加 OCR/code 上传
├── profile.py         — ⏳ Plan B 之后可暴露 MasteryGraph 查询
├── sessions.py        — ✅ 保留
└── errors.py          — ✅ 保留
```

---

## 7. 测试目录结构

```
tests/
├── conftest.py                            — 复用
├── api/                                   — 老 API 测试，复用
├── integration/                           — 集成测试，保留
└── unit/
    ├── agent/                             — 📛 老栈测试（10 文件），保留至 P9
    │   ├── test_full_teach_loop.py
    │   ├── test_minimal_graph.py
    │   ├── test_multi_agent.py
    │   ├── test_qa_direct_branch.py
    │   ├── test_route_intent.py
    │   ├── test_spec_decorator.py
    │   ├── test_spec_loader.py
    │   ├── test_system_eval.py
    │   └── test_teach_loop_nodes.py
    ├── agents/                            — 🆕 新栈 Agent 测试
    │   ├── test_agent_base.py             (Plan 0)
    │   ├── test_retriever.py              (Plan A)
    │   ├── test_curator.py                (Plan B)
    │   ├── test_tutor.py                  (Plan C)
    │   ├── test_critic.py                 (Plan C)
    │   └── test_mock_llm_fixture.py       (Plan C 共用)
    ├── api/                               — 复用
    │   └── test_api.py
    ├── harness/                           — 混合
    │   ├── test_enums.py                  (Plan 0 扩展过)
    │   ├── test_events.py                 🆕 (Plan 0)
    │   ├── test_eventbus.py               🆕 (Plan 0)
    │   ├── test_workspace_state.py        🆕 (Plan 0)
    │   ├── test_mastery_graph.py          🆕 (Plan B)
    │   ├── test_user_profile.py           🆕 (Plan B)
    │   ├── test_memory.py                 📛 复用
    │   ├── test_state.py                  📛 复用 (老 state/)
    │   ├── test_state_manager.py          📛 复用
    │   ├── test_observability.py          📛 复用
    │   ├── test_intent_router.py          📛 复用
    │   ├── test_error_handler.py          📛 复用
    │   ├── test_guardrails.py             📛 复用
    │   └── test_tool_registry.py          📛 复用
    ├── infrastructure/                    — 混合
    │   ├── test_event_store.py            🆕 (Plan 0)
    │   ├── test_mastery_graph_store.py    🆕 (Plan B)
    │   ├── test_rag.py                    🔄 (Plan A 扩展)
    │   ├── test_ocr.py                    🆕 (Plan A)
    │   ├── test_code_index.py             🆕 (Plan A)
    │   ├── test_extractors.py             🆕 (Plan A)
    │   ├── test_memory_store.py           📛 复用
    │   ├── test_stores.py                 📛 复用（⚠️ pre-existing 顺序敏感问题）
    │   └── test_llm.py                    📛 复用
    ├── orchestration/                     — 🆕 全部新建
    │   ├── test_collab_loop.py            (Plan 0)
    │   └── test_graph.py                  (Plan 0)
    └── test_prompts.py                    📛 复用
```

---

## 8. 依赖图（新栈内部）

```
                  ┌───────────────────────────────────┐
                  │  events.py + enums.py             │ ← Plan 0 根契约
                  │  workspace_state.py               │
                  └───────────────────────────────────┘
                              │ (frozen)
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
   ┌─────────┐         ┌──────────────┐      ┌──────────────┐
   │ base.py │         │ eventbus.py  │      │ event_store  │
   │(AgentBase)        │              │      │              │
   └────┬────┘         └──────┬───────┘      └──────────────┘
        │                     │
        │                     ▼
        │              ┌─────────────────────┐
        │              │ collab_loop.py      │
        │              │ orchestration/      │
        │              └─────────────────────┘
        │
        ├──────────────────────┬──────────────────────┬───────────────────┐
        ▼                      ▼                      ▼                   ▼
   ┌──────────┐         ┌──────────────┐      ┌──────────────┐    ┌──────────┐
   │ retriever │  PlanA │   curator    │ PlanB│ tutor/critic │PlanC│conductor │PlanC
   │           │        │              │      │              │    │          │
   └─────┬─────┘        └──────┬───────┘      └──────┬───────┘    └──────────┘
         │                     │                     │
         ▼                     ▼                     ▼
   ┌──────────────┐   ┌──────────────────────┐  ┌──────────────────┐
   │rag/coordinator│   │ mastery_graph       │  │  llm.py (复用)   │
   │ + providers  │   │ + user_profile      │  └──────────────────┘
   │ + extractors │   │ + mastery_graph_    │
   └──────────────┘   │   store              │
                     └──────────────────────┘
```

---

## 9. 整理建议（按下线时序）

### Phase 1 — 现在（Wave 1 仍在做）

- ✅ **保持 `app/agent/` 完全只读**，不能删任何文件，避免老栈 API/测试断裂
- ✅ **新代码只写新目录**：`app/agents/` `app/orchestration/` 以及 `app/harness/` `app/infrastructure/` 下的新文件
- ⚠️ **重叠模块标记**：
  - `app/infrastructure/external/ocr.py` ↔ `app/infrastructure/rag/ocr.py` — Plan A 已重写，老的暂留
  - `app/infrastructure/extraction/` ↔ `app/infrastructure/rag/extractors/` — Plan A 已重写，老的暂留

### Phase 2 — Plan C 完成后

- 把 `app/agent/multi_agent/` 与 `app/agent/system_eval/` 标记为 deprecated（文件顶 docstring）
- API 层在 `chat.py` / `chat_stream.py` 加 feature flag 条件 import

### Phase 3 — Plan D 灰度后

- 灰度成功 → `app/api/chat_multi.py` 下线
- 评估指标对齐 → 老 `app/agent/system_eval/` 下线

### Phase 4 — P9 全量下线

- 删除整个 `app/agent/` 目录
- 删除 `tests/unit/agent/`（10 个测试文件）
- 删除 `app/harness/state/`（老分层 state）
- 评估 `app/harness/state_manager.py` 是否仍需要
- 评估 `app/infrastructure/external/` 是否仍需要
- 评估 `app/infrastructure/extraction/` 是否仍需要

---

## 10. 当前测试基线

| 类别 | 数量 |
|------|------|
| 老栈 unit/agent/ | ~21 测试（10 文件） |
| 老栈 harness/infrastructure 复用部分 | ~100 测试 |
| Wave 0 新增 | ~30 测试 |
| Plan A 新增 | ~68 测试 |
| Plan B 新增 | 35 测试 |
| Plan C 新增（截至现在） | ~25 测试 |
| **全量 pytest passed** | 258（顺序无关跑） |

**已知问题**：`tests/unit/infrastructure/test_stores.py` 4 个测试在全量跑时失败，单独跑通过 — pre-existing baseline 顺序敏感问题（老测试用 `asyncio.get_event_loop().run_until_complete()`，与新 `asyncio.run()` 冲突）。不归本轮重构修复，建议主窗口统筹。

---

## 附录：本轮重构涉及的全部脚本计数

| 类别 | 数量 |
|------|------|
| 🆕 新建源码（含 __init__.py 不计） | 22 |
| 🔄 扩展老源码 | 2（enums.py + rag/coordinator.py） |
| 📛 复用老源码（明确依赖） | ~20 |
| ⛔ 待下线老源码 | ~35（app/agent/ 全部 + 部分 harness 老文件） |
| 🆕 新建测试 | 17 |
| 📛 复用老测试 | ~25 |
