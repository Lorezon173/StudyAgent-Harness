# StudyAgent 多 Agent 重设计 — 设计文档

> **用途**：从架构层面重设计 StudyAgent，构建一个基于事件驱动的多 Agent 学习系统
> **日期**：2026-05-29
> **方法论**：融合式（苏格拉底 ⋂ 费曼）教学法
> **重构策略**：架构重设，复用底层基础设施（LLM / RAG / 记忆 / 可观测）

---

## 0. 决策快照

本设计由 brainstorming 过程中确认的 10 个关键决策驱动：

| # | 维度 | 决策 |
|---|---|---|
| 1 | 重构策略 | 架构重设，复用底层基础设施 |
| 2 | 教学方法 | 融合式（苏格拉底 ⋂ 费曼）动态切换 |
| 3 | 评估深度 | 全面量化 + 自动 A/B + 选型推荐 |
| 4 | 运行形态 | 内部多用户（10-100 用户） |
| 5 | 学科边界 | 通用学科 |
| 6 | 触发机制 | 事件驱动（独立事件总线） |
| 7 | Agent 角色 | Tutor / Retriever / Critic / Curator / **Conductor** |
| 8 | 记忆深度 | 三层 + 掌握点知识图谱 |
| 9 | 知识库 | 文档 + OCR + 代码仓库 |
| 10 | Orchestrator | 规则优先 + LLM Conductor 兜底（5 Agent） |

**架构方案**：🅲 混合型 —— LangGraph 骨架 + 外置事件总线。主图负责稳定的「输入→路由→协作环→收尾」流水线；协作环内部由独立 EventBus 驱动 5 个 Agent 协同工作（单线程事件循环，详见 §3.5）。

### 0.1 否决项及理由（防止重复讨论）

| 被否方案 | 否决理由 |
|---|---|
| 🅐 LangGraph 单图 + 事件 Hook | 事件退化为 state 字段，无独立总线与回放，事件驱动名存实亡，无法支撑 §5 部件级评估 |
| 🅑 自研 Agent Runtime（纯事件） | 失去 LangGraph 的 checkpoint / 流式 / 可视化工具链，TDD 成本过高 |
| 纯规则 Orchestrator（无 Conductor） | 用户自由发挥 / 跨主题跳跃 / 表达模糊时落 default，决策质量退化 |
| 纯 LLM Conductor（无规则） | 每事件一次 LLM，高频路径延迟 500-2000ms + token 成本不可控，决策黑盒化 |
| 4 角色（无 Conductor） | 缺少长尾决策兜底，规则未覆盖场景无解 |
| 纯费曼 / 纯苏格拉底单一教学法 | 单一方法无法覆盖"零基础→精通"全路径；融合式按掌握度动态切换更优 |
| 真并发多 Agent（多线程 / asyncio task） | 引入竞态，事件无法全序回放，违背 §5 replay 需求；教学场景本就顺序因果，真并发收益小 |

---

## 1. 整体架构

### 1.1 三层视图

```
┌────────────────────────────────────────────────────────────┐
│  API 层（FastAPI）                                         │
│  - /chat（同步）/ /chat/stream（SSE）                      │
│  - /eval/run / /eval/report（基准评估）                    │
│  - /knowledge（文档/OCR/代码仓库上传）                     │
│  - /profile/{user_id} / /graph/{user_id}（画像与图谱）     │
├────────────────────────────────────────────────────────────┤
│  Orchestration 层（LangGraph 骨架 + Agent 协作环）         │
│                                                            │
│  主图：  ingest → route → [ CollaborationLoop ] → wrap_up │
│                                ↓                           │
│           协作环 = EventBus + 5 Agents 事件协同           │
│           内部由 Orchestrator（事件消费者）决定退出时机    │
├────────────────────────────────────────────────────────────┤
│  Harness 层（核心契约）                                    │
│  - WorkspaceState：会话内共享内存                          │
│  - EventBus：发布/订阅、回放、record→trace                 │
│  - Orchestrator：事件 → 动作映射器（规则引擎 + Conductor） │
│  - TeachingPolicy：融合式循环状态机（苏格拉底 ⋂ 费曼）     │
│  - MasteryGraph：用户画像的图谱推理引擎                    │
│  - UserProfile：用户偏好与进度                             │
│  - EvalKernel：组件评估接口 + Bench Runner + A/B 控制器    │
├────────────────────────────────────────────────────────────┤
│  Infrastructure 层（复用现有基础设施 + 扩展）              │
│  - LLM Service（重试/回退/成本，已就绪）                   │
│  - RAG Coordinator（已就绪，扩展 OCR / 代码切片）          │
│  - MemoryStore（SQLite+FTS5 两层已就绪；第三层画像记忆新建）│
│  - Observability（打点已就绪；EventSink/replay/TraceStore 新建）│
└────────────────────────────────────────────────────────────┘
         ↑ 严格单向依赖：API → Orchestration → Harness → Infra ↑
```

### 1.2 与现有项目的关键变化点

| 现有 | 重设计后 |
|---|---|
| `app/agent/graph.py` 14 节点扁平主图 | 退化为 4 节点骨架（`ingest / route / collab_loop / wrap_up`） |
| `app/agent/nodes/*` 薄壳节点 | 部分转化为 Agent 内部 step，部分消失（如 `restate_check` 由 Critic 内部判定） |
| 苏格拉底单一教学法 | 融合式：Socratic / Feynman / Analogy / Regress 四模式动态切换 |
| 隐式触发（节点条件边） | 显式 EventBus + Orchestrator 规则引擎 + Conductor 兜底 |
| 会话级评估 | 两层：L1 在线 Critic + L2 旁路 EvalKernel |
| 文本记忆（两层 LRU+SQLite） | 三层记忆 + 掌握点知识图谱 |
| `app/agent/multi_agent/`（SubGraph 多 Agent） | 重写为事件驱动 5 Agent；老实现待下线 |
| `app/agent/system_eval/`（评估 SubGraph） | 重写为 L2 EvalKernel 旁路子系统；老实现待下线 |
| — | 新增 `eventbus / orchestrator / teaching_policy / mastery_graph / user_profile / eval/` |

**迁移原则**：
- 新代码写在全新目录（`orchestration/ agents/ eval/`）；老代码 `app/agent/` 全部保留不动作为参考，**重构期间严禁修改老代码**（避免并行实施时混淆——可读取参考、可整段复制改造到新文件，但不在原地编辑）。
- `app/agent/multi_agent/` 与 `app/agent/system_eval/` 与 14 节点主图一样属于待下线老代码，随 `app/agent/` 在新栈灰度稳定后（P8→P9）一并移除。**废弃理由**：原多 Agent 为 LangGraph SubGraph 隐式条件边耦合，Agent 间通过共享 state 通信而非事件，无独立事件总线、不可回放，无法支撑 §5 的部件级可评估性。
- 现有测试（基线 **155 个 test 函数**，以 `pytest` 实测为准，不硬编码数字）在整个重构期间必须持续全绿；新增模块各自补测试。

---

## 2. 五个 Agent 的职责契约

### 2.1 角色划分

| Agent | 职责 |
|---|---|
| **Tutor** | 教学主体；执行讲解、提问、追问、复述检查、类比生成；订阅 Curator 的画像和 Retriever 的证据 |
| **Retriever** | 知识检索；接 RAG + OCR + 代码索引；输出带置信度的证据片段；订阅 Tutor 的查询事件 |
| **Critic** | L1 在线评估；**只判文本语义层**：掌握度、概念混淆、自相矛盾、回答置信度、RAG 质量；发出观察事件供 Orchestrator 决策。**不读图谱、不判前置缺失、不做路由决策** |
| **Curator** | 维护用户画像与掌握点知识图谱；订阅 Critic 评估事件，更新 MasteryGraph；**只判结构层**：基于图谱前置关系 + 用户在前置节点掌握度，判定"前置薄弱"并发 `GraphPrereqWeakDetected`；为 Tutor 提供画像上下文。**不判文本语义** |
| **Conductor** | 规则未覆盖时的 LLM 决策兜底；不订阅特定事件，由 Orchestrator 按需召唤；输出「下一动作 + 理由」 |

### 2.2 统一 Agent 契约

所有 Agent 共享统一形式：

```
输入：Subscription（一组事件类型）+ WorkspaceState（只读快照）
输出：emit(Event) → 写回 EventBus；可以多次 emit
副作用：仅允许通过 Harness 接口（无直接 LLM 调用、无直接 DB 写入）
状态：每个 Agent 持有自己的 working set，不写 WorkspaceState
```

**关键约束**：
- 5 个 Agent **不直接互相调用**，只通过事件通信
- Agent 内部允许多次 LLM 调用，但必须通过统一的 `LLMService.call(node, intent, ...)` 接口（已就绪）
- 每个 Agent 必须暴露**评估接口** `evaluate(test_case) → metrics`（为 §5 评估体系准备）

### 2.3 Conductor 的特殊性

- 不订阅特定事件，而是被 Orchestrator Router **按需召唤**
- 能力是「决策下一步」，不直接产出教学内容
- 决策频率低（仅规则未覆盖时触发），token 成本可控
- 决策可记录、可回放、可被 EvalKernel 评估为「该决策与人类专家是否一致」
- 形成 L2 → L1 的反馈环：规则未覆盖率高 → Conductor 高频触发 → EvalKernel 检测出该补哪些规则 → 升级规则集

### 2.4 职能正交原则（专业的人做专业的事）

每个 Agent **只在自己的专业领域发出观察事件，不做跨域判定、不做路由决策**。"什么时候做什么"的决策权统一收归 Orchestrator。这是本设计避免职能跨越的核心约束。

以"费曼模式复述失败"为例，失败根因的诊断被正交分解为两个独立观察 + 一次中立路由：

| 子任务 | 性质 | 所需知识 | 归属 | 产出事件 |
|---|---|---|---|---|
| 这次复述质量如何 | 评估 | 用户回答的文本语义 | Critic | `MasteryAssessed` |
| 是否概念混淆 | 语义诊断 | 用户回答的文本语义 | Critic | `ConfusionDetected` |
| 是否前置缺失 | 结构诊断 | 图谱前置关系 + 用户前置掌握度 | Curator | `GraphPrereqWeakDetected` |
| 下一步去哪 | 决策路由 | 以上观察 + 优先级 | Orchestrator | `ActionRequested` |

**关键**：没有任何单一 Agent 做"混淆 vs 前置缺失"的二选一。Critic 从文本发它的、Curator 从图谱发它的，两个观察都进事件队列；Orchestrator 在"回合屏障"（§3.5）后按优先级裁决（前置缺失 priority 100 > 混淆 priority 80，故"既混淆又前置缺失"时优先补前置）。补完前置回来若仍混淆，Critic 会再次发 `ConfusionDetected`，此时图谱前置已达标、`GraphPrereqWeakDetected` 不再触发，自然走 Analogy。**时序 + 优先级自动消解冲突，无需任何 Agent 越权。**

因果链要求：Curator 必须订阅 Critic 的评估事件（`MasteryAssessed` → 触发图谱检查），这是设计的一部分而非耦合——Curator 本就应在掌握度变化时更新图谱。

---

## 3. 事件总线与 Orchestrator

### 3.1 EventBus 数据模型

```
Event {
  id: ULID            # 全局唯一 + 时序可排
  ts: float           # epoch ms
  session_id: str
  source: str         # "tutor" | "retriever" | "critic" | "curator" | "conductor" | "user"
  type: EventType     # 见 §3.2
  payload: dict       # 结构化负载
  parent_id: str?     # 因果链（用于回放和评估）
  metadata: dict      # node / intent / cost / latency_ms 等观测字段
}
```

EventBus 提供：
- `publish(event)` — 发布事件
- `subscribe(agent, event_types)` — 订阅
- `replay(session_id)` — 从 EventStore 回放整条事件链（用于评估）
- 每个事件发布时自动写入 Observability 的 EventSink（trace 沉淀）

### 3.2 事件类型清单（最小完整集）

```
== 用户输入类 ==
UserMessage              用户发言（首轮或回合中）
UserUploaded             用户上传资料

== Tutor 产出类 ==
TutorAsked               Tutor 抛出引导问题（苏格拉底模式）
TutorExplained           Tutor 给出讲解
TutorRequestedRecap      Tutor 要求用户复述（切入费曼模式）
TutorOfferedAnalogy      Tutor 给出类比

== Retriever 产出类 ==
RetrievedEvidence        证据片段集合（带 score, source, gate_status）
RetrievalFailed          检索失败/超时

== Critic 产出类 ==
MasteryAssessed          掌握度评估（mastered/partial/weak）
ConfusionDetected        混淆检测（具体哪两个概念混淆）
ContradictionDetected    自相矛盾检测
LowConfidenceDetected    用户回答置信度不足
RAGQualityAssessed       证据相关性/完整性评分

== Curator 产出类 ==
ProfileUpdated           用户画像变更
GraphNodeStrengthened    掌握点图谱：节点强度变化
GraphPrereqWeakDetected  发现"前置薄弱"，建议回退

== 控制类 ==
LoopExit                 Orchestrator 决定退出协作环
PolicyTransition         融合循环模式切换（Socratic ↔ Feynman ↔ Analogy ↔ Regress）
ActionRequested          Orchestrator 请求 Tutor/Retriever 做下一步
ConductorRequested       规则未覆盖，Orchestrator 召唤 Conductor 决策
ConductorDecided         Conductor 输出决策（动作 + 理由），转为 ActionRequested
OrchestratorTick         内部哨兵：最低优先级，micro-turn 内观察事件静默后触发一次路由决策（实现回合屏障，§3.5.3）
```

### 3.3 Orchestrator 内部结构

Orchestrator 不是 Agent，而是一个**事件路由器**，订阅全部事件：

```
Orchestrator（事件路由器）
   ├── RuleEngine（YAML 规则，~1ms 决策，覆盖高频路径）
   └── 落到 default → 召唤 ConductorAgent（LLM 决策，~1s，处理长尾）
```

决策流程：
```
事件到达 Orchestrator
   ↓
1. 尝试规则匹配（< 1ms）
   ↓
   命中？───── Yes ────→ 发出 ActionRequested（高频路径，零成本）
   ↓
   No
   ↓
2. 落到 ConductorAgent（LLM 决策，500-2000ms）
   输入：最近 N 条事件 + WorkspaceState 快照 + MasteryGraph 摘要
   输出：下一动作 + 选择理由
   ↓
3. 将本次决策记入 trace，喂给 EvalKernel 离线学习"该补什么规则"
```

### 3.4 规则引擎 DSL

```yaml
# orchestrator_rules.yaml （热可换，在 §5 评估时作为对照实验变量）
rules:
  - when: GraphPrereqWeakDetected
    action: REGRESS_TO_PREREQ        # 立即回退到前置点
    priority: 100

  - when: ContradictionDetected
    action: TUTOR_CORRECT            # Tutor 直接讲解
    priority: 90

  - when: ConfusionDetected
    action: TUTOR_OFFER_ANALOGY      # 类比深化
    priority: 80

  - when: MasteryAssessed.level == "weak" AND repeat_count < 2
    action: TUTOR_RE_EXPLAIN         # 重新讲解
    priority: 70

  - when: MasteryAssessed.level == "partial"
    action: TUTOR_REQUEST_RECAP      # 切入费曼，让用户复述
    priority: 60

  - when: MasteryAssessed.level == "mastered" AND topic_complete
    action: LOOP_EXIT                # 出环到 wrap_up
    priority: 50

  - when: RAGQualityAssessed.score < threshold
    action: RETRIEVER_EXPAND_QUERY   # 让 Retriever 重新检索
    priority: 40

  - default:
    action: CONDUCTOR_DECIDE         # 缺省交给 Conductor 兜底决策
```

**关键属性**：
- 规则有 `priority`，多条命中按优先级取最高
- 规则可热配置，在评估体系（§5）中作为可对照的"教学策略变量"
- default 规则把未覆盖情况交给 Conductor，避免死锁与决策退化

### 3.5 协作环执行模型（单线程事件循环 + 优先级队列 + 回合屏障）

这是整个设计的执行内核，决定 5 个 Agent 如何"协同"、事件如何保证可回放、如何与同步 LangGraph 嵌套。

#### 3.5.1 单线程事件循环

协作环对 LangGraph 主图表现为**一个普通的同步节点**。进入该节点后，内部运行一个单线程事件循环：

```
def collab_loop(workspace_state):
    queue = PriorityQueue()                    # 优先级队列
    queue.push(UserMessage(...))               # 用户输入作为种子事件
    turn = 0
    while not queue.empty():
        turn += 1
        if turn > MAX_TURNS:                   # 死循环熔断（见 §9）
            queue.push(LoopExit(reason="max_turns"))
        event = queue.pop()                    # 取优先级最高的事件
        if event.type == LoopExit:
            break
        for agent in subscribers_of(event.type):
            for new_event in agent.handle(event, workspace_state):
                queue.push(new_event)          # Agent 产出的事件回灌队列
        bus.persist(event)                     # 写 EventStore（可回放）
    return workspace_state
```

**为什么单线程**：
- 消除竞态，事件全序可排（直接满足 §5 的 `replay()` 需求）
- 与 LangGraph 嵌套极简：协作环就是一次同步节点执行，对主图透明
- Agent "并发"实为"协同"：每个 Agent 是事件 handler（短任务），不是长驻 task

**代价（已纳入 §9 风险）**：单 Agent 内的 LLM 调用是阻塞的，一回合内多 Agent 无法真并行省时延。但教学场景本就顺序因果（先检索→后讲解→再评估），真并行收益小、可回放收益大，权衡值得。

#### 3.5.2 优先级队列

事件按 `priority` 出队，优先级对齐 §3.4 规则表（如 Critic 的 `ContradictionDetected` 能插队到普通 Tutor 事件前）。同优先级按 `ts` FIFO，保证确定性回放。

#### 3.5.3 回合屏障（micro-turn barrier）—— 职能正交的执行保障

**问题**：若 Critic 的 `ConfusionDetected` 一入队就被 Orchestrator 立刻路由到 Analogy，Curator 的 `GraphPrereqWeakDetected` 还没来得及发，§2.4 的优先级裁决就失效了。

**机制**：Orchestrator **不是每个观察事件一到就路由**，而是采用"回合屏障"——

```
一个 micro-turn = 从某个 UserMessage / ActionRequested 触发，
                  到所有被触发的 Agent 都 emit 完毕（观察事件子队列静默）。

Orchestrator 在 micro-turn 内只收集观察事件（MasteryAssessed /
ConfusionDetected / GraphPrereqWeakDetected / RAGQualityAssessed ...），
不立即决策；待观察事件静默后，对完整观察集做一次路由裁决，
产出唯一的 ActionRequested（或 ConductorRequested / LoopExit）。
```

实现上：观察类事件 priority 高于动作决策，Orchestrator 的"决策"本身是一个最低优先级的哨兵事件 `OrchestratorTick`，只有当队列里没有更高优先级的观察事件时才被处理——队列的优先级语义天然实现了屏障。

这保证 Orchestrator 看到的永远是**完整观察集**，§2.4 的正交分解才能正确工作。

#### 3.5.4 与 LangGraph 的嵌套边界

| 层 | 范式 | 职责 |
|---|---|---|
| 主图（graph.py） | LangGraph 同步 StateGraph | `ingest → route → collab_loop → wrap_up`，提供 checkpoint / 流式 / 可视化 |
| 协作环（collab_loop.py） | 单线程事件循环 | 进入即接管控制权，跑事件循环直到 `LoopExit`，返回更新后的 WorkspaceState |
| Agent | 事件 handler | 被事件触发，产出新事件，无控制权 |

进/出环点明确：`route` 节点决定是否进环（如纯 FAQ 可不进环直接答）；`LoopExit` 是唯一出环信号。

---

## 4. 融合式教学循环（苏格拉底 ⋂ 费曼）

### 4.1 四种模式语义

| 模式 | Tutor 行为 | 用户角色 | 核心意图 |
|---|---|---|---|
| **Socratic** | 抛出引导性问题，不直接给答案 | 思考与回答 | 引出用户已有认知，诊断起点 |
| **Feynman** | 沉默倾听，要求用户复述/教授 | **主讲**，把知识"教给 AI" | 通过"讲出来"暴露盲点 |
| **Analogy** | 给出类比/比喻，要求用户验证类比 | 验证并扩展类比 | 用熟悉事物搭桥，破除概念混淆 |
| **Regress** | 退回前置点，开启前置小循环 | 学习前置知识 | 补齐缺失的前置根基 |

### 4.2 完整状态转移表

模式切换由 Orchestrator 按规则发出 `PolicyTransition` 事件触发。下表是**完整且自洽**的转移定义（替代早期不一致的状态图）：

| 当前模式 | 触发事件（观察） | 目标模式 | 说明 |
|---|---|---|---|
| Socratic | `MasteryAssessed=mastered` ∧ 主题完成 | （LoopExit） | 出环到 wrap_up |
| Socratic | `MasteryAssessed=partial` | Feynman | 切入费曼，让用户复述检验 |
| Socratic | `MasteryAssessed=weak` ∧ repeat<2 | Socratic | 换个角度重新引导（自环） |
| Socratic | `ConfusionDetected` | Analogy | 概念混淆，用类比破解 |
| Socratic | `GraphPrereqWeakDetected` | Regress | 前置薄弱，回退补根基 |
| Feynman | `MasteryAssessed=mastered` | Socratic | 复述达标，回苏格拉底收尾 |
| Feynman | `ConfusionDetected` | Analogy | 复述暴露**概念混淆** → 类比 |
| Feynman | `GraphPrereqWeakDetected` | Regress | 复述暴露**前置缺失** → 回退 |
| Feynman | `MasteryAssessed=weak`（无混淆无前置缺失） | Socratic | 单纯讲不清，回引导重讲 |
| Analogy | `MasteryAssessed≥partial`（类比被理解） | Socratic | 类比奏效，回主线 |
| Analogy | `MasteryAssessed=weak`（类比无效） | Regress | 类比也救不了 → 疑似前置问题，回退 |
| Regress | 前置点 `MasteryAssessed=mastered` | Socratic | 前置补齐，回到原主题主线 |
| Regress | 前置点仍 `GraphPrereqWeakDetected` | Regress | 前置的前置也弱 → 继续向下回退（自环） |
| 任意 | `turn > MAX_TURNS` | （LoopExit） | 熔断出环（§9） |

**Feynman 失败分流的职能归属**（呼应 §2.4）：Feynman 复述失败时，"走 Analogy 还是 Regress"不由任何单一 Agent 二选一决定，而是 Critic（发 `ConfusionDetected`）与 Curator（发 `GraphPrereqWeakDetected`）各自从专业领域发观察，Orchestrator 在回合屏障后按优先级裁决（前置缺失优先）。

模式历史由 TeachingPolicy 记录，供 §5 评估"模式切换合理性"。

### 4.3 典型回合的事件流（示例）

```
0  UserMessage("帮我理解什么是 RAG")
1  ActionRequested(retriever_search)
2  RetrievedEvidence(3 chunks, score=0.78)
3  ActionRequested(tutor_ask)                  # 进 Socratic 模式
4  TutorAsked("你认为 LLM 直接回答和借助外部资料有什么区别？")
5  UserMessage("可能借助资料更准确？")
6  MasteryAssessed(partial)
7  PolicyTransition(Socratic → Feynman)        # 切入费曼
8  TutorRequestedRecap("请用你的话描述一下 RAG 的流程")
9  UserMessage("先搜，再给 LLM …呃 LLM 处理一下")
10 ConfusionDetected(retrieve vs augment)      # Critic 从文本发现混淆
11 PolicyTransition(Feynman → Analogy)         # 回合屏障后路由：无前置缺失，故走 Analogy
12 TutorOfferedAnalogy("RAG 就像考试时翻参考书…")
13 UserMessage("哦原来检索是把资料塞进 prompt")
14 MasteryAssessed(mastered)
15 GraphNodeStrengthened(RAG, +0.3)
16 LoopExit                                    # 出环到 wrap_up
```

整个回合不需要硬编码主图节点，全由事件 + 规则驱动。

---

## 5. 评估体系（核心模块 — 两层架构）

### 5.1 整体视图

```
┌─────────────────────────────────────────────────────────┐
│                    L1: 在线评估                          │
│           Critic Agent（每事件 / 每会话）                │
│           影响当前会话的下一步动作                       │
└─────────────────────────────────────────────────────────┘
                          ↓ 沉淀
           ┌──────────────────────────────────┐
           │  Event Trace Store（事件回放仓） │
           │  - 每个会话完整事件链记录        │
           │  - 含每个 LLM 调用的 span        │
           │  - 含 Agent 输入/输出快照        │
           └──────────────────────────────────┘
                          ↑ 输入
┌─────────────────────────────────────────────────────────┐
│                  L2: 旁路评估 EvalKernel                  │
│   独立运行（CLI / API / CI 触发，不影响线上流量）         │
│                                                          │
│   ┌─ ComponentBench（部件级）                            │
│   │   对每个 Agent / 每个 Infrastructure 组件单独跑      │
│   │   benchmark，输出标准化指标                          │
│   ├─ SystemBench（系统级）                               │
│   │   端到端跑预定义"学习场景"，输出产品级指标            │
│   ├─ ABController（对照实验）                            │
│   │   把同一 benchmark 在两套配置下并行跑，输出 diff      │
│   └─ SelectionReporter（选型推荐）                       │
│       基于 ABController 历史，输出 Markdown 报告         │
└─────────────────────────────────────────────────────────┘
```

**L1 与 L2 的关系**：L1（Critic）在会话内运行，决策权影响下一步动作，每事件触发；L2（EvalKernel）旁路运行，评估整个 Agent 集群所有成员 + 所有部件 + 系统级指标，输出选型建议但不影响在线流量。两者通过 Event Trace Store 解耦。

### 5.1.1 黄金集标注流程与 judge 模型独立性（评估可信度基石）

所有"对照标准答案"的评估都依赖黄金集（golden set）。黄金集质量直接决定 §5.2/§5.3 指标是否可信，故强制以下流程：

**黄金集标注流程**：
1. **双人独立标注**：每条样本由 ≥2 名标注者独立打标（掌握度等级 / 是否混淆 / 前置点等）。
2. **一致性门槛**：计算标注者间 Cohen's κ，κ < 0.6 的维度退回重新定义评分细则（rubric），直到达标。
3. **分歧仲裁**：标注不一致的样本由第三方仲裁，记录仲裁理由。
4. **冻结为不可变 fixture**：通过的黄金集打版本号冻结，存入 `tests/golden/`，此后只增不改（改则升版本），保证跨次评估可比。

**judge 模型独立性（防自我裁判）**：
- 凡用 LLM-as-judge 的指标（解释完整性、图谱连接合理性、Conductor 决策合理性等），**judge 模型必须与被评 Agent 的模型不同族**（如被评 Tutor 用 Claude，则 judge 用 GPT，反之亦然），杜绝"自己给自己打高分"。
- judge 采用**盲评**：不告知 judge 哪个输出来自被评系统、哪个来自基线/对照。
- judge 本身也要校准：judge 的打分与人类黄金标注的一致率（κ）须 ≥ 0.6 才采信该 judge；不达标则换 judge 模型或细化 rubric。
- A/B 实验（§5.4）中 control 与 treatment 由**同一个 judge** 盲评，消除 judge 偏置对 diff 的影响。

### 5.2 ComponentBench 部件级评估接口

每个可评估的部件必须实现：

```
class Evaluatable:
    name: str                       # 唯一标识
    version: str                    # 版本号（用于 A/B）

    def fixtures() -> list[TestCase]:
        # 返回该部件的标准测试用例集

    def run(test_case) -> Output:
        # 执行一次推理

    def metrics(output, expected) -> dict:
        # 输出标准化指标
```

**各部件指标设计**：

| 部件 | 核心指标 |
|---|---|
| **Tutor** | 类比新颖度（unique-trigram ratio）、解释完整性（rubric-LLM-judge）、引导问题开放性（avg q-length / 是否含答案）、回合数效率 |
| **Retriever** | RAG 三件套（faithfulness / answer_relevancy / context_precision）、recall@k、检索延迟、证据冗余度 |
| **Critic** | 掌握度判定与"人类标注"一致率（Cohen's κ）、混淆检测准确率、误报率 |
| **Curator** | 画像更新一致性、图谱节点连接合理性（LLM-judge）、画像漂移检测 |
| **Conductor** | 决策与人类专家一致率、决策置信度分布、触发频次 |
| **LLM Service** | TTFB、TPOT、cost/1k、retry-rate、fallback-rate |
| **RAG Coordinator** | 索引构建速度、查询 P95 延迟、chunk-overlap 合理性 |
| **MemoryStore** | 查询延迟、记忆召回准确率（合成测试集） |
| **MasteryGraph** | 节点更新延迟、前置依赖推理准确率、图谱一致性 |

### 5.3 SystemBench 系统级评估

预定义一组"标准学习场景"（黄金集），每个场景是一份多回合脚本：

```yaml
scenarios:
  - name: "零基础学习 RAG 概念"
    user_profile: blank
    topic: "RAG"
    script: [...]              # 模拟用户的多轮回复
    expected:
      mastery_reached: mastered
      max_turns: 12
      cost_usd: < 0.05

  - name: "有基础但有混淆"
    user_profile:
      mastered: ["LLM 基础"]
      confused_pairs: [["retrieval", "fine-tuning"]]
    expected:
      confusion_detected_within_turns: 3
      mastery_reached: mastered

  - name: "跨主题跳跃（触发 Conductor）"
    script: 模拟用户中途切到另一主题
    expected:
      conductor_triggered: true
      no_loss_of_context: true

  - name: "前置薄弱触发回退"
    script: 直接学习"transformer 注意力机制"但缺少"向量乘法"
    expected:
      regress_to_prereq: true
```

**输出维度**：
- **教学效果**：掌握度达成率、平均所需回合数、平均冷启动时延
- **资源消耗**：cost、token、调用次数
- **决策质量**：Conductor 触发率、规则命中率、误退出环率
- **可靠性**：错误率、超时率、回退路径触发率

**硬约束红线**（任一超限即标记为 regression，阻断"建议升级"）：
- `cost_usd_per_session` < 上限（按"内部多用户 10-100"预算设定，默认 0.10 USD/会话，可配置）
- `p95_turn_latency` < 上限（默认 8s/回合）
- `conductor_trigger_rate` < 上限（默认 30%，过高说明规则集需补充，而非真长尾）
- 每个场景设 `max_turns` 上限，超限视为"教不会"失败

### 5.4 ABController 对照实验

```yaml
ab_experiment:
  name: "Tutor LLM 升级试验"
  variants:
    control:
      tutor.llm.model: "claude-sonnet-4-6"
    treatment:
      tutor.llm.model: "claude-opus-4-7"
  scenarios: [zero_base_rag, confused_basics, ...]
  metrics_to_compare: [类比新颖度, mastery_reached, cost_usd]
  repeats: 3
  significance: 95%
```

执行结果写入 `eval_runs/` 目录，每次实验是不可变快照。

### 5.5 SelectionReporter 输出形式

```markdown
# 选型建议报告 — 2026-05-30
## 建议替换：Tutor LLM
- **从** sonnet-4-6 **到** opus-4-7
- 类比新颖度：+18%（p=0.02）
- 解释完整性：+9%（p=0.04）
- cost/turn：+12%
- 在你设定的"教学质量 / 成本"权重（0.7:0.3）下，**得分 +14%**

## 建议保持：Retriever embedding
- text-embedding-3-large vs text-embedding-3-small
- recall@5 差异不显著（p=0.31），保持小模型节省 60% 成本

## 建议添加规则到 Orchestrator
- ConductorAgent 在"用户连续两轮跑题"的事件模式下被触发 47 次
- 这 47 次决策中 91% 收敛到 "TUTOR_REQUEST_RECAP"
- 建议添加规则：when=UserDriftedTwice → action=TUTOR_REQUEST_RECAP
```

---

## 6. 核心数据结构

```
# WorkspaceState（会话内共享，类似当前 LearningState 但精简）
WorkspaceState {
  session_id: str
  user_id: str
  current_topic: str?
  current_mode: TeachingMode             # Socratic | Feynman | Analogy | Regress
  turn_count: int

  events: list[EventRef]                 # 仅引用，正文存 EventStore
  evidence_pool: list[Evidence]          # Retriever 最近输出
  critic_state: CriticState              # 最近一次评估
  profile_snapshot: ProfileSnapshot      # 进入会话时的画像快照
}

# MasteryGraph（用户级，持久化）
MasteryGraph {
  user_id: str
  nodes: dict[str, MasteryNode]          # 知识点 ID → 节点
  edges: list[MasteryEdge]               # 边（前置/相关/混淆）
}

MasteryNode {
  topic_id: str
  topic_name: str
  mastery: float                          # 0-1
  last_practiced_at: float
  practice_count: int
  confusion_with: list[str]               # 与之混淆的 topic_id
}

MasteryEdge {
  from_topic: str
  to_topic: str
  type: PREREQ | RELATED | CONFLICT
  weight: float
  confidence: float                       # 边的置信度（LLM 推断的边低置信，被交互验证后升权）
  source: DOC_ORDER | LLM_INFER | INTERACTION   # 边的来源（见 §6.1 冷启动建图）
}

# UserProfile（用户级，持久化）
UserProfile {
  user_id: str
  preferences: {                          # 用户偏好（Curator 推断）
    explanation_style: visual|verbal|mathematical
    pace: slow|normal|fast
    depth: shallow|standard|deep
  }
  topics_active: list[str]
  topics_mastered: list[str]
  learning_streak: int
  total_sessions: int
}
```

### 6.1 MasteryGraph 冷启动建图（否则 Regress 模式无边可走）

**问题**：通用学科下，新用户的 MasteryGraph 是空的，没有 PREREQ 边 → `GraphPrereqWeakDetected` 永不触发 → Regress 模式形同虚设。图谱必须能"边用边长"，而非要求预置完整学科图谱。

**冷启动 PREREQ 边的三个来源（采纳"三者都要、置信度加权"）**：

| 来源 | 机制 | 初始 confidence |
|---|---|---|
| `DOC_ORDER` | Retriever 检索到的文档/教材章节顺序隐含前置关系（前面章节是后面的前置） | 中（0.5） |
| `LLM_INFER` | 首次涉及某主题时，由一次轻量 LLM 调用"推断该主题的 2-3 个前置点"，懒加载补边 | 低（0.3） |
| `INTERACTION` | 实际交互验证：用户在 A 弱导致 B 学不会，则强化 A→B 的 PREREQ 边 | 高（0.8） |

**演进规则**：
- 边按 `confidence` 加权参与 Regress 判定；低置信边（仅 LLM 推断、未被验证）触发 Regress 前需更高的"前置薄弱"阈值，避免误退回。
- 被实际交互验证的边（`INTERACTION`）升权；多次验证后成为高置信主干边。
- 这样图谱从"稀疏低置信"逐步长成"密集高置信"，Regress 决策质量随用户使用而提升。

**归属**：冷启动建图属于 Curator 职责（它拥有 MasteryGraph），LLM_INFER 的前置推断是 Curator 的一个子任务（并行实施计划 Plan B 承担）。

### 6.2 三层记忆定义（明确"第三层"）

决策快照的"三层记忆"具体为：

| 层 | 存储 | 作用域 | 负责组件 | 状态 |
|---|---|---|---|---|
| L1 工作记忆 | ShortTermStore（LRU+TTL，内存） | 当前会话上下文 | 现有 memory.py | 复用 |
| L2 会话记忆 | LongTermStore（SQLite+FTS5） | 跨会话「主题×用户」文本汇总 | 现有 memory.py | 复用 |
| **L3 画像记忆** | MasteryGraph + UserProfile（SQLite） | 用户级结构化画像（掌握度图谱 + 偏好） | **Curator（新建）** | 新建 |

**澄清**：现有 `memory.py` 只有 L1+L2 两层；"第三层"不是扩展 memory.py，而是由 Curator 维护的 MasteryGraph + UserProfile 这套**结构化画像**。它与 L2 的区别是：L2 是文本检索式记忆，L3 是结构化可推理画像（支持前置依赖推理、掌握度量化）。

---

## 7. 目录结构

> 标注说明：**[复用]** 原样使用老代码 · **[扩展]** 在现有文件上增能 · **[新增]** 全新文件 · **[下线]** 待 P9 删除

```
app/
├── api/                       # [扩展] 现有 8 路由，仅加 feature flag 切新栈
│
├── orchestration/             # [新增] 目录（取代老 agent/ 的编排职责）
│   ├── graph.py               # [新增] 4 节点骨架：ingest/route/collab_loop/wrap_up
│   ├── collab_loop.py         # [新增] 协作环：单线程事件循环（§3.5）
│   └── routers.py             # [新增] 主图条件边
│
├── agents/                    # [新增] 目录（5 个 Agent 实现）
│   ├── base.py                # [新增] AgentBase 抽象 + Subscription API
│   ├── tutor.py               # [新增]（可参考老 nodes/explain,diagnose,followup 改造）
│   ├── retriever.py           # [新增]（可参考老 nodes/knowledge_retrieval,evidence_gate）
│   ├── critic.py              # [新增]（可参考老 nodes/evaluate,restate_check）
│   ├── curator.py             # [新增]（可参考老 harness/memory）
│   └── conductor.py           # [新增]
│
├── harness/                   # [已存在] 目录含 8 文件，下列为增量
│   ├── enums.py               # [扩展] 加 TeachingMode, EventType, ActionKind
│   ├── workspace_state.py     # [新增]（取代老 state/，老 state/ 待下线）
│   ├── eventbus.py            # [新增] 核心
│   ├── orchestrator.py        # [新增] 规则引擎 + Conductor 召唤 + 回合屏障
│   ├── teaching_policy.py     # [新增] 模式状态机（§4.2）
│   ├── mastery_graph.py       # [新增] 含冷启动建图（§6.1）
│   ├── user_profile.py        # [新增]
│   ├── observability.py       # [扩展] 加 EventSink（replay/TraceStore 是新能力）
│   ├── memory.py              # [复用] L1+L2 两层不动；L3 画像在 mastery_graph/user_profile
│   ├── intent_router.py       # [复用] route 节点可调用
│   ├── error_handler.py       # [复用]
│   ├── guardrails.py          # [复用]
│   ├── tool_registry.py       # [复用]
│   ├── state_manager.py       # [复用/评估] 视集成需要
│   └── state/                 # [下线] 老分层 state，随 P9 移除
│
├── infrastructure/
│   ├── llm.py                 # [复用] 直接用现有 LLMService
│   ├── rag/
│   │   ├── coordinator.py     # [扩展] 接入 OCR + 代码切片来源
│   │   ├── store.py           # [复用]
│   │   ├── extractors/        # [扩展] 现有 file_extract，补 DOCX
│   │   ├── ocr.py             # [扩展] 现有 external/ocr.py 提升为正式管道
│   │   └── code_index.py      # [新增] git clone + AST 切片
│   └── storage/
│       ├── session_store.py 等       # [复用] 现有 5 个 store
│       ├── mastery_graph_store.py    # [新增]
│       └── event_store.py            # [新增] 事件持久化 + replay 支撑
│
├── agent/                     # [下线] 老编排全栈（graph/nodes/multi_agent/
│   │                          #        system_eval/spec_*），P9 整体删除，
│   │                          #        重构期间只读不改
│   └── ...
│
└── eval/                      # [新增] 目录（L2 评估子系统）
    ├── kernel.py              # [新增] EvalKernel 入口
    ├── component_bench.py     # [新增] 部件级
    ├── system_bench.py        # [新增] 系统级
    ├── ab_controller.py       # [新增] A/B 框架
    ├── selection_reporter.py  # [新增] 选型报告
    ├── scenarios/             # [新增] 预定义场景 YAML
    └── fixtures/              # [新增] 各部件的测试用例

tests/
├── unit/                      # [复用] 既有 155 基线，持续全绿
├── eval/                      # [新增] 评估子系统自己的 TDD
└── golden/                    # [新增] 人类标注黄金集（双标注+κ，§5.1.1）

superpowers/                   # [新增] 规划归档（dev-standards.md 要求）
└── 2026-05-29-multi-agent-redesign-raw.md   # 本次原始计划
```

---

## 8. 里程碑切片

> 验收一律以 `pytest` 实测全绿为准（基线 155 个 test 函数不减少），不硬编码数字。每阶段附回退判据。

| Phase | 内容 | 验收 | 回退判据 |
|---|---|---|---|
| **P0** | 仓库 scaffold：新目录 + 不动老代码 | 老代码 pytest 全绿 | 老测试变红 → 回退，新目录与老代码必有耦合 |
| **P1** | 核心契约：WorkspaceState + EventBus + AgentBase + EventStore | EventBus 单测 + AgentBase 注册测试 + 回放测试 | 事件无法全序回放 → 重审 §3.5 执行模型 |
| **P2** | 5 Agent 骨架 + Orchestrator 规则引擎 + 回合屏障 + 4 教学模式 | 协作环跑通空脚本，回合屏障单测通过 | 屏障失效（观察集不完整即路由）→ 回退 §3.5.3 |
| **P3** | 完整教学循环（Critic 评分 → 模式切换 → wrap_up） | 走通 1 个标准场景 | 模式切换不自洽（违反 §4.2 转移表）→ 回退 |
| **P4** | RAG 扩展（OCR + 代码索引）+ MasteryGraph 集成 + 冷启动建图 | 场景"前置薄弱触发回退"通过 | 空图谱下 Regress 不触发 → 回退 §6.1 建图 |
| **P5** | EvalKernel 部件级 ComponentBench + 5 Agent 各跑 1 fixture | 输出 JSON 报告 | judge 与黄金集 κ<0.6 → 换 judge/细化 rubric |
| **P6** | EvalKernel 系统级 SystemBench + 4 预定义场景 | 输出 Markdown 报告 | 任一红线（§5.3）超限 → 标记 regression 不通过 |
| **P7** | ABController + SelectionReporter | 跑通 "Tutor 模型升级" 对照实验 | 同 judge 盲评未生效（judge 偏置）→ 回退 §5.1.1 |
| **P8** | 老代码灰度切换：API feature flag 把 /chat 切新栈 | 灰度上线，新旧栈指标对齐 | 新栈关键指标劣于老栈 → 关 flag 回老栈 |
| **P9** | 删除 `app/agent/`（含 multi_agent/system_eval） | 老代码下线，pytest 全绿 | 删除后有 import 断裂 → 回退，残留耦合未清 |

---

## 9. 风险与权衡

| 风险 | 缓解 |
|---|---|
| 两套范式（LangGraph 骨架 + 事件总线）边界混淆 | 协作环作为单一超级节点，边界文档化（§3.5.4）；进/出环点明确 |
| 单线程事件循环：一回合内多 Agent 无法真并行省时延 | 教学场景本顺序因果，真并行收益小；可回放收益大，权衡接受（§3.5.1） |
| 回合屏障判定"micro-turn 何时结束"出错 | 用优先级队列语义实现（队列无更高优先级观察事件即屏障），有专项单测（P2） |
| EventBus 死循环 | default 规则保证总有动作；`MAX_TURNS` 熔断强制 `LoopExit`（§3.5.1/§4.2） |
| Conductor LLM 决策延迟拖慢会话 | 规则覆盖高频路径，Conductor 仅长尾触发；`conductor_trigger_rate` 红线监控（§5.3） |
| 老代码在重构期间回归 | 新代码全在新目录；老代码只读不改，保留至 P8 灰度稳定（基线 155 测试持续全绿） |
| 评估体系工程量大 | 按 P5→P7 分阶段交付，先部件级后系统级后 A/B |
| LLM-as-judge 自我裁判 | judge 与被评模型强制不同族 + 盲评 + judge 自身 κ 校准（§5.1.1） |
| 空图谱致 Regress 失效 | 冷启动建图三来源 + 置信度加权，图谱边用边长（§6.1） |
| MasteryGraph 维护复杂 | 节点强度增量更新；图谱一致性纳入 ComponentBench |

---

## 10. 规范同步要求（遵循 agent-root.md）

按项目规范，所有 `.md` 规范文件修改时必须同步修改对应的 `.prompt.md`。本次重设计引入新的 Agent 角色与教学模式，需在实现阶段同步创建：

- `specs/agents/tutor.md` ↔ `.prompt.md`
- `specs/agents/retriever.md` ↔ `.prompt.md`
- `specs/agents/critic.md` ↔ `.prompt.md`
- `specs/agents/curator.md` ↔ `.prompt.md`
- `specs/agents/conductor.md` ↔ `.prompt.md`
- `specs/intent_map.yaml` → 新增 `event_map.yaml`（事件→订阅者→动作映射，取代旧 intent_map）

具体规范内容在 writing-plans 阶段细化。

---

## 11. 规划追溯（遵循 dev-standards.md）

本 spec 的设计来源可追溯至 brainstorming 原始材料：

- **raw 材料**：`superpowers/2026-05-29-multi-agent-redesign-raw.md`（项目根 `superpowers/` 目录，非 `docs/superpowers/`；按 dev-standards.md，raw 归档在根、spec 在 `docs/superpowers/specs/`）
- raw 含：原始诉求、规模评估、9 个澄清决策、3 方案对比、2 点评审反馈（评估两层化 + Orchestrator 升级 Conductor）、职能正交（候选 C）讨论

**并行实施划分**（已与用户确认，writing-plans 阶段产出）：6 份计划 / 3 波次
- Wave 0：Plan 0 核心契约地基（WorkspaceState/EventBus/AgentBase/EventStore/enums/骨架）
- Wave 1（并行）：Plan A 检索与知识库 · Plan B 记忆与画像 · Plan C 教学与编排
- Wave 2（并行）：Plan D 集成与灰度 · Plan E 评估体系
- 每份计划自带「上下文与老代码改造指引」：负责文件 / 依赖前置 / 可改造来源 / 严禁触碰范围
