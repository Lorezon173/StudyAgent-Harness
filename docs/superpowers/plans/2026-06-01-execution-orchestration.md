# 多 Agent 重设计 — 并行执行编排与窗口上下文引导

> **用途**：指导在多个 Claude Code 窗口（会话）中并行推进 6 份实施计划。本文件是总调度 + 每个窗口的上下文引导卡。
> **日期**：2026-06-01
> **配套**：spec `docs/superpowers/specs/2026-05-29-multi-agent-redesign-design.md` · 决策记录 `Learned/多Agent重设计-Spec审阅与架构决策.md` · 已就绪计划 `docs/superpowers/plans/2026-06-01-plan-0-core-contracts.md`

---

## 0. 当前状态（务必先读）

| 计划 | 状态 |
|---|---|
| **Plan 0** 核心契约地基 | ✅ **详细计划已就绪**（10 Task TDD），可立即执行 |
| Plan A/B/C/D/E | ⏳ **详细计划待编写**——本文件为每个窗口提供"自助编写+执行"引导卡（含 `writing-plans` 步骤） |

**两种推进方式**（任选）：
- **(a) 自助并行**（本文档支持）：每个窗口照引导卡，先 `writing-plans` 写自己那份 Plan，再执行。三窗口可并行编写+执行。
- **(b) 集中编写**：回到主窗口让我逐份写完 A-E，再多窗口纯执行。产出更统一，但编写阶段串行。

---

## 1. 波次依赖与并行度

```
Wave 0（必须先完成，单窗口串行）
   └── Plan 0 核心契约地基 ──► 【接口冻结检查点】
                                      │
                  ┌───────────────────┼───────────────────┐
                  ▼                   ▼                   ▼
Wave 1（3 窗口并行）   Plan A 检索      Plan B 记忆画像     Plan C 教学编排
                  └───────────────────┼───────────────────┘
                                      ▼
                              【集成检查点】
                                      │
                          ┌───────────┴───────────┐
                          ▼                       ▼
Wave 2（2 窗口并行）   Plan D 集成灰度          Plan E 评估体系
                          └───────────┬───────────┘
                                      ▼
                              【端到端终检】
```

**最大并行度 = 3 窗口**（Wave 1）。Wave 0 与检查点是串行同步屏障。

---

## 2. 关键约束（为什么这样切）

1. **Plan 0 必须单窗口串行**：10 个 Task 顺序依赖（enums→events→…→graph），且集中改 `app/harness/`，多窗口并行会撞同一批文件。**这一步不要开多窗口。**
2. **接口冻结检查点**：Plan 0 全绿后，第 4 节的接口清单**冻结**——Wave 1/2 只能依赖、不得修改这些签名。若某窗口发现接口不够用，回主窗口议定改 Plan 0，而非各自改。
3. **Wave 1 三份文件不重叠**（见第 3 节矩阵）才能真并行。共享文件（`enums.py` / `WorkspaceState`）已在 Plan 0 一次定全，Wave 1 **不改它们的结构**，只在各自模块填充。
4. **老代码只读**：`app/agent/` 全程只读不改（spec §1.2），可参考可复制到新文件，禁止原地编辑。

---

## 3. 文件归属矩阵（防窗口冲突）

每个文件只有一个 owner 计划；其他计划只读。

| 计划 | 拥有（创建/修改）的文件 |
|---|---|
| **Plan 0** | `app/harness/{enums,events,workspace_state,eventbus}.py` · `app/infrastructure/storage/event_store.py` · `app/agents/base.py` · `app/orchestration/{collab_loop,graph}.py` |
| **Plan A 检索** | `app/agents/retriever.py` · `app/infrastructure/rag/{coordinator(扩展),ocr,code_index}.py` · `app/infrastructure/rag/extractors/` |
| **Plan B 记忆画像** | `app/agents/curator.py` · `app/harness/{mastery_graph,user_profile}.py` · `app/infrastructure/storage/mastery_graph_store.py` |
| **Plan C 教学编排** | `app/agents/{tutor,critic,conductor}.py` · `app/harness/{orchestrator,teaching_policy}.py` · `app/orchestration/orchestrator_rules.yaml` · `app/orchestration/graph.py` 的 `_collab_loop_node` 接入点（**唯一跨 Plan 0 改动，见接口冻结 #8**） |
| **Plan D 集成灰度** | `app/api/` feature flag · 端到端串联线 |
| **Plan E 评估体系** | `app/eval/*` · `tests/golden/` · `tests/eval/` |

> **唯一需协调点**：Plan C 要把 `graph.py` 的 `_collab_loop_node` 从占位接到 `run_collab_loop`。Plan 0 已为此留好注入点（节点函数独立、签名稳定）。Plan C 改这一个函数体，不动 Plan 0 其他部分。Wave 1 内 A/B 不碰 `graph.py`，无冲突。

---

## 4. 接口冻结清单（Plan 0 完成后冻结，Wave 1/2 依赖）

这些是 Wave 1/2 的契约前置，**冻结后不得擅改**：

| 冻结项 | 签名/位置 | 谁依赖 |
|---|---|---|
| 1. `Event` | `app/harness/events.py`：`type/source/session_id/payload/parent_id/metadata/id/ts` | 全部 |
| 2. 枚举 | `EventType / EventSource / TeachingMode / ActionKind`（值全集已定） | 全部 |
| 3. 所有权白名单 | `EVENT_OWNERSHIP` + `check_ownership` + `EmitViolationError` | 全部 Agent |
| 4. `AgentBase` | `source / subscriptions / emittable_types / handle(event,ws)->list[Event] / emit(type,ws,payload,parent_id) / evaluate(test_case)` | A/B/C 全部 Agent |
| 5. `EventBus` | `publish / subscribe / subscribers_of / replay` | C（Orchestrator）、全部 |
| 6. `EventStore` | `init / append / replay / close` | E（评估回放） |
| 7. `WorkspaceState` | `session_id/user_id/current_topic/current_mode/turn_count/event_ids/evidence_pool/critic_state/profile_snapshot` | 全部 |
| 8. 协作环 | `run_collab_loop(bus,ws,seed_events,orchestrator=None,max_turns)` + Orchestrator 钩子协议 `on_event(event,ws)->list[Event]` | C |
| 9. 优先级 | `priority_of / EVENT_PRIORITY`（观察<默认<Tick，LoopExit 最先） | C（回合屏障） |

**Agent 实现约定**：每个 Agent 继承 `AgentBase`，声明 `source/subscriptions/emittable_types`，实现 `handle`。`ActionRequested` 带 `target` 字段，Agent 在 `handle` 内按 `event.payload["target"]==自己` 过滤（或由 Orchestrator 定向，Plan C 决定）。

---

## 5. 执行时间线

| 阶段 | 窗口数 | 动作 | 同步屏障 |
|---|---|---|---|
| **T0 现在** | 1 | 执行 Plan 0（10 Task 串行 TDD） | — |
| **T1 接口冻结** | 1 | `pytest` 全绿 + 第 4 节接口冻结确认 | ⛔ 全员等待此点 |
| **T2 Wave 1** | 3 | 窗口①Plan A · 窗口②Plan B · 窗口③Plan C，各自 `writing-plans`→执行 | — |
| **T3 集成检查** | 1 | A/B/C 各单测绿 + 文件无冲突 + 协作环跑通 1 场景 | ⛔ 等待此点 |
| **T4 Wave 2** | 2 | 窗口④Plan D 集成灰度 · 窗口⑤Plan E 评估 | — |
| **T5 终检** | 1 | 端到端 4 场景 + 协作六维指标 + 选型报告 | ✅ 完成 |

---

## 6. 窗口上下文引导卡

> 每张卡的"开场 prompt"可整段复制粘贴到新窗口作为首条消息，新窗口即获得零上下文启动所需的全部信息。

### 窗口①（T0）：Plan 0 核心契约地基 —— 直接执行

**开场 prompt（复制到新窗口）：**
```
你在 StudyAgent 多 Agent 重设计项目中执行【Plan 0：核心契约地基】。这是一个事件驱动的多 Agent 费曼学习系统，核心原则是职能正交（每个 Agent 只发自己专业领域的事件，越权由 EventBus 白名单运行时拦截）。

请读并严格执行：docs/superpowers/plans/2026-06-01-plan-0-core-contracts.md（10 个 Task，全 TDD）。
背景参考（按需查）：docs/superpowers/specs/2026-05-29-multi-agent-redesign-design.md 的 §2.2 / §3.1 / §3.2 / §3.5 / §6。

用 superpowers:subagent-driven-development 或 superpowers:executing-plans 逐 Task 执行：每个 Task 先写失败测试 → 运行验证失败 → 最小实现 → 运行验证通过 → 提交。
硬约束：
- 全部为新建文件，不碰 app/agent/ 老代码（只读可参考）。
- 现有测试基线（约 155 个）必须持续全绿。
- 沿用现有风格：StrEnum、同步 sqlite3（EventStore）、pytest 同步测试。
完成判据：pytest 全绿 + 新增约 28 测试；随后向我确认"接口冻结"（执行编排文档第 4 节）。
```

- **必读**：Plan 0 计划全文 · spec §2.2/§3.1/§3.2/§3.5/§6
- **拥有文件**：见第 3 节矩阵 Plan 0 行
- **依赖**：无（最先）
- **禁区**：`app/agent/` 老代码；不预先创建 A-E 的文件
- **验收**：`pytest -q` 全绿；第 4 节 9 项接口可冻结
- **特别**：本计划已写好，**直接执行，不需 writing-plans**

---

### 窗口②（T2）：Plan A 检索与知识库

**开场 prompt（复制到新窗口）：**
```
你在 StudyAgent 多 Agent 重设计项目中负责【Plan A：检索与知识库】。系统是事件驱动多 Agent，遵循职能正交（每个 Agent 只发自己专业的事件，越权被 EventBus 白名单拦截）。Plan 0（核心契约）已完成并冻结接口。

请先按顺序读：
1. docs/superpowers/specs/2026-05-29-multi-agent-redesign-design.md 的 §2.1(Retriever 行)、§3.2(事件白名单)、§3.6(证据评判流程)、§5.2(Retriever 指标)、§9(RAG 扩展相关)
2. docs/superpowers/plans/2026-06-01-execution-orchestration.md 第 3 节(文件归属) + 第 4 节(接口冻结)
3. Learned/多Agent重设计-Spec审阅与架构决策.md 的 #18(证据质量归属)
4. 已冻结接口源码：app/agents/base.py、app/harness/events.py、app/harness/enums.py、app/infrastructure/rag/coordinator.py(现有)

你的任务：用 superpowers:writing-plans 编写 docs/superpowers/plans/2026-06-01-plan-a-retrieval.md，然后用 subagent-driven-development 执行。

Retriever 事件契约（严格遵守）：
- source = retriever；subscriptions = [ActionRequested(payload.target==retriever)]；emittable = {RetrievedEvidence, RetrievalFailed}
- 只做机械层：向量检索 + 原始 similarity score + retrieval_status(ok|empty|timeout|low_score)。绝不评判"证据够不够好"（语义质量归 Critic 的 RAGQualityAssessed）。
- 实现 evaluate(test_case)（§5.2 RAG 三件套，供 Plan E 调用）。

你拥有的文件（只能改这些）：app/agents/retriever.py、app/infrastructure/rag/{coordinator(扩展),ocr,code_index}.py、app/infrastructure/rag/extractors/
硬约束：不改 Plan 0 冻结接口 / 其他窗口文件 / app/agent/ 老代码；沿用 aiosqlite + pytest(asyncio.run) 风格；严格 TDD 每 Task 提交。
验收：spec §9 场景中 OCR/代码索引可检索；Retriever 单测绿 + evaluate 可跑。
```

- **依赖**：Plan 0 冻结接口（AgentBase / Event / EventBus）
- **禁区**：Critic 的 RAGQualityAssessed（不可自评质量）；其他窗口文件
- **与 B/C 并行安全性**：文件不重叠（只在 `agents/retriever.py` + `infrastructure/rag/`）

---

### 窗口③（T2）：Plan B 记忆与画像

**开场 prompt（复制到新窗口）：**
```
你在 StudyAgent 多 Agent 重设计项目中负责【Plan B：记忆与画像】。系统是事件驱动多 Agent，遵循职能正交。Plan 0（核心契约）已完成并冻结接口。

请先按顺序读：
1. spec docs/superpowers/specs/2026-05-29-multi-agent-redesign-design.md 的 §2.1(Curator 行)、§2.4(职能正交)、§4.2(开局前置探测)、§6/§6.1(MasteryGraph+冷启动建图)、§6.2(三层记忆)
2. docs/superpowers/plans/2026-06-01-execution-orchestration.md 第 3/4 节
3. Learned/多Agent重设计-Spec审阅与架构决策.md 的 #8(冷启动建图)、#17(Curator 双时机触发)
4. 已冻结接口：app/agents/base.py、app/harness/{events,enums,workspace_state}.py、现有 app/harness/memory.py(L1/L2 复用不改)

你的任务：用 superpowers:writing-plans 编写 docs/superpowers/plans/2026-06-01-plan-b-memory-profile.md，然后执行。

Curator 事件契约（严格遵守）：
- source = curator；subscriptions = [MasteryAssessed(回合中), TopicEntered(开局/切主题)]；emittable = {ProfileUpdated, GraphNodeStrengthened, GraphPrereqWeakDetected}
- 只判结构层：基于图谱 PREREQ 边 + 用户前置节点掌握度判"前置薄弱"。绝不判文本语义（那归 Critic）。
- 双时机：TopicEntered→基于历史画像发 GraphPrereqWeakDetected(basis=historical)；MasteryAssessed→基于实测发 basis=observed。historical 分支为渐进启用（冷启动画像空时不触发）。
- 冷启动建图三来源：DOC_ORDER(0.5)/LLM_INFER(0.3)/INTERACTION(0.8)，置信度加权。
- L3 画像记忆 = MasteryGraph + UserProfile（区别于 memory.py 的 L1/L2）。实现 evaluate(test_case)。

你拥有的文件：app/agents/curator.py、app/harness/{mastery_graph,user_profile}.py、app/infrastructure/storage/mastery_graph_store.py
硬约束：不改 Plan 0 接口 / memory.py 的 L1/L2 / 其他窗口文件 / app/agent/ 老代码；aiosqlite + pytest(asyncio.run)；TDD 每 Task 提交。
验收：spec §5.3 场景"前置薄弱触发回退"图谱侧可发 GraphPrereqWeakDetected；Curator 单测绿。
```

- **依赖**：Plan 0 冻结接口
- **禁区**：Critic 语义判定；`memory.py` 的 L1/L2；其他窗口文件
- **与 A/C 并行安全性**：只在 `agents/curator.py` + `harness/{mastery_graph,user_profile}.py` + 一个 store，不重叠

---

### 窗口④（T2）：Plan C 教学与编排 —— Wave 1 最核心

**开场 prompt（复制到新窗口）：**
```
你在 StudyAgent 多 Agent 重设计项目中负责【Plan C：教学与编排】——Wave 1 最核心最重的一份，含 3 个 Agent + Orchestrator + 教学状态机 + 回合屏障 + 主图接入。系统事件驱动、职能正交。Plan 0 已冻结接口。

请先按顺序读：
1. spec docs/superpowers/specs/2026-05-29-multi-agent-redesign-design.md 的 §2.1、§2.3(Conductor)、§2.4(职能正交)、§3.3(Orchestrator)、§3.4(规则DSL)、§3.5(全:事件循环+优先级+回合屏障+嵌套)、§4(全:四模式+完整转移表+开局探测+事件流示例)
2. docs/superpowers/plans/2026-06-01-execution-orchestration.md 第 3/4 节
3. Learned/多Agent重设计-Spec审阅与架构决策.md 的 #14(emit白名单)、#15(复述检查归Critic)、#16(Conductor限制)、#17(Curator触发,理解协作时序)
4. 已冻结接口：app/agents/base.py、app/harness/{events,enums,eventbus,workspace_state}.py、app/orchestration/{collab_loop,graph}.py

你的任务：用 superpowers:writing-plans 编写 docs/superpowers/plans/2026-06-01-plan-c-teaching-orchestration.md，然后执行。建议拆子阶段：Tutor → Critic → Conductor → Orchestrator规则引擎 → 回合屏障 → TeachingPolicy → graph接入。

事件契约（严格遵守）：
- Tutor:    source=tutor;    subscribes=[ActionRequested(target=tutor)]; emits={TutorAsked,TutorExplained,TutorRequestedRecap,TutorOfferedAnalogy}。只生成教学内容,不评判(复述质量归Critic)。
- Critic:   source=critic;   subscribes=[UserMessage, RetrievedEvidence(purpose=teaching)]; emits={MasteryAssessed,ConfusionDetected,ContradictionDetected,LowConfidenceDetected,RAGQualityAssessed}。只判文本语义;复述检查在此;RAG语义质量仅purpose=teaching时评。
- Conductor:source=conductor;subscribes=[ConductorRequested]; emits={ConductorDecided}。只基于已有观察路由;观察不足→emit ConductorDecided(action=REQUEST_OBSERVATION,target=critic|curator),绝不自产语义/结构观察,绝不直接emit ActionRequested(那是Orchestrator的)。
- Orchestrator(非Agent,事件路由器): 实现 on_event(event,ws)->list[Event] 接入 run_collab_loop;规则引擎读 orchestrator_rules.yaml;回合屏障用 OrchestratorTick(最低优先级)收集完整观察集后再裁决唯一动作;规则未命中→ConductorRequested召唤Conductor。emits控制类={ActionRequested,PolicyTransition,LoopExit,TopicEntered,ConductorRequested,OrchestratorTick}。
- TeachingPolicy: 实现 §4.2 完整状态转移表,记录模式历史供评估。

你拥有的文件：app/agents/{tutor,critic,conductor}.py、app/harness/{orchestrator,teaching_policy}.py、app/orchestration/orchestrator_rules.yaml、以及 app/orchestration/graph.py 的 _collab_loop_node(唯一跨Plan0改动:接入run_collab_loop+Orchestrator)
硬约束：不改 Plan0 其他接口 / A/B 文件 / app/agent/ 老代码；各Agent实现evaluate()(供Plan E);严格TDD每Task提交;回合屏障必须专项单测(观察集不完整就路由=失败)。
验收：spec §4.3 事件流示例可复现;走通1标准场景(Socratic→Feynman→Analogy→mastered→LoopExit);回合屏障+越权拦截单测绿。
```

- **依赖**：Plan 0 全部冻结接口（尤其 `run_collab_loop` + 优先级 + 白名单）
- **禁区**：A/B 文件；Plan 0 除 `_collab_loop_node` 外的接口；老代码
- **与 A/B 并行安全性**：只在 `agents/{tutor,critic,conductor}` + `harness/{orchestrator,teaching_policy}` + yaml + `graph._collab_loop_node`，与 A(retriever/rag)、B(curator/mastery_graph) 不重叠
- **提示**：本份最重，建议优先投入人力或拆更细子阶段

---

### 窗口⑤（T4）：Plan D 集成与灰度

**开场 prompt（复制到新窗口）：**
```
你在 StudyAgent 多 Agent 重设计项目中负责【Plan D：集成与灰度】(Wave 2)。Plan 0 + Wave 1(A检索/B画像/C教学编排)已全部完成。

请先读：
1. spec docs/superpowers/specs/2026-05-29-multi-agent-redesign-design.md 的 §1.1(API层)、§3.5.4(LangGraph嵌套边界)、§8(P8灰度)、§9(老代码回归风险)
2. docs/superpowers/plans/2026-06-01-execution-orchestration.md 第 3 节(文件归属)
3. 现有 app/api/ 全部路由;app/orchestration/graph.py 与 collab_loop.py;Wave 1 产出的 5 个 Agent + Orchestrator

你的任务：用 superpowers:writing-plans 编写 docs/superpowers/plans/2026-06-01-plan-d-integration.md,然后执行。把 graph.py 的 collab_loop 节点装配真实 EventBus + 5 Agent + Orchestrator 完整串起来;在 API 层加 feature flag 把 /chat 与 /chat/stream 切到新栈,与老栈指标对齐,可一键回退。

你拥有的文件：app/api/(feature flag 与路由切换)、端到端装配线(在 collab_loop 节点装配 bus+agents+orchestrator,若 Plan C 未完全装配则在此补齐)
硬约束：feature flag 必须能回退老栈(关 flag 即用 app/agent/ 老图);不改老代码;不改 Plan0/Wave1 已冻结的 Agent/编排接口(只装配);TDD。
验收：spec §8 P8 — 灰度上线,/chat 走新栈端到端通,新旧栈关键指标(掌握度/成本/时延)对齐;关 flag 可回退。
```

- **依赖**：Wave 1 全部（A/B/C 的 Agent + Orchestrator 就绪）
- **禁区**：老代码原地改；Wave 1 的 Agent 内部逻辑（只装配不改）
- **与 E 并行安全性**：D 改 `app/api/` + 装配线（在线路径），E 只在 `app/eval/`（旁路），不重叠

---

### 窗口⑥（T4）：Plan E 评估体系

**开场 prompt（复制到新窗口）：**
```
你在 StudyAgent 多 Agent 重设计项目中负责【Plan E：评估体系】(Wave 2,可与 Plan D 并行)。Plan 0 + Wave 1 已完成。

请先读：
1. spec docs/superpowers/specs/2026-05-29-multi-agent-redesign-design.md 的 §5 全节(5.1视图/5.1.1黄金集+judge独立/5.2部件级/5.3系统级+过程断言/5.4协作级/5.5消融/5.6选型报告)
2. docs/superpowers/plans/2026-06-01-execution-orchestration.md 第 3 节
3. Learned/多Agent重设计-Spec审阅与架构决策.md 的 #7(judge独立)、#19(协作评估层)、#20(消融)、#21(黄金轨迹)
4. 已冻结接口：app/infrastructure/storage/event_store.py(replay)、app/agents/base.py(evaluate)、app/harness/events.py(parent_id 因果链)

你的任务：用 superpowers:writing-plans 编写 docs/superpowers/plans/2026-06-01-plan-e-eval.md,然后执行。

关键设计点（来自 spec §5）：
- ComponentBench: 调各 Agent 的 evaluate()。SystemBench: 跑 scenarios YAML(结果断言+过程断言)。
- CollaborationBench: 消费 EventStore.replay 的 parent_id 因果链,算六维(职能正交违约/协作效率/决策稳定/冲突消解/因果链质量/轨迹偏离)。违约率应恒为0。
- ABController: 参数A/B + 组件消融(disable_agent,事件由stub返回默认),回答"架构本身值多少"。
- judge与被评模型不同族+盲评;黄金集双人标注+Cohen's κ≥0.6冻结。

你拥有的文件：app/eval/{kernel,component_bench,system_bench,collaboration_bench,ab_controller,selection_reporter}.py、app/eval/{scenarios,fixtures}/、tests/golden/、tests/eval/
硬约束：纯旁路——只读 EventStore/调 evaluate/replay trace,不改任何在线 Agent/编排代码;TDD。
验收：spec §5.3 四场景跑出报告 + 协作六维可算 + 1个消融实验(Curator价值) + 选型报告 Markdown 产出。
```

- **依赖**：`EventStore.replay` + 各 Agent `evaluate()` + 事件流 `parent_id`
- **禁区**：任何在线代码（只读 + 调评估接口）
- **与 D 并行安全性**：E 只在 `app/eval/` + `tests/{golden,eval}/`，旁路不碰在线路径

---

## 7. 检查点判据

| 检查点 | 判据（全满足才放行下一波） |
|---|---|
| **T1 接口冻结** | `pytest` 全绿 · 第 4 节 9 项接口签名确认 · 越权 emit 拦截测试绿(`test_publish_violation_raises`) · 全序回放测试绿(`test_replay_is_total_order_by_id`) |
| **T3 集成** | A/B/C 各自单测绿 · `git diff --stat` 确认三者无交叉改文件 · 协作环跑通 1 个标准场景 · 全程无 `EmitViolationError`(职能正交未被破坏) |
| **T5 终检** | spec §5.3 四场景端到端通 · CollaborationBench 六维指标产出 · SelectionReporter 报告产出 · 155 基线不减 |

---

## 8. 主窗口协调提示

- **T0**：开 1 个窗口贴【卡①】跑 Plan 0。完成后回主窗口确认接口冻结（对照第 4 节逐项核）。
- **T2**：开 3 个窗口分别贴【卡②③④】(A/B/C)。Plan C 最重，优先保证投入。三窗口各自先 `writing-plans` 写计划、再执行。
- **同步**：各窗口完成后回报，主窗口用 `git diff --stat` 核对文件归属无交叉（第 3 节矩阵）。任何窗口发现冻结接口不够用 → **回主窗口议定改 Plan 0**，切勿各自改冻结接口。
- **T4**：开 2 个窗口贴【卡⑤⑥】(D/E)，可并行。
- **冲突预案**：唯一已知跨界点是 `graph.py._collab_loop_node`（Plan C 拥有）；Plan D 装配在其基础上，属 Wave 2 顺序在后，无并行冲突。

---

> **一句话操作指南**：先单窗口跑【卡①Plan 0】→ 确认接口冻结 → 开三窗口贴【卡②③④】并行做 A/B/C → 集成检查 → 开两窗口贴【卡⑤⑥】做 D/E → 终检。每张卡的开场 prompt 整段复制即可启动新窗口。

