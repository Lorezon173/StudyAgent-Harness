# RAG-D 状态：黄金集与评测接线

> 唯一写者：窗口 D  
> 主清单：[`../designs/2026-07-24-rag-foundation-parallel-todolist.md`](../designs/2026-07-24-rag-foundation-parallel-todolist.md)（**只读；未修改**）  
> 更新日期：2026-07-24  
> 当前状态：🟡 已完成现状、题集映射、敌对审阅与决策分层；RAG-D 实施被共享前置条件阻断，等待主控裁决后接续。

## 1. 当前结论

RAG-D 的黄金集定位为：**对已由项目正式主链摄入、且已部署的《西西弗神话》索引执行 Retriever 部件基线验证**；它不是 EPUB 摄入器、chunker、索引器、检索器，也不证明在线 Tutor 已消费书籍证据。

当前已有可复用资产：20 题 `questions.v1.yaml`、本地 corpus/manifest、`RetrieverAgent.evaluate()` 与 `ComponentBench`。第一轮应以现有 `RetrieverAgent.evaluate()` 的机械召回指标为主，RAGAS judge 结果仅作为可选 enrichment；不新增 evaluator。

在 RAG-B 冻结正式 Chunk/metadata 契约、RAG-A 提供可审计的正式摄入证明、并由主控裁决真实后端准入规则前，RAG-D **不得**输出“该书产品 RAG 基线已完成”的结论；最多输出 `blocked` 或资产校验结论。

**当前完成边界**：已完成 evaluator/benchmark、coordinator/pgvector、EPUB/chunking、Tutor evidence path 四路源码/资产核验，以及 20 题到现有 evaluator 的映射设计和敌对审阅；**尚未**在“已正式摄入该书、单一 vector provider、真实 PostgreSQL/pgvector”的环境运行首轮 20 题，尚未生成任何可宣称的产品 RAG baseline 分数。

## 2. 已核实事实

| 事实 | 位置 | 验证方式 | 路径归属 |
|---|---|---|---|
| `Chunk` 仅有 `content`、`score`、`source`、`metadata`；无稳定 chunk/doc 身份字段。 | `app/infrastructure/rag/coordinator.py:7-21` | 源码与调用链核验 | 检索数据模型 |
| `RAGCoordinator.search()` 聚合被选 provider；`sources=None` 时查询全部 provider；按完整 `content` 去重后按 score 截断。provider 异常被吞没。 | `app/infrastructure/rag/coordinator.py:100-131` | 源码核验 | 在线/评测共享检索主链 |
| `PgVectorProvider.index()` 接收已形成的 docs，写入顶层 `content`、`metadata`、`doc_id`、`source`、`scope`、`user_id`；自身不切块、不生成身份。 | `app/infrastructure/rag/pgvector_provider.py:60-109` | 源码核验 | 正式向量写入主链 |
| PostgreSQL search 虽读取 `doc_id`，但构造返回 `Chunk` 时没有携带它；SQLite 分支仅字符重叠降级。 | `app/infrastructure/rag/pgvector_provider.py:111-180` | 源码核验 | 检索后端 |
| `RetrieverAgent.evaluate()` 只读取 `query`、`golden_chunks`、`golden_answer`、`top_k`，直调 `coordinator.search(..., sources=None, ...)`；不经过事件总线或 `handle()`。 | `app/agents/retriever.py:105-124` | 源码与 ComponentBench 调用链核验 | 离线部件评测旁路 |
| `evaluate()` 以双向子串包含计算 `recall_at_k`/启发式 precision；无 `golden_answer` 时降级并返回 judge 指标 0.0。 | `app/agents/retriever.py:129-181` | 源码核验 | 离线部件评测旁路 |
| RAGAS 路径将人工 `golden_answer` 同时写入 `response` 与 `reference`，不生成 Tutor 答案；因此 judge 分数不代表在线 Tutor 回答质量。 | `app/agents/retriever.py:209-240` | 源码核验 | 离线部件评测旁路 |
| `ComponentBench` 将 `TestCase.input` 原样交给 `.evaluate()`；数值 expected 仅表达下限，空 expected 自动通过，且不传播 `TestCase.meta` 到 `EvalResult.meta`。 | `app/eval/component_bench.py:10-47` | 源码核验 | 通用离线评测框架 |
| 现有《西西弗神话》题集已有 20 题、`gold_answer`、`gold_evidence`、来源定位与版本信息。 | `benchmarks/rag/books/the-myth-of-sisyphus/questions.v1.yaml:1-567` | 题集原文核验 | benchmark 标注资产 |
| 标注指南规定：`paragraph_id` 用于在本地 corpus 定位；完整 paragraph text 才是 canonical gold chunk，excerpt 仅用于人工审计；并已给出题集到 `evaluate` 的映射建议。 | `benchmarks/rag/books/the-myth-of-sisyphus/annotation-guide.md:200-256` | 文档与 evaluator 输入契约交叉核验 | benchmark 标注资产 |
| EPUB 抽取和 paragraph corpus 构建目前只在 benchmark 辅助脚本中存在；产品侧尚无 EPUB→正式 chunks→`index_documents()` 的可见调用链。 | `benchmarks/rag/books/the-myth-of-sisyphus/extract_epub.py:110-137`; `app/infrastructure/rag/coordinator.py:135-139` | 源码/调用点穷举 | benchmark 辅助链 vs 产品主链 |
| 在线 Tutor 不接收 `RetrievedEvidence.chunks`，也不把证据注入其 prompt；当前在线检索结果最多经 Critic 压缩为 RAG 质量观察。 | `app/agents/tutor.py:32-97`; `app/agents/critic.py:33-40`; `app/harness/orchestrator.py`；`app/orchestration/assembly.py:144-154` | 事件链与 prompt 输入核验 | 在线协作链 |

## 3. 不确定项 / 阻断项

### 3.0 当前进展补充

| 进展项 | 当前判断 | 依据 / 证据 | 下一步拟解法 | 原因 |
|---|---|---|---|---|
| 现状核验已完成 | 已完成四路核验：`RetrieverAgent.evaluate` / `ComponentBench`、`RAGCoordinator` / `PgVectorProvider`、西西弗 benchmark 资产、在线 Tutor 证据路径。 | 见本文件 §2 全部事实表；尤其 `app/agents/retriever.py:105-240`、`app/infrastructure/rag/coordinator.py:100-139`、`app/infrastructure/rag/pgvector_provider.py:60-180`、`benchmarks/rag/books/the-myth-of-sisyphus/questions.v1.yaml:1-567`、`app/agents/tutor.py:32-97`。 | 不再重复做现状探索；后续实现仅围绕 adapter / gate / report。 | 事实面已足够支撑 RAG-D 的边界判断，继续探索收益低于推进阻断裁决。 |
| 题集到 evaluator 的映射已收敛 | 已确认 `question -> query`、完整 paragraph text -> `golden_chunks`、`gold_answer -> golden_answer`、`top_k=5` 的单向映射；当前只适合作为 paragraph-containment proxy。 | `benchmarks/rag/books/the-myth-of-sisyphus/annotation-guide.md:200-241`; `app/agents/retriever.py:116-149`。 | 等主控裁决 Freeze-D2 后，把该映射固化进只读 adapter。 | 这是现有契约下唯一诚实、可逆、且不越权冻结产品 identity 的映射。 |
| 决策优先级已完成分层 | 已形成“RAG 基线准入与证据边界包（RAG-BE 包）”的分析：现在先冻结 admission gate、GoldEvidence 边界、baseline/judge 分层、报告状态分类、Tutor 结论边界；identity recall 等推迟。 | 本窗口已完成的决策分层工作流结论；其依据已回落到本文件 §2、§3、§5、§10。 | 如主控认可，可在主清单引用“RAG-BE 包”作为共享决策包名；RAG-D 自身不擅自新增主文档。 | 这些建议已超出单点黄金集实现，属于并行窗口共享边界，需用统一名字便于引用。 |
| 敌对审阅已发现额外约束 | 已确认 admission gate 必须约束“被测评测实例的 provider 集合”，而不是全局产品永久禁多源；也确认每题只能执行一次 evaluator。 | `app/agents/retriever.py:121-124`; `app/infrastructure/rag/coordinator.py:100-117`; `app/infrastructure/rag/code_index.py:15-27`; `app/infrastructure/rag/ocr.py:11-23`。 | 在 RAG-D 实现时把这些约束落实到 runner/gate；在主控裁决前仅记录，不修改产品主链。 | 这样既能保证 baseline 真实，又不会越权阻塞 RAG-C 将来做多源在线能力。 |

| 不确定项 / 阻断项 | 原因 | 判断依据 / 证据 | 拟做的解决方案 | 为什么这样解 | 是否阻断 |
|---|---|---|---|---|---|
| 正式 Chunk/metadata/身份契约 | 当前 `Chunk` 无稳定 ID；`doc_id` 写入后未回传；paragraph_id 不能越权成为 runtime key。 | `app/infrastructure/rag/coordinator.py:7-21`; `app/infrastructure/rag/pgvector_provider.py:137-156`。 | 由 RAG-B 提案、主控冻结；RAG-D 现阶段仅用完整 paragraph text 做 containment proxy，并请求 Freeze-D2。 | 先用 proxy 能跑通现有 evaluator，且不提前污染产品 identity 契约。 | 是：阻断“严格 identity recall”与永久 evidence 映射；不阻断 containment-proxy 设计。 |
| 《西西弗神话》是否已通过 RAG-A 正式摄入到被测产品索引 | 当前无可见产品 EPUB ingestion 调用链，也无 per-corpus provenance 查询契约。 | `benchmarks/rag/books/the-myth-of-sisyphus/extract_epub.py:110-137`; `app/infrastructure/rag/coordinator.py:135-139`。 | 由 RAG-A 提供正式摄入输出与可审计证明；RAG-D 仅在 runner 中要求并记录该证明，缺失即 `blocked:unattested_product_index`。 | 现阶段 benchmark 无法凭自身 SHA/题集内容证明被测索引来源，必须把 provenance 作为外部前置条件。 | 是：阻断“该书真实产品索引 baseline”运行。 |
| 真实向量检索准入 | 配置为 `pgvector` 仍可能落到 SQLite 字符匹配；`evaluate` 固定 `sources=None`，多 provider 可混入 OCR/code FakeRAGStore 结果。 | `app/infrastructure/rag/coordinator.py:54-84,100-117`; `app/infrastructure/rag/pgvector_provider.py:159-180`; `app/agents/retriever.py:121-124`。 | 主控冻结 Freeze-D1；RAG-D 实现时在“被测评测实例”上检查 backend/provider/dialect/provider 集合，不把该 gate 上升为全局产品禁令。 | 这样既防止假 baseline，又不越权限制未来在线多源产品能力。 | 是。 |
| Judge 可用性 | RAGAS/datasets/judge/API 凭据缺失会使 evaluate 降级，且当前 judge 不代表 Tutor 回答质量。 | `app/agents/retriever.py:169-240`; `app/eval/judge.py:17-81`。 | 第一轮 baseline 以 retrieval metrics 为主；judge 仅作 enrichment，不可用则标 `completed_judge_degraded`。 | 把 judge 降级与检索失败分开，能保证第一轮 baseline 仍然诚实可用。 | 否：只阻断 judge enrichment，不阻断 retrieval baseline。 |
| 在线 Tutor 证据消费 | Tutor 当前不接收 `RetrievedEvidence.chunks`，因此无法把 RAG-D 结果外推为在线 grounded answer。 | `app/agents/tutor.py:32-97`; `app/agents/critic.py:33-40`; `app/orchestration/assembly.py:144-154`。 | 由 RAG-C 完成在线证据注入后，再新增系统级验证任务；RAG-D 当前报告中显式限定结论只覆盖 Retriever baseline。 | 这是职责边界问题，不应靠离线 benchmark 伪造在线验证。 | 否：阻断在线 Tutor 结论，不阻断 Retriever baseline。 |
| ComponentBench `passed` 语义可能误导 | 空 expected 自动通过，且 `meta` 不传播；若直接看 pass/fail 可能误读为质量 gate。 | `app/eval/component_bench.py:29-46`。 | RAG-D 外层 report envelope 单独记录 run status 与 raw metrics；若沿用 ComponentBench，只把 `passed` 解释为 execution contract，而非 quality pass。 | 避免把基础设施/降级/空阈值状态误说成检索质量通过。 | 否：不阻断运行，但阻断结果口径。 |

## 4. 拟修改资产

> 下表是 **RAG-D 拟实施资产**，尚未写入或修改。不会修改主清单、RAG-A/B/C 状态片段，也不会改写 RAG 主链实现以绕过共享契约。

| 文件/资产 | 当前职责 | 拟改动 | 三色 | 与谁共享 |
|---|---|---|---|---|
| `benchmarks/rag/books/the-myth-of-sisyphus/` 下的 RAG-D adapter/runner（具体文件名待实施前确定） | 当前只有题集、manifest、标注规范，无自动运行入口。 | 新增只读 asset validator、题集→瞬态 `TestCase` 转换、单次评测运行与报告 envelope。不得抽取/切分/索引/检索。 | 🔴 | RAG-A/B/C、主控 |
| `tests/...` 的 RAG-D 测试文件（具体路径待实施前确定） | 无自动题集到 evaluator 的覆盖。 | 增加 asset/映射/admission/降级/报告测试。 | 🔴 | 主控 |
| `app/agents/retriever.py` | 现有唯一 Retriever evaluator。 | **保持不改**；RAG-D 仅消费其公开 dict 输入/输出。 | 🟢 | 主控 |
| `app/eval/component_bench.py` | 通用 TestCase 运行器。 | 第一轮保持不改；外层 report envelope 承担 provenance 与状态，避免假设 meta 传播。 | 🟢 | 主控 |
| `docs/rag-foundation-status/RAG-D.md` | RAG-D 进度、契约请求和阻断记录。 | 本次已更新。 | 🟡 | 主控 |

## 5. 输入/输出契约

### 5.1 字段分层

| 层 | 现在可填 | 必须等待共享契约后再填 | 约束 |
|---|---|---|---|
| 来源 / provenance | `book_key`、manifest/corpus SHA、题集版本、资产路径 | 产品 ingestion run/ref 的机器可验证关联 | SHA 只能证明 gold 资产一致，不能单独证明被测索引来源。 |
| 标注 / audit | `id`、level、question、status、gold_answer、`gold_evidence[{paragraph_id, excerpt}]`、source_locator、verification_note | `runtime_chunk_id`、`product_chunk_locator`、`retrieved_doc_id` | paragraph_id 仅作离线审计 locator。 |
| 瞬态 evaluate 输入 | `query`、`golden_chunks`、`golden_answer`、`top_k` | N/A | 运行内存构造，调用后丢弃；不得写向量库。 |
| 结果 envelope | case id、原始 metrics、degraded 状态、backend gate、asset SHA、时间戳 | 产品正式 provenance 字段 | 不依赖 `EvalResult.meta`，因为当前 bench 不传播它。 |

### 5.2 题集到现有 evaluator 的单向映射

| 标注字段 | 瞬态 `TestCase.input` | 消费者 | 语义 |
|---|---|---|---|
| `question` | `query` | `RetrieverAgent.evaluate()` | 检索 query |
| `gold_evidence[].paragraph_id` | 查本地 corpus 后取得完整 paragraph text，组成 `golden_chunks` | `RetrieverAgent.evaluate()` | 当前 paragraph-containment proxy 的目标文本 |
| `gold_answer` | `golden_answer` | `RetrieverAgent.evaluate()` / 可选 RAGAS | 人工参考答案；不是 Tutor 生成答案 |
| 固定基线配置 | `top_k=5` | `RAGCoordinator.search()` | 首轮统一检索深度 |

**禁止映射**：`paragraph_id`、本地 hash、excerpt、DB row id、未冻结的 `(doc_id, chunk_idx)` 不能成为 `Chunk` runtime identity 或检索 pass/fail 主键。

### 5.3 运行输出状态

| 状态 | 含义 | 是否执行 `evaluate()` |
|---|---|---|
| `blocked:asset_invalid` | 题集/corpus/SHA/locator/excerpt 校验失败 | 否 |
| `blocked:not_real_pgvector` | 配置、provider、dialect 或多源隔离未满足 | 否 |
| `blocked:unattested_product_index` | 无法提供已正式摄入该书的外部可审计证明 | 否 |
| `infrastructure_inconclusive` | 已运行但健康检查或 evaluator 执行出现基础设施异常 | 视异常阶段 |
| `completed_judge_degraded` | retrieval metrics 已完成，judge 不可用/降级 | 是，一次 |
| `completed` | retrieval 与可选 judge 结果完成 | 是，一次 |

## 6. 方案对照与选择理由

### 6.1 黄金集角色

| | 选择：只读验证 adapter | 备选：benchmark 自建 paragraph corpus/index/search |
|---|---|---|
| 做法 | 读取现有题集/corpus；调用真实项目 `RetrieverAgent.evaluate()`。 | 由 benchmark 抽 EPUB、切 paragraph、写库、向量检索。 |
| 收益 | 评测对象是项目 RAG；不重复主链能力。 | 可在产品缺失时快速得到看似完整的分数。 |
| 代价 | 产品 ingestion 未就绪时必须 blocked。 | 测到的是 benchmark 私有 RAG，违反任务边界。 |

**选择理由**：黄金集只能是项目 RAG 的验证器；产品链缺口必须暴露给 RAG-A/B，而不能由 RAG-D 补造。

### 6.2 evidence 表达

| | 选择：完整 paragraph text 作为临时 `golden_chunks` | 备选：先冻结 paragraph_id/doc_id 为 runtime evidence key |
|---|---|---|
| 做法 | 依现有 annotation guide 与 evaluate 的字符串包含规则运行。 | 把 benchmark locator 升格为产品身份契约。 |
| 收益 | 立即兼容现有 evaluator，且不修改主链。 | 理论上支持精确 identity recall。 |
| 代价 | 仅为 paragraph-containment proxy；跨 chunk/改写可能误判。 | 当前 `Chunk`/search 未回传稳定身份，属于越权冻结。 |

**选择理由**：在 RAG-B 冻结前保留 containment proxy，并在报告显式标注其限制。

### 6.3 执行路径

| | 选择：每题一次 `ComponentBench.run()` **或**一次直接 `evaluate()`（二选一） | 备选：先直接 evaluate，再交 ComponentBench 重跑 |
|---|---|---|
| 做法 | 单次检索、单次 judge、单份 metrics。 | 同一题进行两次独立检索/judge。 |
| 收益 | 可复现，latency/结果有唯一来源。 | 同时拿 raw 和 bench 输出。 |
| 代价 | 需要外层从单次结果生成 report envelope。 | 索引/judge 状态变化会令两份结果不一致。 |

**选择理由**：外层可做展示与状态分类，但不得让单题被评测两次。

### 6.4 第一轮指标角色

| | 选择：retrieval baseline 为主，judge enrichment 可选 | 备选：RAGAS 作为首轮质量 gate |
|---|---|---|
| 做法 | 主看 `recall_at_k`、启发式 precision、latency、redundancy、degraded。 | 以 faithfulness/answer relevancy 阈值决定首轮通过。 |
| 收益 | judge 依赖缺失时仍能验证真实召回。 | 语义分数表面更完整。 |
| 代价 | 不能把首轮说成端到端回答质量。 | 混淆 judge 可用性与检索质量；且当前 answer 是人工 gold。 |

**选择理由**：第一轮目标是校准 Retriever，不是验证 Tutor 生成。

## 7. 影响传播

| 影响面 | 结论 / 待同步检查 |
|---|---|
| 上游 RAG-A | RAG-D 需要其提供正式 EPUB ingestion 的完成状态及可审计 product-index 证明；不从 benchmark 旁路补入库。 |
| 上游 RAG-B | RAG-D 等待其冻结 chunk/metadata/identity 契约；冻结后再评估从 containment proxy 升级到 identity recall 的可能性。 |
| 上游 RAG-C | 当前在线 Tutor 不消费证据，因此 RAG-D 基线不能作为 Tutor 验收；RAG-C 接通后须新增 online evidence consumption 的系统测试。 |
| RAG 主链 | 保持 `EmbeddingService → PgVectorProvider → RAGCoordinator → RetrieverAgent → RetrieverAgent.evaluate`；不得新增并行检索链。 |
| 数据库 | RAG-D 不写 `vector_chunks`；现有无 doc_id 回传、无 per-corpus provenance/过滤问题由主控分配给对应产品任务裁决。 |
| 离线评测 | 复用 `RetrieverAgent.evaluate`；ComponentBench 的 `passed` 不得被解释为质量通过，尤其在 empty expected 或降级情况下。 |
| 文档 | 本状态片段是唯一已改文档；主清单和根 README 未改。实施后再判断 README 是否需更新。 |

## 8. 验证状态表

| 声称 / API / 签名 | 状态 | 依据 |
|---|---|---|
| `RetrieverAgent.evaluate(test_case: dict) -> dict` 读取四键 | ✅ 源码核验 | `app/agents/retriever.py:105-124` |
| `ComponentBench.run()` 原样传 `TestCase.input` | ✅ 源码核验 | `app/eval/component_bench.py:10-47` |
| 真实 PostgreSQL pgvector 的近邻查询路径存在 | ✅ 源码核验；⏳ 未在本会话连真实库运行 | `app/infrastructure/rag/pgvector_provider.py:131-157` |
| SQLite pgvector 分支不是语义向量检索 | ✅ 源码核验 | `app/infrastructure/rag/pgvector_provider.py:159-180` |
| `evaluate()` 会查询全部已注册 provider | ✅ 源码核验 | `app/agents/retriever.py:121-124`; `app/infrastructure/rag/coordinator.py:100-117` |
| 20 题题集与标注映射资产存在 | ✅ 资产原文核验 | `benchmarks/rag/books/the-myth-of-sisyphus/questions.v1.yaml:1-567`; `annotation-guide.md:200-256` |
| 正式 EPUB ingestion 已打通 | ❌ 未发现 | `app/infrastructure/rag/coordinator.py:135-139` 仅接收已切 docs；待 RAG-A |
| 产品 Chunk/metadata/identity 契约已冻结 | ⏳ 待主控裁决 | 依赖 RAG-B |
| 当前在线 Tutor 消费证据原文 | ❌ 源码反证 | `app/agents/tutor.py:32-97`; `app/agents/critic.py:33-40` |
| 真实单源 PostgreSQL 环境可运行 20 题 | ⏳ 待外部产品索引与环境证明 | 需要 RAG-A/主控准备，RAG-D 不自建 |

## 9. 测试矩阵

### 9.1 实施前 / adapter 单元测试

| 场景 | 输入 | 预期 |
|---|---|---|
| 题集合法映射 | 已验证题、存在 paragraph、excerpt 为子串 | 生成四键瞬态 evaluate input；不调用 index/search。 |
| 未知 `paragraph_id` | evidence locator 缺失 | `blocked:asset_invalid`，带 case id/locator。 |
| excerpt 不匹配 | excerpt 非连续子串 | `blocked:asset_invalid`，不得静默跳过。 |
| 缺 `gold_answer` / evidence | 不完整题目 | 拒绝进入 judge/评测输入。 |
| status 不允许 | 候选或未核验题 | 不进入 verified baseline。 |
| corpus / manifest SHA 不符 | 资产漂移 | `blocked:asset_invalid`。 |
| 同 paragraph 多 evidence | 多 locator 指向同一段 | 报告 evidence_count 与 unique_paragraph_count；明确 `golden_chunks` 去重策略。 |

### 9.2 admission / 降级测试

| 场景 | 预期 |
|---|---|
| `rag_backend != 'pgvector'` | `blocked:not_real_pgvector`，不得退回 FakeRAGStore。 |
| vector provider 非 `PgVectorProvider` | `blocked:not_real_pgvector`。 |
| DB dialect 非 PostgreSQL | `blocked:not_real_pgvector`，不得用 SQLite 字符匹配。 |
| provider 集合不等于 `{'vector'}` | `blocked:not_real_pgvector`，防止 evaluate 的 `sources=None` 混源。 |
| 无产品索引 provenance 证明 | `blocked:unattested_product_index`。 |
| judge 不可用 | `completed_judge_degraded`；保留 retrieval metrics，不把 0.0 误判为召回失败。 |
| provider/基础设施异常 | `infrastructure_inconclusive`；报告异常摘要，不把静默空结果直接算质量失败。 |

### 9.3 happy-path（依赖 RAG-A/B/主控解锁）

- [ ] 至少一题完整经过 **正式产品 ingestion 产物 → `EmbeddingService` → `PgVectorProvider`（PostgreSQL）→ `RAGCoordinator` → `RetrieverAgent.evaluate`**。
- [ ] 20 题在单一 vector provider、真实 PostgreSQL 后端与已证明产品索引上各执行一次。
- [ ] 报告逐题保留 `recall_at_k`、context precision proxy、latency、redundancy、sources_used、degraded 状态。
- [ ] 明确标记 recall 为 paragraph-containment proxy；不宣称 strict identity recall。

## 10. 请求主控冻结 / 修订

### 请求 1：Freeze-D1 — RAG-D 真实检索准入 gate（请求主控裁决）

请主控在 RAG-A/B/C 状态片段合并后裁决以下运行前置条件：

1. `settings.rag_backend == 'pgvector'`；
2. 被测 coordinator 的 vector provider 为 `PgVectorProvider`；
3. 实际 DB dialect 为 PostgreSQL；
4. provider 集合严格为 `{'vector'}`，因为现有 `evaluate()` 固定 `sources=None`；
5. 调用方提供“该书已通过正式产品 ingestion 写入被测索引”的外部可审计证明；RAG-D 只记录，不伪造机器证明。

**请求理由**：否则 SQLite/FakeRAGStore、多 provider 混源或无 provenance 的索引可能被错误报告为“真实《西西弗神话》RAG 基线”。

### 请求 2：Freeze-D2 — GoldEvidence 与产品 Chunk 的边界（请求主控裁决）

在 RAG-B 冻结前，批准 RAG-D 临时规则：

- `paragraph_id`、excerpt、source locator 仅在 benchmark audit 层使用；
- 运行时 `golden_chunks` 采用完整 paragraph text；
- 指标名称/报告必须称为 **paragraph-containment proxy**，不称 strict evidence-id recall；
- 禁止 benchmark 创建或冻结 runtime evidence key；
- 待 RAG-B 正式 Chunk identity 契约冻结后，由主控决定是否新建版本化映射与是否保留/迁移该 proxy。

### 请求 3：修订现有 RAG-D 验收措辞

原模板中的“gold evidence 可映射项目实际 Chunk”不应在 Freeze-D2 前作为 happy-path 硬条件；应改为：

> gold evidence 可由已验证的 benchmark corpus 映射为完整文本，并由项目现有 evaluator 以 containment proxy 比对；严格项目 Chunk identity 映射待 RAG-B 冻结。

## 11. 未做事项

- [ ] 等主控裁决 Freeze-D1/D2，并同步 RAG-A/B/C 的共享契约状态。
- [ ] 在 RAG-A 提供正式产品 ingestion/index 证明后，确认其可审计字段与 RAG-D report envelope 的边界。
- [ ] 在 RAG-B 冻结后，决定是否需要版本化 `GoldEvidence → product Chunk` 映射；本窗口不自行冻结。
- [ ] 选择并实现唯一一次执行路径：`ComponentBench.run()` 或直接 `RetrieverAgent.evaluate()`，不得二次评测同题。
- [ ] 实现只读 asset validator、瞬态 TestCase adapter、admission gate、report envelope 与测试。
- [ ] 在合格 PostgreSQL 单源环境上跑首轮 20 题，并人工复核零召回/高冗余 case。
- [ ] RAG-C 完成后，另立在线 Tutor evidence consumption 系统验证；不得把本任务结果外推为 Tutor 质量。
