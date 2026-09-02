# RAG Foundation 决策画布 · BLK-006

> **本页目的**：先说明 BLK-006（backend/outcome 真实性）在整体计划里解决什么，再下钻到三项技术选择。  
> **当前状态**：三项技术裁决（D-006-1/2/3）已由用户确认并固化（DEC-007/008/009）；本页是决策阅读视图的源，不是已确认事实源。  
> **正式事实源**：已确认决策写入 `2026-07-27-rag-p0-confirmed-decisions.md`；阶段状态与 blocker 写入 RAG Foundation 主清单。  
> **阅读建议**：只想判断方向，读第 0–3 节与第 13 节；要审实现合理性，再读第 4–12 节。

---

## 0. 三分钟决策摘要

### BLK-006 解决什么

```text
用户提问 → 检索 → 检索"成功"了，但：
  · 后端其实跑的是 fake（字符匹配），不是真向量检索
  · 或者 provider 全挂了，却被当成"没搜到"
  · 或者异常把 SQL/连接串泄进了事件 payload
→ Tutor 拿到一份"看似有证据、实则不可信"的结果
```

BLK-006 让检索的**结果状态可区分、后端真实性可强制、失败信息不泄密**。它是"真实结果与评测"支柱的地基——没有它，Phase 5 baseline 和 Phase 6 grounded answer 都建立在无法分辨真伪的结果上。

### 为什么现在决策

- BLK-004（DEC-005/006）已固化 identity 与 range，证据"是谁、从哪来"有了；
- DEC-003 已冻结 `EvidenceProjection` 含 `retrieval_status` 与 `safe_summary`，但**这两个字段取什么值、装什么内容**还没定义——正是 BLK-006 要冻结的；
- DEC-004 要求 empty/failed/Critic 无输出仍产生受控回复，前提是**能判定当前是 empty 还是 failed**，而这恰是当前代码做不到的。

### 当前只需判断三件事

| 待确认 | 推荐 | 为什么与上层目标有关 | 现在不决定的后果 |
|---|---|---|---|
| production 后端校验 | 在线 composition 入口显式要求 pgvector + PostgreSQL，不满足 fail-fast | 防止生产静默跑 fake 被当真能力 | baseline/E2E 可能测到 fake 还以为通过 |
| outcome 状态枚举 | `{ok, empty, degraded, failed, invalid-request}` 五态 | 让"没数据/部分降级/全挂/非法请求"可区分 | Tutor 无法据状态走受控降级，落入空回复 |
| 安全摘要边界 | payload 只放分类错误码 + 安全摘要；原始异常只进内部日志 | 防止 SQL/连接串/堆栈泄进事件链与 Tutor | 安全风险 + 评测无法按失败类型分类 |

> ⚠️ 同意这三项不等于 BLK-006 解除。Provider 异常传播改造、`safe_summary` 具体文案、production composition 的实现机制仍需 RAG-C 在 spec 里落到可编码。

---

## 1. 上层建筑：BLK-006 对应哪个支柱

| 能力支柱 | 用户最终获得什么 | 已确认/待解决 | 主要阶段 |
|---|---|---|---|
| 正式摄入与证据身份 | 知识真实进入索引，每块证据可回查 | DEC-002/005/006 已确认 | Phase 1B → 2 → 4 |
| 授权隔离 | 只检索当前用户有权看的内容 | DEC-001 已确认 | Phase 2 → 4 → 6 |
| 当前回合证据消费 | 当前检索证据只进入当前 Tutor 回复 | DEC-003/004 已确认 | Phase 3 → 6 |
| **真实结果与评测** | **fake/失败/空结果不冒充成功；baseline 只测真索引** | **BLK-006 当前待决** | **Phase 2 → 5 → 6** |

**BLK-006 只负责"检索结果是真是假、是哪种非正常态、失败时说什么"。** 它不负责授权（DEC-001）、不负责证据身份（DEC-005/006）、不负责在线投影路由（DEC-003/004），但后三者都要消费它定义的 `retrieval_status` 与 `safe_summary`。

---

## 2. outcome 数据流与状态分工

```text
query + visibility
  ↓
RAGCoordinator.search
  │ 对每个 provider：try search → 成功累积 / 失败记录
  │   ↓（当前：except Exception: continue，失败被吞）
  ↓
Provider（PgVector / OCR / Code）
  │   ↓（当前 SQLite 分支：字符匹配降级，无标记）
  ↓
RetrieverAgent
  │ 按机械结果判定 retrieval_status
  │   ↓（当前：仅 empty/low_score/ok）
  ↓
RetrievedEvidence / RetrievalFailed
  │ payload 含 retrieval_status、sources_used、safe_summary
  ↓
Orchestrator EvidenceProjection（DEC-003）
  ↓
Tutor 据 status 走受控降级或正常 grounded 回复（DEC-004）
```

| 状态 | 回答的问题 | 谁产生 | 当前是否存在 |
|---|---|---|---|
| `ok` | 正常有结果、分数够 | Retriever | ✅ 有 |
| `low_score` | 有结果但机械分数低 | Retriever | ✅ 有（建议降为 ok 的质量子标记） |
| `empty` | 真调用真 provider，无数据 | Retriever | ✅ 有 |
| `degraded` | 部分基础设施降级（多 provider 部分失败 / SQLite 降级） | Coordinator+Retriever | ❌ 缺 |
| `failed` | 全部 provider 失败 / 基础设施异常 | Coordinator+Retriever | ❌ 缺（当前混入 empty） |
| `invalid-request` | 缺身份 / 无授权 / 无效 query | 检索入口（衔接 DEC-001） | ❌ 缺 |

这张表解释了为什么不能只靠 `empty`：当前代码把"全挂"和"真没数据"都报成 empty（`coordinator.py:111-117` 吞异常后返回空），Tutor 和评测都无法区分。

---

## 3. BLK-006 在 Phase 0–6 中的位置

```text
Phase 0  已确认 DEC-001~006，分发窗口边界
   ↓
Phase 1C RAG-C spec 修订（含 outcome 归约、production composition）
                     ▲
                     └── 你现在正在裁决 BLK-006 的三项基线
   ↓  只有 C spec 通过主控复核才进入编码
Phase 2  C-10 provider outcome + 安全摘要；C-11 production 显式 PgVector
   ↓
Phase 3  C-15 覆盖 empty/degraded/failed/invalid-request 的受控回复
   ↓
Phase 4  正式摄入（依赖 BLK-006 的 outcome 契约写 attestation 失败态）
   ↓
Phase 5  baseline（admission gate 要核 backend 真实性，正是 BLK-006 的产出）
   ↓
Phase 6  grounded answer E2E（要区分召回失败 / projection 失败 / 生成失败）
```

### 决策的下游传播

| 本轮决定 | Phase 2 影响 | Phase 3 影响 | Phase 5/6 影响 |
|---|---|---|---|
| production composition 校验 | C-11 实现装配校验 | 在线链确定跑真后端 | admission gate 可据 backend 判准入 |
| outcome 五态归约 | C-10 实现状态判定 | C-15 据状态走受控降级 | baseline 能按失败类型分类 |
| 安全摘要边界 | C-10 移除 `str(exc)` | projection 只透出安全摘要 | E2E 不泄密、可审计 |

因此这不是"多加几个状态字符串"，而是让 **Phase 3 的受控降级、Phase 5 的 baseline 分类、Phase 6 的失败归因** 都有可判定的输入。

---

## 4. 已核验事实

| 事实 | 证据 | 影响 |
|---|---|---|
| 默认 `rag_backend="fake"`，注释明言"默认 fake 保持测试兼容" | `app/core/config.py:21` | 不显式配置就跑假检索 |
| Coordinator else 分支静默包装 `FakeRAGStore`，无 production 校验 | `app/infrastructure/rag/coordinator.py:54-84` | 生产忘配 pgvector 也不会报错 |
| `search` 对每个 provider `except Exception: continue`，失败被吞 | `app/infrastructure/rag/coordinator.py:111-117` | 全部 provider 失败仍返回空 `SearchResult`，与"真没数据"不可区分 |
| `sources_used` 只在 provider **有 chunks** 时才记录 | `app/infrastructure/rag/coordinator.py:114-115` | "调了但失败"的 provider 不出现，无法知道调过谁 |
| `RetrievalFailed.reason = str(exc)`，原始异常直接进 payload | `app/agents/retriever.py:54-63` | SQL/连接串/堆栈可能泄进事件链与 Tutor |
| 失败时 `retrieval_status` 硬编码 `"timeout"`，不反映真实异常类型 | `app/agents/retriever.py:59` | 所有失败都被标成 timeout，无法分类 |
| 成功路径 `retrieval_status` 仅 `empty/low_score/ok` | `app/agents/retriever.py:80-85` | 缺 `degraded/failed/invalid-request` |
| 非 PostgreSQL 时 `search` 用字符重叠评分（SQLite 降级） | `app/infrastructure/rag/pgvector_provider.py:159-180` | 误连 SQLite 会静默退化为字符匹配 |

> ⚠️ 当前没有任何机制保证"在线生产路径跑的是真 PgVector + PostgreSQL"。BLK-006 的第一项决策就是堵这个口。

---

## 5. 决策一：production 后端校验

### 为什么必须做这个选择

`config.py:21` 默认 fake，`coordinator.py:54-84` 不校验。如果生产环境漏配 `rag_backend=pgvector`，或 DB 误连 SQLite，系统会**静默跑假检索/字符匹配**，而 Phase 5 baseline 和 Phase 6 E2E 都可能把它当真能力通过。

| | A：在线 composition 入口显式校验 + fail-fast（推荐） | B：全局启动即校验禁 fake | C：不加校验，靠文档约定 |
|---|---|---|---|
| 做法 | 在线装配 Retriever 时要求 provider class=PgVectorProvider 且 dialect=postgresql；不满足抛错 | 进程启动时若非测试环境就禁用 fake | 仅在部署文档写"生产要配 pgvector" |
| 保护范围 | 精确覆盖在线热路径 | 全局，但误伤测试/本地开发 | 无强制力 |
| fake/SQLite 是否仍可用 | 是，仅在非在线路径（测试、bench）保留 | 否，需大量改测试 | 是 |
| 漏配后果 | 立即失败，可发现 | 启动失败 | 静默跑假，不可发现 |
| 实施代价 | 需定义"在线 composition 入口"边界 | 需区分环境、改大量 fixture | 零 |
| 适用目标 | 正式产品链 | 强约束但笨重 | 不可靠 |

**推荐裁决 D-006-1：选择 A。**

- 在线生产 composition（`/api/chat`、`/api/chat/stream` 装配的 Retriever 链）必须显式注入 `PgVectorProvider`，并在装配点校验 `rag_backend=="pgvector"` 且运行时 dialect 为 postgresql；不满足则 fail-fast，不进入检索。
- fake、SQLite、多源（OCR/Code）在**非在线路径**（单元测试、集成测试、离线 bench）继续保留，不受限。
- 禁止在线路径静默回退 fake；禁止"pgvector 不可用时悄悄用 fake 顶上"。

**选择原因**：fake/SQLite 是测试刚需，不能全局禁（B 代价过大且误伤）；但在线热路径必须强制真后端（C 无强制力）。A 把"强制"精确落在在线 composition 边界，既保护生产又不破坏测试。

> ⚠️ "在线 composition 入口"的精确代码落点（assembly/依赖注入）由 RAG-C 在 spec 里定义；本决策只冻结"必须校验、必须 fail-fast、不静默回退"。

---

## 6. 决策二：outcome 状态归约

### 为什么必须做这个选择

`retriever.py:80-85` 只有 `empty/low_score/ok`，加上失败路径硬编码 `timeout`。DEC-003 冻结的 `EvidenceProjection.retrieval_status` 取值、DEC-004 的"empty/failed 受控回复"都需要一个**可判定的状态枚举**。

| 候选枚举 | 语义 | 代价 |
|---|---|---|
| A：`{ok, empty, degraded, failed, invalid-request}`，`low_score` 并入 ok 的质量子标记（推荐） | ok=正常；empty=真无数据；degraded=部分降级；failed=全挂；invalid-request=非法 | 5 态，清晰；low_score 不占独立状态位 |
| B：保留 `low_score` 为独立第六态 | 区分"有但分低" | 状态空间膨胀，且 low_score 本质是质量代理（归 Critic） |
| C：只加 `failed`，不区分 degraded | 最小改动 | 部分 provider 失败与全挂混淆，降级不可观测 |

**推荐裁决 D-006-2：选择 A。**

outcome 五态精确定义：

```text
ok               真实 provider 正常返回，有结果
empty            真实 provider 正常返回，无结果（真没数据）
degraded         部分基础设施降级：多 provider 部分失败 / SQLite 字符匹配降级 / embedding 降级但仍可用
failed           全部 provider 失败或基础设施异常（DB 连不上、embedding 服务挂）
invalid-request  缺认证身份 / 无授权 scope / 无效 query（衔接 DEC-001 fail closed，不检索）
```

- `low_score` 不作为独立 outcome 态，降为 `ok` 的质量子标记（`quality: low/acceptable`），语义质量继续归 Critic。
- `degraded` 必须可观测：哪些 provider 失败、是否走了降级路径，进 `sources_used` 与内部日志，安全摘要对外。
- `invalid-request` 在检索入口拦截（衔接 DEC-001），不进入 provider 调用。

**选择原因**：A 既满足 DEC-004"区分 empty/failed"的硬要求，又让"部分降级"可观测（C 做不到），还不让质量代理（low_score）污染状态空间（B 的代价）。

---

## 7. 决策三：安全摘要与 provider 异常传播

### 为什么必须做这个选择

`retriever.py:58` `"reason": str(exc)` 把原始异常字符串直接放进 `RetrievalFailed` payload，会沿事件链流到 Orchestrator、Tutor、API。同时 `coordinator.py:111-117` 吞掉所有异常，使 `failed` 无法产生。

| | A：分类错误码 + 安全摘要对外，原始异常只进日志（推荐） | B：保留 str(exc) 但截断 | C：完全不透出失败信息 |
|---|---|---|---|
| 对外 payload | 固定错误码集合（如 `backend_unavailable/embedding_failed/db_error`）+ 一句安全摘要 | `str(exc)[:N]` | 无 reason |
| 安全性 | 不含 SQL/连接串/堆栈 | 仍可能泄露片段 | 最安全 |
| 可诊断性 | 内部日志保留完整异常；外部可按码分类 | 部分 | 无法分类失败 |
| 实施代价 | 需定义错误码集合 + 摘要模板 | 小 | 但失去可观测性 |

**推荐裁决 D-006-3：选择 A。**

- `RetrievalFailed` / `EvidenceProjection.safe_summary` 只允许出现**分类错误码**与**预定义安全摘要**，禁止 `str(exc)`、SQL、连接串、堆栈进入 payload。
- `coordinator.py:111-117` 的 `except Exception: continue` 改造为：记录失败 provider 与异常（进内部日志），并据此判定 `degraded`（部分失败）或 `failed`（全部失败），不再静默吞没。
- 原始异常、SQL、连接串、堆栈只进结构化内部日志（含 trace_id/retrieval_id 关联），不进事件 payload、不进 Tutor、不进 API 响应。
- 错误码集合与摘要文案由 RAG-C 在 spec 里枚举（如 `backend_unavailable`、`embedding_failed`、`db_error`、`invalid_request`），本决策只冻结"分类码+安全摘要对外、原始异常对内"的边界。

**选择原因**：安全与可诊断性不矛盾——原始异常留内部、分类码对外，既不泄密又能按类型排查（B 仍有泄露风险，C 失去可观测性）。

---

## 8. 用产品需求反向判断本方案

| 你的上层需求 | 必须成立的技术保证 | BLK-006 如何支撑 | 不符合需求时怎么改 |
|---|---|---|---|
| 回答基于真知识，不是 fake | 在线强制 PgVector+PostgreSQL | D-006-1 composition 校验 | 若接受演示用 fake，则降级为 prototype，baseline/E2E 不可信 |
| 失败要能说清是哪种失败 | empty/degraded/failed/invalid-request 可区分 | D-006-2 五态归约 | 若不区分，Tutor 无法走受控降级 |
| 系统不泄密 | 异常不进 payload/Tutor | D-006-3 安全摘要边界 | 若保留 str(exc)，有泄露风险 |
| baseline 诚实 | admission 能核 backend 真实性 | D-006-1 产出可校验的 composition 证明 | 若不校验，可能测到 fake |

### 主控判断

若目标是"真实、可区分失败、不泄密的检索结果，并能被 baseline 与 E2E 审计"，BLK-006 三项决策都是必要前提。若目标只是"先跑通演示"，可暂缓 D-006-1（接受 fake），但必须诚实标为 prototype，不能进入 Phase 5/6 正式验收。

---

## 9. 已确认决策如何约束 BLK-006

| 已确认决策 | 对 BLK-006 的约束 | 决策原因 |
|---|---|---|
| DEC-001：fail closed | `invalid-request` 在检索入口拦截缺身份/无授权请求，不进 provider | 授权缺失不得检索 |
| DEC-003：EvidenceProjection 含 retrieval_status/safe_summary | BLK-006 定义这两个字段的取值集合与内容边界 | 字段已冻结，取值待 BLK-006 填 |
| DEC-004：empty/failed/Critic 无输出仍受控回复 | BLK-006 必须让 empty 与 failed 可判定 | 否则受控降级无输入 |
| DEC-005/006：identity/range | attestation 失败态用 BLK-006 的错误码表达 | 摄入失败也要安全可分类 |

---

## 10. 确认后怎么实施

### 10.1 RAG-C 必须在 spec 里落到可编码

| 待 RAG-C 定义 | 通过标准 |
|---|---|
| 在线 composition 入口的精确代码落点与校验逻辑 | 装配时 provider class + dialect 双校验，fail-fast 可测 |
| 五态判定逻辑（empty vs degraded vs failed 的边界） | 多 provider 部分失败 → degraded；全失败 → failed；无异常无数据 → empty |
| 错误码集合与安全摘要文案 | 枚举完整、文案不含敏感信息、可单元测试 |
| coordinator 异常传播改造 | 失败 provider 可观测、不再静默吞没 |

### 10.2 实施责任链

```text
RAG-C  定义 composition 校验、五态判定、错误码、安全摘要；改 coordinator 异常传播
RAG-B  摄入失败复用 BLK-006 错误码写 attestation
RAG-D  admission gate 据 backend 真实性 + outcome 状态判 baseline 准入
主控   复核 spec、错误码集合、跨窗口冲突
```

### 10.3 Happy-path 与失败路径验收

| 路径 | 必须验证 |
|---|---|
| Happy-path | 在线 composition 装配 PgVector+PG，正常检索返回 ok |
| fake 拦截 | 在线路径误配 fake → fail-fast，不进入检索 |
| SQLite 降级 | 非在线路径 SQLite 可用；在线路径 SQLite → fail-fast 或标记 degraded |
| 全失败 | 所有 provider 异常 → failed，payload 含错误码不含堆栈 |
| 部分失败 | 多 provider 一成一败 → degraded，sources_used 反映 |
| 非法请求 | 缺身份/无授权 → invalid-request，不调 provider |
| 安全摘要 | payload 全文不含 SQL/连接串/str(exc)，内部日志含完整异常 |

本轮三项决策确认后，BLK-006 仍保持 `blocked`，直到 spec、错误码、composition 实现、五态判定与上述测试全部满足。

---

## 11. R10 影响传播检查

确认 BLK-006 三项决策后，需同步检查的下游：

- [ ] `coordinator.py:111-117` 异常传播（D-006-3 要求改造）
- [ ] `coordinator.py:54-84` composition（D-006-1 要求加校验）
- [ ] `retriever.py:54-63` RetrievalFailed（D-006-3 要求去 str(exc)）
- [ ] `retriever.py:80-85` retrieval_status（D-006-2 要求扩五态）
- [ ] EvidenceProjection.retrieval_status 取值（DEC-003 字段 + BLK-006 取值）
- [ ] DEC-004 受控回复（依赖五态判定）
- [ ] Phase 2 C-10/C-11、Phase 3 C-15（执行顺序文档）
- [ ] attestation 失败态（DEC-002/005 关联）

---

## 12. 本页待确认

> ✅ **D-006-1、D-006-2、D-006-3 已由用户确认，并固化为 DEC-007/008/009**（见 `docs/rag-work/plans/2026-07-27-rag-p0-confirmed-decisions.md` §8-10）；主清单 BLK-006 章节、Phase 1C/2/3 Todo 与 RAG-C 回应已同步。

### 技术裁决

1. **D-006-1**：在线 composition 入口显式校验 PgVectorProvider + PostgreSQL，不满足 fail-fast；fake/SQLite 仅限非在线路径，禁止静默回退。
2. **D-006-2**：outcome 采用五态 `{ok, empty, degraded, failed, invalid-request}`；`low_score` 降为 ok 的质量子标记，不占独立状态位。
3. **D-006-3**：payload 只放分类错误码 + 安全摘要；原始异常/SQL/连接串/堆栈只进内部日志；`coordinator` 异常不再静默吞没。

确认后才会：

- 将 D-006-1/2/3 写入已确认决策记录和主清单；
- 同步修订 `docs/rag-work/specs/2026-07-24-online-rag-p0-repair-spec.md`（outcome/composition/failure 语义）；
- 再进入 BLK-007（baseline admission）。
