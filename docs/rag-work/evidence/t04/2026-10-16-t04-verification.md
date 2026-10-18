# T04 离线验证记录

日期：2026-10-16（Asia/Shanghai）
状态：T04 本包实施与纯逻辑验收完成；已按主控定向 review 修订并重跑，待定向复审；不代表真实数据库、远端 embedding 或 G1 验收。

## 基线与范围

- 执行计划：`docs/rag-work/plans/2026-10-16-t04-execution-plan.md`，已完整读取；步骤15按离线独立验收及组合回归交接执行。
- 冻结 spec：`docs/rag-work/specs/2026-10-16-rag-mvp-contracts-v1.md`；实际 `Get-FileHash ... -Algorithm SHA256` 为 `31379383758B82C82D5FE583F371E590F4B187AD0371744EDCEF635743B41F95`，与计划值一致；命令退出码 0。
- 分支：`codex/rag-mvp-first-wave`（读取命令退出码 0）。
- 开始前 `git status --short` 显示主控/其他任务已有改动：`README.md`、`docs/rag-work/README.md`、`docs/rag-work/plans/2026-07-24-rag-foundation-parallel-todolist.md`，以及新增的首轮计划索引、复查文档、T02/T03/T04计划、v1原始及当前spec、`superpowers/rag-foundation/`。这些均为初始状态，本包不回退或改写。
- 开始前本包七个允许路径尚无文件。本包只新增三个产品文件、三个单测文件和本证据文件；README及执行计划由主控维护。
- 本地 `.venv/Scripts/python.exe` 存在；不安装依赖。开始时尚未执行测试，未访问真实服务，未 commit 或 push。

## 逐步记录

| 步骤 | 结果 | 命令与退出码 |
|---|---|---|
| 01 基线核对 | 通过；冻结 SHA 与计划一致，初始状态如上。 | `Get-FileHash ... -Algorithm SHA256`：0；`git status --short`：0；`git branch --show-current`：0 |
| 02 contracts 失败用例 | 新增 `test_rag_contracts.py`；覆盖七类值对象、深层冻结、RunRecord、严格JSON及固定 identity/manifest 向量；每个测试本地启用 pgvector 不利设置、SDK/embedding/SQLAlchemy/PgVectorProvider 调用陷阱。 | 写入测试文件；尚无实现 |
| 03 contracts 红灯 | 首次确认因 `app.infrastructure.rag.contracts` 缺失而收集失败，属于预期红灯；随后补加 URL/API key/换行秘密标记拒绝用例，暴露 model/version 字段漏检（2 failed）。 | `.venv/Scripts/python.exe -m pytest tests/unit/infrastructure/test_rag_contracts.py -q -p no:cacheprovider`：1（缺模块）；同命令：1（秘密样例未拒绝） |
| 04 纯类型与规范化 | 新增冻结值对象、递归复制冻结、严格JSON字节和保留重复行的多重集合SHA；Binding端点仅内存且不进入repr，模型/版本只拒绝明显URL/凭证形式，允许 `vendor/embedding-v2` 和 `snapshot/release-v2`。 | 实现 `contracts.py`；未触碰共享/既有文件 |
| 05 contracts 绿灯 | 最终 contracts 单测全部通过；fixture 结束时 SDK 工厂、embeddings.create、embed_one/embed_many、同步/异步引擎及 provider 连接计数均为0。 | `.venv/Scripts/python.exe -m pytest tests/unit/infrastructure/test_rag_contracts.py -q -p no:cacheprovider`：0，21 passed |
| 06 identity 失败用例 | 新增 `test_embedding_identity.py`：真实 `EmbeddingService` + 无凭证SDK替身；覆盖固定摘要、模型/部署/参数差异、绑定端点、缓存client、配置漂移、精确导出和异常/凭证边界。 | 写入测试文件；未运行网络请求 |
| 07 identity 红灯 | 新接口模块缺失导致预期收集失败。 | `.venv/Scripts/python.exe -m pytest tests/unit/infrastructure/test_embedding_identity.py -q -p no:cacheprovider`：1，`ModuleNotFoundError` |
| 08 identity 实现 | 新增 `describe_embedding`、`fingerprint_embedding`、`to_json_dict`；读取实际service model/dim和SDK client端点两次，严格比对，不发embedding请求。 | 实现 `embedding_identity.py`；SDK替身不保存测试密钥 |
| 09 identity 绿灯 | 全部身份测试通过；SDK工厂仅创建固定替身，远端 create/embed 与数据库陷阱均为0。 | `.venv/Scripts/python.exe -m pytest tests/unit/infrastructure/test_embedding_identity.py -q -p no:cacheprovider`：0，10 passed |
| 10 attestation 失败用例 | 新增 `test_ingestion_attestation.py`：独立 fixture、成功 build/validate、恢复核验时间、完整输出键、build拒绝矩阵、validator字段/类型/身份/权限/isolation矩阵、输入不可变、秘密边界及IO/远端陷阱。对没有独立 Expectation 字段的 `source_format`、`import_namespace`、`normalizer_version` 明确测试 build 从 preparation 透传；不伪造额外 expected 字段。 | 写入测试文件；不调用真实服务 |
| 11 attestation 红灯 | 初次运行缺少实现时已有 152 passed、8 failed；修正测试与契约边界后，在实现补齐前再次确认红灯：155 passed、6 failed，失败暴露目标凭证 URL、协议值、outer Mapping、隔离时间和测试 expectation 构造问题。 | `.venv/Scripts/python.exe -m pytest tests/unit/harness/test_ingestion_attestation.py -q -p no:cacheprovider`：1（首次 152 passed/8 failed；复核红灯 155 passed/6 failed） |
| 12 证明构造和核验实现 | 新增纯逻辑 `build_attestation` / `validate_attestation`。build 交叉核验 intent/preparation、manifest、已有 `IngestResult`、snapshot、Identity，成功对象只使用原 preparation 值和显式 `verified_at`。validate 要求外层是 dict、拒绝混用冻结协议，比较独立 expected 与 snapshot 中可比较字段，并核验隔离 target/manifest/row count/时间。对 source format、namespace、normalizer 等没有独立 expected 的字段，build 保持 preparation 原值；validator 只执行冻结版本和类型规则。 | 实现 `app/harness/ingestion_attestation.py`；仅消费现有 `IngestResult` |
| 13 attestation 绿灯 | 完整 build/validate 用例通过；不同核验时间沿用旧 run ID，证明时间采用本次核验值。重入调用相同、输入保持不变，文件打开、SDK create/embed和数据库陷阱均未触发。 | `.venv/Scripts/python.exe -m pytest tests/unit/harness/test_ingestion_attestation.py -q -p no:cacheprovider`：0，161 passed |
| 14 包内联合验证 | 三个测试文件联合通过，包含所有局部不利 pgvector fixtures；未等待或导入 T02 新接口。 | `.venv/Scripts/python.exe -m pytest tests/unit/infrastructure/test_rag_contracts.py tests/unit/infrastructure/test_embedding_identity.py tests/unit/harness/test_ingestion_attestation.py -q -p no:cacheprovider`：0，193 passed in 2.38s |
| 15 独立离线边界验收与组合回归交接 | 三测试文件各自设置 `rag_backend=pgvector`、固定 SDK 替身和 create/embed/SQLAlchemy/PgVectorProvider 调用即失败陷阱；contracts、identity、attestation 分别在被测纯逻辑调用期间设置文件打开陷阱。重复联合测试通过，fixture teardown 断言远端请求和数据库连接计数为0。T04 未执行旧跨包命令；交主控仅在 T02/T03 fixture 与隔离边界复核后执行并补充证据。 | 步骤14同一命令：0，193 passed in 1.74s；旧跨包命令未执行（按计划交接） |
| 16 自查与主控交接 | Ruff 首轮发现3项未使用局部变量和3项未使用测试导入，已删除后复查通过。精确文件清单及覆盖限制见下文；README由主控维护。最终状态中本包仅有清单中的六个代码/测试文件及一份证据记录；其余显示的项目改动与T02/T03或基线同时任务相关，未碰触。 | `ruff.exe check --no-cache app/infrastructure/rag/contracts.py app/infrastructure/rag/embedding_identity.py app/harness/ingestion_attestation.py tests/unit/infrastructure/test_rag_contracts.py tests/unit/infrastructure/test_embedding_identity.py tests/unit/harness/test_ingestion_attestation.py`：首轮1，修正后0 `All checks passed!`；`git diff --check`：0（Git仅报告其他工作树文件的 LF→CRLF 提示）；七允许文件尾随空白检查：0条；最终 `git status --short`：0 |

## 覆盖与交接

三个实现/测试文件覆盖如下：contracts 检查冻结值对象、深层不可变、strict JSON、固定摘要、重复保留的manifest摘要、非bool整数及 RunRecord 状态；embedding identity 检查真实service实例配置、缓存SDK端点、模型/维度漂移、严格binding、指纹/JSON向量和凭证秘密边界；attestation 检查精确字段与版本、intent/manifest/snapshot/result的一致性、scope/owner、身份重算、计数/行完整性、policy/warnings、独立expected对抗、isolation与新旧时间、稳定安全错误，以及重复调用/不变性。三组文件均在局部 fixture 中使用假SDK和远端/DB陷阱，不读用户凭证。

消费者和信任边界：`source_format`、`import_namespace`、`normalizer_version` 等字段在冻结接口中没有独立 expected 输入，因此证明构造器只从已准备记录透传；它们是否真实由可信 preparation 生产者生成须由调用方保证。snapshot 的真实数据库来源、database/schema 可信性、binding 注册与版本证据、resource/isolation 引用文件内容和来源，以及写入/查询时 Identity 实例未被后续替换，也由 T08/T09/T13 的生产者/调用方核查；纯校验器不读文件或服务，不能单独证明这些外部事实。README由主控维护。

允许路径共七个：`app/infrastructure/rag/contracts.py`、`app/infrastructure/rag/embedding_identity.py`、`app/harness/ingestion_attestation.py`、`tests/unit/infrastructure/test_rag_contracts.py`、`tests/unit/infrastructure/test_embedding_identity.py`、`tests/unit/harness/test_ingestion_attestation.py`、`docs/rag-work/evidence/t04/2026-10-16-t04-verification.md`。未运行旧跨包 embedding/knowledge_ingestion/rag_d 回归；未连接真实 PostgreSQL、远端 embedding或执行恢复落盘；未安装依赖、commit或push。跨包回归由主控满足步骤15条件后运行并追加结果，本包结果不能表述为 G1/G2 通过。

## 主控定向复审修订（2026-10-16）

复审指出 B1 冻结值和 encoding_format 秘密边界尚未落实，先补针对性用例再修改实现。红灯结果：联合命令 exit 1，197 passed、15 failed（7.87s），失败覆盖未冻结 preparation 值、危险/不支持 encoding_format、JSON/fingerprint 重验证、build/validate 边界。修改后同一联合命令 exit 0，212 passed（1.96s）；Ruff 对限定六个实现/测试文件 exit 0，`All checks passed!`。这些结果更新步骤14/15之后的最新包内结果；原步骤14/15结果保留为首次通过记录。

定向修订为：`source_format` 固定 `epub`；preparation 与证明的 `normalizer_version`、`chunking_version`、`doc_protocol`、`chunk_protocol` 固定为 `doc-norm-1`、`chunk-policy-1`、`doc-v1`、`chunk-v1`。build 从原 preparation 校验，不填默认；validate 对证明执行同一固定值核验。`import_namespace` 保持原样透传，因为 spec 没有冻结其唯一值或提供独立 expected。encoding_format 只接受冻结默认 `service_default` 与已安装 OpenAI SDK 声明的显式 `float`/`base64`；构造器与 identity 导出/指纹重验证拒绝凭证标记、URL、换行及其他格式。attestation build/validate 对完全匹配其自报指纹的危险 encoding_format 也拒绝，且安全错误不回显标记。Binding 中的 endpoint 仍为仅内存敏感绑定，repr隐藏；调用方不得对 Binding 进行通用 dataclass 序列化，Identity专用 JSON导出拒绝 Binding。

定向验证命令与退出码：

- `.venv/Scripts/python.exe -m pytest tests/unit/infrastructure/test_rag_contracts.py tests/unit/infrastructure/test_embedding_identity.py tests/unit/harness/test_ingestion_attestation.py -q -p no:cacheprovider`：定向红灯1（197 passed/15 failed）；修复后绿灯0（212 passed）。
- `C:/Users/A1985/AppData/Local/uv/cache/archive-v0/QcnXSOJpzJovd_JVU2u2H/ruff-0.15.7.data/scripts/ruff.exe check --no-cache app/infrastructure/rag/contracts.py app/infrastructure/rag/embedding_identity.py app/harness/ingestion_attestation.py tests/unit/infrastructure/test_rag_contracts.py tests/unit/infrastructure/test_embedding_identity.py tests/unit/harness/test_ingestion_attestation.py`：0，`All checks passed!`。

## 定向复审非阻断补充（2026-10-16）

在 `test_embedding_identity.py` 固定其它 Identity 字段，分别构造 `service_default`、`float`、`base64` 三种 encoding_format，断言三种指纹两两不同；原默认固定SHA测试保留。独立用例未依赖 build 产物或动态生成期望值。测试命令 `.venv/Scripts/python.exe -m pytest tests/unit/infrastructure/test_embedding_identity.py::test_encoding_format_values_have_distinct_fingerprints -q -p no:cacheprovider`：0，1 passed in 1.08s。限定六文件 Ruff 重跑：0，`All checks passed!`。按要求未重复全量联合测试；产品代码未改。基线描述已改为“开始时尚未执行测试”。

## 主控组合回归

T02/T03离线fixture稳定并复核后，主窗口将本包三文件及旧embedding/ingestion/rag_d等共十文件组合运行：最终Round 2为547 passed、1 deselected，退出0；本包贡献213项。完整命令与后续最终修订结果见[主窗口记录](../2026-10-16-first-wave-execution.md)。没有真实PG/SDK/judge调用，组合回归不替代正式环境验收。
