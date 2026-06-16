# app_old 旧代码迁移与保留清单

> **目标**：把「2026-05-29 之前的旧代码」迁移到新建的 `app_old/`，同时保留重构期间对旧代码的必要修改，以及全部新代码。
> **方法**：三轮识别（不动文件）→ 统一执行迁移。本文件为唯一事实来源，随每轮追加。
> **进度**：第一轮 ✅ · 第二轮 A/B/C ✅ · 第三轮（修改必要性复核，§四）✅ · **迁移执行 ✅**（策略 (a)，见 §五；零回归 362 passed / 4 预存失败）
> **最后更新**：2026-06-02

---

## 一、第一轮：旧代码边界与重构修改识别（基于 git 事实）

### 1.1 时间边界

- **旧代码基线 = 提交 `c3318ce`（2026-05-14）**，正好是 `feat/core-redesign-observability-memory-llm` 分支的 tip。
- 2026-05-29 的两个提交（`7dc4058`、`af8f73f`）**仅为重设计的设计文档**，不含脚本 → 符合「5 月 29 日之前的脚本都是旧代码」。
- 2026-06-01 起（`11ef599` → `63fb13c`）为**新重构代码**（Plan 0 / A / B / C 多 Agent 体系）。
- 整个重构期间 `c3318ce → HEAD`：**无删除（D）、无改名（R）**，只「新增（A）+ 少量修改（M）」。
- `app_old/` 尚未创建。

### 1.2 重构修改过的旧文件 —— 仅 6 个（修改必须保留）

| 旧文件 | 改动量 | 改动性质（必须保留的内容） |
|--------|--------|------------------------------|
| `app/harness/enums.py` | +69 | **纯追加**：末尾新增 4 个枚举类 `EventType`/`EventSource`/`TeachingMode`/`ActionKind`（服务多 Agent 重设计），旧枚举 `EvalMetric` 等一行未动 |
| `app/infrastructure/rag/coordinator.py` | +139 / -10 | **向后兼容扩展**：新增 `Chunk`/`SearchResult`/`IndexProvider` + 多源 `search()`；旧 `retrieve()`/`index_documents()` 接口与返回格式保留 |
| `tests/conftest.py` | +16 | 追加新 fixture（`mock_llm_invoke_json` 等） |
| `tests/unit/harness/test_enums.py` | +33 | 追加 4 个新枚举类的测试 |
| `tests/unit/infrastructure/test_rag.py` | +126 | 追加多源检索测试 |
| `README.md` | +32 | 文档进度更新 |

> **关键难点**：除这 6 个文件外，旧/新代码都是「整文件级别」干净可分（要么纯旧、要么纯新）；唯独这 6 个文件**旧代码与新代码纠缠在同一文件内**，新代码依赖其中的新增部分，无法整体移入 `app_old/`。第三轮要清理的「旧脚本内不必要修改代码块」主要落在这里。

### 1.3 旧代码总览（迁移候选 → `app_old/`）

`c3318ce` 已存在且**未被重构改动**的纯旧代码（按模块）：

- **app/agent/**（单数，旧 LangGraph 架构）：`graph.py`、`routers.py`、`node_wrapper.py`、`spec_decorator.py`、`spec_loader.py`、`nodes/*`(15)、`multi_agent/*`(6)、`system_eval/*`(4)
- **app/api/**：`auth/chat/chat_multi/chat_stream/errors/eval/knowledge/profile/sessions`
- **app/core/**：`config/database/prompts`
- **app/harness/**（除 `enums.py`）：`error_handler/guardrails/intent_router/memory/observability/state_manager/tool_registry`、`state/*`(6)
- **app/infrastructure/**（除 `rag/coordinator.py`）：`llm.py`、`external/*`、`extraction/*`、`rag/store.py`、`rag/__init__.py`、`storage/*`(旧 5 个)
- **app/models/**、**app/ui/**、**app/worker/**、`app/main.py`
- **tests/** 中对应的旧测试

> 注意：上面是「候选」。其中部分旧文件被新代码当作依赖**仍在使用**（见第二轮逐 Plan 标注），这类必须保留在 `app/`，不能盲目搬走。

### 1.4 新增代码（重构产物，留在 `app/`，不迁移）

`app/agents/*`(7) · `app/orchestration/*`(3) · `app/harness/` 新增 `eventbus/events/mastery_graph/user_profile/workspace_state` · `app/infrastructure/rag/` 新增 `code_index/ocr/extractors/*` · `app/infrastructure/storage/` 新增 `event_store/mastery_graph_store` · 对应新测试 · `docs/superpowers/*`、`superpowers/*`、`Learned/*`。

### 1.5 依赖清单状态

`pyproject.toml` / `uv.lock` 在 `c3318ce → HEAD` 之间**完全未变动**。新 RAG provider 引入的外部库未登记（详见 2.A 依赖库缺口）。

---

## 二、第二轮：按 Plan 阶段的「保留 / 迁移」判定

> 来源：用户逐阶段提供的清单 + 与第一轮 git 事实交叉核对。本轮仍**不修改、不移动**任何文件。

### 2.A Plan A（检索与知识库）✅

#### A-1 Plan A 新代码 → 全部保留在 `app/`（9 源码 + 6 测试 + 2 文档）

| 文件 | git | 备注 |
|------|-----|------|
| `app/agents/retriever.py` | A 新增 | `RetrieverAgent`, `LOW_SCORE_THRESHOLD=0.3` |
| `app/infrastructure/rag/coordinator.py` | **M 修改** | 纠缠文件：旧 `RAGCoordinator` 被扩展，新增协议三件套 + 多源 `search()`，整文件留 `app/` |
| `app/infrastructure/rag/ocr.py` | A 新增 | `OCRProvider` |
| `app/infrastructure/rag/code_index.py` | A 新增 | `CodeIndexProvider`（仅标准库 ast/glob/os） |
| `app/infrastructure/rag/extractors/__init__.py` | A 新增 | 包声明 |
| `app/infrastructure/rag/extractors/base.py` | A 新增 | `Extractor`, `get_extractor()` |
| `app/infrastructure/rag/extractors/text_extractor.py` | A 新增 | `TextExtractor` |
| `app/infrastructure/rag/extractors/pdf_extractor.py` | A 新增 | `PDFExtractor` |
| `app/infrastructure/rag/extractors/docx_extractor.py` | A 新增 | `DocxExtractor` |
| `tests/unit/infrastructure/test_rag.py` | **M 修改** | 追加多源检索测试 |
| `tests/unit/infrastructure/test_ocr.py` | A 新增 | |
| `tests/unit/infrastructure/test_code_index.py` | A 新增 | |
| `tests/unit/infrastructure/test_extractors.py` | A 新增 | |
| `tests/unit/agents/test_retriever.py` | A 新增 | |
| `tests/integration/test_retriever_integration.py` | A 新增 | |
| `docs/superpowers/plans/2026-06-01-plan-a-retrieval.md` | A 新增 | 实施计划 |
| `README.md` | **M 修改** | 追加 Plan A 进度段落 |

#### A-2 Plan A 依赖的旧文件 → 真·旧文件，**保留在 `app/` 不迁移**（被新代码实时复用）

| 旧文件 | git | Plan A 怎么用 → 为何不能搬走 |
|--------|-----|------------------------------|
| `app/infrastructure/rag/store.py` | 旧[未改] | `FakeRAGStore` 是三个 IndexProvider（`_VectorStoreProvider`/`OCRProvider`/`CodeIndexProvider`）的存储后端，新代码运行时强依赖 |
| `app/infrastructure/rag/__init__.py` | 旧[未改] | 空包声明，rag 包结构所需 |
| `app/harness/enums.py` | 旧[**M**] | 纠缠文件（见 1.2）：Plan A 用到的 `EventType.ACTION_REQUESTED/RETRIEVED_EVIDENCE/RETRIEVAL_FAILED`、`EventSource.RETRIEVER/ORCHESTRATOR`、`ActionKind.RETRIEVER_SEARCH/RETRIEVER_EXPAND_QUERY` 全在 Plan 0 追加的新枚举里，整文件留 `app/` |

#### A-3 清单中被列为「旧依赖」但实为 Plan 0 新代码 → 留 `app/`（非旧代码，勿误判）

> 交叉核对修正：Plan A 清单「必须保留的 9 个旧依赖」里，下列 6 个在 git 中是 **2026-06-01 新增（A）**，属于重构新代码，并非旧代码。它们是 Plan 0 冻结接口，Plan A 仅调用不修改。

`app/agents/base.py` · `app/harness/events.py` · `app/harness/workspace_state.py` · `app/harness/eventbus.py` · `app/orchestration/collab_loop.py` · `app/infrastructure/storage/event_store.py`

#### A-4 Plan A 取代的旧 stub → **迁移候选（→ `app_old/`）**

| 旧文件 | git | 替代品 | 说明 |
|--------|-----|--------|------|
| `app/infrastructure/external/ocr.py` (5 行) | 旧[未改] | `app/infrastructure/rag/ocr.py` | spec §7 标注「提升为正式管道」；Plan A 未 in-place 改，新写后废弃旧 stub |
| `app/infrastructure/extraction/file_extract.py` (14 行) | 旧[未改] | `app/infrastructure/rag/extractors/` | 同上 |

> 这两个是 Plan A 范围内**唯一**的真·旧迁移候选。第三轮确认其无其他引用后再迁移/清理。

#### A-5 依赖库缺口（⚠ 需在第二轮「依赖清单」中处理）

Plan A 新文件以惰性 import 引入了 **`pyproject.toml` 未声明**的外部库：

| 文件 | 用到的库 | pyproject 状态 |
|------|----------|----------------|
| `extractors/pdf_extractor.py` | `pdfplumber`、`PyPDF2` | ❌ 未声明 |
| `extractors/docx_extractor.py` | `python-docx`（`from docx import Document`） | ❌ 未声明 |
| `rag/ocr.py` | `pytesseract`、`Pillow`（PIL） | ❌ 未声明 |
| `rag/code_index.py` | 仅标准库 ast/glob/os | ✅ 无需 |

> 现有 `[project.optional-dependencies].rag` 只含 llama-index / chromadb 系列，不含上述 5 个解析库。迁移完成后应补登记（建议放入 `rag` extra 或新增 `extract`/`ocr` extra）。

### 2.B Plan B（记忆与画像）✅

> 来源：`docs/superpowers/refactor-script-inventory.md` 第 3 章
> git 交叉核对：以下 4 源码 + 4 测试**全部为 `c3318ce` 后新文件**，在旧基线中不存在

#### B-1 Plan B 新代码 → 全部保留在 `app/`（4 源码 + 4 测试）

| 文件 | 职责 | 依赖（全部为新栈文件） |
|------|------|---------|
| `app/infrastructure/storage/mastery_graph_store.py` | aiosqlite 持久化：3 张表 + CRUD 8 方法 | 标准库 only |
| `app/harness/mastery_graph.py` | MasteryNode/Edge + MasteryGraph 引擎 + 置信度加权 find_weak_prereqs | `mastery_graph_store`（本阶段新文件） |
| `app/harness/user_profile.py` | UserProfile dataclass | `mastery_graph_store` |
| `app/agents/curator.py` | Curator Agent（双时机渐进启用） | `base.py`, `events`, `enums`, `workspace_state`, `mastery_graph` |
| `tests/unit/infrastructure/test_mastery_graph_store.py` | 5 测试 | |
| `tests/unit/harness/test_mastery_graph.py` | 12 测试 | |
| `tests/unit/harness/test_user_profile.py` | 5 测试 | |
| `tests/unit/agents/test_curator.py` | 13 测试 | |

#### B-2 Plan B 复用的旧文件（不改） → **保留在 `app/` 不迁移**

| 旧文件 | 关系 | 说明 |
|--------|------|------|
| `app/harness/memory.py` | L1/L2 记忆 — Plan B 的 MasteryGraph/UserProfile 是 **L3 层与 L1/L2 并列**，非扩展 | 老栈记忆体系仍在使用 |
| `app/infrastructure/storage/memory_store.py` | L2 后端 | |

### 2.C Plan C（教学与编排）✅

> 来源：`docs/superpowers/plans/2026-06-01-plan-c-teaching-orchestration.md`（19 Task TDD）
> git 交叉核对：本阶段 19 个 commit（`c4c6d74` → `bdad167`）。下列源码相对旧基线 `c3318ce` 均为新增（A）；唯 `enums.py` / `conftest.py` 为纠缠修改（M，见 1.2），`graph.py` 为 Plan 0 新增、Plan C 改其 `_collab_loop_node`。

#### C-1 Plan C 新代码 → 全部保留在 `app/`（5 源码 + 1 规则 + 8 测试 + 3 文档）

| 文件 | git | 备注 |
|------|-----|------|
| `app/agents/tutor.py` | A 新增 | `TutorAgent`：生成类教学动作（ASK/PROBE_PREREQ/EXPLAIN/RE_EXPLAIN/CORRECT/REQUEST_RECAP/OFFER_ANALOGY），按 `payload.target==tutor` 过滤 |
| `app/agents/critic.py` | A 新增 | `CriticAgent`：文本语义评估，单次 LLM 拆多观察（Mastery/Confusion/Contradiction/LowConfidence/RAGQuality），复述检查归此（#15）、RAG 质量仅 `purpose=teaching`（#18）|
| `app/agents/conductor.py` | A 新增 | `ConductorAgent`：只 emit `ConductorDecided`（不直接发 ActionRequested），观察不足→`REQUEST_OBSERVATION`（#16）|
| `app/harness/teaching_policy.py` | A 新增 | `TeachingPolicy` + `ObservationSet`：§4.2 完整状态转移表 + 模式历史；纯函数状态机，无 LLM、无事件订阅 |
| `app/harness/orchestrator.py` | A 新增 | `RuleEngine` + `load_rules` + `Orchestrator`：规则引擎 + 回合屏障（OrchestratorTick 哨兵）+ Conductor 召唤 + ConductorDecided 转译；`on_event(event, ws)` 钩子接入 `run_collab_loop` |
| `app/orchestration/orchestrator_rules.yaml` | A 新增 | §3.4 规则 DSL（9 条，priority 降序，含 default→conductor_decide 兜底）|
| `app/orchestration/graph.py` | A（Plan 0）/ **M（Plan C）** | 纠缠点 ≠ 旧文件：整文件属新栈（Plan 0 建）。Plan C 改 `_collab_loop_node` 接入 `run_collab_loop` + 新增 `CollabRuntime` / `build_collab_runtime` / `_TolerantSerde`（绕 LangGraph 对运行时对象的序列化限制）；零参数 `build_main_graph()` 行为保持 Plan 0 兼容 |
| `tests/unit/agents/test_tutor.py` | A 新增 | 11 测试（7 动作 + 越权防御）|
| `tests/unit/agents/test_critic.py` | A 新增 | 11 测试（多观察拆分 + RAG teaching-only + 越权）|
| `tests/unit/agents/test_conductor.py` | A 新增 | 7 测试（观察足够/不足两分支 + 越权）|
| `tests/unit/agents/test_mock_llm_fixture.py` | A 新增 | `mock_llm_invoke_json` fixture 自测（决策 #22）|
| `tests/unit/harness/test_teaching_policy.py` | A 新增 | 19 测试（§4.2 全转移 + 优先级 + 熔断）|
| `tests/unit/harness/test_orchestrator.py` | A 新增 | 19 测试（规则匹配 + Tick 裁决 + **回合屏障专项** + Conductor 转译）|
| `tests/unit/orchestration/test_graph_collab_loop_integration.py` | A 新增 | 2 测试（运行时工厂 + 节点接入；Plan 0 graph 测试保持全绿）|
| `tests/integration/test_plan_c_e2e_scenario.py` | A 新增 | 端到端复现 spec §4.3（Socratic→Feynman→Analogy→mastered→LoopExit）|
| `docs/superpowers/plans/2026-06-01-plan-c-teaching-orchestration.md` | A 新增 | 实施计划（7 Phase / 19 Task）|
| `Learned/多Agent重设计-Spec审阅与架构决策.md` | **M 修改** | 追加 #22（LLM Mock 策略：fixture+monkeypatch）|
| `README.md` | **M 修改** | 追加 Plan C 进度段（纠缠文件，见 1.2）|

#### C-2 Plan C 依赖的旧文件 → 真·旧文件，**保留在 `app/` 不迁移**（被新代码实时复用）

| 旧文件 | git | Plan C 怎么用 → 为何不能搬走 |
|--------|-----|------------------------------|
| `app/infrastructure/llm.py` | 旧[**未改**] | `LLMService.invoke_json` 被 **Tutor / Critic / Conductor 三个 Agent 实时调用**（构造默认 `LLMService()`）。c3318ce 后零改动 = 纯旧文件，新代码运行时强依赖，留 `app/` |
| `app/harness/enums.py` | 旧[**M**] | 纠缠文件（见 1.2）：Critic 用的 `MasteryLevel` 是**旧枚举**，`EventType`/`EventSource`/`ActionKind`/`TeachingMode` 是 Plan 0 追加段。新旧枚举在同文件、新代码依赖新增段，整文件留 `app/` |

#### C-3 清单中像「旧依赖」但实为 Plan 0 新代码 → 留 `app/`（非旧代码，勿误判，同 A-3）

> Plan C 大量 import 下列文件，但它们在 git 中是 **2026-06-01 Plan 0 新增（A）**，属重构新代码、是冻结接口，Plan C 仅调用不修改。**勿当旧依赖迁走**。

`app/agents/base.py`（AgentBase）· `app/harness/events.py`（Event/白名单/优先级）· `app/harness/workspace_state.py` · `app/harness/eventbus.py` · `app/orchestration/collab_loop.py`（`run_collab_loop`）。
间接依赖（经 eventbus/collab_loop，Plan C 不直接 import）：`app/infrastructure/storage/event_store.py`。

#### C-4 Plan C 功能取代的旧文件 → **随 `app/agent/` 整体 P9 下线（非本阶段独立迁移候选）**

> 与 A-4 区分：A-4 取代的是 `app/infrastructure/` 下的独立旧 stub（本阶段独立迁移候选）；Plan C 取代的旧文件全部属于 `app/agent/` 老栈整体，会随 1.3 的「app/agent/ 全部」在 P9 统一下线（spec §1.2 重构期只读不改）。此处仅登记**功能取代映射**，本阶段**不迁移、不删除、不修改**。

| 新文件（保留） | 功能取代的旧文件（随 app/agent/ 下线） | 取代性质 |
|----------------|------------------------------------------|----------|
| `app/agents/tutor.py` | `app/agent/nodes/{diagnose, explain, followup, answer_policy}.py` | 生成类教学动作 |
| `app/agents/critic.py` | `app/agent/nodes/{evaluate, restate_check}.py` | 评估类（复述检查归 Critic，#15）|
| `app/harness/orchestrator.py` | `app/agent/multi_agent/orchestrator_graph.py` | 编排：SubGraph 条件边 → 事件路由器 + 规则引擎 |
| `app/harness/teaching_policy.py` | `app/agent/multi_agent/teaching_graph.py` | 教学状态机：隐式图 → §4.2 显式转移表 |
| `app/orchestration/graph.py`（`_collab_loop_node`）| `app/agent/graph.py` 的多节点教学编排 | 主图：14 节点 → 4 节点骨架 + 协作环 |

#### C-5 依赖库缺口（⚠ 需在迁移执行时补登记，同 A-5）

| 文件 | 用到的库 | pyproject 状态 |
|------|----------|----------------|
| `app/harness/orchestrator.py` | `pyyaml`（`import yaml`）| ❌ **未显式声明** —— 当前经 `langfuse` 等传递依赖间接可用，但应显式登记到 `pyproject.toml`（建议入主依赖，规则文件是核心运行时路径）|

> `app/orchestration/graph.py` 用 `langgraph` —— 旧栈已声明的项目主依赖，非缺口。

### 2.E 老栈文件「证据化」处置裁决（统筹 A/B/C 后的**全库**消费者实测）

> 把 §1.3 笼统的「部分旧文件被新代码使用」升级为 **grep 全库实测消费者表**。判据＝「**新栈是否真的（含传递）import 它**」。结果修正了 `refactor-script-inventory.md` §6.3 多处乐观的「✅复用」标注。
> ⚠ **方法学订正**：本表用的正则为 `(from|import)\s+app\.harness\.<mod>\b`，对 `app/`+`tests/` 全量扫描。早前一版漏扫 `tests/` 且正则缺陷（`import.*memory` 抓不到 `from ...memory import`），导致误判 `memory.py` 等「零消费者」，现已纠正。

| 老文件 | 新栈(app)消费 | 老栈 app/agent 消费 | 其他 app 消费 | **证据化裁决** |
|--------|:-:|:-:|------|------|
| `app/infrastructure/llm.py` | **3**（tutor/critic/conductor）| 7 | — | **必留 app/**（见 C-2）|
| `app/harness/observability.py` | **传递**（`llm.py` 惰性 import `get_observability`/`LLMSpan`）| 1（node_wrapper）| `llm.py` | ⚠**改判：必留 app/** —— 经 `llm.py` 被新栈传递依赖，原「随老栈迁移」错误 |
| `app/infrastructure/rag/store.py` | ✅（Plan A 3 providers + coordinator）| — | `rag/coordinator.py` | **必留 app/**（见 A-2）|
| `app/infrastructure/rag/__init__.py` | ✅（包结构）| — | — | **必留 app/** |
| `app/harness/enums.py`(M) / `rag/coordinator.py`(M) | ✅纠缠 | — | — | **必留 app/**（§1.2）|
| `app/harness/memory.py` | 0 | 0 | `memory_store.py` | **改判**：与 `memory_store.py` 互引的**自洽休眠子系统**（仅彼此+自测用，两栈均不调）→ 整子系统迁移候选 |
| `app/infrastructure/storage/memory_store.py` | 0 | 0 | （仅 `test_memory_store`）| 同上，随 memory 子系统迁移 |
| `app/harness/intent_router.py` | 0 | 1（route_intent）| — | 仅老栈用 → 随 `app/agent/` 迁移 |
| `app/harness/error_handler.py` | 0 | 1（node_wrapper）| — | 仅老栈用 → 随 `app/agent/` 迁移 |
| `app/harness/guardrails.py` | 0 | 0 | — | 仅自测引用 → 迁移候选 |
| `app/harness/tool_registry.py` | 0 | 0 | — | 仅自测引用 → 迁移候选 |
| `app/harness/state_manager.py` | 0 | 0 | — | 仅自测引用 → 迁移候选 |
| `app/harness/state/`（整包 6 文件）| 0 | **20** | — | ✅ 随 `app/agent/` 迁移 |
| `app/infrastructure/external/`（含 ocr.py）| 0 | 0 | — | 迁移候选（A-4 已含 ocr.py）|
| `app/infrastructure/extraction/`（含 file_extract.py）| 0 | 0 | — | 迁移候选（A-4 已含 file_extract.py）|

> **统筹结论（已修正）**：新栈对**旧代码**的真实依赖闭包**恰好 6 处** —— `llm.py`(C-2) → 传递 `observability.py` · `rag/store.py`(A-2) · `rag/__init__.py` · 纠缠的 `enums.py`/`coordinator.py`(§1.2)。**这 6 个必留 `app/`**；inventory 标「复用」的其余 harness 文件（memory/guardrails/tool_registry/state_manager/intent_router/error_handler/state）均**不被新栈依赖**，属迁移候选或随老栈迁移，**不阻断新栈**。
> ⚠ **修正 B-2**：B-2 称 `memory.py` 老栈仍用 —— 实测老栈 `app/agent/` 也不用，仅 `memory_store.py` 与自测引用。`memory.py`+`memory_store.py` 为休眠子系统，第三轮确认后随老栈迁移。

---

## 三、迁移执行计划（已选策略 (a)，✅ 已执行 —— 见 §五 执行记录）

### 3.0 ⚠ 核心约束：老栈 `app/agent/` 仍是「生产活路径」，迁移 ≠ 简单 `git mv`

双向依赖实测：

- **新栈 → 老栈：零依赖** —— `app/agents/`·`app/orchestration/`·新 harness 对 `app.agent.*` 零引用 ✅ 可整体迁移
- **老栈 → 新栈：零污染** —— `app/agent/` 不 import 任何新栈文件 ✅
- **但老栈仍被生产入口消费**：
  - `app/api/chat.py:4` → `from app.agent.graph import build_learning_graph`（已挂载 `main.py:26`）
  - `app/api/chat_stream.py:5` → 同上（已挂载 `main.py:27`）
  - `tests/unit/agent/`（10 个老测试）→ import `app.agent.*`
- **新栈编排仍是 dark launch** —— `app/orchestration/graph` **未被任何 API / main.py 接入**（Plan D 才装配 feature flag）

> **推论（迁移首要决策点）**：把 `app/agent/` 移入 `app_old/`，必须**同步改写** `chat.py`/`chat_stream.py` 的 import（`app.agent.graph` → `app_old.agent.graph`）+ 10 个老测试路径，否则生产 `/api/chat`、`/api/chat_stream` 立即 500。三种策略待用户定：
> - (a) 连 API import 一起改写指向 `app_old/`（彻底归档，老栈仍可跑）
> - (b) 老栈暂留 `app/`，待 Plan D 灰度切换后再移（最安全）
> - (c) 仅物理归档老栈、API 层加 feature flag 双写

### 3.1 执行清单

- [x] **决策 3.0**：已选 **(a) 彻底归档**——老栈搬 `app_old/`，同步改写 API/测试/conftest import 指向 `app_old.`，老栈仍可跑
- [x] 创建 `app_old/`（含 `__init__.py` 包骨架）
- [x] 迁移纯旧文件（**已排除 §2.E 必留闭包 6 个**：`llm.py`/`observability.py`/`rag.store`/`rag.__init__`/`enums.py`/`coordinator.py` 留 `app/`）。`memory.py`+`memory_store.py` 按 §2.E 订正**已随老栈迁移**
- [x] §1.2 六个纠缠文件 **原样保留于 `app/`**（§四 结论：修改全部设计强制）；`coordinator.py::retrieve()` 按 §4.3 **保留**未剥离；`conftest.py` 顶层 `app.harness.state` import 已按 §4.4 改写为 `app_old.harness.state`（测试套件收集正常）
- [x] A-4 废弃 stub（`external/ocr.py`、`extraction/file_extract.py`）：随 `external/`、`extraction/` **整目录归档至 `app_old/`**（归档非删除）
- [ ] 补登记依赖库缺口 A-5（pdfplumber/PyPDF2/python-docx/pytesseract/Pillow）+ C-5（pyyaml）—— **属新栈遗留，与本次迁移正交**，惰性 import 有降级，非阻断，待后续单独处理
- [x] 跑测试验证：**362 passed / 4 failed（4 个为 test_stores.py 预存失败，迁移前后一致）→ 零回归**

---

## 五、迁移执行记录（2026-06-02 · 策略 (a)）

### 5.1 实际迁移清单（git mv，rename 历史保留）

**代码 → `app_old/`（57 个 .py + specs 共 96 文件）：**

| 源 | 目标 | 说明 |
|----|------|------|
| `app/agent/`（整目录）| `app_old/agent/` | 老 LangGraph 栈：graph/routers/node_wrapper/spec_*/nodes(15)/multi_agent(7)/system_eval(5)/specs(34) |
| `app/harness/state/`（6）| `app_old/harness/state/` | 老分层 LearningState |
| `app/harness/{state_manager,intent_router,error_handler,memory,guardrails,tool_registry}.py` | `app_old/harness/` | 老 harness 工具（仅老栈/休眠）|
| `app/infrastructure/storage/memory_store.py` | `app_old/infrastructure/storage/` | 休眠 L2 后端（与 memory.py 互引）|
| `app/infrastructure/external/`（ocr/redis_pubsub/web_search）| `app_old/infrastructure/external/` | 零消费者孤儿 |
| `app/infrastructure/extraction/`（file_extract）| `app_old/infrastructure/extraction/` | 零消费者孤儿 |

**新建包骨架**：`app_old/__init__.py` · `app_old/harness/__init__.py` · `app_old/infrastructure/__init__.py` · `app_old/infrastructure/storage/__init__.py`

### 5.2 import 改写（共 20 个非迁移文件就地改写）

- **改写规则**：迁移集模块 `app.<mod>` → `app_old.<mod>`（perl 词边界，区分 `state`/`state_manager`、`agent`/`agents`）；指向 stays 文件（`enums`/`observability`/`llm`/`rag`）的引用**保持 `app.`**
- **外部边界 3 处**：`app/api/chat.py`、`app/api/chat_stream.py`、`tests/conftest.py` → 改指 `app_old.`
- **老测试就地改写**（未移动测试文件，符合策略 (a)「改写老测试路径」）：`tests/unit/agent/`(10) + `tests/unit/harness/{test_state,test_state_manager,test_intent_router,test_error_handler,test_memory,test_guardrails,test_tool_registry}.py` + `tests/unit/infrastructure/test_memory_store.py`
- **路径片段补修**：`test_spec_loader.py`/`test_spec_decorator.py` 的 `SPEC_DIR = ... / "app" / "agent" / "specs"` → `"app_old"`（perl 点号改写未覆盖的路径段，pytest 暴露后修正）

### 5.3 必留 `app/` 未动（§2.E 闭包 + 新栈）

`app/infrastructure/llm.py`（→传递 `observability.py`）· `rag/{store,coordinator,__init__,ocr,code_index,extractors}` · `harness/{enums,events,eventbus,workspace_state,mastery_graph,user_profile,orchestrator,teaching_policy,observability}` · `storage/{event_store,mastery_graph_store}` + 4 个被 API 复用的老 store（session/user/knowledge/eval）· 全部 `agents/`、`orchestration/` 新栈

### 5.4 验证结果

- ✅ `app/` 内**零残留**指向已搬模块的引用
- ✅ `app_old` 全部子包可独立 import；`SpecLoader.default()` 经 `__file__` 相对路径正确解析 `app_old/agent/specs`
- ✅ 新栈 `app.main` + 5 Agent + orchestration + `chat`（经 `app_old` 桥接）import 成功
- ✅ `pytest < /dev/null`：**362 passed / 4 failed**（与迁移前基线完全一致，4 失败为预存 test_stores.py，非本次引入）
- ✅ git 全部识别为 rename（R/RM），历史保留；`docs/app_old_migration_plan.md` 等未跟踪文档不受影响

### 5.5 遗留（非阻断，后续可选）

1. **依赖库登记**（A-5/C-5）：pdfplumber/PyPDF2/python-docx/pytesseract/Pillow/pyyaml 未在 `pyproject.toml` 显式声明（属新栈，惰性 import 有降级）
2. **old 测试位置**：老测试仍物理位于 `tests/`（仅改了 import）。若需 `tests/` 仅含新栈测试，可后续将其归档至 `app_old/tests/`（需同步 conftest 拆分）
3. **`coordinator.py::retrieve()`**：保留的零消费者向后兼容方法（§4.3），Plan D 若不复用可届时剥离

---

## 四、第三轮：基于 superpowers 设计文档的「修改必要性」复核（分析，未改动任何文件）

> 任务：读 5/30+ superpowers 文档，判定 §1.2 六个纠缠文件里哪些旧脚本改动「不必要」可剥离。

### 4.1 依据与方法

以「**设计是否强制该修改** + **实测消费者**」双判据复核。核心依据：

- `docs/superpowers/plans/2026-06-01-execution-orchestration.md` §3 **文件归属矩阵**：每个被改文件都有唯一 owner 计划，改动是计划内指派（Plan 0 拥有 `enums.py`；Plan A 拥有 `coordinator.py(扩展)`）
- `docs/superpowers/plans/2026-06-01-plan-0-core-contracts.md` §Task1：明文 `Modify: app/harness/enums.py（在文件末尾追加 4 个枚举）` + `Modify: test_enums.py（追加断言）`
- execution §2#4 + spec §1.2：`app/agent/` 全程**只读不改**（git 已证：0 处 M）
- execution §2#3：`enums.py` 是**共享文件**，Plan 0 一次定全，Wave 1 不改其结构

**总判据结论**：6 个纠缠文件的修改**全部是设计强制、owner 指派的「扩展」，无一处偶然/权宜 hack**。

### 4.2 六纠缠文件逐一裁决

| 文件 | 修改内容 | owner | 必要性证据 | 裁决 |
|------|----------|-------|------------|------|
| `enums.py` | 末尾追加 4 枚举类 | Plan 0 | plan-0 §Task1 明文指派；新栈 11 处 import EventType/EventSource/TeachingMode/ActionKind | **必要，不可剥离** |
| `coordinator.py` | 重写多 Provider + 保留 retrieve/index_documents | Plan A(扩展) | retriever.py 生产调 `search()`（L72/123）；`index_documents()` 被 Plan A 测试当 setup | **主体必要**；唯 `retrieve()` 见 4.3 |
| `conftest.py` | 追加 `mock_llm_invoke_json` fixture | Plan C | 三 Agent 单测统一经此注入 LLM mock（决策 #22）| **必要，不可剥离** |
| `test_enums.py` | 追加 4 新枚举断言 | Plan 0 | TDD 配套 | **必要** |
| `test_rag.py` | 追加多源检索测试 | Plan A | 覆盖 search/providers/去重 | **必要**；唯 retrieve() 的 3 测试随 4.3 |
| `README.md` | 追加 Plan 进度段 | 各 Plan | README 维护规范 | **必要**（文档）|

### 4.3 全项目唯一「技术性零生产消费者」的修改块 → `coordinator.py::retrieve()`

- **位置**：`coordinator.py:133-156`（"向后兼容"段）+ `test_rag.py` 3 处测试（L9/L18/L122）
- **证据**：retriever.py 生产代码只调 `search()`，从不调 `retrieve()`；老栈 `app/agent/` 完全不引用 coordinator；唯一调用方是 test_rag.py 测它自身
- **建议：保留（低价值剥离）**。① 它是 Plan A 刻意的向后兼容设计；② Plan D 切 `/api/chat` 到新栈时，旧消费者可能需 dict 格式 `retrieve()` 作桥接；③ 仅 24 行 + 3 测试，无害。**若追求极简方可剥离**，连带删 test_rag.py 3 个 retrieve 测试。

### 4.4 第三轮新发现的迁移阻断：`conftest.py` 顶层硬依赖旧 state

- `tests/conftest.py:2-3` **顶层 import** `app.harness.enums.{Stage,Intent}`（旧枚举）+ **`app.harness.state.LearningState`（旧 state 包）**
- conftest 是**全局**的：一旦 `app/harness/state/` 迁往 `app_old/`，顶层 import 即失败 → **整个测试套件收集失败**（与 §3.0 chat.py 阻断同类）
- 旧 fixture `blank_state`/`teach_state`（L6-27）服务老 `tests/unit/agent/`；新 fixture `mock_llm_invoke_json`（L30-43）服务 Plan C
- **处置**：迁 `state/` 时须同步迁走 conftest 的旧 fixture+旧 import，新 fixture 留 `app/` 的 conftest

### 4.5 第三轮结论

1. **「删除没有必要的修改」前提基本不成立**：6 纠缠文件改动全部设计强制、owner 指派，迁移应**原样保留全部 6 文件于 `app/`**。
2. **唯一可选剥离项** = `coordinator.py::retrieve()` + 其 3 测试（4.3），**建议保留**。
3. **纠缠不可约**：新栈用的 `MasteryLevel`（旧枚举，14 处）钉死 `enums.py` 必留 `app/`，无法整体移走旧枚举段；其余 9 个旧枚举（仅老栈用）只能在 `enums.py` 内随新栈留存为惰性死重，强拆会破坏 `app/agent/` import。
4. **真正的迁移工作量不在"剥离修改"，而在"切断老栈生产/测试硬依赖"**：§3.0（chat.py/chat_stream.py）+ §4.4（conftest）两处顶层 import 才是迁移实际阻断点。
