# T00 契约归档与接口冻结记录

日期：2026-10-16。状态：**T00 完成；rag-mvp-contracts-v1 已冻结，代码未实现**。用户已确认 MVP 执行方案，并明确要求开始 T00。本次只交付正式 spec、审阅及主控记录，不开展 T01 或 T02～T14 实现。

## 1. 产物与来源

- 当前正式规范：[RAG MVP 共享契约](../../docs/rag-work/specs/2026-10-16-rag-mvp-contracts-v1.md)，后续v1.0.1勘误见第6节；[原v1冻结字节](../../docs/rag-work/specs/2026-10-16-rag-mvp-contracts-v1-original.md)。
- 冻结时文件SHA-256：`64e1f13d58adc2c30685284f2e221584951b974416609637d6ee46192e133cc0`。该值标识本次审阅后保存的字节版本；后续修改须更新版本/记录，不静默沿用此冻结证据。
- raw来源：[已确认MVP方案](2026-10-15-rag-mvp-execution-plan.md)、[执行方案review](2026-10-15-rag-mvp-execution-plan-review.md)、[DAG](2026-10-16-rag-mvp-dag-and-scheduling.md)。
- 原DEC-001～012保持不变；既有三份窗口spec不代写，新增共享spec由主控维护，仅覆盖本轮设计增量。
- 采用此前已加载的 brainstorming/writing-plans/receiving-code-review 原则，按用户规则使用三层文字设计，不在计划内放实现代码。

## 2. T00 已完成检查项

- [x] 保存正式 spec，逐项追溯 raw、review、DEC。
- [x] 定义契约集和准备结果、两级清单、意图、证明、embedding身份、评测输出、基线报告与投影版本。
- [x] 固定新函数的模块、所有者、输入、返回、错误及兼容边界。
- [x] 固定 owner/user_id 映射、版本/计数/null校验、成功与失败条件。
- [x] 固定embedding公开配置规范化及SHA，实际查询身份与证明比较，保留远端别名不可锁定的限制。
- [x] 固定20题有效执行不变量、单次多k、judge逐项校验及严格JSON。
- [x] 固定空目标预计划持久化、提交后只读恢复和隔离证据责任，禁止自动重导。
- [x] 归档C入口、六码、top_k、投影/引用上限、回合关联及日志上下文。
- [x] 固定迁移测试连接注入、变更前目标守卫与A/B对抗要求。
- [x] 主控自查；子代理独立审阅；修补三项接口闭合问题；子代理定点复核通过。
- [x] 将结果同步到主清单、工作区入口、DAG及README，不代写各窗口状态片段。

冻结含义：本轮共享接口已有唯一可引用基线，即 G0 的契约条件已满足。**不将整个 S0、子任务派发门或 G1～G6 标为通过。** T01 环境盘点尚未执行，逐包实施 plan 尚未编制，不能仅凭 T00 完成派发业务编码。

## 3. 独立审阅与修补

审阅者：子代理 review_rag_plan，读取正式草稿、raw、review、DEC及必要代码，未修改文件或连接真实服务。

| 首轮发现 | 修补 | 定点复核 |
|---|---|---|
| 恢复无法得到原运行namespace、策略、版本、warnings与完整identity/资源引用 | intent写前持久化完整preparation及identity，快照重建计数；T08生成隔离证据、T09核验 | 通过 |
| 准备级manifest误要求runid/target/embedding字段，prepare_file无法提供 | T02产prepared-manifest-v1；T08仅加运行envelope，rows不重生成 | 通过 |
| PreparedIngestion/RunRecord没有唯一类型路径和所有者 | 前者及准备异常由T02在knowledge_ingestion定义；RunRecord由T04在纯数据contracts定义 | 通过 |
| 非阻断：清单展示排序与摘要排序可能解释不同 | 计算摘要统一完整行规范JSON字节排序、保留重复，与展示顺序分离 | 通过 |
| 非阻断：RunRecord错误码未固定 | 六码复用，额外拒绝用安全规则ID；phase摘要固定、禁止异常原文 | 通过 |

最终审阅结论：原三项阻断均闭合，未发现新的T00阻断项，可冻结文字契约。该结论不证明代码、恢复行为或真实基础设施通过。

## 4. 问题与历史主清单映射

下表是责任映射，不修改历史BLK的稳定编号，也不把新缺口误写成历史任务尚未做过。

| 本轮问题 | 原BLK/责任范围 | 后续包 |
|---|---|---|
| R01、R13、R15 | BLK-006/010，故障与报告真实性 | T03/T09/T10 |
| R02 | BLK-004，写入确认边界 | T02 |
| R03 | BLK-002/007，正式证明 | T04/T08/T09/T11 |
| R04 | BLK-007，corpus隔离 | T04/T07/T09/T11 |
| R05 | BLK-003/005，在线证据与请求保真 | T06/T13 |
| R06 | BLK-005/006，候选接口收敛 | T00已归档；T06/T10实现 |
| R07 | BLK-008，schema与fixture | T05/T07 |
| R08 | BLK-006/008，真实后端 | T01/T07 |
| R09 | BLK-002，真实原子性 | T02/T07 |
| R10 | BLK-002/004/007，真实摄入与来源 | T08/T11 |
| R11 | BLK-009/002，真实书籍兼容 | T01/T11 |
| R12 | BLK-010/013的proxy基线，非strict identity扩展 | T03/T12 |
| R14 | BLK-006，审计关联 | T10/T13 |
| R16 | BLK-007/010，评测资产 | T01/T12 |
| R17 | BLK-001/003，权限过滤及生成隔离 | T07/T13 |
| R18 | BLK-007/010，正式baseline | T12 |
| R19 | BLK-003/005，双入口与因果验证 | T06/T13/T14 |
| R20 | 主控文档/交接，无新BLK编号 | T00文档索引、T14最终交接 |
| R21 | CI与检查现状，无新BLK编号 | T01及各包验收/T14 |
| R22 | BLK-011/012/013及明确非目标 | 后置，不在T00解锁 |
| R23 | BLK-010，20题有效完成 | T03/T09/T12 |
| R24 | BLK-006/007，embedding身份绑定 | T04/T08/T09/T13 |
| R25 | BLK-008，迁移目标注入 | T05/T07 |
| R26 | BLK-002/007，提交后恢复与证明 | T02/T08/T11 |
| R27 | BLK-010，judge有效性 | T03/T12 |

## 5. 交接与剩余工作

首批T02/T03/T04将统一消费rag-mvp-contracts-v1。下一步分别编制独立plan，固定每包精确读写文件、新接口消费、实施步骤、必要测试命令、预期结果和证据位置，再审阅并派发；本次不把执行方案/DAG当作这些plan。

T00没有完成：真实环境盘点、实际代码/schema模块、正式迁移、真实书籍摄入、20题baseline、在线接线、各窗口handoff全面补齐或全仓lint清理。S0-05仅完成本轮主控入口/冻结记录同步，历史文档整理仍有遗留。

验证边界：检查文档结构、版本/任务映射、本地链接与Git变更范围；未运行pytest、真实PG/embedding或LLM。旧99通过等结果仍是历史证据，不作为本次完成依据。没有commit/push，没有全局配置/skill/记忆修改。

## 6. 首批独立plan编写后的主控勘误

当前执行契约集升级为rag-mvp-contracts-v1.0.1，当前文件SHA-256：`31379383758b82c82d5fe583f371e590f4b187ad0371744edcef635743b41f95`。原v1完整字节按第1节原SHA保存，未删除冻结历史。

勘误固定build_attestation的显式verified_at输入、非法top_k/未知latency为null、runner完整安全失败metrics、无gold/未judge边界、准备错误摘要/非法写入确认和overlap=0。影响T02/T03/T04/T08/T09，数据schema_version保持不变。主窗口按原变更规则记录并统一三个plan，未让各代理自行改变共享契约。

详见[首批主窗口review](../../docs/rag-work/plans/2026-10-16-first-wave-plan-review.md)及[plan索引](../../docs/rag-work/plans/2026-10-16-execution-plan-index.md)。T02/T03/T04独立plan现已编写并经主窗口修订复核通过，可供后续派发；本次仍未启动编码，T01及其他执行包plan状态见索引，不自动解锁G1～G6。
