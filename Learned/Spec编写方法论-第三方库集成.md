# Spec 编写方法论：第三方库集成场景

> 最后更新：2026-06-22

## 目录

- [Q1: 为什么 "32 tests passed" 会掩盖 RAGAS happy-path 的三处 API bug？](#q1-为什么-32-tests-passed-会掩盖-ragas-happy-path-的三处-api-bug)
- [Q2: 写第三方库集成 spec 时，怎么避免 API 误用？](#q2-写第三方库集成-spec-时怎么避免-api-误用)
- [Q3: 如何判断 spec 里某个设计点是"经过验证的事实"还是"自洽的猜测"？](#q3-如何判断-spec-里某个设计点是经过验证的事实还是自洽的猜测)

---

## Q1: 为什么 "32 tests passed" 会掩盖 RAGAS happy-path 的三处 API bug？

**日期**：2026-06-22

**问题**：
Phase 1 完成时说「32 tests passed，RAGAS 落地验收通过」。但 review 发现有三处 API 误用：① metric import 得到的是子模块而非实例；② Dataset 列名是 0.1.x 旧格式；③ 用 `.columns`/`.iloc[0]` 提取 EvaluationResult（该对象无此接口）。这三个 bug 在真实调用时会崩溃，但 32 个测试全部通过，为什么没有抓住？

**回答**：

**根因：测试覆盖率在「路径」层面，而非「功能」层面。**

RAGAS 的真实评估路径（`ragas_eval` 被实际调用）从未执行，因为：
1. 测试环境无 `OPENAI_API_KEY`
2. `build_judge()` 检测到无 key → 返回 None
3. 代码立即走降级分支（`if judge_handle is None: return {..., "degraded": True}`）
4. `ragas_eval(...)` 那行从未跑到

结果是「32 个测试全部测的是降级路径」。三处 API bug 都藏在那个从未执行的分支里，任何测试都不会触及。

**三处 bug 的具体成因**：

| Bug | 发现方式 | 为什么 tests 没抓到 |
|---|---|---|
| `from ragas.metrics.collections import faithfulness` 是子模块 | 实测 `type()` | 在降级前已 return，该 import 虽执行成功（模块存在），但 `metrics=[module]` 从未传给 evaluate |
| Dataset 列名用 `question`/`answer`/`contexts` | 查 metric._required_columns | 同上，Dataset 构造了但 evaluate 未运行 |
| `result.columns`/`result["x"].iloc[0]` 接口不存在 | inspect EvaluationResult | evaluate 从未返回 EvaluationResult，提取代码从未执行 |

**信号**：验收时只说「X tests passed」但没说「happy-path 至少跑了 1 次」——这本身就是一个 🔴 信号，意味着核心路径未验证。

**教训**：
- **测试通过 ≠ 功能验证**，只有当测试覆盖了关键路径时才有意义
- 外部 key 依赖会静默跳过核心路径；需要「mock 外部 key 但保留内部逻辑」的测试专门覆盖该路径
- 验收标准应区分：「降级路径 N 例通过」vs「happy-path 至少 1 例通过（含 mock）」

---

## Q2: 写第三方库集成 spec 时，怎么避免 API 误用？

**日期**：2026-06-22

**问题**：
spec 里的代码示例（ragas 调用、metric import、Dataset 构造、结果提取）看起来合理，其实都是从文档/注释里推断的，没有实际验证。三处 API 误用在 spec 阶段就定型了，Phase 1 照着写，测试又没覆盖，直到独立 review 才发现。怎么在写 spec 时就拦住这类问题？

**回答**：

**核心原则：第三方库集成的 spec 代码示例，不得靠文档/注释推断——必须先跑通一个最小可验证片段（spike），spec 才能写。**

**具体操作规则**：

**规则 1：对每个「直接使用」的外部 API 调用，先做类型实测**

```python
# 写 spec 前先确认
from ragas.metrics.collections import faithfulness
print(type(faithfulness))          # 是模块还是实例？
print(hasattr(faithfulness, 'measure'))  # 能用吗？
```

不能「这个导入路径看起来对」——看起来对和实际正确是两回事，特别是跨大版本的库。

**规则 2：对数据格式，查「required_columns」而非看文档**

文档可能过时。直接查 metric 对象的约束：
```python
from ragas.metrics import faithfulness
print(faithfulness._required_columns)   # 实际需要的列名，不猜
```

**规则 3：对返回值类型，先看接口而非假设**

```python
import inspect
from ragas.evaluation import EvaluationResult
print([m for m in dir(EvaluationResult) if not m.startswith('_')])
# 有没有 .columns？有没有 .to_pandas？getitem 返回什么？
```

绝对不能把「RAGAS 以前返回 DataFrame」的印象带到新版本里，API 会 break。

**规则 4：凡 spec 里出现「第三方库的函数调用」，必须在「事实标注」列注明验证状态**

| 代码片段 | 验证状态 |
|---|---|
| `Dataset.from_dict({"user_input":...})` | ✅ 实测 ragas 0.4.3 metric._required_columns 确认 |
| `result._scores_dict["faithfulness"][0]` | ✅ inspect EvaluationResult 确认无 .columns |
| `from ragas.metrics import faithfulness as m_f` | ✅ type() 确认是 Metric 实例 |

未验证的标 `⏳`，进入实施前必须先做 spike。

**规则 5：识别「版本双轨陷阱」**

当一个库出现 deprecation warning 时，说明它处于双轨状态——旧 API 还能用但会警告，新 API 接口可能不兼容。此时：
- 不能盲目用 deprecation warning 里建议的「新路径」（新路径可能需要不同的 LLM 接口）
- 应测试新旧两条路径的兼容性，**选能跑通的，而非选「更现代的」**
- 在 spec 里明确记录选择理由与切换触发条件

---

## Q3: 如何判断 spec 里某个设计点是"经过验证的事实"还是"自洽的猜测"？

**日期**：2026-06-22

**问题**：
spec 里写 `faithfulness`（幻觉检测）时，把 `golden_answer` 传给 `answer` 字段，理由是「用理想答案判断检索内容能否支撑——幻觉检测」。这个解释在自己的逻辑框架里是自洽的，但 review 指出这是语义误用（faithfulness 度量的应该是模型真实输出，而非参考答案）。问题在于：自洽 ≠ 正确，当时我怎么应该发现这个问题？

**回答**：

**根因：在「找到一个能说通的解释」之后就停止了探索，没有穷举所有可能性。**

正确的探索链路应该是：

1. **先问「这个字段的设计意图是什么」**，不是「我传什么进去能说通」
   - `answer`/`response` 字段 = 被评模型的真实输出
   - 正确问法：「Retriever 本身不生成回答，这个字段该传什么？」
   - 而非：「我传 golden_answer，这样 faithfulness 就能算检索完整性了」

2. **穷举 answer 字段的填充选项**（不能只找一个「说得通」的）：
   - 选项 A：传 `golden_answer`（理想答案）→ 度量「检索是否支撑理想答案」
   - 选项 B：调 Tutor 真实生成 → 度量「Tutor 输出是否幻觉」（字面定义正确，但引入依赖）
   - 选项 C：不算 faithfulness，改成系统级评估 → 最语义正确，但 scope 变大
   
   列出所有选项，说明选 A 的理由（独立部件，不引入 Tutor 依赖）和代价（语义偏移）。

3. **红线信号**：「这样解释就说得通了」出现时立即停下——这正是 CLAUDE.md 宪法里写的自洽替代事实的信号。

**Spec 中处理语义歧义的正确写法**：

不能把「我选了 A，A 说得通」写成「这是幻觉检测」。应写成：

```
faithfulness 当前实现语义：检索完整性代理（检索内容能否支撑理想答案）
与 RAGAS 字面定义（模型输出幻觉检测）不同，原因：...
两种定位的对照：... | ...
当前选择：A，理由：...，代价：...
待 Phase 3 决策：是否补真实生成路径
```

**可迁移规则**：每个「我用 X 当 Y 的输入」这类语义映射，都欠一份对照表，说明为什么这样映射（而非其他映射），以及这个映射的语义偏移程度。缺对照表 = 「只找到了一个自洽解释，没有穷举」。
