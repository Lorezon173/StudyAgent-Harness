# T02 执行证据（进行中）

日期：2026-10-16。当前状态：实现未完成，等待本包测试与主控 review；此记录只登记实际执行，不代表 plan 预期已达成。

## 基线与边界

- 冻结 spec：`docs/rag-work/specs/2026-10-16-rag-mvp-contracts-v1.md`，SHA-256 `31379383758b82c82d5fe583f371e590f4b187ad0371744edcef635743b41f95`，与 plan 要求一致。
- 基线工作区包含其他并行任务的改动；没有撤销或改写这些内容。本包仅写 plan 授权的 T02 文件，不提交、不推送、不切分支。
- 离线隔离：测试 fixture 屏蔽 SDK/PG 初始化；数据库测试仅允许内存 SQLite 和受控连接替身。没有调用真实 PostgreSQL、Embedding SDK 或 LLM。
- `uv run --no-sync pytest ...` 在测试收集前因 UV 无权写入 AppData interpreter cache 失败；未安装依赖。改用 `.venv/Scripts/python.exe -m pytest`。默认 `tmp_path` 也因沙盒临时目录不可写报错；使用工作区 `--basetemp .pytest-tmp-t02` 后测试进入执行。

## 已完成的红绿组

| 组 | RED 实测 | GREEN 实测 |
|---|---|---|
| T01 Embedding 批次/维度 | `.venv/Scripts/python.exe -m pytest tests/unit/infrastructure/test_embedding.py -q -p no:cacheprovider`：退出码 1，16 failed、12 passed；新增断言暴露设置维度漂移、短/长响应和 index 顺序/有效性问题。 | 同命令：退出码 0，28 passed。实例维度绑定，响应长度与批内 index 校验/重排已实现。 |
| T02 provider 整批验证 | `.venv/Scripts/python.exe -m pytest tests/unit/infrastructure/test_pgvector_provider.py -q -p no:cacheprovider --basetemp .pytest-tmp-t02`：退出码 1，10 failed、32 passed；短/长批次、维度及数值校验未在 insert 前完成。 | 事务定向命令 `... -k 'failure or ack_loss or rollback'`：退出码 0，4 passed、42 deselected；全文件命令：退出码 0，46 passed。SQLite/替身结果不能证明真实 PG 原子性。 |
| T03 兼容计数红灯 | `.venv/Scripts/python.exe -m pytest tests/unit/harness/test_knowledge_ingestion.py -q -p no:cacheprovider --basetemp .pytest-tmp-t02 -k boolean_as_confirmed_integer`：退出码 1，1 failed、50 deselected。旧 `ingest_file` 将 provider 返回的 `True` 当作整数 1 并报告 `ok`；断言要求 `index_unconfirmed`、written=0 和固定安全 warning。 | 尚未实现。 |

## 初始隔离回归

- Embedding 原有测试：同上 Python 命令，退出码 0，11 passed。
- Provider 原有测试：同上 Python 命令（加 `--basetemp .pytest-tmp-t02`），退出码 0，27 passed。
- Chunking 只读回归：`.venv/Scripts/python.exe -m pytest tests/unit/harness/test_chunking_service.py -q -p no:cacheprovider`，退出码 0，17 passed。
- Ingestion 原有回归：第一次使用默认临时目录时在 `tmp_path` fixture 阶段失败；改用 `--basetemp .pytest-tmp-t02` 后，退出码 0，10 passed。

## 接下来

T03 整文件的实施前 RED：`.venv/Scripts/python.exe -m pytest tests/unit/harness/test_knowledge_ingestion.py -q -p no:cacheprovider --basetemp .pytest-tmp-t02`，退出码 1，40 failed、11 passed；主要为两阶段方法和 Prepared 类型缺失，另复现 bool 计数误报成功。

Prepared 快照子步：先运行定向构造器测试，退出码 1，1 failed、51 deselected，原因为 `PreparedIngestion` 尚不存在；实现深冻结值对象、固定安全异常、intent 副本与规范 JSON/manifest SHA helper 后，命令 `... pytest tests/unit/harness/test_knowledge_ingestion.py -q -p no:cacheprovider --basetemp .pytest-tmp-t02 -k prepared_ingestion_constructor_freezes_snapshot_and_intent` 退出码 0，1 passed、51 deselected。

`prepare_file` 子步：使用同一受控命令并筛选 `prepare_file or prepare_snapshot or prepared_manifest_matches or preparation_error or prepared_ingestion_constructor`，退出码 0，21 passed、31 deselected。覆盖无写入副作用、一次提取/切块、源变化拒绝、嵌套冻结/intent 隔离、固定 manifest 向量、乱序/重复行摘要、非法 owner/策略、精确异常摘要及 error 映射。本步使用既有假提取器、固定 chunker、记录型 vector provider；未调用外部服务。

随后实现 `ingest_prepared` 的类型/身份/策略/行清单复核与一次隔离 docs 写入，`ingest_file` 只委托 prepare/ingest。第一次整文件 GREEN 尝试退出码 1，50 passed、2 failed，暴露兼容入口错误文本需保留固定 `global`/`private` 标记；改为仅追加白名单字段名后，同命令退出码 0，52 passed。

新增防御复核 RED：`.venv/Scripts/python.exe -m pytest tests/unit/harness/test_knowledge_ingestion.py -q -p no:cacheprovider --basetemp .pytest-tmp-t02 -k 'untrusted_warnings or boolean_private_chunk_owner or inconsistent_snapshot'` 退出码 1，7 failed、11 passed。复现私有 `user_id=True` 通过，以及 manifest 中 owner bool、index bool、locator bool/float 与原值 Python 相等、旧 digest 未重算而放行；也复现 warnings 可注入 API key/异常文本。修复为显式 owner 类型检查、从 manifest 实际 rows 重算规范摘要并逐行比对规范 JSON 字节；构造、intent 导出和 ingest 共用 warnings 白名单验证。相同筛选命令退出码 0，18 passed、44 deselected。

T03 最终定向文件回归：`.venv/Scripts/python.exe -m pytest tests/unit/harness/test_knowledge_ingestion.py -q -p no:cacheprovider --basetemp .pytest-tmp-t02` 退出码 0，62 passed。接下来进行四文件限定回归、缓存 Ruff、`git diff --check` 与允许文件审计；尚未执行的命令和限制会在完成时追加，主控单独维护 README 与 plan 状态。

## 独立 review 修复与最终检查

- P2 导出校验 RED：命令 `.venv/Scripts/python.exe -m pytest tests/unit/harness/test_knowledge_ingestion.py -q -p no:cacheprovider --basetemp .pytest-tmp-t02 -k 'constructor_freezes_snapshot_and_intent or to_intent_metadata_rejects_invalid_direct_snapshot or private_intent_metadata'` 退出码 1，5 failed、1 passed、61 deselected；其中四个 owner/schema/policy/manifest digest 用例确认非法直接快照原先可以导出。剩余一项是测试快照将 `chunk_size=10` 与默认 `chunk_overlap=50` 组合成非法策略，修正为 overlap=0 后重跑。
- P2 GREEN：同一命令退出码 0，6 passed、61 deselected。合法快照的构造深冻结、private owner=7 的 metadata 导出与返回副本隔离均通过；非法 owner/schema/policy/摘要在导出前由完整快照校验拒绝。校验不访问源文件或外部服务。
- 最终四文件回归：`.venv/Scripts/python.exe -m pytest tests/unit/harness/test_knowledge_ingestion.py tests/unit/harness/test_chunking_service.py tests/unit/infrastructure/test_pgvector_provider.py tests/unit/infrastructure/test_embedding.py -q -p no:cacheprovider --basetemp .pytest-tmp-t02` 退出码 0，158 passed。
- 六文件 Ruff：缓存版 `ruff 0.15.7` 原始命令 `ruff.exe check --no-cache app/harness/knowledge_ingestion.py app/infrastructure/rag/pgvector_provider.py app/infrastructure/rag/embedding.py tests/unit/harness/test_knowledge_ingestion.py tests/unit/infrastructure/test_pgvector_provider.py tests/unit/infrastructure/test_embedding.py` 退出码 1，唯一诊断为 `tests/unit/infrastructure/test_pgvector_provider.py:667` 的 E402。`git show HEAD:tests/unit/infrastructure/test_pgvector_provider.py` 确认该行 `VisibilityContext` 导入在基线中已存在，未改动该无关代码。之前用 `ruff check --no-cache --ignore E402` 检查同六文件退出码 0；原始 lint 命令仍记录为未全通过。
- `git diff --check` 退出码 0；Git 打印多条无关既有文件的 LF→CRLF 提示。最终分支仍为 `codex/rag-mvp-first-wave`。本包代码/测试改动仅在六个授权文件；本证据文件是唯一 T02 文档写入。没有修改 README、plan、spec 或其他包文件，也未 commit/push。
- 最终验证仍只覆盖受控替身与本地 SQLite；没有运行真实 PostgreSQL、Embedding SDK 或 LLM。UV 受限与默认 pytest 临时目录权限问题详见“基线与边界”。工作区临时目录 `.pytest-tmp-t02` 因清理动作被中断而保留；它仅包含 pytest 临时样例，不是产品输出或验收证据。

交接状态：T02 代码与本地离线验证稳定，等待主控复审。README 与 plan 状态由主控统一维护；本记录不宣称真实 PG 事务验收或全局 MVP 放行。
