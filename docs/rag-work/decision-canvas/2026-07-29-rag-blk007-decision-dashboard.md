# RAG Foundation 决策画布 · BLK-007

> **本页目的**：先说明 BLK-007（baseline admission）在整体计划里解决什么，再下钻到两项技术选择。  
> **当前状态**：两项技术裁决（D-007-1/2）已由用户确认并固化（DEC-010/011）；本页是决策阅读视图的源，不是已确认事实源。  
> **正式事实源**：已确认决策写入 `2026-07-27-rag-p0-confirmed-decisions.md`；阶段状态与 blocker 写入 RAG Foundation 主清单。  
> **阅读建议**：只想判断方向，读第 0–1 节与第 8 节；要审实现合理性，再读第 2–7 节。

---

## 0. 三分钟决策摘要

### BLK-007 解决什么

```text
20 题黄金集已就绪 → 想跑"《西西弗神话》Retriever baseline"
但：
  · 被测后端可能是 fake/SQLite（不是真向量检索）
  · 被测索引可能没经过正式产品摄入（无 provenance）
  · 被测库里可能混着别的语料（跨书污染）
→ 跑出的分数不能称为"产品 baseline"
```

BLK-007 是 baseline 的**准入门禁**：不满足真实性条件就不许跑、不许报。它是"真实结果与评测"支柱的最后一道闸，也是 P0 blocker 的最后一个。

### 为什么现在决策

- DEC-005/006 已给产品 chunk 正式身份（顶层 `chunk_id` + range），**语料隔离从此可以用 `doc_id` 过滤实现**，不必只靠隔离 DB；
- DEC-007 已冻结 production 后端校验，gate 的 backend 三项检查可直接消费它的校验输出；
- DEC-002 的 attestation 是 gate 的摄入证明来源；
- RAG-D 已提交三项裁决请求（Freeze-D1/D2 + 措辞修订），等主控回复后才能继续实现 validator/gate/report。

### 当前只需判断两件事

| 待确认 | 推荐 | 为什么与上层目标有关 | 现在不决定的后果 |
|---|---|---|---|
| 准入 gate 最终版 | 主清单六项版（RAG-D 五项 + **corpus 隔离**） | 防止混源/假后端/无 provenance 索引被报成产品 baseline | RAG-D 无法实现 gate；baseline 永远 blocked 或冒险放行 |
| gold evidence 边界 | containment proxy 为第一轮口径；paragraph_id 只做审计 locator | 在正式 identity 生效前不越权冻结，又能诚实产出第一轮基线 | RAG-D 要么停滞，要么把 benchmark locator 升格成产品身份 |

> ⚠️ 同意这两项不等于 baseline 可以运行。真实运行还依赖 Phase 4（正式摄入 + attestation）与 RAG-D 工具实现（D-01~07）。

---

## 1. 上层建筑与 Phase 位置

BLK-007 属于"真实结果与评测"支柱，是 **Phase 5 的闸门**：

```text
Phase 2  C-09 visibility 过滤（为隔离过滤铺路）
   ↓
Phase 4  首本书正式摄入 + attestation（gate 的证明输入）
   ↓
Phase 5  ★ BLK-007 gate 全绿 → 20 题 baseline
   ↓
Phase 6  在线 grounded answer E2E
```

### 决策的下游传播

| 本轮决定 | Phase 1D 影响 | Phase 5 影响 | 对 BLK-013 影响 |
|---|---|---|---|
| gate 六项版 | D-03 按最终版实现 admission gate | 全绿才跑 20 题 | strict identity recall 的准入前提 |
| containment proxy | D-02 adapter 用完整 paragraph text 做 golden_chunks | 第一轮指标名义固定为 proxy | proxy→strict 的升级路径由 BLK-013 承接 |

---

## 2. 已核验事实

| 事实 | 证据 | 影响 |
|---|---|---|
| 主清单已裁决 BLK-007 方向（方案 A 严格准入），列六项运行前证明 | `docs/rag-work/plans/2026-07-24-rag-foundation-parallel-todolist.md:273-291` | 方向已定，本轮裁决具体 gate 版本 |
| RAG-D Freeze-D1 提交五项 gate，**缺 corpus 隔离项** | `docs/rag-work/status/RAG-D.md:204-214` | 与主清单六项存在差异，需裁决取舍 |
| RAG-D Freeze-D2 请求 containment proxy 临时规则 + 请求 3 措辞修订 | `docs/rag-work/status/RAG-D.md:216-230` | 待主控正式批准 |
| RAG-D report envelope 六状态（blocked×3 / infrastructure_inconclusive / completed_judge_degraded / completed） | `docs/rag-work/status/RAG-D.md:89-98` | run 级状态，与 DEC-008 检索级 outcome 互补 |
| 题集 20 题全部 `verified_v1`，corpus SHA 已记录 | `benchmarks/rag/books/the-myth-of-sisyphus/questions.v1.yaml:563-567` | gold 资产本身已就绪 |
| `paragraph_id` 是 gold 主定位；完整 paragraph text 是 canonical gold chunk | `benchmarks/rag/books/the-myth-of-sisyphus/annotation-guide.md:39-59,200-239` | proxy 口径的资产基础 |
| `evaluate()` 固定 `sources=None`，gate 必须约束 provider 集合 | `app/agents/retriever.py:123` | gate 第 4 项（vector-only）的由来 |
| baseline 未运行（README checklist 未勾选） | 主清单验证状态表（`baseline 已运行 | ❌ 未发现`） | 诚实状态：一切分数都还不存在 |

---

## 3. 决策一 D-007-1：准入 gate 最终版

### 为什么必须做这个选择

RAG-D 的 Freeze-D1 给了五项 gate，但主清单 BLK-007 明确要求第六项：**"使用仅含本书当前产物的隔离 DB，或存在已验证的 corpus/doc provenance 查询过滤"**。两者必须裁决统一，否则 gate 实现会漏项。

| | A：主清单六项版（推荐） | B：RAG-D 五项版 |
|---|---|---|
| 做法 | 五项机械检查 + corpus 隔离/过滤要求 | 仅五项机械检查 |
| 防住的污染 | fake 后端 + 无证明索引 + **跨书混源** | fake 后端 + 无证明索引 |
| 代价 | 需要隔离 DB 或 provenance 过滤 | 混入其他语料的召回会污染分数 |
| 与已确认决策 | 衔接 DEC-005/007（见下） | 遗漏主清单既定要求 |

**推荐裁决 D-007-1：选择 A，gate 最终版为六项。**

gate 六项与已确认决策的衔接：

| gate 项 | 证明来源 / 衔接 |
|---|---|
| 1. `rag_backend == "pgvector"` | DEC-007 composition 校验输出 |
| 2. provider class = `PgVectorProvider` | DEC-007 composition 校验输出 |
| 3. DB dialect = PostgreSQL | DEC-007 composition 校验输出 |
| 4. provider 集合严格 `{"vector"}` | `evaluate()` 固定 `sources=None`（`retriever.py:123`），必须显式约束 |
| 5. 正式 ingestion attestation（关联 EPUB SHA/版本/目标索引/块计数） | DEC-002 IngestResult / JSON attestation |
| 6. corpus 隔离：隔离 DB **或** 已验证的 provenance 查询过滤 | DEC-005 顶层 `chunk_id`/`doc_id` 生效后，过滤可随 Phase 2 C-09 的 visibility WHERE 一并实现 |

**选择原因**：五项版挡住"假后端/无证明"，但挡不住"真后端里混了别的书"——而混源正是 baseline 失真最隐蔽的来源。第六项的隔离成本也因 DEC-005/006 与 C-09 而显著降低（过滤条件可随可见性过滤同批实现），不再是沉重负担。

> ⚠️ R11 代价前提已核验：`pgvector_provider.search` 当前无 `doc_id`/visibility WHERE（`pgvector_provider.py:131-157` 仅按 distance 排序）；隔离过滤是**新增实现**，不是零改动，但它已在 Phase 2 C-09 的范围内。

---

## 4. 决策二 D-007-2：gold evidence 边界与 containment proxy

### 为什么必须做这个选择

正式产品 chunk identity（DEC-005/006）刚冻结边界、canonical bytes 尚未补证，严格 identity recall 现在做不了。但黄金集不能一直等——需要裁决第一轮的诚实口径。

| | A：containment proxy 临时口径（推荐） | B：等严格 identity 再跑 | C：paragraph_id 升格为 runtime identity |
|---|---|---|---|
| 做法 | 完整 paragraph text 做 golden_chunks，字符串包含比对 | 第一轮 baseline 推迟到 identity 全部落地 | benchmark locator 直接当产品 chunk 主键 |
| 收益 | 立即诚实产出第一轮基线 | 口径最严格 | 实现最省 |
| 代价 | proxy 有跨 chunk/改写误判，名义必须标 proxy | Phase 5 长期空转 | 违反 BLK-004 已冻结的"benchmark ID 不入产品身份" |
| 合规 | 符合已冻结边界 | 符合但代价大 | **违反 DEC-005 冻结边界** |

**推荐裁决 D-007-2：选择 A，批准 RAG-D Freeze-D2 全部四条 + 请求 3 措辞修订。**

1. `paragraph_id`、excerpt、source locator 仅在 benchmark audit 层使用；
2. 运行时 `golden_chunks` 采用完整 paragraph text；
3. 指标名称/报告必须称 **paragraph-containment proxy** 与 **gold-answer/context enrichment**，不称 strict evidence-id recall、不称 Tutor 质量；
4. 禁止 benchmark 创建或冻结 runtime evidence key；待正式 identity 落地后，由主控决定是否建版本化映射（BLK-013）。
5. 验收措辞同步修订：gold evidence "可映射项目实际 Chunk" 不作为 Freeze-D2 前的 happy-path 硬条件，改为"可由已验证 benchmark corpus 映射为完整文本，以 containment proxy 比对；严格 identity 映射待正式契约生效"。

**选择原因**：A 在不越权的前提下让 Phase 5 能诚实推进；B 让评测长期空转；C 直接违反已冻结边界。proxy 的局限通过强制命名与报告标注来诚实披露。

---

## 5. 已被现有裁决覆盖、无需重复裁决的 RAG-D 事项

以下事项 RAG-D 已给出方案，且与主清单/已确认决策一致，**本轮不列为待裁决项**，仅备案：

| 事项 | 已覆盖依据 |
|---|---|
| 每题单次执行（不双跑 evaluator） | 主清单 D-05 已冻结 |
| 报告固定命名 proxy / enrichment | 主清单 D-06 与 BLK-007 裁决已冻结 |
| report envelope 六状态 | RAG-D §5.3 自洽；与 DEC-008 检索级 outcome 互补（run 级 vs 单题检索级），不冲突 |
| RAGAS 只做 enrichment、第一轮主指标为机械召回代理 | 主清单 BLK-007 裁决已冻结 |
| baseline 结果不外推 Tutor 质量 | 主清单 BLK-007 裁决 + Phase 6 边界已冻结 |

---

## 6. 用产品需求反向判断本方案

| 你的上层需求 | 必须成立的技术保证 | BLK-007 如何支撑 | 不符合需求时怎么改 |
|---|---|---|---|
| baseline 分数代表真实产品检索能力 | 被测后端/索引/语料全部真实且单一来源 | D-007-1 六项 gate | 若接受代理分数，只能标 dev-proxy，不入正式结论 |
| 评测诚实、不夸大 | proxy 名义强制标注，不冒充 strict recall | D-007-2 命名与措辞修订 | 若去掉标注，等于允许误导 |
| benchmark 不越权造产品能力 | paragraph_id 不入 runtime identity | D-007-2 第 4 条 | C 方案违反已冻结边界，不可选 |
| P0 收口、进入实施 | 所有 P0 blocker 的裁决项清空 | BLK-007 是最后一个 P0 | 不裁决则 Phase 1D 的 gate 实现无依据 |

### 主控判断

BLK-007 确认后，**全部 P0 blocker（BLK-001~007）的裁决层面即清空**，剩余全部是"补证 + 编码 + 运行证据"层面的解除条件。这是从"决策阶段"转入"实施阶段"的临界点。

---

## 7. 确认后怎么实施

### 7.1 责任链

```text
RAG-D  实现 validator / adapter / gate / report（Phase 1D D-01~07）；gate 按六项最终版
A/B    提供 attestation 与正式索引（Phase 4）
C      visibility/provenance 过滤为隔离提供查询能力（Phase 2 C-09）
主控   gate 全绿后批准 Phase 5 运行；复核报告口径
```

### 7.2 Happy-path 与失败路径验收

| 路径 | 必须验证 |
|---|---|
| Happy-path | 六项 gate 全绿 → 20 题各一次 → 报告标 proxy/enrichment，含 backend/attestation 引用 |
| gate 拦截 | fake/SQLite/多源/无 attestation/混源 各自触发对应 `blocked:*` 状态，不执行 evaluate |
| proxy 诚实 | 报告不出现 strict recall / Tutor 质量字样 |
| 降级 | judge 不可用 → `completed_judge_degraded`，retrieval 指标仍完整 |

---

## 8. 本页待确认

> ✅ **D-007-1、D-007-2 已由用户确认，并固化为 DEC-010/011**（见 `docs/rag-work/plans/2026-07-27-rag-p0-confirmed-decisions.md` §11-12）；主清单 BLK-007 章节、D-03/D-08 Todo 与 RAG-D 回应已同步。**至此全部 P0 blocker（BLK-001~007）裁决层面清空，工作重心转入补证与实施。**

### 技术裁决

1. **D-007-1**：准入 gate 采用主清单六项版（RAG-D Freeze-D1 五项 + corpus 隔离/过滤）；隔离可走隔离 DB 或 DEC-005 生效后的 `doc_id` provenance 过滤。
2. **D-007-2**：批准 RAG-D Freeze-D2 四条临时规则与请求 3 措辞修订；第一轮口径为 paragraph-containment proxy + gold-answer/context enrichment；严格 identity 映射归 BLK-013。

确认后才会：

- 将 D-007-1/2 写入已确认决策记录（DEC-010/011）和主清单 BLK-007 章节；
- 回复 RAG-D 窗口三项请求；
- **P0 裁决层面全部清空**，工作重心转入补证与实施（Phase 1A/1B/1C/1D 并行推进）。
