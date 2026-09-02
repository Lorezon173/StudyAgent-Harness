# StudyAgent 多 Agent 协作架构

> **最后更新**：2026-08-26
> **内容来源**：对 `app/agents/`、`app/harness/`、`app/orchestration/` 实际源码的通读梳理（基于代码事实，非规范文档）
> **快照说明**：本文为 2026-07-14 时点对实际代码的梳理快照，架构仍在演进，内容可能随后续重构变动。
> **相关文档**：`Learned/多Agent重设计-Spec审阅与架构决策.md`（记录的是重设计过程中的争议与决策；本文记录的是落地后的实际架构与协作模式）

## 目录

- [Q1: 多 Agent 整体组织结构与七角色总览](#q1-多-agent-整体组织结构与七角色总览)
- [Q2: 五个 Agent 的命名含义、作用、事件契约与职能边界](#q2-五个-agent-的命名含义作用事件契约与职能边界)
- [Q3: Agent 之间如何协作（事件总线 / 协作环 / 回合屏障 / 两层决策）](#q3-agent-之间如何协作)
- [Q4: 一次完整回合的协作时序](#q4-一次完整回合的协作时序)
- [Q5: 关键设计原则](#q5-关键设计原则)
- [Q6: Curator 和 Critic 的职责区分与功能边界](#q6-curator-和-critic-的职责区分与功能边界)
- [Q7: 用户回答追问时，掌握度由谁维护、RAG 如何处理、Curator 与 Critic 如何协作](#q7-用户回答追问时掌握度由谁维护rag-如何处理curator-与-critic-如何协作)

---

## Q1: 多 Agent 整体组织结构与七角色总览

**日期**：2026-07-14

**问题**：
StudyAgent 的多 Agent 组织结构是怎样的？各角色分别是谁？

**回答**：

### ⚠ 先做一个关键事实校正

项目根规范 `.claude/rules/agent-root.md` 指向的 `app/agent/`（单数）**已废弃**，现在实际是 `app_old/agent/`（旧的 LangGraph 节点流实现）。**当前活跃代码是 `app/agents/`（复数）**，是一套全新的**事件总线驱动**架构。阅读源码时应以 `app/agents/` 为准，不要被那份过时规范误导。

- 当前 HTTP 入口：`app/api/chat.py`、`app/api/chat_stream.py` → `app/orchestration/assembly.py:run_new_agent_session`。
- `app/orchestration/graph.py` 虽是一个 LangGraph 外壳（`StateGraph`+`MemorySaver`），但**目前没有任何 API 调用它**——主链路是 `assembly.py` 同步跑协作环。

### 一句话定性

这是一套**基于费曼学习法、事件总线驱动的"职能正交"多 Agent 协作系统**：5 个职能互不重叠的 Agent + 1 个事件路由中枢（Orchestrator），通过**发布/订阅事件**协作，而不是互相直接调用。

### 七角色全景

事件来源身份定义在 `app/harness/enums.py:126`（`EventSource`），共 7 个角色，但**只有 5 个是 Agent**：

| 角色 | 中文名 | 是 Agent? | 归属 | 职能层 | 位置 |
|---|---|---|---|---|---|
| **Tutor** | 导师 | ✅ | `app/agents/` | 生成层 | `app/agents/tutor.py` |
| **Critic** | 评审 | ✅ | `app/agents/` | 语义评估层 | `app/agents/critic.py` |
| **Retriever** | 检索器 | ✅ | `app/agents/` | 机械层 | `app/agents/retriever.py` |
| **Curator** | 策展人 | ✅ | `app/agents/` | 结构层（图谱） | `app/agents/curator.py` |
| **Conductor** | 指挥 | ✅ | `app/agents/` | 路由决策兜底 | `app/agents/conductor.py` |
| **Orchestrator** | 编排器 | ❌（路由中枢） | `app/harness/` | 规则路由 | `app/harness/orchestrator.py` |
| User | 用户 | ❌（外部） | — | 输入来源 | — |

> **最易混淆的一对：Conductor vs Orchestrator**
> - **Orchestrator（编排器）**不是 Agent，是协作环的"路由钩子"，用**确定性规则**（YAML）做决策；
> - **Conductor（指挥）**是真 Agent，只在规则**未命中**时被 Orchestrator 召唤，用 **LLM 做兜底决策**。

---

## Q2: 五个 Agent 的命名含义、作用、事件契约与职能边界

**日期**：2026-07-14

**问题**：
每个 Agent 的名字是什么含义？分别发挥什么作用？彼此如何区分职责？

**回答**：

所有 Agent 继承 `AgentBase`（`app/agents/base.py:9`），契约是三个类属性 + 一个方法：

- `source` — 事件来源身份
- `subscriptions` — 订阅哪些事件类型
- `emittable_types` — 只能发布哪些事件类型（**声明即契约**，越界 `emit` 直接抛 `ValueError`，见 `base.py:38`）
- `handle(event, ws) -> list[Event]` — 处理一个事件，返回新事件

### 1. Tutor（导师）—— 教学主体，"只生成不评判"

- **文件**：`app/agents/tutor.py:9`
- **订阅** → `ACTION_REQUESTED`（按 `payload.target==tutor` 过滤，`tutor.py:35`）
- **发布** → `TutorAsked` / `TutorExplained` / `TutorRequestedRecap` / `TutorOfferedAnalogy`
- **作用**：根据 Orchestrator 下达的 `ActionKind`（提问/讲解/重讲/纠错/类比/复述/前置探查）调 LLM 生成教学内容。
- **边界**：**只生成内容，绝不评判质量**（复述质量归 Critic）。按 `payload.action` 内部分派到 `_ask` / `_explain` 等私有方法（`tutor.py:74-97`）。

### 2. Critic（评审）—— 文本语义评估，"只判语义层"

- **文件**：`app/agents/critic.py:9`
- **订阅** → `USER_MESSAGE` + `RETRIEVED_EVIDENCE`
- **发布** → `MASTERY_ASSESSED` / `CONFUSION_DETECTED` / `CONTRADICTION_DETECTED` / `LOW_CONFIDENCE_DETECTED` / `RAG_QUALITY_ASSESSED`
- **作用**：一次 LLM 调用产出一份 JSON，含多个观察字段，Critic 据此**拆成多条事件分别 emit**（`critic.py:49-80`）——掌握度、概念混淆、自相矛盾、用户自我不确定、RAG 证据质量。
- **边界**：**不读知识图谱、不判前置缺失、不做路由决策**；且 RAG 质量评估**仅在 `purpose=teaching` 时触发**（纯探索不评，省成本，`critic.py:37`）。

### 3. Retriever（检索器）—— 知识检索，"只做机械层"

- **文件**：`app/agents/retriever.py:24`
- **订阅** → `ACTION_REQUESTED`（按 `target==retriever` 过滤）
- **发布** → `RETRIEVED_EVIDENCE` / `RETRIEVAL_FAILED`
- **作用**：委托 `RAGCoordinator` 做向量检索，附带原始 `similarity score` 和一个**纯机械的** `retrieval_status`（`empty`/`low_score`/`ok`，阈值 0.3，`retriever.py:79-85`）。
- **边界**：**绝不评判"证据够不够好"**（语义质量归 Critic 的 `RAGQualityAssessed`）。失败时发 `RetrievalFailed`（`retriever.py:54`）。

### 4. Curator（策展人）—— 维护用户画像与掌握度知识图谱，"只判结构层"

- **文件**：`app/agents/curator.py:9`（继承 `CuratorBase`，强制 `handle` 必须同步，`base.py:50-67`）
- **订阅** → `MASTERY_ASSESSED` + `TOPIC_ENTERED`
- **发布** → `PROFILE_UPDATED` / `GRAPH_NODE_STRENGTHENED` / `GRAPH_PREREQ_WEAK_DETECTED`
- **作用**：把 Critic 评出的掌握度写进 `MasteryGraph`（掌握点知识图谱），并基于图谱的 `PREREQ`（前置）边判断"前置知识薄弱"。有两个时机（`curator.py:18-23`）：
  - `TopicEntered`（开局/切主题）→ 基于历史画像发 `basis=historical`
  - `MasteryAssessed`（回合中实测）→ 发 `basis=observed`
- **边界**：**只判结构层（前置薄弱），绝不判文本语义**（那归 Critic）。historical 分支渐进启用，冷启动（无 PREREQ 边/前置节点缺失）不触发。

> **CuratorBase 的同步约束**：`__init_subclass__`（PEP 487）会在子类定义时自动拒绝 `async handle`（`base.py:59-67`）。原因是协作环以同步方式调用 Curator，async handle 会返回 coroutine 而不被 await，造成图谱更新静默丢失。

### 5. Conductor（指挥）—— LLM 决策兜底，"只路由不自产观察"

- **文件**：`app/agents/conductor.py:9`
- **订阅** → `CONDUCTOR_REQUESTED`
- **发布** → `CONDUCTOR_DECIDED`
- **作用**：规则引擎匹配失败（`default` 规则）时，Orchestrator 把完整观察集喂给它，它用 LLM（`invoke_json`）给出一个 `ActionKind` 决策（`conductor.py:33-47`）。
- **边界**：**只能在已有观察之上路由，不自产语义/结构观察**；观察不足时 emit `REQUEST_OBSERVATION` 让 Critic/Curator 先看，下轮可能命中规则。

---

## Q3: Agent 之间如何协作

**日期**：2026-07-14

**问题**：
Agent 之间不直接调用，那它们如何协同完成一次教学回合？

**回答**：

协作由四个机制叠加实现：**事件总线**、**协作环**、**回合屏障**、**两层决策**。

### 3.1 事件总线（EventBus）—— 唯一通信通道

`app/harness/eventbus.py:8`。Agent 之间**绝不互相调用**，只通过事件发布/订阅。`publish` 是唯一写入口，做两件事（`eventbus.py:28`）：

- **所有权校验**（`check_ownership`）——越权发布直接抛错、事件不落库；
- **持久化**到 `EventStore`（事件溯源，可回放）。

注意：**EventBus 本身不调用 Agent**。分发由协作环用 `subscribers_of` 驱动（`eventbus.py:25`），保持单线程循环对控制流的完全掌控。

### 3.2 协作环（Collaboration Loop）—— 单线程优先级队列

`app/orchestration/collab_loop.py:31` 的 `run_collab_loop` 是整个协作的发动机：

```
种子事件(UserMessage + TopicEntered + 首个ActionRequested) 入队
   ↓
循环：pop 一个事件（优先级小的先出）
   → 分发给所有订阅该类型的 Agent.handle()
   → Agent 产出新事件 publish+入队
   → Orchestrator.on_event() 做路由决策，产出新事件入队
   ↓
直到 pop 出 LoopExit（唯一出环信号）
```

- **优先级队列**（`collab_loop.py:12`）：`LoopExit(5)` < 观察类`(10)` < 默认`(20)` < `Tick(100)`；同优先级 FIFO，保证确定性回放。
- **死循环熔断**：`MAX_TURNS=50`，超限强制注入 `LoopExit`（`collab_loop.py:56`）。

### 3.3 回合屏障（Micro-turn Barrier）—— Orchestrator 的精髓

`app/harness/orchestrator.py:63`。问题：一个用户消息可能同时触发 Critic 的 `MASTERY_ASSESSED` **和** Curator 的 `GRAPH_PREREQ_WEAK_DETECTED`，如果看到第一个观察就决策，会过早。

解法（`orchestrator.py:80-98`）：

1. 观察类事件先缓冲进 `_pending_obs`；
2. 同时注入一个 `ORCHESTRATOR_TICK` 哨兵，**优先级最低（100）**；
3. 因为 Tick 最低优先级，它一定在"本 micro-turn 所有观察事件之后"才被弹出——此时观察已收集齐；
4. Tick 弹出时，Orchestrator 对**完整观察集**做**唯一一次**路由裁决（`_on_tick`，`orchestrator.py:100`）。

### 3.4 两层路由决策（规则优先，LLM 兜底）

观察集收集齐后，交给 `RuleEngine`（`orchestrator.py:23`）匹配 `app/orchestration/orchestrator_rules.yaml`：

| 规则名 | 条件 | 动作 | 优先级 |
|---|---|---|---|
| prereq_weak_observed | 前置薄弱（实测） | regress_to_prereq | 100 |
| prereq_weak_historical | 前置薄弱（历史） | tutor_probe_prereq | 100 |
| contradiction | 自相矛盾 | tutor_correct | 90 |
| confusion | 概念混淆 | tutor_offer_analogy | 80 |
| weak_within_repeat | 掌握度 weak（连续<2次） | tutor_re_explain | 70 |
| partial | 部分掌握 | tutor_request_recap | 60 |
| mastered_topic_complete | 已掌握且主题完成 | **loop_exit** | 50 |
| rag_quality_low | RAG 质量低 | retriever_expand_query | 40 |
| default | 兜底 | **conductor_decide** | 0 |

- 规则命中 → Orchestrator 发 `ACTION_REQUESTED`（带 `target` 定向到 Tutor/Retriever，`orchestrator.py:149-154`）；
- 规则未命中（default）→ 发 `CONDUCTOR_REQUESTED`，召唤 Conductor 用 LLM 决策，再由 `_translate_conductor_decision`（`orchestrator.py:205`）把决策转译回 `ACTION_REQUESTED`；
- 规则是 **YAML 热可换**的，不改代码就能调协作策略。

### 3.5 教学模式转换（TeachingPolicy）

路由的同时，`TeachingPolicy.next()`（`orchestrator.py:132`）根据观察集决定是否切换教学四模式（`enums.py:137`）：**Socratic（苏格拉底提问）/ Feynman（费曼复述）/ Analogy（类比）/ Regress（回退前置）**。切换时发 `POLICY_TRANSITION` 事件并更新 `ws.current_mode`（`orchestrator.py:133-140`）。

> 注：`TeachingPolicy` 的内部转换逻辑（`app/harness/teaching_policy.py`）本文未深入，待补充。

### 协作拓扑图（以事件总线为唯一枢纽）

```
                         ┌──────────┐
                         │   用 户   │
                         └────┬─────┘
                              │ UserMessage
                              ▼
   ╔═══════════════════════════════════════════════════╗
   ║                EventBus 事件总线                   ║
   ║      发布/订阅 · 所有权校验 · 持久化(可回放)        ║
   ╚═══╤══════════╤═══════════════╤═══════════════╤═══╝
       │          │               │               │
       ▼          ▼               ▼               ▼
   ┌───────┐ ┌─────────┐     ┌─────────┐     ┌──────────┐
   │Critic │ │ Curator │     │  Tutor  │     │Retriever │
   │ 语义层 │ │  结构层  │     │  生成层  │     │  机械层   │
   └───┬───┘ └────┬────┘     └────▲────┘     └─────┬────┘
       │          │               │                │
       │ Mastery  │ PrereqWeak    │ Tutor*         │Retrieved
       │ Assessed │  等观察        │ 教学内容        │ Evidence ──┐
       │  等观察   │               │                │            │横向喂回
       │   ↓      │               │                │            │(评RAG质量)
       │  Curator 也订阅此事件      │                │            │
       └──────────┘                │                │            │
                                   │                │            │
       所有「观察类事件」──────────┘                │            │
                 │                                  │            │
                 ▼                                  │            │
        ┌─────────────────────┐  ◀─────────────────┘            │
        │   Orchestrator       │   Retriever 的 RetrievedEvidence│
        │   (编排器·非Agent)   │   也是观察类，同样进缓冲         │
        │  回合屏障 + 规则路由  │                                 │
        └──────────┬──────────┘
              命中 │规则        default│未命中
                   ▼                  ▼
          ActionRequested      ┌─────────────┐
          target=tutor/        │  Conductor  │ LLM 兜底
          retriever            └──────┬──────┘
              │                       │ ConductorDecided
              │                       │ (Orchestrator 转译回
              │                       │  ActionRequested)
              └───────────┬───────────┘
                          ▼
                  回到总线 → 下一轮分发
```

### 两层决策图

```
                   收齐的观察集
                        │
                        ▼
            ┌───────────────────────┐
            │  规则引擎 (YAML热可换)  │   ← 覆盖已知模式，确定性、可调试
            │  按 priority 降序匹配   │
            └───────────┬───────────┘
                  │     │
            命中  │     │  default(未命中)
                 ▼     ▼
        ┌──────────┐  ┌───────────────────┐
        │ 直接路由  │  │ 召唤 Conductor    │   ← LLM 看完整观察集决策
        │ → Tutor/ │  │ emit Conductor-   │     覆盖规则盲区，但成本高
        │   Retriever│  │  Requested       │
        └──────────┘  └────────┬──────────┘
                               │ LLM 返回决策
                               ▼
                       Orchestrator 转译
                       → ActionRequested
                       (并打标 via_conductor=true)
                               │
                               └──→ 同样回到「直接路由」出口
```

---

## Q4: 一次完整回合的协作时序

**日期**：2026-07-14

**问题**：
能否用一个具体例子把整个协作串起来？

**回答**：

以用户回答"我觉得是 A"（实际有概念混淆 + 前置薄弱）为例，走 `assembly.py:132` 的 `run_new_agent_session`：

```
   ① 用户消息 + TopicEntered + 首个ActionRequested(tutor_ask)  ─ 种子入队
        │
        ▼
   ┌──────────── 协作环 (单线程·优先级队列) ────────────┐
   │  优先级: LoopExit(5) < 观察(10) < 默认(20) < Tick(100)  │
   └─────────────────────────────────────────────────┘
        │
        │ ② pop 出 UserMessage → 分发给订阅者 Critic
        │        Critic 调LLM → emit MasteryAssessed + ConfusionDetected
        │
        │ ③ MasteryAssessed 被 Curator 订阅
        │        Curator 更新图谱 → emit GraphPrereqWeakDetected
        │
        │ ④ 这些观察入队时，Orchestrator 同时注入 OrchestratorTick(优先级最低100)
        │        → Tick 必然排在"本回合所有观察"之后才被弹出  ← 回合屏障
        │
        │ ⑤ pop 出 Tick → 观察已收齐 {confusion:T, prereq_weak:T, basis:observed}
        │        → 规则引擎按优先级匹配 → regress_to_prereq
        │        → emit ActionRequested(target=tutor, action=regress_to_prereq)
        │        → (可选) emit PolicyTransition(Socratic→Regress)
        │
        │ ⑥ pop 出 ActionRequested → Tutor 订阅 → 调LLM生成 → emit TutorExplained
        │
        │ ⑧ …… 循环，直到 mastered + topic_complete
        │        → 规则 loop_exit → emit LoopExit
        ▼
   pop 出 LoopExit → 出环 → assembly 提取 Tutor 面向用户事件作为最终回复

   ⚑ 熔断: 超过 MAX_TURNS=50 强制注入 LoopExit
```

**横向协作要点**：Critic 产出的 `MasteryAssessed` 被 Curator 订阅（Critic→Curator）；Retriever 产出的 `RetrievedEvidence` 又喂回 Critic 评 RAG 质量（Retriever→Critic）。这些 Agent **没有直接调用对方**，纯粹靠事件订阅形成协作链。

---

## Q5: 关键设计原则

**日期**：2026-07-14

**问题**：
这套架构背后的核心设计思想是什么？

**回答**：

### 1. 职能正交

生成(Tutor) / 语义(Critic) / 机械(Retriever) / 结构(Curator) / 路由(Conductor) 五个层面**互不越界**。代码里反复用注释强调"只 X 不 Y"（如 `tutor.py:12`、`critic.py:12`、`retriever.py:8`）。这是为了避免 LLM 在同一个调用里既当运动员又当裁判导致的评判失真。

运行时强制手段：每个 Agent 的 `emittable_types` 是"声明即契约"，越界 emit 在 `base.py:38` 直接抛 `ValueError`；EventBus.publish 的 `check_ownership` 是第二道闸（`eventbus.py:29`）。

### 2. Agent 不持有副作用

Agent 不直接写 DB/LLM（经 Harness 接口）、不写 `WorkspaceState`、不互相调用（`base.py:17-19`）。所有副作用集中在 `EventBus.publish` 一处，可追溯、可回放。

### 3. 规则优先 + LLM 兜底

确定性规则覆盖 90% 已知模式（YAML 可热可换），Conductor 只在规则失效时介入——兼顾**可调试性**与**覆盖率**，并控制 LLM 成本。Conductor 还能在"观察不足"时主动请求专业 Agent 先看（`REQUEST_OBSERVATION`），让下轮有机会命中规则，避免无脑 LLM。

---

> **一句话概括协作模式**：5 个职能正交的 Agent **只与事件总线对话**（订阅→处理→发布），**Orchestrator 作为"回合制裁判"**用回合屏障收齐所有观察、用规则引擎做确定性路由、规则失效时才召唤 **Conductor** 用 LLM 兜底——形成一条**用户→评估→图谱→路由→生成→回评估**的闭环。

---

## Q6: Curator 和 Critic 的职责区分与功能边界

**日期**：2026-08-26

**问题**：
Curator 和 Critic 两个 Agent 的职责如何区分？两者的边界和功能设计分别是什么？

**回答**：

Curator 和 Critic 是当前多 Agent 架构中最关键的一组正交设计。它们分别处理**不同层级的判断**：

- **Critic**：处理**文本语义层**，回答"用户刚才这段话体现出怎样的掌握度、混淆、矛盾与不确定性？"
- **Curator**：处理**知识结构层**，回答"当前主题在知识图谱里的前置知识是否薄弱、画像是否需要更新？"

### 1. 核心边界：语义层 vs 结构层

一句话概括就是：**Critic 读文本，Curator 读图谱。**

| 维度 | Critic | Curator |
|---|---|---|
| 判断对象 | 用户回答文本、检索证据 | 知识图谱节点与 PREREQ 边 |
| 处理层级 | 语义层 | 结构层 |
| 判据来源 | LLM 对文本语义的理解 | 图谱中 mastery 数值 + 前置关系 |
| 典型问题 | 用户是不是理解了？有没有说错？有没有混淆？ | 当前主题的前置知识是否薄弱？画像是否要更新？ |
| 是否调 LLM | ✅ 是 | ❌ 否 |

### 2. Critic 的职责设计：只判语义，不管结构

`app/agents/critic.py` 的设计重点是：**单次 LLM 调用，产出一组语义观察，再拆成多条事件 emit**。

它订阅：
- `UserMessage`
- `RetrievedEvidence`

它可能发布：
- `MasteryAssessed`
- `ConfusionDetected`
- `ContradictionDetected`
- `LowConfidenceDetected`
- `RAGQualityAssessed`

也就是说，Critic 负责的是：
1. 读用户文本，评估掌握度（level + score + rationale）
2. 识别概念混淆
3. 识别自相矛盾
4. 识别低自信表达
5. 在 teaching 场景下评估 RAG 证据质量

它**明确不做**的事：
- 不读知识图谱
- 不判断前置知识是否缺失
- 不做路由决策
- 不更新用户画像

所以 Critic 更像一个**语义传感器**：把当前回合中从文本里能观察到的事实，结构化为事件发给系统。

### 3. Curator 的职责设计：只判结构，不管文本

`app/agents/curator.py` 的设计重点是：**维护 MasteryGraph，并基于 PREREQ 边判断前置知识薄弱。**

它订阅：
- `MasteryAssessed`
- `TopicEntered`

它可能发布：
- `ProfileUpdated`
- `GraphNodeStrengthened`
- `GraphPrereqWeakDetected`

Curator 的职责分成两部分：

#### A. 图谱维护

当收到 `MasteryAssessed` 时，Curator 会：
- 更新当前 topic 节点的 mastery 值
- 记录 previous_mastery → mastery 的变化
- 发 `GraphNodeStrengthened`
- 发 `ProfileUpdated`

#### B. 前置薄弱检测

更新图谱后，Curator 会检查当前主题的前置节点：
- 如果存在 PREREQ 边
- 且某个前置 topic mastery 低于阈值
- 则发 `GraphPrereqWeakDetected`

它有两个触发时机：

| 时机 | 输入事件 | basis | 含义 |
|---|---|---|---|
| 开局/切主题 | `TopicEntered` | `historical` | 基于历史画像预判前置是否薄弱 |
| 回合中实测 | `MasteryAssessed` | `observed` | 基于当前回合最新实测结果判断前置是否薄弱 |

Curator **明确不做**的事：
- 不读取用户原始回答文本
- 不判断文本是否有混淆/矛盾
- 不调用 LLM 做语义分析

所以 Curator 更像一个**结构维护器 + 图谱裁判**。

### 4. 两者之间的协作关系：单向接力，而非双向耦合

两者最重要的协作链路是：

```text
UserMessage
  → Critic
  → MasteryAssessed
  → Curator
  → GraphNodeStrengthened / GraphPrereqWeakDetected / ProfileUpdated
```

也就是说：
- **Critic 先从文本中推导出掌握度事实**
- **Curator 再把这个事实写入图谱，并推导结构层结论**

这里是典型的**单向接力**，而不是互相调用：
- Critic 不知道图谱内部长什么样
- Curator 不知道用户原话是什么
- 两者都只通过 EventBus 交换结构化事件

### 5. 为什么要拆成两个 Agent，而不是一个 Agent 一次做完？

这个拆分的好处主要有四个：

#### （1）避免一个 LLM 既当运动员又当裁判

如果同一个 Agent 既负责理解用户文本、又负责决定图谱结构和前置缺失，那么它会把语义判断和结构判断混在同一次调用里，增加不可解释性与漂移风险。

#### （2）把"文本事实"和"图谱事实"分开

- 文本事实：来自当前一轮回答
- 图谱事实：来自多轮累积的 mastery 和记忆结构

二者本来就是不同来源，分开更清晰。

#### （3）便于独立评估

- Critic 可以单独评：给它一段用户文本，看 `MasteryAssessed` 是否合理
- Curator 可以单独评：给它一张图谱和一个 score，看 `GraphPrereqWeakDetected` 是否合理

#### （4）便于规则路由

Orchestrator 不需要理解文本本身，只需看标准化观察集：
- `mastery=weak`
- `confusion=true`
- `prereq_weak=true`
- `prereq_basis=observed`

这样路由层和内容层彻底解耦。

### 6. 一句话总结两者边界

- **Critic**：负责把"用户这段话说明了什么"变成观察事件
- **Curator**：负责把"这些观察对知识图谱意味着什么"变成结构事件

换句话说：

> **Critic 管当前语义真相，Curator 管长期结构真相。**

---

## Q7: 用户回答追问时，掌握度由谁维护、RAG 如何处理、Curator 与 Critic 如何协作

**日期**：2026-08-26

**问题**：
假设一个场景：用户回答了 Tutor 的追问。这个时候掌握度信息由谁维护？RAG 返回结果如何处理？Curator 和 Critic 在这个场景中如何协作？

**回答**：

这个场景最适合用一条完整事件链来看。可以把它理解成：

> **Critic 先把用户回答变成语义观察，Curator 再把这些观察变成图谱更新与结构判断；如果检索被触发，则 Retriever 先给证据，Critic 再评证据质量。**

### 1. 用户回答追问后，谁维护掌握度？

答案不是单一 Agent，而是一个**接力链**：

- **Critic 负责评出掌握度**
- **Curator 负责把掌握度写进图谱并维护画像/结构状态**

具体过程：

#### 第一步：Critic 评估用户回答

当 `UserMessage` 入队后，Critic 会消费它，并调用 LLM：

- 读当前 topic
- 读用户回答文本
- 输出 JSON

例如得到：

```json
{
  "mastery_level": "weak",
  "mastery_score": 30,
  "rationale": "回答中存在明显概念混淆",
  "confusion": {"concept_a": "A", "concept_b": "B"},
  "low_confidence": true
}
```

然后 Critic 会拆出事件：
- `MasteryAssessed(score=30, level=weak, rationale=...)`
- `ConfusionDetected(...)`
- `LowConfidenceDetected(...)`

这里要注意：**Critic 自己并不保存 mastery**，它只是负责把这轮语义评估结果发出来。

#### 第二步：Curator 维护掌握度图谱

Curator 订阅了 `MasteryAssessed`，因此它会接着处理：

1. 如果当前 topic 节点不存在，先创建节点
2. 读取旧 mastery
3. 把新的 score 写进 `MasteryGraph`
4. 发 `GraphNodeStrengthened(previous_mastery=..., mastery=...)`
5. 发 `ProfileUpdated`
6. 检查前置知识是否薄弱

所以从"谁维护掌握度"这个问题上说：

- **语义上的掌握度判断由 Critic 产生**
- **图谱中的掌握度状态由 Curator 维护**

### 2. RAG 返回结果如何处理？

RAG 不会在每个用户追问场景里自动发生，它只会在 Orchestrator 或 Conductor 决定需要检索时触发。

完整链路是：

```text
ActionRequested(target=retriever)
  → Retriever.search()
  → RetrievedEvidence(chunks, scores, retrieval_status)
  → Critic.handle(RetrievedEvidence)
  → RAGQualityAssessed(score, relevance, sufficiency)
  → Orchestrator 看是否需要 retriever_expand_query
```

#### Retriever 的职责

Retriever 做的是**机械检索**：
- 调 `RAGCoordinator.search()`
- 返回 chunks
- 计算原始 similarity scores
- 给出机械 `retrieval_status`
  - `empty`
  - `low_score`
  - `ok`

Retriever **不判断语义质量**。

#### Critic 的职责

Critic 订阅 `RetrievedEvidence`，但只在：

```python
if event.payload.get("purpose") != "teaching":
    return []
```

也就是**仅 teaching 场景**评估 RAG 质量。

它会基于 chunks 的数量和内容，用 LLM 评估：
- `score`
- `relevance`
- `sufficiency`
- `rationale`

然后发 `RAGQualityAssessed`。

#### Orchestrator 的后续处理

当 `RAGQualityAssessed` 进入回合屏障后，Orchestrator 把它折叠成观察字段：
- `rag_quality_low = score < 0.5`

如果命中规则：

```yaml
- name: rag_quality_low
  when:
    rag_quality_low: true
  action: retriever_expand_query
```

就会再次触发 Retriever 去扩展检索。

所以 RAG 的处理链是：

- **Retriever** 负责把证据找回来
- **Critic** 负责判断这些证据够不够好
- **Orchestrator** 决定要不要继续检索

### 3. Curator 和 Critic 在这个场景里如何协作？

两者的协作不是对话式的，而是**事件接力 + 回合汇合**。

#### 协作链 A：掌握度接力

```text
UserMessage
  → Critic
  → MasteryAssessed
  → Curator
  → GraphNodeStrengthened / GraphPrereqWeakDetected
```

这条链里：
- Critic 从文本提取出掌握度事实
- Curator 把掌握度事实写入知识图谱
- Curator 再从图谱推导结构层结论

#### 协作链 B：观察汇合到 Orchestrator

Critic 和 Curator 的事件最终都进入 Orchestrator 的 `_pending_obs`：

- Critic 贡献：
  - `mastery`
  - `confusion`
  - `contradiction`
  - `low_confidence`
  - `rag_quality_low`
- Curator 贡献：
  - `prereq_weak`
  - `prereq_basis`

当 `OrchestratorTick` 出队时，完整观察集才会被统一裁决。

例如用户回答较差、且前置薄弱时，完整观察集可能是：

```python
{
  "mastery": "weak",
  "confusion": True,
  "low_confidence": True,
  "prereq_weak": True,
  "prereq_basis": "observed"
}
```

规则优先级下：
- `prereq_weak_observed` priority 100
- `confusion` priority 80
- `weak_within_repeat` priority 70

最终会优先命中：

```yaml
action: regress_to_prereq
```

于是系统决定先回退讲前置知识，而不是继续当前问题追问。

### 4. 一个具体微回合时序

假设用户回答 Tutor 的追问：

> "我感觉大概是 A，但我不太确定，而且 B 好像也差不多。"

可能发生的时序如下：

```text
1. UserMessage 入队
2. Critic 消费 UserMessage
   → emit MasteryAssessed(level=weak, score=30)
   → emit ConfusionDetected(A, B)
   → emit LowConfidenceDetected

3. Curator 消费 MasteryAssessed
   → 更新 MasteryGraph 当前 topic 节点 mastery=30
   → emit GraphNodeStrengthened
   → emit ProfileUpdated
   → emit GraphPrereqWeakDetected(basis=observed)

4. Orchestrator 收集上述观察到 _pending_obs
   → 注入 OrchestratorTick

5. Tick 出队，Orchestrator 汇总观察
   → 规则匹配命中 prereq_weak_observed
   → emit ActionRequested(target=tutor, action=regress_to_prereq)
   → emit PolicyTransition(Socratic → Regress)

6. Tutor 消费 ActionRequested
   → emit TutorExplained（开始讲前置知识）
```

### 5. 一句话总结这个场景的协作关系

- **掌握度的语义判断**：Critic
- **掌握度的图谱维护**：Curator
- **RAG 证据的拉取**：Retriever
- **RAG 证据的质量评估**：Critic
- **基于这些观察的最终路由决策**：Orchestrator

所以这条链可以压缩成一句话：

> **Critic 负责把“用户刚才说了什么”翻译成掌握度与观察，Curator 负责把“这些观察对知识图谱意味着什么”落到长期状态里；如果需要外部知识，Retriever 拉证据，Critic 再判证据质量，最后由 Orchestrator 汇总裁决。**
