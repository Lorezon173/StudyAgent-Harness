# T01 环境与资产只读盘点

盘点日期：2026-10-17（Asia/Shanghai）。用户授权：“先执行t1”。依据[已复核T01计划](../../plans/2026-10-17-t01-execution-plan.md)。本次没有运行测试/收集、CI、迁移、摄入、PG查询、embedding或judge请求，没有安装依赖、读取.env或导入业务settings。

**inventory_coverage=covered；resource_readiness=blocked。** 计划要求的资产、运行时/CI、PG来源、embedding来源和交接均已核对并记录观察/缺失/未知原因；这表示盘点交付完成，不表示真实环境就绪。T05/T08/T09的9项设计问题及G1～G6状态不变。

## 1. 基线、方法与来源

- 分支：codex/rag-mvp-first-wave；HEAD：6324b9442b6f1671ccb4a19cdacb42bb91597187。
- 冻结spec实际SHA-256：31379383758b82c82d5fe583f371e590f4b187ad0371744edcef635743b41f95，与计划一致。
- 使用项目.venv的Python 3.12.11，平台win32。一次性只读动作通过标准库pathlib/hashlib/tomllib/ast/importlib.metadata和已安装PyYAML解析文件、统计元数据；没有创建探测脚本或生产代码。
- 资产来源：book目录的source-manifest.yaml、README.md、questions.v1.yaml及局部.gitignore。manifest的“用户已验证版权页”是历史声明，本次没有重新核实合法来源或版权。
- 运行时来源：pyproject.toml、uv.lock、.github/workflows/ci.yml；包版本来自当前.venv发行元数据，不通过导入应用或评测库验证可运行性。
- 配置来源：仅静态AST读取app/core/config.py中的公开默认值；进程环境按计划指定键检查存在性，未读取值。默认值不是有效运行配置，.env覆盖未知。
- PG/embedding登记：用户本轮没有提供可信资源记录、装配工厂或binding登记。对仓库根的指定候选名，以及app、scripts、alembic、.github、docs/rag-work/specs中的resources.json、bindings.json、resource-record.json、target-allowlist.json、writer-evidence.json做限定文件名枚举，未匹配；不据此断言其他位置不存在登记。

## 2. 资产观察与声明分离

| 对象 | 声明/来源 | 本次观察 | 就绪状态 |
|---|---|---|---|
| source EPUB | manifest登记一个历史macOS外部路径；声明SHA见下方 | 尚未提供本机Windows映射；没有扩大磁盘搜索，未读取EPUB，exists/实际SHA均unknown | blocked：当前来源未解析 |
| corpus.local.jsonl | manifest声明已抽取313段；本书.gitignore忽略该正文文件 | 明确登记的book目录位置不存在；字节数、实际摘要、实际段数均null | blocked：本地语料缺失 |
| questions.v1.yaml | 正式题集文件 | 文件存在，28,690字节；20条mapping、20个唯一非空ID，缺失/重复ID均0；verified_v1=20、draft=0、unknown=0 | 最小结构盘点ready；完整资产准入仍blocked |
| 题集与manifest关联 | book_key、corpus_version.source_sha256 | 两项声明互相匹配；只证明元数据自洽，不能证明EPUB/正文一致或gold引用有效 | unknown：缺实际源/corpus |

source声明SHA-256：`341696af4d08a3f0dec622ac2311556495459d68517387bd912c5fcc8d545a7f`。这是manifest声明，不是本次EPUB实测值。corpus实际SHA=null，不用source摘要代替。

本次实测文件指纹：

| 相对路径 | 字节数 | SHA-256 |
|---|---:|---|
| benchmarks/rag/books/the-myth-of-sisyphus/source-manifest.yaml | 1896 | 48179b84f1a1254b08150038edb778b92a109124cf33592eef8947b167aa1f0c |
| benchmarks/rag/books/the-myth-of-sisyphus/questions.v1.yaml | 28690 | e9b41e563bdad3799b02e884ce43cf3dbd4abcb6c0df8e68ba94741b9d37c0f9 |
| pyproject.toml | 1767 | 18770f95869a6fc9bf8468932f8094bb03d59a55a14a010451b6b1730eadaa20 |
| uv.lock | 1224674 | f3e3887f9463f7edf78a9a58de4b2d0ae88f303e98b0b8bf77ecef77be34029c |
| .github/workflows/ci.yml | 651 | e6999e50a8bebd28f95a01edfe99aee4ef7f368968fd11d5310b57c0458c6ccc |

没有打印题干、答案、gold片段或正文，也没有执行完整validate_assets。verified标签计数不能代替正式validator或人工质量复核。

## 3. 运行时、依赖与CI

Python约束为>=3.11，当前解释器3.12.11满足此版本范围；没有据此证明全部依赖兼容。

| 关键发行包 | 当前.venv发行元数据 | uv.lock声明 |
|---|---|---|
| SQLAlchemy | 2.0.49 | 2.0.50 |
| alembic | 1.18.4 | 1.18.4 |
| psycopg | 未找到发行元数据 | 3.3.4 |
| asyncpg | 未找到发行元数据 | 0.31.0 |
| pgvector | 未找到发行元数据 | 0.4.2 |
| openai | 2.36.0 | 2.38.0 |
| ragas | 未找到发行元数据 | 0.4.3 |
| datasets | 未找到发行元数据 | 4.8.5 |
| pytest | 9.0.3 | 9.0.3 |
| pytest-asyncio | 1.3.0 | 1.4.0 |
| httpx | 0.28.1 | 0.28.1 |
| PyYAML | 6.0.3 | 6.0.3 |
| pydantic-settings | 2.14.1 | 2.14.1 |
| ruff | 未找到发行元数据 | 未列入此次锁文件关键包结果 |

“未找到发行元数据”不等同于已测试import失败，也不排除其他解释器、源码路径或测试替身；本次没有导入这些库检查功能。SQLAlchemy、openai、pytest-asyncio与锁版本有差异，未证明当前.venv与锁文件同步。未自动安装或升级。

先前使用的缓存ruff.exe路径仍是普通文件，目录名标识0.15.7；本次没有执行ruff或验证其运行版本。项目dev extra不声明ruff，CI使用uvx取得工具。

CI静态事实：push main及pull_request触发；runner=ubuntu-latest；命令为`uv sync --extra dev`、`uvx ruff check .`、`uv run pytest tests/ -v`。eval是独立optional extra，当前CI安装命令未显式选择eval。pytest addopts为`-m 'not integration'`：按marker筛选，非按目录排除，收集仍可能执行模块顶层；这不是数据库/网络隔离机制。本次未访问远端CI，也没有运行上述命令或pytest收集。

首批547 passed、1 deselected及既有E402仅引用[2026-10-16主控历史证据](../2026-10-16-first-wave-execution.md)，不算T01重新验证结果或真实服务证据。

## 4. PG与embedding的来源/能力

静态公开默认值：rag_backend=fake、embedding_model=doubao-embedding-vision、embedding_dim=2048。这些是app/core/config.py的代码默认值，不是本次实际settings值，也不代表远端模型或维度。

按存在性检查，以下进程环境键本次均未出现：DATABASE_URL、TEST_PG_URL、RAG_BACKEND、OPENAI_API_KEY、OPENAI_BASE_URL、EMBEDDING_MODEL、EMBEDDING_DIM、RAG_INGEST_CONTROL_DIR、RAG_TEST_TARGET_ALLOWLIST_ROOT、RAG_TEST_TARGET_ALLOWLIST_PATH、RAG_TEST_SQLITE_ROOT。只记录键名与不存在；未取值，.env未读取。因此不能据此断言其他配置来源没有凭据或服务不可用。

| 对象/字段 | 观察或来源状态 | 处理 |
|---|---|---|
| resource_record_ref / target_index_id /用途 | 未提供可核验的真实登记；限定候选枚举无匹配 | unknown；不创建登记，不把测试/计划示例当真实来源 |
| PG实例唯一绑定、database/schema/search_path | 无可信装配来源；未读取实际数据库 | query_attempted=false；not_probed |
| session/current role、权限审计、专用writer | 无实际连接与可信审计引用 | unknown；不以角色声明代替权限排他证据 |
| 只读事务、5s连接/10s语句超时 | 未满足建立连接的前置 | 未建立连接；无事务或连接需要rollback/close，亦未验证这些能力 |
| binding_record_ref、service/deployment/version来源 | 没有独立可信登记 | unknown；不构造EmbeddingBinding或SDK client |
| 参数身份、实际配置指纹与alias版本能力 | 仅有代码默认模型/维度；实际服务不可观察 | unknown；无describe/fingerprint实际服务调用 |
| 真实向量维度、PG扩展/事务/锁 | 未执行相应探测或测试 | 未验证，留T07及后续真实验收 |

PG查询次数=0，SDK/client构造和embedding/judge请求未执行。这里“0/未执行”来自本次执行动作范围，不宣称安装了全局外联拦截器或证明服务器不可用。

## 5. 缺口账本与责任交接

以下均coverage=covered，ready状态另列；unknown不以猜测补齐。

| ID | 类别/状态 | 事实/缺口 | 责任交接 | 后续影响 |
|---|---|---|---|---|
| INV-01 | source / blocked | 历史源声明存在，本机可读路径与实际源SHA未知 | 用户/资产owner提供合法本地EPUB精确路径；主控核对声明与实际哈希 | T11/G3、T12/G4 |
| INV-02 | corpus / blocked | 登记位置corpus.local.jsonl缺失，313段仅历史声明 | 资产owner按既有合法来源另行安排恢复/提取；不得本轮擅自重建 | T12/G4；题集gold关联尚不能验证 |
| INV-03 | questions / unknown | 20唯一verified标签已观察，但源/语料实物链未闭合 | 主控/T12在资产齐备后运行正式validator与人工复核 | 不以标签计数准入baseline |
| INV-04 | runtime / blocked | 关键PG/评测包未见发行元数据，部分版本与lock不同 | 环境维护者先确认目标解释器和所需extras，再另行安排依赖同步与验证 | T07真实PG、真实judge及可复现运行 |
| INV-05 | PG resource / unknown | 可信target用途、实例唯一性、受控工厂和审计来源未提供 | 资源owner/主控明确测试与基线资源，再交T07真实核验 | T05/08/09运行装配、T07/G2 |
| INV-06 | writer / unknown | 实际登录身份、排他权限、搜索路径及读写保护未验证 | T05/T08/T09先修订RV2，T07/资源owner提供实际权限与身份事实 | RV2-02/05/06/07/08/09仍未关闭 |
| INV-07 | embedding / unknown | 独立service/deployment/version/binding来源未提供，实际指纹/维度未测 | 服务owner/主控指定可信公开登记与装配，T07/T09/T12核验 | T08证明、T09准入、真实检索 |
| INV-08 | CI / unknown | 只有工作流声明及历史本地测试证据，没有本次CI/测试执行 | 主控/T14在对应范围就绪后安排验证 | 不声称CI或G1～G6通过 |

T01盘点覆盖完成不关闭RV2-01～09，不等于T05/T08/T09计划获批。允许继续这些包的计划修订；真实探测/迁移/摄入/baseline仍按DAG与实际资源条件推进。

## 6. 执行结果与限制

1. 一次性元数据/资产计数/文件哈希/发行版本/环境键存在性核查，退出0；没有业务模块导入、正文输出或服务调用。
2. 静态CI、局部.gitignore和分支/HEAD读取完成。首次全仓候选文件枚举遇既有pytest临时目录权限拒绝，结果不完整，未据此声称注册文件不存在，也未请求额外权限或清理目录。
3. 随后改为本节第1部分列出的明确目录与文件名候选范围，返回无匹配、无读取错误，退出0。这个有限范围不覆盖用户其他位置或外部登记系统；本轮也没有提供对应引用。
4. 静态AST公开默认值、uv.lock关键包及已知缓存工具文件存在性核查退出0。没有读取.env，没有访问任何环境变量值。
5. 所有缺项已登记状态、原因及下游责任。只新增本证据；README/主清单/索引和计划状态由主控同步。原暂存区与产品文件不改，不提交、不推送。
