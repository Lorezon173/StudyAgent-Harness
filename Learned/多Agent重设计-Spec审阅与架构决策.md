# 多 Agent 重设计 — Spec 审阅记录

> **日期**：2026-05-29（持续更新）
> **来源**：对 `docs/superpowers/specs/2026-05-29-multi-agent-redesign-design.md` 的两轮深度审阅
> **状态标注**：✅ 已决策 / 🔧 已修复（spec 已更新） / 💬 待讨论 / 📌 已记录

---

## 目录

1. [现存模块缺失：multi_agent/ 与 system_eval/ 未提及](#1)
2. [目录结构与现状偏离](#2)
3. ["147 个测试"数字不准确](#3)
4. [基础设施"已就绪"程度需校准](#4)
5. [EventBus 协作环执行模型缺失](#5)
6. [教学状态机"悬空状态"](#6)
7. [Critic 自评估"裁判循环"](#7)
8. [MasteryGraph 前置依赖从哪来（cold-start）](#8)
9. [评估体系与现有 system_eval 的关系](#9)
10. [决策快照缺少"否决项"](#10)
11. [里程碑缺少回退判据](#11)
12. [成本预算未量化](#12)
13. [raw 追溯材料缺失](#13)
14. [emit 白名单：职能正交的运行时强制](#14)
15. [复述检查归属：spec 内部矛盾](#15)
16. [Conductor 越权风险：规则未覆盖时正交如何不塌](#16)
17. [Curator 触发时机：开局前置薄弱测不到](#17)
18. [证据质量双归属：RAG 质量到底谁判](#18)
19. [协作评估层缺失：测不出协作质量](#19)
20. [消融实验缺失](#20)
21. [黄金协作轨迹缺失](#21)

---

### 1. 现存模块缺失：multi_agent/ 与 system_eval/ 未提及 ✅

**发现**：代码库中已存在 `app/agent/multi_agent/`（orchestrator_graph / teaching_graph / retrieval_graph / eval_graph）和 `app/agent/system_eval/`（eval_graph / orchestrator_eval / teaching_eval），但 spec §1.2 的"现有 vs 重设计后"对照表只字未提，仅把现状描述为"14 节点扁平主图"。新设计的核心命题（多 Agent、Orchestrator、评估体系）恰与这两个现存模块高度重叠。

**决策**：完全废弃重写。将 `app/agent/multi_agent/` 和 `app/agent/system_eval/` 与 14 节点主图一样列入待下线老代码，新栈稳定后（P9）随 `app/agent/` 一并移除。废弃理由：原多 Agent 为 LangGraph SubGraph 隐式条件边耦合，Agent 间通过共享 state 通信而非事件，无独立事件总线、不可回放，无法支撑 §5 的部件级可评估性。

**spec 变更**：§1.2 对照表补上这两个模块及处置策略。

---

### 2. 目录结构与现状偏离 ✅

**发现**：spec §7 的目录树把 `app/harness/` 写成全新目录，但实际上它已存在且含 8 个文件（enums.py / memory.py / observability.py / state_manager.py / guardrails.py / intent_router.py / error_handler.py / tool_registry.py）。未标注哪些文件复用、哪些扩展、哪些新增。

**决策**：目录树每个文件标注 `[复用] / [扩展] / [新增] / [下线]`。现有 harness 文件多数复用或扩展，核心新建文件是 eventbus.py / orchestrator.py / teaching_policy.py / mastery_graph.py / user_profile.py / workspace_state.py。

**spec 变更**：§7 目录树已加标注（见 spec 当前版本）。

---

### 3. "147 个测试"数字不准确 ✅

**发现**：spec 三处引用"147 个测试"（§1.2、§8 里程碑、§9 风险表），但实际 `tests/` 下有 32 个测试文件、155 个 `test_` 函数（以 `pytest` 实测为准）。

**决策**：不硬编码数字，改用动态表述"基线 155 个 test 函数（以 P0 时刻 `pytest` 实测全绿为准，不硬编码）"。

**spec 变更**：三处引用已修正为动态基线表述。

---

### 4. 基础设施"已就绪"程度需校准 ✅

**发现**：spec §1.1 对三个基础设施组件的"已就绪"判断部分高估：

| 组件 | spec 声称 | 实际 |
|---|---|---|
| LLM Service | 重试/回退/成本已就绪 | **属实** — invoke / invoke_json / stream / fallback_llm / _calc_cost 齐全 |
| Observability | 扩展 EventSink | **高估** — 有 trace / llm_span / metric / session_summary，但**没有事件持久化/回放能力**，EventBus 的 `replay()` 和 Event Trace Store 需要全新持久化层，不是"扩展" |
| MemoryStore | 三层 + 图谱 | **高估** — 只有 ShortTermStore (LRU+TTL) + LongTermStore (SQLite+FTS5) 两层 + MemoryManager，**没有第三层、没有图谱**。第三层是什么需要在设计文档中明确定义 |

**决策**：明确"复用"和"新建"的界线。"三层记忆"的第三层 = MasteryGraph + UserProfile 这套由 Curator 维护的结构化画像（区别于 L2 的文本检索式记忆）。

**spec 变更**：§1.1 已校准表述；§6.2 新增"三层记忆定义"小节。

---

### 5. EventBus 协作环执行模型缺失 ✅

**发现**：这是初版 spec 最大的未决工程问题。文档说"5 个 Agent 并发订阅 EventBus"，但并发执行模型完全缺失——是 asyncio 协程？线程？单线程顺序消费？这直接决定了事件顺序是否确定、回放是否可行、与同步 LangGraph 如何嵌套。

**决策**：采用单线程事件循环 + 优先级队列。协作环对 LangGraph 表现为一个同步节点，内部运行事件循环直到 `LoopExit`。Agent 不是长驻 task，而是事件 handler（短任务）。代价：单 Agent 内 LLM 调用是阻塞的，一回合内多 Agent 无法真并行省时延。但教学场景本就顺序因果（先检索→后讲解→再评估），真并行收益小、可回放收益大，权衡接受。

**spec 变更**：已新增 §3.5「协作环执行模型（单线程事件循环 + 优先级队列 + 回合屏障）」和 §0.1 否决项（明确否决真并发方案）。

---

### 6. 教学状态机"悬空状态" ✅

**发现**：初版 §4.1 的 ASCII 状态机图与 §4.2 的模式语义表格不一致——例如 Feynman 检测出 weak 时，表格说回退 Analogy，图画的却是 Feynman→Regress。Analogy 模式没有进入 Regress 的边，Regress 也没有明确的全部出口。ASCII 图天然容易遗漏转移。

**决策**：用完整状态转移表替代 ASCII 图。表中列出全部（当前模式 × 触发事件 → 目标模式）组合，确保每个状态都有兜底转移，并加"任意模式 + turn > MAX_TURNS → LoopExit"的熔断行。

**spec 变更**：§4.1 已删除 ASCII 图，§4.2 改为完整状态转移表（14 行），覆盖四个模式全部转移 + 熔断。

---

### 7. Critic 自评估"裁判循环" ✅

**发现**：§5.2 多个部件指标依赖 LLM-judge（解释完整性、画像合理性、图谱一致性），而 Critic 本身也是 LLM 做评估。若 judge 与被评 Agent 用同一模型族，就是"用 Claude 评 Claude"，评估结论不独立。此外，"人类标注黄金集"谁来标、标多少、标注规范是什么——这是整个评估体系可信度的地基，spec 初版只隐含提了 `tests/golden/` 目录，没有标注流程。

**决策**：
- judge 模型与被评 Agent 模型强制不同族（如被评用 Claude 则 judge 用 GPT）
- judge 采用盲评，不告知输出来源
- judge 本身需校准：与人类黄金标注的一致率（Cohen's κ）≥ 0.6 才采信
- 黄金集标注流程：双人独立标注 → Cohen's κ 一致性门槛（< 0.6 退回细化 rubric）→ 分歧仲裁 → 版本冻结

**spec 变更**：已新增 §5.1.1「黄金集标注流程与 judge 模型独立性（评估可信度基石）」。

---

### 8. MasteryGraph 前置依赖从哪来（cold-start）✅

**发现**：§4 Regress 模式、规则 `GraphPrereqWeakDetected` 都依赖"知识点前置关系图"（MasteryEdge type=PREREQ）。但通用学科（决策 5）意味着无法预置完整学科图谱——新用户的图谱是空的，没有 PREREQ 边 → `GraphPrereqWeakDetected` 永不触发 → Regress 模式形同虚设。必须解决"边从哪来"的 cold-start 问题。

**决策**：三个来源 + 置信度加权，图谱边用边长：
- DOC_ORDER（教材章节顺序，confidence=0.5）
- LLM_INFER（首次涉及某主题时 LLM 推断 2-3 个前置点，懒加载补边，confidence=0.3）
- INTERACTION（实际交互验证：在 A 弱导致 B 学不会 → 强化 A→B 边，confidence=0.8）

低置信边（仅 LLM 推断）触发 Regress 前需更高的"前置薄弱"阈值。被交互验证的边升权，图谱从稀疏低置信逐步长成密集高置信。

**spec 变更**：已新增 §6.1「MasteryGraph 冷启动建图（否则 Regress 模式无边可走）」。

---

### 9. 评估体系与现有 system_eval 的关系 ✅

**发现**：§5 EvalKernel 设计完整，但已有 `app/agent/system_eval/` 包含 teaching_eval / orchestrator_eval / eval_store。新评估体系是重写还是在其上演进？

**决策**：随议题 #1，`app/agent/system_eval/` 与 multi_agent 一样属于待下线老代码。新 EvalKernel 完全重写在新目录 `app/eval/`。废弃理由：老评估为 SubGraph 内嵌式，无法旁路独立运行（L2 需求），无部件级 benchmark 抽象，无 A/B 框架。

**spec 变更**：§1.2 和 §7 已标注 system_eval 为待下线。

---

### 10. 决策快照缺少"否决项" ✅

**发现**：初版 §0 列了 10 个决策，但没有记录被否决的方案及原因。后人只看决策结论，不知道曾经考虑过什么替代路线、为什么被否——容易导致重复讨论已否决方案。

**决策**：新增"否决项及理由"子表，列出被否方案（纯 LangGraph 单图、纯事件自研 Runtime、纯规则 Orchestrator、纯 LLM Conductor、4 角色无 Conductor、纯费曼/纯苏格拉底、真并发多 Agent）及否决理由。

**spec 变更**：已新增 §0.1「否决项及理由（防止重复讨论）」。

---

### 11. 里程碑缺少回退判据 ✅ 🔧

**发现**：§8 里程碑表只有"内容 + 验收"，没有"若验收失败怎么办"。P8 有灰度回退（关 feature flag），但 P1-P7 缺少回退判据——某一阶段验收不通过时，是回退到上一阶段重做、还是修改设计、还是继续？

**建议**：每个 Phase 增加"回退判据"列。例如 P1 若 EventBus 无法全序回放 → 回退重审 §3.5 执行模型；P2 若回合屏障失效 → 回退 §3.5.3。

**现状（已核实）**：spec §8 里程碑表已含"回退判据"列，P0-P9 每阶段都有（如 P1 事件无法全序回放→重审 §3.5；P4 空图谱 Regress 不触发→回退 §6.1）。#11 实际已落地。

---

### 12. 成本预算未量化 ✅ 🔧

**发现**：决策 4 是"10-100 内部用户"，但全文没有月度 token/成本预算上限。Conductor 兜底 + 5 Agent 多次 LLM 调用，单次会话成本可能显著高于单链路。没有成本红线，§5.3 SystemBench 的"资源消耗"维度缺少基准。

**建议**：在 §5.3 的"资源消耗"维度设 per-session 成本红线（如 0.10 USD/会话），并增加硬约束红线表格：任一红线超限即标记为 regression、阻断"建议升级"。同时设 conductor_trigger_rate 上限（如 30%），过高说明规则集需补充而非真长尾。

**现状（已核实）**：spec §5.3 已有"硬约束红线"段（`cost_usd_per_session` 默认 0.10 USD/会话、`p95_turn_latency` 默认 8s、`conductor_trigger_rate` 默认 30%、每场景 `max_turns` 上限），任一超限即标记 regression、阻断"建议升级"。#12 实际已落地。

---

### 13. raw 追溯材料缺失 ✅（已核实存在，原判断有误）

**发现**：§11 写 raw 材料在 `docs/superpowers/2026-05-29-multi-agent-redesign-raw.md`，但 `docs/superpowers/` 下**没有这个文件**（只有 plans/ 和 specs/ 子目录）。按项目 dev-standards.md 规范，spec 必须可追溯到 raw 材料，否则违反追溯规范。另外 raw 归档位置在项目根 `superpowers/` 而非 `docs/superpowers/`，两处描述不一致。

**建议**：确认 raw 材料实际位置，若未归档则补归档；统一 §11 的路径描述。

**现状（已核实，纠正原发现）**：raw 文件**真实存在**于 `superpowers/2026-05-29-multi-agent-redesign-raw.md`（项目根，5106 字节），spec §11 描述正确。原"发现"判断有误——第一轮 review 只查了 `docs/superpowers/`，未查项目根 `superpowers/`。#13 非问题，追溯链完整。

---

### 14. emit 白名单：职能正交的运行时强制 ✅ 🔧

**发现**：spec §2.4 把职能正交写成文字原则，§2.2 的 Agent 契约只约束了"不直接互相调用、不直接写 DB"，**没有约束"只能发自己专业领域的事件"**。到了实现阶段，Tutor 代码里 `emit(ConfusionDetected(...))` 是合法的，不会有运行时错误。

**后果**：
- **边界塌方**：一旦 Tutor 能评复述，下一步就能评"我讲得好不好"，再下一步自产 `MasteryAssessed` 架空 Critic。每个 Agent 开发者都有最强动机"我自己搞定算了，不等别人"。
- **调试地狱**：排查"为什么走错了模式"时，5 个 Agent + Conductor 都可能 emit 越权事件，没有明确的嫌疑范围。
- **评估不可信**：量化评估 Critic 的准确率时，混入其他 Agent 自产的评估噪音，Cohen's κ 不再纯粹。

**方案对比**：

| 方案 | 机制 | 否决理由 |
|---|---|---|
| 纯文档约定 | code review + spec 约束 | 零运行时保障，职能正交只是意愿 |
| 事件前缀命名空间 | Agent 只能发自己前缀的事件 | 与白名单本质等价，命名约定不如显式查表可审计 |
| **事件所有权白名单（采纳）** | 每种 EventType 绑定唯一合法 source，`EventBus.publish()` 校验越权直接抛错 | — |

**决策**：采纳事件所有权白名单。每个 Agent 声明 `emittable_types`，越权 emit 抛 `EmitViolationError`。

**事件所有权表**：

| Agent | 可 emit 的事件类型 |
|---|---|
| Tutor | `TutorAsked`, `TutorExplained`, `TutorRequestedRecap`, `TutorOfferedAnalogy` |
| Retriever | `RetrievedEvidence`, `RetrievalFailed` |
| Critic | `MasteryAssessed`, `ConfusionDetected`, `ContradictionDetected`, `LowConfidenceDetected`, `RAGQualityAssessed` |
| Curator | `ProfileUpdated`, `GraphNodeStrengthened`, `GraphPrereqWeakDetected` |
| Conductor | `ConductorDecided` |
| User | `UserMessage`, `UserUploaded` |
| Orchestrator | `LoopExit`, `PolicyTransition`, `ActionRequested`, `ConductorRequested`, `OrchestratorTick` |

**核心优势**：白名单既强制执行了正交，又免费产出"越权 emit 次数（应恒为 0）"这个协作质量的硬度量指标。

---

### 15. 复述检查归属：spec 内部矛盾 ✅ 🔧

**发现**：同一件事在 spec 两处被分给了不同 Agent——§2.1 写 Tutor 职责含「复述检查」，§1.2 又写「`restate_check` 由 Critic 内部判定」。

**为什么不能归 Tutor**：「检查复述质量」本质是评估动作（评判用户回答与正确答案的差距），不是生成动作。Agent 职能可以二分：

| 职能类型 | 做什么 | 归属 |
|---|---|---|
| 生成 (generative) | 产出教学内容：讲解、提问、类比、发起复述请求 | Tutor |
| 评估 (evaluative) | 评判产出质量：掌握度、混淆、矛盾、复述质量、RAG 质量 | Critic |

如果 Tutor 做复述检查：**自我裁判**（Tutor 教→发起复述→自己评，和 §5.1.1 防范的"LLM 自己评自己"是同一问题）、**混淆雪崩**（一处缺口被逐级扩大，最终架空 Critic）、**评估噪音**（Tutor 自评混入评估体系指标计算）。

**正确切法**：

| 动作 | 谁做 |
|---|---|
| 决定"现在该让用户复述了"（教学策略） | Tutor |
| 发起复述请求 `TutorRequestedRecap` | Tutor |
| 听用户复述、评估掌握度/混淆/矛盾 | **Critic** |
| 根据评估结果决定下一步 | Orchestrator（基于 Critic 观察裁决） |

Critic 不需要区分"这次回答是提问回答还是复述"——它只做一件事：对着用户文字输出掌握度 + 是否混淆 + 是否矛盾。

**决策**：Tutor 职责中删掉"复述检查"，改为"发起复述请求"；`restate_check` 确认为 Critic 内部行为（对包含复述内容的 UserMessage 做常规掌握度评估）。

---

### 16. Conductor 越权风险：规则未覆盖时正交如何不塌 ✅ 🔧

**发现**：当前 spec 设计：规则未覆盖 → Orchestrator 召唤 Conductor → 喂给它"最近 N 条事件 + WorkspaceState + MasteryGraph 摘要"→ 让它决策下一步。隐患：Conductor 的输入包含 `UserMessage`（用户原话），LLM 看到"CNN 是不是就是很多层全连接？"不需要 Critic 就能自己判断混淆，然后直接决策。**Critic 还在，但被绕过了。**

**后果**：
- **正交在长尾路径失效**：高频路径走规则（正交完好），低频路径走 Conductor（一人包揽评估+决策），正交性取决于规则覆盖率
- **Conductor 变成后台全能 Agent**：不主动教学，但每次被召唤就自己判断状态 + 自己决定动作
- **评估死区**：Conductor 隐含的语义判断没走 EventBus，不进 Trace Store，评估体系永远看不到

**方案**：Conductor 只能在已有观察事件之上做路由决策，不能自产语义/结构观察。降格为纯路由器：

```
Conductor 收到：
  - 观察事件（Critic/Curator 产出）
  - WorkspaceState 快照
  - MasteryGraph 摘要
  - UserMessage 仅作上下文参考，不可据此自判语义

情况 1：观察足够 → 基于已有观察选择动作（无越权）
情况 2：观察不足 → 不自己判断，emit ActionRequested(target=critic, reason="需要语义评估")
                → 让专业的人先看，观察补齐后下轮可能命中规则
```

**代价**：Conductor 可能需要多轮 micro-turn 才能做出最终决策——这是正交的代价，分工带来多一轮通信，换来的是一致性和可评估性。

**配套变更**：`ActionRequested` 事件需扩展 `target` 字段。可选：新增 `ObservationRequested` 事件类型。

**决策**：采纳 Conductor 限制。

---

### 17. Curator 触发时机：开局前置薄弱测不到 ✅ 🔧（方案 A + 渐进实现）

**发现**：§2.4 写"Curator 订阅 Critic 的 `MasteryAssessed` → 触发图谱检查"。但考虑场景：用户开局就说"教我 transformer 注意力机制"——此时还没有任何用户回答，Critic 无 `MasteryAssessed` 可发，于是 Curator 不检查图谱，`GraphPrereqWeakDetected` 不会在开局触发，Regress 模式形同虚设。而 §5.3 偏偏有场景"直接学注意力机制但缺向量乘法 → expected: regress_to_prereq"，当前设计下**必然失败**。

**目的**：表面是"Curator 少订阅一类事件"，本质是 **Regress 模式对最高频用户群体失效**。最常见的真实场景就是新手上来直接学高阶主题（大概率缺前置），这正是 Regress 最该在**开局第一秒**发挥价值的时刻。当前设计却要求用户先答一轮高阶题、答错了系统才反应过来"你前置不行"——本末倒置。

**目标**：
1. 覆盖双时机：前置检查既能"开局/切主题"触发，也能"回合中"触发
2. 职能不越界：Curator 仍只判结构层（图谱 + 历史 mastery），不碰文本语义
3. 不制造新体验坑：不能因为用历史数据就把"已补过课的老用户"强制按回去复习
4. 架构一致：开局检查也在事件流里，可回放、可被评估（呼应 #16 消除评估死区的原则）

**关键洞察 — 两个时机本质不同**：

| 时机 | 触发点 | 输入来源 | 置信度 |
|---|---|---|---|
| 回合中检查 | 用户答完一轮，Critic 评完 | 本轮实际表现 + 图谱 | 高（实测，可直接 Regress） |
| 开局检查 | 用户刚选定主题，还没答题 | 用户历史画像 + 图谱 | 低（历史推断，可能过时，需先探测确认） |

开局检查的数据（用户对前置点的历史 mastery）已躺在 MasteryGraph 里，Curator 完全有能力在主题确定瞬间就查，不用等 Critic。缺的只是触发信号——该信号来自协作环外的 `route` 节点（它定主题、写 `WorkspaceState.current_topic`），目前没以事件形式进入协作环。

**新隐患 — 过时画像**：用户三个月前"矩阵乘法"weak，但这期间可能自己补过了。开局就因历史数据强制 Regress 回矩阵乘法 = "按着会的人复习"，体验糟，且"内部多用户长期使用"形态会让此问题随画像积累而放大。

**三方案优缺点**：

| 方案 | 机制 | 优点 | 缺点 |
|---|---|---|---|
| **A（采纳）** | 新增 `TopicEntered` 事件（source=orchestrator，首次进入+切主题都发），Curator 订阅它做开局检查，区分 `basis=historical`（探测确认后再 Regress）/`observed`（直接 Regress） | 唯一能跑通 §5.3 且不误伤老用户；探测确认本身是苏格拉底式动作，契合融合教学法；职能正交完整 | 工程量最大：+1 事件、+1 字段（basis）、+1 动作（TUTOR_PROBE_PREREQ）、+2 规则；探测多 1 回合 |
| B | 同样新增 `TopicEntered`，但开局/回合中不区分，开局也直接 Regress | 工程量小；也能跑通 §5.3 | 过时画像陷阱；"按着会的人复习"；与 §6.1 置信度加权精神不一致；风险随画像积累上升 |
| C | 不走事件，`collab_loop` 启动时硬调 `curator.check()` | 不增事件类型 | 破坏纯事件驱动、不可回放；制造评估死区（与 #16 同类病）；架构债 |

**决策：采纳方案 A，并接受"渐进实现"排期**

- **先排除 C**：为省一个事件类型却制造评估死区，与 #16 刚堵住的洞同类，架构一致性 > 省一个枚举。
- **A vs B 核心分歧**：开局发现前置弱，要不要**直接**回退。选 A（不直接），因为过时画像问题真实存在，且"内部用户长期使用"会放大它。
- **渐进路径**（A 与 B 不必二选一）：spec **设计按 A 写全**（`basis` 字段、Curator 双订阅、规则双分支都进文档），但**实现排期**上——系统冷启动初期画像为空，`historical` 检查本就发不出信号，此时 A≈B；故 **P4 先落 `observed` 分支**跑通场景，`historical` 探测分支留到画像积累后再启用。设计完整稳健，实现初期约等于 B 的成本，不堵死稳健路径。

**spec 改动点（已落地 🔧）**：
- §3.2 事件清单新增 `TopicEntered [source: orchestrator]`，并入白名单
- §6 `GraphPrereqWeakDetected` payload 增加 `basis: historical | observed` 字段
- §2.1 Curator 订阅从 `[MasteryAssessed]` 扩为 `[MasteryAssessed, TopicEntered]`
- §3.4 规则增加：`basis=observed → REGRESS_TO_PREREQ`（priority 100）；`basis=historical → TUTOR_PROBE_PREREQ`（先探测）
- §4.2 Regress 入口转移补 historical/observed 分支说明
- 新增动作 `ActionKind: TUTOR_PROBE_PREREQ`
- 标注 historical 分支为"渐进启用"

---

### 18. 证据质量双归属：RAG 质量到底谁判 ✅ 🔧（方案 A + 成本优化）

**发现**：Retriever 输出带 `gate_status` 的证据（§3.2），Critic 又有 `RAGQualityAssessed`（§3.2），"证据够不够好"在两处都判，边界不清。深挖现有 `app/agent/specs/prompts/evidence_gate.md` 发现根因——它把**两种本质不同的判断焊死在一个门里**：
- 机械门槛：`rag_found`？返回 0 条？score 低？超时？——布尔/数值，确定性，无需语义
- 语义充分性："上下文充分"——证据够不够支撑回答，需理解，是评估（原文"无论 LLM 多自信"暴露 gate 内部在调 LLM）

**为什么语义充分性不能归 Retriever**：与 #15（复述检查）、#16（Conductor）同源——生成者不评判自己的产出。三个危害：① 质量信号不独立 → `RAGQualityAssessed.score<threshold→RETRIEVER_EXPAND_QUERY` 规则失效（Retriever 不会说自己差）；② 评估不可量化（自评污染指标）；③ 违约不可观测（违背 #14 白名单）。

**三方案**：

| 方案 | 机制 | 评价 |
|---|---|---|
| **A（采纳）** | gate 降级为机械状态 `retrieval_status: ok\|empty\|timeout\|low_score`；语义质量全归 Critic `RAGQualityAssessed`（唯一信号） | 从根上拆开焊死；信号独立可信；evidence_gate 语义部分自然迁移到 Critic |
| B | 保留 `gate_status` 名，文档限定为"机械门槛" | 只贴约定，`gate` 一词留歧义，后人易再塞回语义 |
| C | Retriever 自带轻量 gate 粗筛 + Critic 精判 | Retriever 自评=自我裁判，违背正交，归因困难 |

**成本优化（用户追加）**：只有当证据**即将用于教学动作**时才触发 Critic 的 RAG 评估（检索意图携带 `purpose=teaching|exploration`，纯探索检索跳过），把成本压在必要路径。

**连带澄清（§5.2 三件套归属）**：§5.2 Retriever 的"RAG 三件套"是 **L2 离线 benchmark**（EvalKernel 用黄金集+独立 judge 考核 Retriever 部件，非自评）；在线 `RAGQualityAssessed` 由 Critic 评当前证据够不够。两者分层，不矛盾。

**决策**：1→语义质量归 Critic；2→`gate_status` 换机械语义 `retrieval_status`（方案 A）；3→§5.2 加分层澄清；4→加成本优化（purpose 门）。流程图见 spec §3.6。

**spec 改动点（已落地 🔧）**：
- §2.1 Retriever 行：明确只做机械层（检索+原始 score+retrieval_status），不自评语义
- §2.1 Critic 行：RAG 语义质量评估仅当证据将用于教学动作时触发
- §3.2 `RetrievedEvidence`：`gate_status` → `retrieval_status`（纯机械状态）
- §3.2 `RAGQualityAssessed`：唯一语义质量信号，purpose=teaching 才触发
- §3.4 规则：注明质量信号来自 Critic、独立于 Retriever
- §3.6（新增）：证据评判流程图（机械门槛 vs 语义质量）
- §5.2：加 RAG 三件套分层归属澄清

---

### 19. 协作评估层缺失：测不出协作质量 ✅ 🔧（六维全采纳）

**发现**：这是两轮 review 最重要的发现，直接回答"当前评估体系能否衡量协作质量"——**不能**。

现有评估是"部件级 + 系统级"的夹心结构，唯独缺中间的"协作级"：

| 层 | 测什么 | 覆盖 |
|---|---|---|
| ComponentBench (§5.2) | 每个 Agent **单独**考试考几分（孤立能力） | ✅ 有 |
| **协作级（缺失）** | **5 个 Agent 之间协作得好不好**（过程质量） | ❌ 无 |
| SystemBench (§5.3) | 整个系统**端到端**教学结果 | ✅ 有 |

协作质量是涌现属性——既 ≠ 各部件质量之和，也 ≠ 最终结果反推。**反证很硬**：一个系统完全可能每个部件单测全优、最终掌握度也达标，但协作过程是事件风暴 / 决策来回震荡 / 某个 Agent 几乎不工作（角色冗余）——现有指标会给它满分。

更讽刺的是，数据结构已经为协作评估备好了料（§3.1 `parent_id` 因果链注明"用于回放和评估"），但 §5 没有任何一个指标真正消费因果链。

**候选协作指标族**：

| 协作维度 | 候选指标 | 对应诉求 |
|---|---|---|
| 职能正交违约 | 跨域 emit 次数（应恒为 0）、越权决策次数 | 「不能跨职能范围操作」的量化验证 |
| 协作效率 | 每教学回合事件数、无效事件率（emit 了但没影响任何决策）、Agent 利用率（是否有角色几乎不干活） | 「协调」 |
| 决策稳定性 | Orchestrator 反悔率、模式切换震荡频率（§4.2 自洽 ≠ 运行时不震荡） | 「协调且专业」 |
| 冲突消解 | Critic/Curator 观察冲突率、优先级裁决是否真的消解（§2.4 机制运行时验证） | 正交是否落地 |
| 因果链质量 | 因果链完整性（每个动作可追溯到触发观察）、孤儿事件率（凭空行动）、因果树深度 | `parent_id` 真正服务评估 |

**决策**：采纳新增 §5.4 CollaborationBench，六维指标全要（违约/效率/稳定/冲突/因果链/轨迹偏离）。核心洞察：本层与职能正交**一体两面**——#14 白名单→违约率、§2.4 屏障→冲突消解率、§3.1 parent_id→因果链质量，**职能正交的强制机制同时就是协作质量的度量基础设施**。直接回答"量化体系能否衡量协作质量"：原体系**不能**（部件+系统的夹心缺中间层），补上 CollaborationBench 后**能**。

**spec 改动点（已落地 🔧）**：§5.1 整体视图图加协作级；新增 §5.4 CollaborationBench（六维指标表 + 数据源 parent_id + 输出）；§8 P6 并入协作级验收（违约率>0 即 regression）。

---

### 20. 消融实验缺失 ✅ 🔧（采纳组件消融）

**发现**：§5.4 ABController 只支持"换模型/换配置"的 A/B 实验，**不支持"关掉某个 Agent / 关掉回合屏障"的消融实验**。

消融是科学证明"这套 5-Agent 协作架构本身值多少增益"的唯一方法——这恰恰是做整套量化体系的元目标（客观评估 + 选型参考）。没有消融，你永远无法回答：
- "Curator 到底带来了多少价值？要不要保留？"
- "回合屏障是让协作更稳定还是增加了延迟？"
- "Conductor 对长尾场景的实际贡献率是多少？"

**决策**：采纳 ABController 扩展"组件消融"（类型二），与参数 A/B 并列。这是「选型参考」诉求的**核心**——只有消融能回答"这套 5-Agent 架构本身值多少增益"（Curator 砍不砍、回合屏障值不值、Conductor 长尾贡献率），参数 A/B 永远答不了。可消融对象：任一 Agent / 回合屏障 / Conductor / 某条规则。落地节奏：并入 P7（与 A/B 同阶段）。

**spec 改动点（已落地 🔧）**：§5.5 ABController 增加"类型二：组件消融"YAML 示例（disable_agent + stub）+ 说明；§8 P7 加"Curator 价值消融"验收。

---

### 21. 黄金协作轨迹缺失 ✅ 🔧（采纳过程断言）

**发现**：§5.1.1 的黄金集只标"单点标签"（掌握度/是否混淆），§5.3 场景的 `expected` 只有**结果断言**（mastery_reached / max_turns / conductor_triggered）。没有**过程/轨迹断言**——专家认为"理想情况下事件流该长什么样、Orchestrator 决策序列该如何"。

没有轨迹断言，你就无法评"实际协作轨迹 vs 理想轨迹"的偏离度。这是评估协作质量的另一维度——不仅看最终结果对不对，也看过程是否合理。

**决策**：采纳场景加过程断言（黄金轨迹）。结果断言（mastery_reached/max_turns）只判结果对不对，过程断言判过程合不合理——评"实际协作轨迹 vs 专家理想轨迹"偏离度。字段：`expected_mode_path` / `must_contain_events` / `must_not_contain_events`。偏离度接入 §5.4 CollaborationBench"轨迹偏离"维度。落地节奏：成本低，并入 P6。

**spec 改动点（已落地 🔧）**：§5.3 SystemBench 首个场景 expected 加过程断言示例（mode_path + must_contain/not_contain）+ 过程断言说明段；§8 P6 并入黄金轨迹。

---

## 关联关系

以上 21 个问题之间存在以下联动：

```
事实性问题（#1-#4）→ 已修复，spec 已更新

设计缺陷（#5-#9）→ 已修复，spec 已更新
    └── #5 协作环执行模型 ← 是 #19 协作评估的运行时前提
    └── #8 冷启动建图 ← 是 #17 Curator 触发时机的上游

增强建议（#10-#13）→ 全部已落地/已核实
    └── #10 否决项、#11 回退判据(§8)、#12 成本红线(§5.3) ← spec 已落地
    └── #13 raw 材料 ← 已核实存在于项目根 superpowers/（原判断有误）

职能正交三件套（#14-#16）→ 全部已决策
    └── #14 emit 白名单是第一道防线
    └── #15 复述检查归 Critic 消除了 spec 内部矛盾
    └── #16 Conductor 限制堵住了长尾越权漏洞
    └── 三者共同为 #19 违约率/冲突率指标提供数据基础

协作评估四件套（#17-#21）
    └── #17 Curator 触发时机 ✅🔧 已落地（方案 A）；#18 证据边界 ✅🔧 已落地（方案 A + purpose 门）← 职能正交剩余边界
    └── #19 协作评估层 ✅🔧 已落地（§5.4 CollaborationBench 六维）← 核心缺口
    └── #20 消融实验 ✅🔧（§5.5 类型二）+ #21 黄金轨迹 ✅🔧（§5.3 过程断言）← #19 的评估方法支撑，并入 P6/P7
```