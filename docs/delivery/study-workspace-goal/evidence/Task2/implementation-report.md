# Task2 实施报告

状态：画像模型、兼容Store与迁移已实现，独立审查两项Important已在fix round1修复，等待范围复审；未提交、未推送。首次Task2定点26项全通过；本次Store+Graph单测30项通过。完整默认回归有1项原基准同样复现的评估失败，详见下文。

## 范围与实现

- 新增 `topic_profiles` / `profile_nodes` / `profile_edges` 三表；未创建 `profile_evidence`，未扩展 sessions/chat_requests（留Task3）。旧 mastery 两表及其语义保留。
- 画像归属 FK 指向 users；画像 `(user_id,id)` 与节点 `(profile_id,id)` 唯一约束为后续归属链提供候选键。边两端用 `(profile_id,node_id)` 复合外键确保同画像，同用户不同画像/不同用户均不可串联。
- UUID标识不依赖节点标题；未评估 mastery 保持 NULL。
- `TopicProfileStore.create(user_id,name,scope)` flush父画像并返回ORM记录；`get_owned(user_id,profile_id)` 返回本人记录，否则None。Store不commit。
- `ProfileMasteryStore(db,profile_id)`保留既有四方法user_id签名，逐方法验证归属。load读出节点revision与画像revision；节点save执行条件UPDATE；无load且无显式节点revision的已有节点覆盖被拒绝。边独立记录已读/本实例创建的键，禁止通过save_nodes获得覆盖未读边的授权；profile CAS防止旧画像快照覆盖新结果。
- 同实例的load_nodes/load_edges发现profile revision改变会拒绝混合快照；save发生异常后该Store失效，caller必须rollback并新建Store，防止沿用失败事务缓存。
- 兼容save仅用于受控初始化/离线；Task8在线评估必须实现增量提交，不能把本Store接成旧全图写回。
- 新迁移revision `20261023_topic_profiles`接在`20260729_chunk_id`之后。仅有效旧图谱owner获得唯一legacy画像；确定性UUID5使用owner及完整旧topic_id，500字共同前缀、同标题、跨owner不碰撞；已存在legacy复用，不向normal画像复制。
- legacy来源标记在 `topic_profiles.kind=legacy`；边保留原真实source以兼容现有EdgeSource，不伪造消息或评估证据。旧表原值完整保留，新节点不新增raw未定义的confusion_with字段。
- 旧边缺任一端点会在DDL和复制前明确拒绝。downgrade只允许三张新表全部为空；存在任何画像数据均拒绝，提示先导出和明确移除数据。

## 模型注册路径

- `app/core/database.py`定义Base后显式导入原`app.models.tables`与新`app.models.workspace_tables`；因此仅导入Base再create_all也包含三张新表。
- `alembic/env.py`原有Base/旧tables导入自然覆盖同一模型注册；新增标准`config.attributes["connection"]`入口，测试把开启SQLite外键的同一连接交给Alembic全过程使用。未修改历史迁移文件。

## TDD与验证证据

全部命令在项目根目录运行，使用项目已有 `.venv\Scripts\python.exe`，未安装依赖。DB/API执行走工具原生审批路径。

1. `.\.venv\Scripts\python.exe -m pytest tests/unit/storage/test_topic_profile_store.py -q`
   - `evidence/Task2/red.log`：12 failed；首个断言证明Base缺三张新表，其他证明Store模块尚不存在。
2. `$env:WORKSPACE_TEST_DATABASE_URL='postgresql+asyncpg://goal_test:goal_test_local_only@127.0.0.1:55440/goal_workspace'; .\.venv\Scripts\python.exe -m pytest tests/integration/test_workspace_migrations.py -m integration -q`
   - `migration-red.log`最初3 failed、2 passed、1 setup ERROR；ERROR是测试先替换同步SQLite URL后首次导入异步Base所致，非产品失败证据。
   - 仅修测试初始化导入顺序后`migration-red-fixed.log`：4 failed、2 passed，无ERROR；SQLite/PG均因缺画像表、脏边未被拒绝出现预期FAIL。
3. `.\.venv\Scripts\python.exe -m pytest tests/unit/storage/test_topic_profile_store.py -q`
   - `revision-red.log`：3 failed、13 passed；发现初始化新节点可绕过未读边保护、load_edges刷新旧节点快照、失败flush后实例未失效。修复三个产品缺口。
4. `$env:WORKSPACE_TEST_DATABASE_URL='postgresql+asyncpg://goal_test:goal_test_local_only@127.0.0.1:55440/goal_workspace'; .\.venv\Scripts\python.exe -m pytest tests/unit/storage/test_topic_profile_store.py tests/integration/test_workspace_migrations.py -m 'integration or not integration' -q`
   - `green-final.log`：**26 passed in 13.03s**，其中16个SQLite Store/注册测试、5个SQLite迁移测试、5个真实PostgreSQL迁移测试。
   - 实跑空库完整历史迁移→upgrade head、新表数据复制/归属FK、可重入前置检查、已有legacy复用、normal不污染、旧数据保留、脏边拒绝、带数据downgrade拒绝、空表降级成功。升级后head断言为`20261023_topic_profiles`。
   - SQLite各连接 `PRAGMA foreign_keys=ON`；PG每用例新建随机 `workspace_task2_<uuid>`子库，结束只删除该测试生成的子库；未清理或写入原有业务库。
   - 额外首轮日志`first-green.log`：19 passed；后续`green.log`：21 passed、1 failed（新增测试在rollback后同步访问过期ORM id触发MissingGreenlet，仅缓存测试ID修正，产品异常保护已生效）。最终结果以green-final为准。
5. `docker exec studyagent-goal-test-pg psql -U goal_test -d goal_workspace -Atc 'SELECT version()'`
   - `pg-version.log`：PostgreSQL 16.15 (Debian 16.15-1.pgdg12+2)，x86_64，64-bit。仅访问主会话授权的独立测试容器 `studyagent-goal-test-pg`，端口55440，无挂载卷。
6. `.\.venv\Scripts\python.exe -m pytest tests/ -q`
   - `regression.log`：**1060 passed、18 deselected、1 failed、1 warning，62.02s**；默认按项目配置排除integration（路径在integration目录但未打marker的旧用例仍会运行）。
   - 唯一失败：`tests/integration/test_retriever_integration.py::test_evaluate_produces_valid_metrics`，`context_precision=None`与float比较触发TypeError。warning是既有Starlette TestClient/httpx弃用提示。
7. 独立进程通过`subprocess.run(['git','show','d0584d9:app/agents/retriever.py'])`只读取原基准源码，用`types.ModuleType`独立namespace加载，并仅将该进程中`app.agents.retriever.RetrieverAgent`临时绑定为原基准class后，执行`pytest.main(['tests/integration/test_retriever_integration.py::test_evaluate_produces_valid_metrics','-q'])`。
   - `baseline-evaluation.log`：原基准同样 **1 failed in 0.46s**，失败位置和值完全相同。进程结束恢复，工作树未变。coordinator、FakeRAGStore、judge及该测试相对d0584d9无diff，调用路径无Base/models依赖；该失败不能归因于本Task2新模型注册。未修改不相关产品或放宽断言。
8. `uvx --offline ruff check app/models/workspace_tables.py app/core/database.py app/infrastructure/storage/topic_profile_store.py app/infrastructure/storage/profile_mastery_store.py alembic/env.py alembic/versions/20261023_topic_profiles.py tests/unit/storage/test_topic_profile_store.py tests/integration/test_workspace_migrations.py`
   - 无法执行：本机没有Ruff工具缓存，离线解析失败；未安装新依赖，不把未执行写成lint通过。`git diff --check -- app/core/database.py alembic/env.py`无输出通过。

## 文件与边界

产品：`app/models/workspace_tables.py`、`app/core/database.py`、`alembic/env.py`、`alembic/versions/20261023_topic_profiles.py`、`app/infrastructure/storage/topic_profile_store.py`、`app/infrastructure/storage/profile_mastery_store.py`；fix round1按ADJ006最小扩展`app/harness/mastery_graph.py`。

测试：`tests/unit/storage/test_topic_profile_store.py`、`tests/integration/test_workspace_migrations.py`。

证据：`docs/delivery/study-workspace-goal/evidence/Task2/`；本报告在`.superpowers/sdd/2026-10-23-study-workspace-core/`。

依主会话分工未改README、asset inventory、status、raw、plan，未提交、未推送。README需主会话补充三表、legacy标记位置、兼容save边界/异常后新实例契约与降级拒绝策略。

## 独立审查修复：fix round1 / 5

主会话完整转达两项Important，并以ADJ006明确授权最小扩展`app/harness/mastery_graph.py`；已载入receiving-code-review技能并核对真实调用路径。没有修改评估契约、README或status，没有重复已通过的迁移/全套。

1. `ProfileMasteryStore.save_nodes`对既有节点仅更新输入实际包含的字段，缺省description/archived不再清空或解归档；同样保留缺省的title/mastery/practice_count/rationale等原值，新节点依原模型/数据库默认值。显式传空串、False仍能更新。
   - 新增真实ProfileMasteryStore→MasteryGraph.load/save→新DB连接读取测试：说明及归档状态保留；后续显式清空/解归档成功，未提供的其他值仍保留。
2. `MasteryNode.mastery`与`add_node`参数类型支持`float | None`，兼容默认0.0未改；`find_weak_prereqs`明确跳过mastery=None，未知不算已证明薄弱。
   - 新增真实Store→Graph.load测试，包含unknown PREREQ及已评估20分PREREQ；前者不报错、不返回薄弱、不生成分数，后者仍返回薄弱；Graph.save并新连接读取后unknown保持NULL、practice_count仍0。

实际命令（两轮相同）：

`.\.venv\Scripts\python.exe -m pytest tests/unit/storage/test_topic_profile_store.py tests/unit/harness/test_mastery_graph.py -q`

- `fix-round1-red.log`：**2 failed、28 passed in 7.81s**。一项断言说明从“人工说明”变空，另一项在None与float比较处TypeError；均为预期产品缺口而非fixture故障。
- 最小修复后`fix-round1-green.log`：**30 passed in 6.66s**。包含18项Task2 Store测试、12项既有MasteryGraph测试。
- `git diff --check -- app/infrastructure/storage/profile_mastery_store.py app/harness/mastery_graph.py tests/unit/storage/test_topic_profile_store.py`无输出通过。

本轮改动仅`profile_mastery_store.py`、`mastery_graph.py`、`test_topic_profile_store.py`和本报告/Task2日志。产品diff再次冻结，交主会话范围复审；未提交、未推送。
