# Task7 实施交接报告（冻结待独立代码审查）

分支 `codex/frontend-ui-optimization`；实施基线 `32243791a5b168c9e2c024b5f3f91b93c8f92f51`。未经独立代码审查，本报告不宣称 Task7 已验收。未提交、推送、安装依赖、部署或进入 Task8。

## 已批准设计

- round1 v1.1：`docs/superpowers/plans/2026-10-25-task7-round1.md`，SHA256 `3796c7196aa30ce9e09fbac45ab62cee7e8811521f916cb51f7f26c52c1f5780`，独立计划复审 PASS 见 `evidence/Task7/round1-plan-review-final.md`。
- round2：`docs/superpowers/plans/2026-10-25-task7-round2.md`，SHA256 `c6d137a41c74863a6a2176d045fa2f27e70a9b978ea37664888c279c16a30137`，独立 PASS 见 `evidence/Task7/round2-plan-review.md`。发现真实路由不符后先报告、等待该轮授权，未提前改 Orchestrator。
- 规划依据 raw：`superpowers/frontend-ui/2026-10-23-final-implementation-raw.md` 第二层 C / 第三层上下文接口。

## 输入与产物

`build_teaching_context(snapshot, messages, current_message, profile_summary, *, summarizer=None)` 消费本会话已提交历史及可信画像。已知 schema1 字段严格校验；合法 JSON 扩展逐值保留而不执行、渲染；unknown schema 报具名错误。legacy 兼容读取模式及完整成对 turn_index 计数，保留调用方 legacy 原对象。

统一最终 HumanMessage 由历史、当前输入、画像组成；Conductor 另有本轮结构化观察段。摘要、上一问题、模式、阶段、消息角色与引用标记共用历史 12000 字符预算；至多12条历史，最近消息项至多4000字符，当前原文4000字符完整保留，4001在构建时拒绝。画像展示至多20节点，说明200字符、标题512字符、展示主题128字符；校验集合保留完整未归档节点。观察自由文本纳入统一历史预算，结构化段只接受有限的枚举、数值与布尔投影。

恢复业务 TeachingPolicy 与模式历史；运行队列、订阅实例、证据池和内部 turn_count 每请求重建。run 的旧位置参数、三元组 build 返回、旧六字段 NewStackResult 构造及 RAG 开关保留。online 末尾可选 context 原样转交低层；context session/user/原文不匹配时模型前失败。实际动作后的提示使用 ws 当前模式。

结果返回 schema1 候选 `teaching_state` 与 `assessment_deltas`。候选 committed_turn_count=原值+1，原快照不修改。最后真实 Tutor 输出为 ask/recap 才保存待答；explain/analogy 清旧问题并设 presented；无新输出设 no_output。Critic 只对有效待答及当前回答产出合法有限0–100分，topic_id 使用可信 UUID，不信模型伪造节点。Curator 两分支不创建未知节点、不默认零分；无 context 的旧离线路径保留。

Regress 初始动作及后续 Policy/规则动作均真正进入 Tutor→SpecLoader→LLMService。前置来自当前图的 PREREQ 边与可见节点交集；缺失/未知/归档时明确安全诊断，无当前节点询问学习范围。round2 修正普通掌握度路由丢弃 Policy 动作、observed 前置依据被后续 historical 覆盖两条真实路径；保留全局高优先规则、retriever 门禁和旧无 context 路由。

摘要 helper 通过真实 LLMService.invoke、intent=teaching_summary；只输入旧摘要及本次实际省略的消息。默认无 summarizer 时明确缩减；失败、空/过长候选保留原摘要及截止；旧边界未出现在提供消息时不扩展。调用方历史连续性及生产 LLM 注入仍属于 Task8。

## 红绿与执行记录（如实保留限制）

日志目录：`docs/delivery/study-workspace-goal/evidence/Task7/`。以下命令均使用已有 `.venv/Scripts/python.exe -m pytest`，未 uv sync/安装。

| 步骤 | 命令范围 | 证据与结果 |
|---|---|---|
| 7.1 | `tests/unit/orchestration/test_conversation_context.py -q` | `7.1-red.log` 17 failed；全部停在 find_spec 缺模块断言。它只证明契约模块不存在，**不是17项具体业务行为均已证伪**。实现后 `7.1-green.log` 17 passed。该阶段严格业务 TDD 证据不足，未事后篡改或伪造红灯。 |
| 7.2 | conversation_context + test_assembly + test_teaching_policy | `7.2-red.log` 3 failed/49 passed，真实历史丢失、候选缺失、转发缺失断言；`7.2-green.log` 52 passed。 |
| 7.3 | conversation_context | `7.3-red.log` 23 failed/28 passed，真实最终提示缺上下文、动作无回复、错误建点等；使用最下游受控 LLM client，无网络。 |
| 7.3 | conversation_context + 四个指定 Agent 文件 | 普通沙箱 `7.3-green.log` 停留72%，非通过；原生独立 `7.3-green-native.log` 99 passed/1.86s。首次 fixture 把13条历史末项 user 正文当 assistant，已纠正真实角色/turn_index，未放宽预算断言。 |
| 7.3 补充 | strict known shapes、observation free text | `7.3-validation-red.log` 3 failed/5 passed：非字符串模式导致 TypeError、观察自由文本越段。 |
| 7.3 补充 | 实际模式转换后的最终 HumanMessage | `7.3-mode-red.log` 1 failed，快照 Feynman 而真实提示仍 Socratic。 |
| 7.3 定向 | 上述边界及两 Curator 分支/待答/真实两轮 | `7.3-boundaries-green.log` 25 passed/55 deselected。 |
| 7.3 路由阻断 | 实际协作环后续 Analogy/Regress/observed | `7.3-policy-route-red.log` 3 failed，保留原断言并报告后申请 round2。 |
| 7.4 | API 文件的 `task6_stored_and_legacy_snapshot_context_roundtrip` | `7.4-roundtrip.log` 1 passed/13 deselected；现有产品已支持交接，该新增集成断言首跑即绿，没有虚称其新增业务红灯。 |
| round2 红灯 | test_orchestrator + conversation_context | `round2-red.log` 9 failed/111 passed，含原3条协作环与新增顺序/模式实际路由边界。 |
| round2 中间 | 同组 | `round2-green.log` 21 failed/99 passed，原因是新枚举使用漏 import；保留失败证据。 |
| round2 绿灯 | 同组 | `round2-green-final.log` 120 passed/1.11s。 |
| 最终组合 | 下列受影响完整组合 | `regression-final.log` **352 passed, 1 deselected, 1 warning /16.56s**；最终工具 session_id=55977，随后同句柄取回 exit_code=0。 |

最终组合精确命令：

```text
.venv/Scripts/python.exe -m pytest tests/unit/orchestration/ tests/unit/agents/ tests/unit/harness/test_workspace_state.py tests/unit/harness/test_teaching_policy.py tests/unit/harness/test_orchestrator.py tests/unit/api/test_workspace_sessions_api.py tests/unit/api/test_chat_new_stack_e2e.py tests/unit/api/test_chat_stream_new_stack_e2e.py -q
```

该组合使用单独 `DATABASE_URL=sqlite+aiosqlite:///D:/backup/basic_file/Program/LearningAgent/StudyAgent-Harness/docs/delivery/study-workspace-goal/evidence/Task7/task7-regression.sqlite`；运行前以当前 `Base` 的 init_db 建表，完成后恢复 shell 环境变量。Task6 fixture 每物理连接开启外键、file SQLite + NullPool，先刷新父记录，回合 fixture 只最终 commit。没有访问用户旧 SQLite 或业务 PostgreSQL。测试二进制已核实 resolved path 属于工作区且为本轮生成，移入 ignored `.superpowers/sdd/2026-10-23-study-workspace-core/task7-regression.sqlite`，不应提交，不作为验收依赖。

排除项为 `tests/unit/agents/test_retriever.py::test_evaluate_ragas_real_judge`，其 `@pytest.mark.integration` 被 `pyproject.toml` 既有 `addopts = "-m 'not integration'"` 排除；该真实 OpenAI/RAGAS 测试**未执行、未验收**。warning 为既有 `test_chat_new_stack_e2e.py:12` 导入 TestClient 的 Starlette/httpx 废弃提醒，未为消警安装或改无关代码。

## 执行失误与处置

第一次7.3组合误用普通沙箱（含 Curator 异步 SQLite），且工具封装只输出 `r.output`，未保留返回 session_id，导致无法按原句柄轮询。该进程仍活跃时误起了一次相同范围的原生组合；两组只用各自临时 SQLite，原生结果独立记录，**不改写为原进程成功**。主会话指出后停止重复启动。

原生 CIM 只读诊断确认 PID19000=pwsh、11320=venv Python、12760=底层 Python，其命令行全部只属于该原7.3测试；原日志81字节、LastWriteTime=2026-10-25 00:50:40，多次未推进。由于 -q 重定向未记录当前项，**不能事实确定卡在某个具体测试**；收集顺序含后续 Curator SQLite 并非确切卡点证据。主会话根据进程与原生对照授权后，只清理这三个明确自建测试 PID；未杀其他 Python 或业务服务，原运行记为中断。`7.3-collection-order.log` 仅为只读收集顺序。一次管道读取 collect 输出提前关闭产生 stdout OSError，随后完整保存收集列表，均非测试通过证据。

## 实际提示词及隔离证据

`actual-prompt-synthetic.json` 保存6次真实 Agent→SpecLoader.compose→LLMService.invoke_json→_call_with_span→受控 client 的 SystemMessage/HumanMessage、两轮候选与合法增量，全部合成数据，无网络。第二轮包含第一轮用户原文、上一助手问题引用、当前“刚才的例子”，上一问题正文仅一次；Conductor含同上下文及真实结构化观察。字符预算测试捕获 Tutor 八个动作/Critic/Conductor 最终请求；同画像 A/B 历史交错调用及 session/user 不符模型调用次数0有自动断言。模型伪造 topic_id 被替换为可信稳定UUID；0和100保留，bool/NaN/inf/None/文本/越界均不评分。

真实 Task6 交接测试由 SessionService/DTO 读取、结束读事务、受控 assembly、JSON 候选、fixture 显式保存 state_json，再次读入；验证非默认 Feynman/history/stage/last_question/summary/边界/count 及嵌套扩展，legacy 与 unknown schema。它是测试 fixture 接线，**不是生产 ConversationService/HTTP/SSE 持久化闭环**。

## 本实现者变更文件（20个）

产品：
- 新 `app/harness/teaching_context.py`
- `app/harness/workspace_state.py`
- `app/harness/teaching_policy.py`
- `app/harness/orchestrator.py`（round2授权）
- `app/orchestration/assembly.py`
- `app/agents/tutor.py`
- `app/agents/critic.py`
- `app/agents/conductor.py`
- `app/agents/curator.py`

成对规范：
- `app/specs/agents/tutor.md`
- `app/specs/agents/tutor.prompt.md`
- `app/specs/agents/critic.md`
- `app/specs/agents/critic.prompt.md`
- `app/specs/agents/conductor.md`
- `app/specs/agents/conductor.prompt.md`
- `app/specs/agents/curator.md`
- `app/specs/agents/curator.prompt.md`

测试：
- 新 `tests/unit/orchestration/test_conversation_context.py`
- `tests/unit/harness/test_orchestrator.py`
- `tests/unit/api/test_workspace_sessions_api.py`

此外仅新增/生成本报告、Task7测试日志、合成提示词JSON、冻结 manifest；两份已批准计划及 review 证据由主会话负责，不是本实现者改写。本实现者未修改 README、asset-inventory、账本、status、raw、主计划、终稿或 Task6 service/schema。既有用户改动保持原状。`git diff --check` 在去除本轮八份文档尾部空白后通过（另有 Git 既有 LF→CRLF 提示）。

## 未实现与交接

Task8 必须加载可信已归属 session 的完整连续历史/区间，短事务结束后显式注入真实摘要 LLM；生产领取、租约、幂等、归属重验、原子回合提交、真实 answer_message_id/request_id 填充、HTTP/SSE共用服务、PostgreSQL重启/跨账号验收均 PENDING。Task7只返回未保存候选与纯业务增量，不调用整图save，不声称已部署或总Goal完成。独立代码审查仍须覆盖全部20文件及规划、红绿限制；若要求修复，按新一轮 plan→独立review PASS→execution，不自行继续改冻结diff。README由主会话审查后更新。

## Round3（code fix 1/5）五项独立审查修复交接

本轮依据 `docs/superpowers/plans/2026-10-25-task7-round3.md`，SHA256 `2192dc8f9c4817f2a16816ae3231f8c4e437c16b2e704187a58fe5e84f73694f`，独立计划 PASS 见 `evidence/Task7/round3-plan-review.md`；原发现见 `round2-code-review.md`。已加载 receiving-code-review 并逐项核实 Task6 的字符串 role 与实际排序、缺图清选点、原文split、摘要截断、legacy类型问题。未改旧证据；旧7.1/7.3限制继续成立。用户 SC-001 限定只完成 Task7，完成后停止，不做 Task8。

### 五项实际修复

1. `_messages` 接受合法字符串 role，非字符串仍拒绝；与 Task6 同样按 turn_index、user=0/assistant=1/其他=2、id 排序。system/tool/custom 都留在 HumanMessage 中作为普通数据，不提升为 SystemMessage/工具执行。角色和正文共同受单项4000字符限制并标记缩减。legacy计数采用同turn同时含 user/assistant，而非角色集合必须完全相等；其他角色不再破坏真实完整往返计数。待答定位仍只看 assistant。
2. context 可信有效选点而 graph=None/缺节点时，在模型和 EventBus 装配前抛 `TeachingContextError(code="graph_context_mismatch")`，不改输入UUID、context/state或图，不产候选/评分。未选点仍可聊天。此为 Task7 内部具名错误，未宣称有 Task8 HTTP 映射。
3. renderer持有历史、当前原文、画像、观察四个真实分段，`assert_final_prompt`改为只接收可信分段并校验历史≤12000、原文≤4000，然后一次拼接。Tutor/Critic/Conductor删除对已渲染字符串进行不安全重复split的调用，保留唯一构造器的共同预算校验。原文包含任意“【当前输入】/【画像】/【本轮观察】”、换行或组合时，不转义、不改写、不截当前原文。
4. builder与renderer共用 `_history_layout`。接受候选时以枚举最大模式长度及最大历史note512、观察自由说明512与标签/换行预留容量，包含“摘要=”及分隔符；渲染先完整放摘要，较早历史只用其余容量。3500字候选若接受，各实际Agent请求全文出现；恰好容量接受，多1字符失败保留旧摘要和截止。旧超长摘要可安全裁剪并记录缩减而不移动旧边界。`_clip`在剩余额度0–4字符也不再返回超预算的完整截断标记。
5. legacy mode/history先检查字符串/列表及每项类型，再检查有效枚举；数组/对象/布尔/数值非法mode使用明确Socratic默认，非法history用[mode]。嵌套非法项不再抛unhashable TypeError；schema1原严格失败行为保留，legacy原字典不修改。

### 本轮真实红绿与命令

均为已有 `.venv/Scripts/python.exe -m pytest`，原生审批路径；没有安装/联网/真实模型/PG/迁移。所有结果来自真实测试断言；未用进程内篡改或收集错误伪造红灯。

- `round3-red.log`：新增五类断言（conversation_context及Task6真实API交接）**11 failed、9 passed、94 deselected /4.55s**。具体失败含真实system历史invalid_history、双入口缺图未抛错误、原文分隔符触发AssertionError、3500摘要未完整渲染、legacy非法类型TypeError。其他合法边界首跑已绿，如实保留。
- `round3-capacity-red.log`：恰好/多1字容量和 `_clip` 零/极小剩余 **7 failed、99 deselected /0.79s**。
- `round3-targeted-green.log`：全部27个本轮新增断言 **27 passed、94 deselected /3.01s**。
- `round3-context-task6-green.log`：`tests/unit/orchestration/test_conversation_context.py tests/unit/api/test_workspace_sessions_api.py -q`，**121 passed /9.87s**；session_id=82190，同句柄取回 exit_code=0。
- `round3-regression-final.log`：前轮相同完整受影响组合，加本轮27项，**379 passed、1 deselected、1 warning /17.07s**；session_id=32511，同句柄取回 exit_code=0。仅执行一次此完整组合，没有重启或重复活跃命令。

完整组合仍为前文精确八组路径。运行采用 ignored 独立数据库：

```text
DATABASE_URL=sqlite+aiosqlite:///D:/backup/basic_file/Program/LearningAgent/StudyAgent-Harness/.superpowers/sdd/2026-10-23-study-workspace-core/task7-round3-regression.sqlite
```

一个临时执行进程中先为 SQLAlchemy Engine 注册每物理连接 `PRAGMA foreign_keys=ON`，以当前 Base 的 init_db建表，再 pytest.main 运行相同路径参数；完成恢复shell环境变量。Task6 fixture继续独立文件SQLite+NullPool、父先flush。该ignored测试二进制不提交、不作为证据必需品。唯一排除项与旧warning均与前轮相同：`test_retriever.py::test_evaluate_ragas_real_judge` 被既有 integration 默认配置排除，未执行；Starlette TestClient/httpx 导入废弃提醒未涉及本轮改动。

### 本轮范围与冻结

相对主会话 `round3-before/` 的上一冻结版本，仅修改以下7个代码/测试文件：

- `app/harness/teaching_context.py`
- `app/orchestration/assembly.py`
- `app/agents/tutor.py`
- `app/agents/critic.py`
- `app/agents/conductor.py`
- `tests/unit/orchestration/test_conversation_context.py`
- `tests/unit/api/test_workspace_sessions_api.py`

另追加本报告，新增 `round3-*` 日志及冻结manifest。未修改 Orchestrator、Task6 service/schema、Curator、八份规范文件、数据库模型、README、账本、计划或全局配置，未提交/推送。真实下游客户端断言覆盖Tutor八动作、Critic、Conductor的包含分隔符4000字符原文；没有用renderer反解析当前输入作为测试预期。摘要实际三Agent请求、最大note/自由观察说明、手工推导容量及多1字符、已存长摘要和失败原边界均有断言。

本轮冻结后等待原reviewer对五项逐项 ADDRESSED/NOT ADDRESSED及新破坏范围复审；计划PASS和379绿灯不能替代独立代码审查。本实现者不自行继续改产品。Task7验收通过后按SC-001结束，不进入Task8。

## Round4（code fix 2/5）最新真实问答保护修复交接

依据已独立PASS的 `docs/superpowers/plans/2026-10-25-task7-round4.md`，SHA256 `e043f04d239d5232f4407be252fef861dd5d423ff7ffab7a136795917b30040e`，证据 `round4-plan-review.md`；原范围复审见 `round3-code-review.md`。原五项已ADDRESSED，本轮只处理多角色历史最新问答保护的新P1；SC-001仍只完成Task7。

`_protected_messages` 从实际提供且已校验的有序历史分别选最近user与assistant，缺任一角色不造替代项；不再用history末两条索引推断问答。`_select_history` 优先保护这些真实项（包括默认末12条之外或旧摘要边界前的已提供记录），再从旧边界后的历史按新近补足至12，最终仍按原Task6顺序保留。renderer与摘要容量共用同一保护规则，先为真实两项含引用/角色/截断标记各≤4000预留，再放摘要和其他普通历史。system/tool继续仅作为HumanMessage普通数据，不能占用真实问答保护位。

新摘要只消费旧截止之后的实际连续省略前缀，到该tail中的首个保留项为止。旧边界前的保护项不会阻断这个前缀；但保留项之后的零散遗漏只能记history_gap/context_reduced，不拼成伪连续摘要推进截止。未知旧边界仍不调用摘要、不扩展截止；原legacy完整pair计数、待答/评分门禁及前五项修复保持。

真实红绿（均已有venv、原生审批、无网络/真实模型）：

- `round4-red.log`：本轮9项中 **8 failed、1 passed、121 deselected /4.20s**。真实10个下游Agent请求及Task6长历史交接显示user/assistant被挤出；末12外、单角色、前缀/间隙、旧边界前保护各有真实失败。无真实角色的边界首跑已绿，未虚称其有红灯。
- `round4-targeted-green.log`：**9 passed、121 deselected /2.67s**。四role各3500字符+旧摘要5000字符时，Tutor八动作、Critic、Conductor所有最终请求均完整保留两条真实问答引用与原文，单项≤4000、历史总段≤12000；预算由可信已知后缀长度核证，没有反解析用户分隔符。
- `round4-context-task6-green.log`：完整 `conversation_context.py` + `test_workspace_sessions_api.py`，**130 passed /11.12s**；session_id=80757，同句柄取回exit_code=0。
- `round4-regression-final.log`：前轮同一完整受影响组合加本轮9项，**388 passed、1 deselected、1旧warning /18.94s**；session_id=70586，同句柄取回exit_code=0。仅运行一次该完整组合，未重复或重启活跃命令。

完整组合使用独立 ignored `DATABASE_URL=sqlite+aiosqlite:///D:/backup/basic_file/Program/LearningAgent/StudyAgent-Harness/.superpowers/sdd/2026-10-23-study-workspace-core/task7-round4-regression.sqlite`。与round3相同，单进程先为所有SQLAlchemy物理连接注册FKON，当前Base建表后pytest.main运行原八组路径；Task6 fixture仍file SQLite+NullPool、父先flush。shell环境变量已恢复，二进制不提交。唯一排除项仍是既有integration配置排除的真实OpenAI/RAGAS `test_evaluate_ragas_real_judge`（未验收），唯一warning仍是已有Starlette/httpx TestClient废弃提醒。

连续摘要新增断言明确验证：保护位在id3/id7时，只向summarizer提供连续前缀[1,2]并截止2，不混入后续间隙；旧截止5之前的问答id1/id2继续保护，同时只摘要截止后的[6..15]并推进至15；未知截止100保持100且不调用摘要。只有user、只有assistant、无两者时均不伪造完整往返或评分配对。

相对 `round4-before/` 本轮仅改以下3个文件；其他17个冻结产品/测试/规范文件要求字节不变：

- `app/harness/teaching_context.py`
- `tests/unit/orchestration/test_conversation_context.py`
- `tests/unit/api/test_workspace_sessions_api.py`

另仅追加本报告、新增round4日志及冻结manifest，未改Agent/Orchestrator/Task6服务/数据库模型/README/账本/计划，未提交、未进入Task8。原7.1/7.3历史限制不变。本轮再次冻结，等待同一reviewer范围复审；388绿灯不替代独立审查。
