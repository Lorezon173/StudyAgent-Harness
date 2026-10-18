# T08 / T09 / T05 第二批计划正式审阅

日期：2026-10-17（Asia/Shanghai）。审阅对象为2026-10-16三份计划的当前工作区稿件，不是实现代码差异。三个独立只读审阅代理均使用gpt-6-luna / xhigh，主窗口逐条对照冻结spec和实际代码核验；未运行测试、服务、迁移或摄入，未修改产品代码、冻结契约或暂存区。

**结论：暂不通过派发。确认9项需修订，其中7项P1、2项P2；另有1项非阻断澄清。** 这次结论更新[前一轮文档复读](2026-10-16-second-wave-plan-review.md)之后的状态，不把历史复读记录改写成当前通过。

冻结依据：[rag-mvp-contracts-v1.0.1](../specs/2026-10-16-rag-mvp-contracts-v1.md)，实际SHA-256仍为`31379383758b82c82d5fe583f371e590f4b187ad0371744edcef635743b41f95`；依赖与调度依据[已确认DAG](../../../superpowers/rag-foundation/2026-10-16-rag-mvp-dag-and-scheduling.md)。下列行号均指本轮审阅时计划稿，后续修改后需按规则ID追溯。

## T08：2项P1、2项P2

### RV2-01 · P1 · intent已落盘但pending尚未创建时，新run可绕过未决意图

- 定位：[T08计划](2026-10-16-t08-execution-plan.md:85)，及该文件156、183～184、190、195行。
- 触发：intent.json和plan-manifest.json已发布，在创建prepared marker之前进程退出。PG session锁随连接终止而释放，target仍为空。
- 问题：新run仅按target查pending文件，可能因此进入；原run又因缺marker和proof只能inconclusive。没有发现阻止新run的其他持久登记步骤，违反spec A4“未决意图未处理前所有受控写入者不得启动新run”。这与文末已说明的unconfirmed返回值持久化窗口是两件不同的事。
- 修订：在发布任何需阻止新run的持久意图之前先建立可发现的target占用记录；为marker存在但intent尚不完整的已知未开始写入状态设计只读处置规则。或者给出等效的完整持久登记/扫描机制，不能只靠当前marker缺失判断安全。覆盖两个发布动作之间逐点崩溃，以及随后run/recover的行为。

### RV2-02 · P1 · 专用writer证据未绑定实际数据库登录角色

- 定位：[T08计划](2026-10-16-t08-execution-plan.md:70)，及111～113、181、185、192行。
- 触发：资源证据登记受审计的专用writer role，但database_url_env实际使用另一个可写角色；database/schema名字均匹配。
- 问题：计划核对目标和锁，却没有要求从同一连接读取实际session/current role并与权限审计事实绑定。锁只能协调遵守协议的writer，不能补足身份不符的权限证据；仍可能生成排他成功证明。spec A4明确不能排除外部writer时不准成功恢复。
- 修订：定义同连接实际登录角色、有效角色与可信权限审计记录的比对方式；无法确认时在写入或补证明前拒绝。正常与恢复均覆盖“目标相同、账号不同”的受控反例，不泄露DSN或凭证。

### RV2-03 · P2 · 预检失败时尚无合法run UUID可构造RunRecord

- 定位：[T08计划](2026-10-16-t08-execution-plan.md:181)，及161、183行。
- 触发：参数、registry、数据库或lease预检在“生成UUID”之前失败，而流程要求返回RunRecord。
- 依据：[RunRecord](../../../app/infrastructure/rag/contracts.py:378)在构造时无条件验证ingestion_run_id为UUID。
- 修订：在任何可能返回失败的校验前生成一次本次调用UUID，并在排他记录、intent、manifest、marker和返回值中复用；不要在后续步骤再次生成。明确仅返回诊断ID与需要持久化登记的失败范围。

### RV2-04 · P2 · runtime构造与身份核验先后顺序互相矛盾

- 定位：[T08计划](2026-10-16-t08-execution-plan.md:147)，及75、181行。
- 问题：_build_runtime要求调用describe_embedding并返回含已验证Identity的Runtime；run流程却要求完成数据库/lease/空前态校验和排他记录后才describe，而这些前置又要先取得runtime中的provider。
- 修订：拆明service/provider装配与identity描述两个阶段，或调整唯一顺序；结构字段、helper契约、正常和恢复流程及测试调用顺序必须一致。此次是接口顺序冲突，不声称SDK配置读取本身会发出远端请求。

## T05：3项P1

### RV2-05 · P1 · current_schema校验不足以约束revision的实际解析目标

- 定位：[T05计划](2026-10-16-t05-execution-plan.md:57)，及61、106、141行。
- 触发：search_path中测试schema在前、业务schema在后，某待修改表只在业务schema存在。current_schema仍是测试schema，守卫可通过。
- 依据：现有[context recall revision](../../../alembic/versions/20260623_add_ragas_context_recall.py:22)使用无schema限定的op.add_column('evals', ...)；其他revision也存在未限定表操作。
- 修订：在变更前限制并核验有效schema搜索/对象解析范围，拒绝可能命中未批准业务/基线对象的路径；或将测试资源限定为整个隔离数据库并证明解析范围。仅设置version_table_schema并不能约束全部revision。补“当前schema合法、后续schema有业务表”的反例，真实PG执行留T07。

### RV2-06 · P1 · 数据库名加schema不能唯一识别PostgreSQL服务实例

- 定位：[T05计划](2026-10-16-t05-execution-plan.md:106)，及141行。
- 触发：连接误指向另一PG实例，但其数据库名/schema与获批测试目标相同。
- 问题：计划将database_id定义成数据库名，allowlist碰撞集合也仅含(database_id, schema_name)，这两项查询无法识别服务实例差异。
- 修订：在私有可信资源映射中明确可唯一绑定服务实例的标识及同连接只读验证方式，或由受信连接装配方提供可核验的唯一目标绑定。公开失败只输出安全ID；不得通过输出完整URL补识别。覆盖“不同实例、相同数据库名和schema”反例。无需单方改冻结Config.attributes字段。

### RV2-07 · P1 · 预检autobegin导致Alembic事务责任改变

- 定位：[T05计划](2026-10-16-t05-execution-plan.md:57)，及61、104、113行。
- 触发：注入Connection原先不在事务中，守卫先execute只读查询，再context.configure。
- 主控核验：本地已安装Alembic的`.venv/Lib/site-packages/alembic/runtime/migration.py:159`在配置时记录connection.in_transaction()；416行起在外部事务下返回空transaction context。守卫查询会触发SQLAlchemy autobegin，因而“沿用context.begin_transaction”不等于Alembic会负责提交这次连接上的事务。
- 后果：若调用方没有提交，该事务可在连接关闭时回滚，迁移调用返回但实际更新未保留；反过来，直接提交又可能错误提交调用方已有工作。
- 修订：记录入口是否已有调用方事务；明确预检产生事务的结束方式，以及外部事务由谁提交/回滚。新增事务所有权矩阵和成功/失败边界断言，不能仅用run_migrations惰性spy证明事务正确；本包使用受控事务对象/本地隔离验证，真实PG事务留T07。

## T09：2项P1

### RV2-08 · P1 · 真实查询provider未与证明及snapshot的目标绑定

- 定位：[T09计划](2026-10-16-t09-execution-plan.md:145)，及148～149、198行。
- 触发：context、snapshot、proof均属于目标A；agent实际vector provider连接目标B；两者都是PG且embedding配置相同。
- 依据：现有[provider构造](../../../app/infrastructure/rag/pgvector_provider.py:42)可选择独立db_url；[默认dialect探测](../../../benchmarks/rag/books/the-myth-of-sisyphus/rag_d.py:207)只确定方言。计划比较的是声明context/snapshot字段和实际embedding，而没有列出读取并绑定live provider实际数据库/schema/目标的步骤。
- 后果：可能在B上评测，却以A的证明、快照、目标标识输出完成报告。
- 修订：准入时核对执行检索的同一provider连接的实际目标与受控资源和快照一致，并固定运行期绑定；不能仅增加一个自报target字符串。provider指向B、其余证据属于A时必须零次evaluate并阻断。

### RV2-09 · P1 · baseline保护在snapshot之后获取，且没有跨包持有/互斥协议

- 定位：[T09计划](2026-10-16-t09-execution-plan.md:78)，及76、84、198行；对照T08计划71、163、186行。
- 触发：取snapshot后、取得保护前目标变化；或20题运行中T08 writer并不认识所谓read_only_frozen保护，仍可获得自己的writer lease。
- 问题：active=True等mapping值只能表达声明。计划没有规定保护句柄从snapshot前持续持有到baseline结束、由谁在finally释放，以及它与T08的目标锁是否冲突。
- 修订：由T12受控调用者先取得同target的保护，再读取实际snapshot/核验，持续持有直至baseline结束并finally释放；定义与T08 writer使用的相容/冲突协议或等效的权限冻结机制。T09只消费受控绑定，不独立复制锁实现；离线包用替身验证顺序/冲突/生命周期，实际机制在T07/T12验证。保留摄入UUID和本次report UUID的区分。

## 非阻断澄清 C-01：未决报告应显式保留已知D3上下文

T09独立审阅还指出，首错/异常/漂移后的infrastructure_inconclusive可能沿用旧counts-only envelope。主窗口复核发现，计划25、173、177～182行已要求完整字段、未知才null，并给出了可带status的报告构造器，因此不将其重复计作已确定的P2缺陷。建议明确所有准入后未决出口复用已验证context，并在首题失败/异常/漂移测试中同时断言target、identity、proof、manifest与计数，减少实现歧义。此条不代替RV2-08/09。

## 修订优先顺序与范围

1. 先处理T05三项P1与T09实际目标绑定，保证操作/评测对象正确且事务责任清楚。
2. 处理T08的写前持久占用窗口、实际role绑定；与T09共同明确writer/baseline保护协议，避免各自通过但集成失效。
3. 修正T08 UUID和runtime顺序，并将每项反例映射到明确的离线测试步骤与真实T07/T12后置验收。C-01可随T09同文件修订。
4. 原起草者只修改本包计划；跨包互斥语义由主窗口统一记录。修订后定向复核，再请求用户确认计划及其中新增私有装配设计。不能因本次review启动产品编码。

本轮只归档审阅结论、同步README/索引/主清单与计划状态。原已暂存39文件保持不变，本轮新增/变更文档没有暂存、提交或推送；不重跑已验收首批测试，也不把此前547项结果作为第二批设计正确性的证据。


## 用户追加T01计划编写

本次用户将[T01环境与资产只读盘点](2026-10-17-t01-execution-plan.md)加入同批计划，由gpt-6-luna / xhigh起草、主窗口复核。T01只编写计划，未执行资产哈希盘点、环境读取、PG查询、SDK请求或测试。

主窗口首读四处定向意见已落实：CI按integration标记排除而非按目录，收集仍可能运行模块顶层；有条件PG查询仅使用本次专用新同步连接，不接管调用方已有事务；查询前落实只读与5秒连接/10秒语句超时上限，超时/拒绝均rollback/close；题集区分verified_v1/draft/unknown状态，.env始终不读取。计划区分来源声明、允许观察、未知与责任方，允许在完整记录缺口后完成盘点覆盖，但不将资源标为ready或关闭真实门。

T01文档已完成本轮定向复核，待用户确认后执行；它不能替代T07权限/事务/迁移验收，也不能自动关闭RV2-01～09。T05/T08/T09仍保持需修订、不派发的结论，冻结契约及DAG硬依赖未改。
