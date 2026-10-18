# 子代理审阅结论的针对性核验

日期：2026-10-13。范围：对 `2026-10-13-plan-review.md` 的五类建议核对冻结决策、spec、代码及定向复现。遵循 systematic-debugging / karpathy-guidelines；未修改生产代码、既有 spec 或原规划。

## 验证方式与边界

- 现有定向测试：`.venv/Scripts/python.exe -m pytest tests/eval/test_rag_d.py tests/unit/infrastructure/test_pgvector_provider.py tests/unit/infrastructure/test_embedding.py tests/unit/harness/test_knowledge_ingestion.py tests/unit/agents/test_retriever.py -q -p no:cacheprovider`。
- 正常临时目录重跑结果：**99 passed, 1 skipped, 1 deselected**。首次沙箱临时目录不可写导致 16 个 setup error，不能算代码失败；获准重跑后通过。
- 新的针对性检查用内存 SQLite、受控 embedding/provider、内存 log capture 和替换后的输入资产运行现有函数；不调用外部服务，不生成业务索引，不保存新的测试代码文件。
- 真实 PostgreSQL、真实 embedding、真实本书 baseline 本轮未执行；SQLite 或替身不能证明 PG 验收完成。

## 1. 多 k 指标：审阅正确，属于未实现能力

代码依据：`app/agents/retriever.py:219` 单次搜索；`:225-231` 计算整个返回集合的 recall；各返回分支只有 recall_at_k。`rag_d.py:219` 每题一次 evaluate。

复现：相关片段分别排第 1 和第 5，两个场景均只搜索一次，现有输出均为 recall_at_k=1.0，且只含这一个 recall 字段。实际 Recall@1 应分别为 1 和 0，因此现有聚合输出无法还原多 k。

结论：D-10 应明确新增单次 top-5 结果前缀派生 Recall@1/3/5 的向后兼容任务，而不是继续写成“核对是否支持”。这是满足计划指标的能力缺口，不是当前单个 recall_at_k 计算本身出错。

## 2. corpus 隔离：审阅风险成立，但独立双库是建议方案

DEC-010 要求纯本书当前产物隔离 DB，或已验证 provenance 查询过滤。`rag_d.py:188` 仅接受 mode 和 verified 声明，并不查询库内实际产物。`PgVectorProvider.search:132` 的参数没有 doc_id/corpus 过滤，PG WHERE 只有权限条件；evaluate 固定 sources=None，未传 corpus 过滤。

复现：仅提供 `mode=provenance_filter, verified=True` 即可通过 gate，没有执行过滤真实性检查。此复现说明 gate 依赖外部证明，不能证明已发生实际数据污染，也不是任意外部用户可利用的线上授权漏洞。

修正审阅措辞：独立权限测试库与纯本书基线库是当前最直接的实施选择，不是 DEC 强制要求必须两库；若选择其他策略，必须给出受验证的过滤或重新隔离证明。当前不能把 visibility 过滤当 corpus 过滤，也不能仅凭 verified=true 宣称隔离成立。

## 3. attestation：审阅正确，且 gate 校验比成功证明要求更弱

DEC-002 §3.4 要求版本化 JSON、run ID、输入 SHA/格式、doc ID、版本、planned/written 数量、backend/dialect、scope/owner、安全码和摘要。具体版本字段名、run ID 生成法尚需设计确认，不能假称已经冻结字段名。

`KnowledgeIngestionService.IngestResult:16` 只提供 status、doc_id、planned/written count、warnings；`app/` 和 `scripts/` 未找到正式 attestation 生成 runner。`rag_d.py:30` 必需字段清单不含版本、安全码/摘要或目标索引绑定字段；`:180-186` 主要检查键存在、部分值和计数相等。

复现：空 ingestion_run_id、空 normalizer/chunking 版本、planned=written=None、scope=private/owner=None 的证明仍可通过 gate（其他必需条件使用受控有效输入）。

结论：需分别补 runner/证明契约和消费者验证设计。不能把“字段都出现了”作为完整成功证明；该问题当前只在受控评测工具核验层确认，不外推成在线鉴权缺陷。

## 4. 原子性与写入计数：审阅需要细分

### 已实现并验证的部分

`PgVectorProvider.index:126-129` 明确 commit/异常 rollback。内存 SQLite 制造第二行 NOT NULL 约束失败：抛出 IntegrityError，第一行也回滚，最终本轮残留 0 行。

因此不能写成“回滚未实现”或“已有部分提交缺陷”；子代理把它列为真实环境验收补项是合理的。PG 中途失败后无残留仍未实测，DEC-002 已冻结该要求，必须纳入 Phase 4 验收。

### 条件性代码缺陷：短 embedding 列表造成虚假写入确认

`PgVectorProvider.index:93` 用 zip(docs, embeddings)，`:130` 无条件返回 len(docs)。受控 embedding 对两文档返回一个向量：实际插入 1 行，provider 确认 2。通过真实 KnowledgeIngestionService 调用同一路径，结果为 status=ok、planned=2、written=2，实际只有 1 行。

触发边界：provider 支持注入 embedding_service，该接口层未保护数量一致性；默认 `EmbeddingService.embed_many:96` 在 API 返回数量不足时会先抛 IndexError，发生在写库之前。因此已证明接口防御和实际写入确认缺陷，未证明默认线上服务响应不足会造成同样的部分提交。

建议作为正式摄入前的修复候选：明确数量/维度契约、不允许短结果静默截断、确认真正写入数；先补模块规划和回归用例，再编码。

## 5. 内部审计与日志关联：审阅正确，缺口已确认

代码依据：provider SQL 直接排除歧义行，没有 logger 或审计调用；Coordinator 在 `:195` 记录 provider 名与异常，不带 retrieval_id/trace_id；Retriever 的异常日志也没有关联字段。现有 observability 模块有结构化 log 接口，但上述 RAG 调用链未使用它传递关联信息。

复现一：写入一条公共规范行及 global+owner/未知 scope 行，受限检索只返回规范行，日志记录数为 0。说明权限过滤有效，但歧义行审计缺失。

复现二：受限请求带 retrieval_id=probe-retrieval，provider 抛受控异常；失败事件保留 ID 和 db_error，内部日志仅 `RAG provider 'vector' search failed`，LogRecord 的 retrieval_id/trace_id 都为空。

结论：不是所有日志都没实现，也不是权限隔离失效；缺失的是 spec §D/§G/§I 已要求的歧义行审计及内部异常关联。应列为明确验收缺口，与可选错误枚举重构分开。

## 6. 额外发现：评测丢失检索失败状态（优先处理）

这是原子代理审阅未指出的问题，直接影响正式 baseline 可信性。

根因：Coordinator.search 捕获 provider 异常后返回 SearchResult(outcome=failed, error_code=db_error)；RetrieverAgent.evaluate 只使用 chunks，不向指标输出传递 outcome、error_code、sources_used、失败来源。runner 仅在 evaluate 抛异常时标 infrastructure_inconclusive，否则根据 metrics.degraded 决定 completed/completed_judge_degraded。

两层复现：

1. 直接输入 failed SearchResult：输出 recall=0，不含 outcome、error_code、sources_used。
2. 完整 runner 受控验证：20 题全部使 provider 抛数据库异常；真实 Coordinator 和 Retriever.evaluate 处理，准入 dialect 和输入资产使用替身，RAGAS 明确设不可用。最终 20 条结果仍报告 `completed_judge_degraded`，而非基础设施不确定；报告也未提供 backend 或 sources_used 字段。

这并非真实 PG 压测，但证明了运行状态传播缺口。现有测试用 FakeAgent.evaluate 直接抛异常，未覆盖真实 Coordinator 将异常转为 outcome 后的路径。

修订建议：在正式基线前补“检索 outcome/来源/安全失败信息保真与 runner 分类”执行任务；judge 降级与检索基础设施失败分开；真实失败不得静默计入零召回质量结论。状态修订的具体接口在三层执行规划中确认，不在本轮直接实施。

## 推进建议

先确认并修复评测失败状态传播、provider 条件性虚假写入确认及 gate 输入有效性；同时完成正式 attestation 执行契约与隔离方案。多 k 指标和日志关联纳入后续明确执行包。整体阶段顺序可以保留，不以现有 99 项通过替代新发现问题的验收。
