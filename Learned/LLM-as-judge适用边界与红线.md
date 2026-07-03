# LLM-as-judge 适用边界与红线

> 最后更新：2026-06-28

本文档约束 StudyAgent 评估体系中 LLM-as-judge 的使用范围，是 Phase 3 及任何评估扩展的基线约束。
核心立场：**评估体系不需要新增 LLM-judge 体系——它已是一个边界克制的混合体；需要的是守住边界，而非扩张。**

## 目录

- [Q1: 评估体系里 LLM 当前用在哪些层？](#q1-评估体系里-llm-当前用在哪些层)
- [Q2: 什么条件下才该用 LLM-as-judge？](#q2-什么条件下才该用-llm-as-judge)
- [Q3: LLM-judge 的适用范围是什么？](#q3-llm-judge-的适用范围是什么)
- [Q4: LLM-judge 应处于什么层次？](#q4-llm-judge-应处于什么层次)
- [Q5: 绝对禁止的边界（六条红线）是什么？](#q5-绝对禁止的边界六条红线是什么)

---

## Q1: 评估体系里 LLM 当前用在哪些层？

**日期**：2026-06-28

**问题**：
讨论"是否给评估体系加 LLM-as-judge"前，必须先核实现状——LLM 已经在哪些评估层用了？

**回答**：

经代码核查（`app/eval/` + `app/agents/`），评估体系**已经是混合体**：

| 评估层 | 文件 | 评什么 | 是否用 LLM |
|---|---|---|---|
| ComponentBench-Retriever | `retriever.py:evaluate` | 检索质量 | ✅ 已用（RAGAS，Phase 1） |
| ComponentBench-Tutor | `tutor.py:evaluate` | 教学质量 | ⏳ 计划用（DeepEval，Phase 3） |
| ComponentBench-Critic | `critic.py:101` | 语义判断 | ✅ **被评对象自己是 LLM**（非 judge） |
| SystemBench | `system_bench.py` | 场景结果/过程断言 | ❌ 纯规则（事件匹配/路径比对） |
| CollaborationBench | `collaboration_bench.py` | 六维协作指标 | ❌ 纯算法（因果树/计数/比率） |
| ABController | `ab_controller.py` | 消融增益 | ❌ 纯数值（delta + 阈值） |

**关键结论**：真问题不是"要不要引入 LLM-judge"，而是"已有的边界（开放语义维度用 LLM，结构/数值维度用确定性算法）该不该往外扩"。这个分野不是偶然，是有架构理由的（见 Q2）。

---

## Q2: 什么条件下才该用 LLM-as-judge？

**日期**：2026-06-28

**问题**：
什么维度值得用 LLM-judge，什么维度绝不该用？

**回答**：

LLM-judge 只在满足**全部**三个条件时才值得用：

| 条件 | 含义 | 满足的维度 |
|---|---|---|
| ① 评估对象是**开放文本语义** | 没有可枚举的正确答案，需要"理解" | 检索内容是否支撑答案、教学是否有引导性 |
| ② 确定性指标**无法替代** | 字符重叠/正则/计数会失真 | 混合评估设计 §3.2 已证字符 Jaccard 与语义无关 |
| ③ 评估结果**容忍非确定性** | 同输入可能不同分，需 κ 校验兜底 | 旁路评估容忍，且有 §5.1.1 κ≥0.6 门槛 |

**反过来，不该用 LLM-judge 的维度，恰恰是现在没用的那些**：

- **CollaborationBench 六维**：`orphan_rate`、`repent_rate`、`events_per_turn`——事件图的结构性事实，有精确算法。用 LLM 评 = 用昂贵的非确定性工具做确定性算术，纯退化。
- **SystemBench 断言**：`must_contain_events`、`mode_path` 偏离——可枚举的轨迹匹配，正则/集合运算就是 ground truth。LLM 在此只会引入幻觉。
- **ABController delta**：数值差 + 阈值，确定性最强的地方。

**边界结论**：LLM-judge 的天花板就是"开放语义"维度。**结构性、可枚举、数值型的评估维度，绝对禁止引入 LLM。**

---

## Q3: LLM-judge 的适用范围是什么？

**日期**：2026-06-28

**问题**：
具体哪些指标算"适用范围内"？

**回答**：

适用范围 = **L2 旁路评估中，被评对象产出"自然语言/语义内容"的那部分指标**。具体三类：

1. **检索质量**（Retriever）：内容能否支撑答案、是否切题、排序好坏 → RAGAS，已落地
2. **教学质量**（Tutor）：引导性、清晰度、概念覆盖 → DeepEval G-Eval，Phase 3
3. **（潜在）Tutor 真实生成的忠实度**：混合评估设计 §3.2 提到的——SystemBench 串联 Retriever→Tutor 真实生成后，评 Tutor 是否忠于检索。这是**唯一一处可考虑新增** LLM-judge 的适用点，前提是 SystemBench 先支持真实生成。

**范围外明确排除**：协作六维、系统轨迹断言、消融 delta。

---

## Q4: LLM-judge 应处于什么层次？

**日期**：2026-06-28

**问题**：
LLM-judge 在架构里应锁死在哪一层？

**回答**：

混合评估设计 §0 决策 4 已写死：**RAGAS/DeepEval 只在 L2 旁路出现，严禁进入在线 `handle()` 路径。** 层次的精确定位：

```
L1 在线 handle()        ← LLM 可在此，但那是【被评对象】的 LLM（Critic 评语义）
   │                       不是【judge】的 LLM。两者绝不能混。
   │ 事件沉淀
   ▼
EventStore
   │ replay（离线）
   ▼
L2 旁路 EvalKernel       ← LLM-as-judge 只活在这一层
   ├─ ComponentBench     ← judge 在此（检索/教学语义）✅
   ├─ SystemBench        ← 纯规则，judge 禁入 ❌
   ├─ CollaborationBench ← 纯算法，judge 禁入 ❌
   └─ ABController       ← 纯数值，judge 禁入 ❌
```

**最易混淆、必须厘清的核心区分**：

| | Critic 的 LLM（L1） | Judge 的 LLM（L2） |
|---|---|---|
| 身份 | **被评对象** | **评估者** |
| 位置 | 在线 `handle()` | 离线旁路 `evaluate()` |
| 能否同族 | 无所谓 | **必须不同族**（§5.1.1） |
| 作用 | 产生教学决策 | 给被评对象的产出打分 |

**绝对不能做**：让 judge 的 LLM 进入 L1，或让 Critic（被评对象）给自己打 judge 分——那是"运动员兼裁判"，评估失去独立性。`judge.py:54` 的不同族校验正是守这条线。

---

## Q5: 绝对禁止的边界（六条红线）是什么？

**日期**：2026-06-28

**问题**：
任何评估扩展都不可逾越的红线有哪些？

**回答**：

按违反严重性排序：

🔴 **红线 1：judge 绝不进在线路径**
LLM-judge 只在 `app/eval/` 和 `Agent.evaluate()` 出现。一旦进 `handle()`，在线延迟和成本失控，且评估与决策耦合。
验证：`grep -r "import ragas\|import deepeval" app/agents/` 只允许命中 `evaluate` 方法体内。

🔴 **红线 2：judge 与被评对象绝不同族**
否则同族模型的偏好会自我强化（GPT 评 GPT 倾向打高分）。已由 `judge.py:54` 强制（Tutor=Claude → judge=OpenAI 满足）。**新增任何 judge 维度时，这条校验必须复用，不能绕过。**

🔴 **红线 3：确定性可算的维度，绝不用 LLM**
协作六维、系统轨迹断言、消融 delta——有精确算法的地方引入 LLM = 用非确定性污染确定性，且白烧钱。这是范围的硬上界。

🔴 **红线 4：降级分数绝不伪装成真分**
judge 不可用时（同族/无 key/库未装/异常），必须显式标 `degraded: true`，**不能**用字符 Jaccard 之类启发式假装语义分。混合评估设计 §0 否决项已立此规，任何新 judge 维度沿用。

🔴 **红线 5：κ 未达标的 judge 分数绝不采信**
§5.1.1 要求 judge 自身 κ≥0.6 才采信。**没有 κ 校验的 LLM 打分，不配叫 judge，只是噪声。** 任何新 judge 维度上线前必须有 κ 抽查。

🔴 **红线 6：judge 绝不参与它自己评估链路的训练/选型闭环**
若未来用 judge 分数自动选 Tutor prompt，judge 本身绝不能也由同一优化循环调整——否则评估标准会被"优化"成容易得高分的样子（Goodhart 定律）。评估标准必须相对被评对象**冻结**。

---

## 附：本次讨论的结论速查

| 问题 | 结论 |
|---|---|
| 是否需要新增 LLM-judge 体系？ | **不需要**。已有边界克制的混合体，需守边界而非扩张。 |
| 适用范围？ | 仅 L2 旁路中被评对象产出"开放语义"的维度（检索/教学质量），最多加 SystemBench 串联后的"生成忠实度"。 |
| 层次？ | 严格锁死 L2 离线旁路，与 L1 在线的"被评对象 LLM"物理隔离，身份不可混。 |
| 绝对禁止？ | 进在线 / 同族评 / 替代确定性算法 / 降级伪装真分 / 无 κ 采信 / judge 进自身优化闭环——六条红线。 |
