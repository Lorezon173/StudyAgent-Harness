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

**架构方案**：🅲 混合型 —— LangGraph 骨架 + 外置事件总线。主图负责稳定的「输入→路由→协作环→收尾」流水线；协作环内部由独立 EventBus 驱动 5 个 Agent 并发协作。

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
│           协作环 = EventBus + 5 Agents 并发订阅           │
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
│  - MemoryStore（SQLite + FTS5，已就绪，扩展图谱表）        │
│  - Observability（Langfuse/Console，已就绪，扩展 EventSink）│
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
| 文本记忆 | 三层记忆 + 掌握点知识图谱 |
| — | 新增 `eventbus / orchestrator / teaching_policy / mastery_graph / user_profile / eval/` |

**迁移原则**：新代码写在全新目录（`orchestration/ agents/ eval/`），老代码 `app/agent/` 保留不动作为参考，待新栈灰度稳定后再下线。现有 147 个测试在整个重构期间必须持续通过。

---

## 2. 五个 Agent 的职责契约

### 2.1 角色划分

| Agent | 职责 |
|---|---|
| **Tutor** | 教学主体；执行讲解、提问、追问、复述检查、类比生成；订阅 Curator 的画像和 Retriever 的证据 |
| **Retriever** | 知识检索；接 RAG + OCR + 代码索引；输出带置信度的证据片段；订阅 Tutor 的查询事件 |
| **Critic** | L1 在线评估；评估每轮交互的「掌握度 / 混淆 / 矛盾 / 重复 / RAG 质量」；订阅所有事件，输出评分事件供 Orchestrator 决策 |
| **Curator** | 维护用户画像与掌握点知识图谱；订阅 Critic 评分，更新 MasteryGraph；为 Tutor 提供画像上下文 |
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

---

## 4. 融合式教学循环（苏格拉底 ⋂ 费曼）

### 4.1 模式状态机

```
        ┌─────────┐   ConfusionDetected  ┌──────────┐
        │ Socratic│  ─────────────────►  │ Analogy  │
   ┌──► │  模式   │                      │  模式    │
   │    └────┬────┘  ◄─────────────────  └─────┬────┘
   │         │  MasteryAssessed=partial         │
   │         ▼                                  │
   │    ┌─────────┐                             │
   │    │ Feynman │  GraphPrereqWeakDetected    │
   │    │ 模式    │  ────────►  ┌──────────┐    │
   │    └────┬────┘             │ Regress  │ ◄──┘
   │         │                  │  模式    │
   └─────────┘   MasteryUp      └──────────┘
   MasteryAssessed=mastered
```

### 4.2 模式语义

| 模式 | Tutor 行为 | 用户角色 | 退出条件 |
|---|---|---|---|
| **Socratic** | 抛出引导性问题，不直接给答案 | 思考与回答 | mastery=mastered 出环；mastery=partial 进 Feynman |
| **Feynman** | 沉默倾听，要求用户复述/教授 | **主讲**，要把知识"教给 AI" | Critic 检测出 mastered 退回 Socratic 收尾；检测出 weak 回退 Analogy |
| **Analogy** | 给出类比/比喻，要求用户验证类比 | 验证并扩展类比 | 类比被认可后回 Socratic |
| **Regress** | 退回前置点，重新开始小循环 | 学习前置知识 | 前置点 mastery=mastered 后回到原主题 |

模式切换由 Orchestrator 发出 `PolicyTransition` 事件，TeachingPolicy 内部记录历史用于评估。

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
10 ConfusionDetected(retrieve vs augment)
11 PolicyTransition(Feynman → Analogy)
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

---

## 7. 目录结构

```
app/
├── api/                       # 不变（已就绪）
│
├── orchestration/             # 新（替换原 agent/，老 agent/ 保留作参考）
│   ├── graph.py               # 4 节点骨架：ingest/route/collab_loop/wrap_up
│   ├── collab_loop.py         # 协作环：启动 EventBus + 5 Agent
│   └── routers.py             # 主图条件边
│
├── agents/                    # 新（5 个 Agent 实现）
│   ├── base.py                # AgentBase 抽象 + Subscription API
│   ├── tutor.py
│   ├── retriever.py
│   ├── critic.py
│   ├── curator.py
│   └── conductor.py
│
├── harness/
│   ├── enums.py               # 扩展：TeachingMode, EventType, ActionKind
│   ├── workspace_state.py     # 新（替换原 state/）
│   ├── eventbus.py            # 新（核心）
│   ├── orchestrator.py        # 新（含规则引擎 + Conductor 召唤）
│   ├── teaching_policy.py     # 新（模式状态机）
│   ├── mastery_graph.py       # 新
│   ├── user_profile.py        # 新
│   ├── observability.py       # 复用（扩展 EventSink）
│   ├── memory.py              # 复用（扩展图谱存取）
│   └── ... 其他保留
│
├── infrastructure/
│   ├── llm.py                 # 复用
│   ├── rag/                   # 复用（扩展 OCR + 代码切片器）
│   │   ├── coordinator.py
│   │   ├── extractors/        # PDF/MD/TXT/DOCX
│   │   ├── ocr.py             # 新
│   │   └── code_index.py      # 新（git clone + AST 切片）
│   └── storage/
│       ├── ... 现有
│       ├── mastery_graph_store.py   # 新
│       └── event_store.py           # 新
│
└── eval/                      # 新（L2 评估子系统）
    ├── kernel.py              # EvalKernel 入口
    ├── component_bench.py     # 部件级
    ├── system_bench.py        # 系统级
    ├── ab_controller.py       # A/B 框架
    ├── selection_reporter.py  # 选型报告
    ├── scenarios/             # 预定义场景 YAML
    └── fixtures/              # 各部件的测试用例

tests/
├── unit/                      # 既有
├── eval/                      # 新（评估子系统自己的 TDD）
└── golden/                    # 新（人类标注的黄金数据）

superpowers/                   # 规划归档（按 dev-standards.md 要求）
└── 2026-05-29-multi-agent-redesign-raw.md   # 本次原始计划
```

---

## 8. 里程碑切片

| Phase | 内容 | 验收 |
|---|---|---|
| **P0** | 仓库 scaffold：新目录 + 不动老代码 | 老代码 147 测试仍通过 |
| **P1** | 核心契约：WorkspaceState + EventBus + AgentBase | EventBus 单元测试 + AgentBase 注册测试 |
| **P2** | 5 个 Agent 骨架 + Orchestrator 规则引擎 + 4 教学模式 | 协作环可跑通空脚本 |
| **P3** | 完整教学循环（Critic 评分 → 模式切换 → wrap_up） | 走通 1 个标准场景 |
| **P4** | RAG 扩展（OCR + 代码索引）+ MasteryGraph 集成 | 场景"前置薄弱触发回退"通过 |
| **P5** | EvalKernel 部件级 ComponentBench + 5 Agent 各跑 1 个 fixture | 输出 JSON 报告 |
| **P6** | EvalKernel 系统级 SystemBench + 4 个预定义场景 | 输出 Markdown 报告 |
| **P7** | ABController + SelectionReporter | 跑通 "Tutor 模型升级" 对照实验 |
| **P8** | 老代码灰度切换：API 层加 feature flag，把 /chat 切到新栈 | 灰度上线 |
| **P9** | 删除 `app/agent/`（仅在确认 P8 稳定后） | 老代码下线 |

---

## 9. 风险与权衡

| 风险 | 缓解 |
|---|---|
| 两套范式（LangGraph 骨架 + 事件总线）边界混淆 | 协作环作为单一超级节点，边界文档化；进/出环点明确 |
| EventBus 并发死锁 | default 规则保证总有动作；Orchestrator 设最大回合上限强制 LoopExit |
| Conductor LLM 决策延迟拖慢会话 | 规则引擎覆盖高频路径，Conductor 仅长尾触发；监控触发率 |
| 老代码（147 测试）在重构期间回归 | 新代码全在新目录，老代码保留至 P8 灰度稳定 |
| 评估体系工程量大 | 按 P5→P7 分阶段交付，先部件级后系统级后 A/B |
| MasteryGraph 图谱维护复杂 | 节点强度采用增量更新；图谱一致性纳入 ComponentBench |

---

## 10. 规范同步要求（遵循 agent-root.md）

按项目规范，所有 `.md` 规范文件修改时必须同步修改对应的 `.prompt.md`。本次重设计引入新的 Agent 角色与教学模式，需在实现阶段同步创建：

- `specs/agents/tutor.md` ↔ `.prompt.md`
- `specs/agents/retriever.md` ↔ `.prompt.md`
- `specs/agents/critic.md` ↔ `.prompt.md`
- `specs/agents/curator.md` ↔ `.prompt.md`
- `specs/agents/conductor.md` ↔ `.prompt.md`
- `specs/intent_map.yaml` → 改为 `event_map.yaml`（事件→动作映射）

具体规范内容在 writing-plans 阶段细化。
