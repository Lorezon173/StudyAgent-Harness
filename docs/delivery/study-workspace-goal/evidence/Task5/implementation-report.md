# Task5 第1轮实现报告（冻结待独立代码审查）

## 依据与范围

- 工作树基线 `ebb49fc`，分支 `codex/frontend-ui-optimization`。
- 执行计划 `docs/superpowers/plans/2026-10-24-task5-round1.md`；独立计划审查证据 `docs/delivery/study-workspace-goal/evidence/Task5/round1-plan-review.md`，计划 SHA256 `b2204f6fb1ed10b8c4a6d335ec8b21282b56f0b1a3c1302632ab3604ad2a7b95`。
- 已完整读取计划、AGENTS.md、CLAUDE.md、权威 raw 中主题数据/API/摘要及函数设计，并载入 Karpathy、TDD 和 writing-good-tests。
- 本轮仅主题画像管理和真实摘要；未实现 Task6 会话 API、Task7 教学上下文、Task8 在线增量提交、UI 或自动规划，无新增表/迁移。

## 文件与行为

新增产品 `app/orchestration/profile_service.py`、`app/api/topic_profiles.py`；扩展 `app/models/workspace_schemas.py`；`app/main.py` 仅新增路由 import 和注册。旧 `app/api/profile.py` 未改。

- ProfileService.create 先 flush UUID 画像，再 flush 同名 UUID 节点。初始 profile/node revision=0、mastery=null、practice_count=0；同名不合并。
- list_owned 始终过滤 JWT owner，created_at DESC/id DESC 稳定排序，limit+1 分页；URL safe base64 的时间+ID JSON 游标严格解码，错误映射422。
- _get_owned 对本人画像查询；读路径 PostgreSQL 使用共享行锁，写路径使用排他行锁。跨账号或节点不属于画像返回404。
- _advance_revision 用 owner/id/expected_revision 条件 UPDATE，只在命中时 revision+1，随后 refresh ORM。profile metadata 与节点写入在同一调用方事务；修改节点另增 node revision，创建节点 revision=0。
- _ensure_snapshot_transaction 在 SQLite 取实际 driver_connection.in_transaction；若只有 SQLAlchemy 逻辑 autobegin，则发 BEGIN。保留已有真实事务，不 begin(session) 重入、不 commit 或 reset 调用方事务。
- get_detail 返回 profile 元数据对象、profile_revision、全部节点（包含 archived）与真实边；get_summary 在同一读事务内取详情及当前本人画像最近10条真实证据，并连接实际 session/message/request 核对归属。
- summary 均值仅计算未归档且 mastery 非 null 节点；coverage 单独计算 assessed/total。无评估 score=null、coverage=0；全归档 score/coverage=null；归档证据仍可追溯，边要求两端均活跃。
- Profile/Node 写 DTO extra forbid，名称 trim 后非空、长度限制、严格字符串、非 bool 非负 expected_revision；手动节点写只开放 title/description/archived，不开放掌握度/练习次数等字段。Patch 用显式字段集，空修改422。
- 路由用现有真实 JWT get_current_user；写成功只调用一次 commit，所有异常 rollback；读不 commit，由依赖关闭会话释放锁。

新增测试 `tests/unit/api/test_topic_profiles_api.py`、`tests/integration/test_topic_profiles_service.py`。

## 实际命令与结果

证据均在 `docs/delivery/study-workspace-goal/evidence/Task5/`。已有 .venv，未安装库；API/数据库命令通过正常 require_escalated 原生审批执行。最初一次只读审批超时后仅重试一次并成功，未改沙箱/系统权限。

1. API 红灯：`.venv/Scripts/python.exe -m pytest tests/unit/api/test_topic_profiles_api.py -q`。
   - `round1-api-red.log`：17 failed in 8.40s。未注册端点导致405/404等行为失败，没有收集错误。
2. 完成最小实现后同 API 命令：
   - `round1-api-green.log`：17 passed in 8.58s，无 warnings。
   - 真实 JWT 无 get_current_user override；每例独立文件 SQLite、每连接 FK ON、真实 user1/user2。覆盖 UUID/同名/null初始节点、改名ID稳定/显式字段、节点新增及revision、旧版本409无覆盖、owner/node归属404、只读字段和严格类型422、80/null/归档/恢复及真实 session/request/message/evidence 来源、同时间分页与非法游标。
3. 服务测试：设置独立 `WORKSPACE_TEST_DATABASE_URL` 指向 `127.0.0.1:55440/goal_workspace`，执行 `.venv/Scripts/python.exe -m pytest tests/integration/test_topic_profiles_service.py -m 'integration or not integration' -q`。
   - `round1-service.log`：8 passed in 6.33s，无skip。SQLite4项、真实PG4项；SQLite每连接 FK ON，PG每例创建 `workspace_task5_<uuid>` 随机子库，finally只删除本例子库。未操作业务库或读取 .env 文件内容。
   - 中断时命令句柄 session_id=12445；恢复仅 poll 同句柄，确认正常退出，未重跑已绿 API17/service8。
   - 覆盖 get_detail/get_summary 读期间另一连接 CAS 后修改节点/边/证据，观察读版本及释放后的新版本；调用方已有未提交真实事务不会被读取/修改服务擅自提交；旧revision冲突；初始节点 flush 注入异常后 caller rollback，画像与节点全部无残留。
4. 旧 profile API 兼容：同进程包装设置全新 TEMP DATABASE_URL、应用 engine 各 SQLite 连接 FK ON，init_db 后显式查询并打印 FK，再 `pytest.main(['tests/unit/api/test_api.py::test_profile', '-q'])`。
   - 首次包装器在 connect 回调中错误地同步取 aiosqlite cursor.fetchone，初始化时 TypeError，测试尚未执行。保留 `round1-legacy-profile.log`；这不是产品错误。修正为异步 connection.scalar 查询 FK 后仅重跑此未通过项。
   - `round1-legacy-profile-final.log`：1 passed、1 Starlette 既有弃用 warning in 1.01s。
   - 实际默认隔离库 `sqlite+aiosqlite:///C:/Users/A1985/AppData/Local/Temp/task5-legacy-profile-79e6c142ac7e4019a3115c5bc8761ce6.db`，打印 `Default SQLite foreign_keys: 1`。临时库结果不代表用户工作区旧 SQLite 已迁移。
5. `git diff --check -- app/main.py app/models/workspace_schemas.py` 无空白错误，仅 Windows 换行规范化提示；新增产品与测试五个文件执行 py_compile 成功。未重复全套或迁移测试。

已知前轮全量基线 Retriever context_precision=None 失败仍存在，本轮未改评估契约，未宣称全套全绿。未运行 tests/api/test_profile_real.py：其历史 fixture 没有 seed user，外键默认关闭；主会话明确本轮仅跑旧 test_api::test_profile，不扩大 fixture 修正。

## 事件同步方式与必须保留的证据限制

并发测试完全使用 asyncio.Event 与 wait_for 超时，不 sleep；每例外层25秒界限，事件和writer完成等待10秒。reader 在读到profile后设置 profile_read，writer 等待此事件，并在 SQLAlchemy before_cursor_execute 看到 UPDATE topic_profiles 时设置 writer_attempted。reader 等到该事件后继续读取节点/边/证据，断言 revision0、score40、edge .2、evidence40；先 reader.rollback 释放事务，再等待 writer commit；最后新 session 读到 revision1、score90、edge .9、evidence90，防止测试互锁。

**当前8项服务绿灯不能单独证明 PostgreSQL 写者已实际进入锁等待，也没有直接断言 SQLite driver.in_transaction。** writer_attempted 在执行前事件设置，writer_committed 尚未置位也可能只是写者还没被调度完成；本轮没有 pg_locks/pg_stat_activity 等额外观测，也没有安排 writer 先完成提交再检查读快照。因此不能以当前通过结果宣称已充分验证真实阻塞/真实BEGIN。产品采用了共享锁/显式BEGIN，但实现存在与否不能替代测试证据。此具体缺口已向主会话报告，产品/测试保持不改，下一轮须先计划审查再补强。

服务“新 session”读取可能复用同一 engine 的空闲物理连接；并发reader/writer确实同时持有不同连接，但结束后读取不声称独立新engine/全新物理连接。PG测试证明随机真实数据库内事务行为，不代替生产重启持久化验收。

## 冻结清单与边界

以下 SHA256 为本轮产品/测试冻结版本：

| 文件 | SHA256 |
|---|---|
| app/orchestration/profile_service.py | F2BCB0C87585CA44FB8A118EE67D4930796F42ED21E19E13628897DB10E766C4 |
| app/api/topic_profiles.py | FF6FC7D8F7AE4889251A12ABBB84FF90E604DA4254A07B78D4E349296622CA2D |
| app/models/workspace_schemas.py | 71BA15361CD33B7EFBDCA3120D3297B3C8263D6ACA48EEC5E9C6DBF7DC0B3CE2 |
| app/main.py | 2C0E711207DF6563ED4E9BFAFDE908943297183A7D07A23BFD0F4A17996B6822 |
| tests/unit/api/test_topic_profiles_api.py | 1B48F0A20A0BC3EEEB22A6AE4BE2419E2578E507C78D34198668F21B01E13B17 |
| tests/integration/test_topic_profiles_service.py | 9D74B4F118BBB8F9CEF4F2DC45D25011F0783D05C88A202C03385A79330088C5 |

产品/测试冻结后只写本报告。无未轮询执行会话。主会话生成包含未跟踪新增文件的审查包并进行独立code review；本报告不是Task5完成声明。

未修改 README、asset inventory、status、raw、plan；保护其原有未提交改动。README和账本更新交主会话收尾。未提交、推送、合并、部署或自行派reviewer。未越序实现Task6。

## 第2轮：真实锁等待、事务与独立物理连接证据

执行计划 `docs/superpowers/plans/2026-10-24-task5-round2.md`，SHA256 `9957c9fcaa6407f4d67feecfbbabfce46d515b9ef04467ab258115a27eb2bda5`；独立PASS证据 `docs/delivery/study-workspace-goal/evidence/Task5/round2-plan-review.md`。本轮仅改服务集成测试、API游标测试、ProfileService._decode_cursor规范校验及报告/日志。原事务/共享锁实现、schema和API字段保持不改。

### 游标红绿

1. 新增参数化 `test_cursor_rejects_noncanonical_but_decodable_inputs` 三项：日期only、带padding、标准Base64专用字符。每项先独立验证 base64.b64decode(validate=True)、json.loads、datetime.fromisoformat 与 UUID 原本均成功。
   - 标准字符案例使用 UTF8 BOM+合法时间/UUID JSON，base64产生 `/`；json.loads(bytes)接受BOM，因此这不是原本就无效的乱码。
   - 日期only为合法UUID+`2026-01-01`；padding使用合法JSON载荷，在必要时加合法尾部空白确保原base64带 `=`。
2. `.venv/Scripts/python.exe -m pytest tests/unit/api/test_topic_profiles_api.py -k noncanonical -q`：`round2-cursor-red.log` 为 **3 failed、17 deselected in 4.38s**。三个错误均为API实际200而应422，收集和前置解码断言均成功。
3. `_decode_cursor` 仅增加两项往返检查：解码字节再次URL-safe编码并去padding后必须等于原输入；naive datetime.isoformat必须等于输入日期文本。既有JSON键集合/字符串/UUID校验保留。
4. `.venv/Scripts/python.exe -m pytest tests/unit/api/test_topic_profiles_api.py -q`：`round2-api.log` 为 **20 passed in 7.63s，无warnings**；包括原有生成游标正常分页、同时间稳定排序和owner过滤。

### 数据库测试补强

- `connection_fingerprint(connection)` 在同一个仍持有连接上获得实际driver强引用及PG pg_backend_pid。reader和writer改为显式持有两个engine.connect连接；取得PID后的辅助查询事务先rollback，再把session绑定这些连接。读取结束/写入提交后连接仍处于打开上下文，直到独立物理连接验收完成才关闭。
- SQLite模拟JWT用户SELECT后先确认driver.in_transaction=False，再由Service读到profile后直接断言driver.in_transaction=True。测试检查实际driver属性，不以SQLAlchemy逻辑事务替代。
- PostgreSQL reader读取profile并持共享锁后通知writer；第三个独立NullPool observer连接有界查询指定writer PID的pg_stat_activity与pg_blocking_pids，限定current_database。只有wait_event_type='Lock'且阻塞PID包含本reader后才允许reader继续。每次查询前清理统计快照，轮询靠数据库await主动让出，无sleep。
- reader/profile-read、writer-PID-ready、observer-confirmed、reader-released分别用事件标识。observer异常或超时仍由finally先rollback reader，再取消/收束writer与observer；不会先等待被自己锁住的writer。保留外层25秒、事件/任务10秒、observer轮询6秒界限。
- 原rev0/节点40/边.2/证据40快照断言保留；reader释放后writer提交，再由新engine独立读取rev1/节点90/边.9/证据90。
- `independent_read` 每次创建全新async engine+NullPool，SQLite每连接FK ON并readback=1。一次独立连接取画像/节点/边/证据/用户记录，PG PID必须不同于仍存活reader/writer/caller；SQLite比较强引用对象 `is not`，不能只以可复用的id证明不同连接。日志的对象id只是显示，断言使用对象身份。
- caller真实事务rollback、metadata commit、旧revision拒绝和初始节点flush失败rollback的最终结果，均改为此独立读取，而非同pool新session。

正常命令：设置既有独立55440 PG URL，`.venv/Scripts/python.exe -m pytest tests/integration/test_topic_profiles_service.py -m 'integration or not integration' -q -s`。

`round2-service.log` 为 **8 passed in 9.55s，无skip/warnings**。没有更改产品锁或BEGIN实现；此正常组只执行一次。

实际观察记录（均本轮随机测试子库）：

| 场景 | reader PID | writer PID | observer PID | 数据库等待事实 | 独立读取PID |
|---|---:|---:|---:|---|---:|
| PG get_detail | 2687 | 2688 | 2689 | Lock / transactionid / blockers=[2687] | 2690 |
| PG get_summary | 2692 | 2693 | 2694 | Lock / transactionid / blockers=[2692] | 2695 |
| PG caller事务 | 2697 | — | — | rollback后rev0、commit后rev1、冲突后仍rev1 | 2698/2699/2700 |
| PG初始节点失败 | 2702 | — | — | caller rollback后画像和节点均空 | 2703 |

SQLite两个并发场景打印实际 `SQLITE_REAL_TRANSACTION True`，driver分别为1909100690800、1909101057888；独立driver分别为1909103173680、1909103573808。各场景用强引用身份与仍持有reader/writer逐一核对，不依靠这些数字本身。caller rollback/commit/conflict与初始创建失败也全部输出独立指纹。

### 保护关闭负控制

`round2-guard-controls.log` 保存两个独立Python进程。进程内临时替换类方法，进程退出自动恢复，工作树完全没有回退或修改产品保护：

1. PG进程临时让 `_get_owned` 的read模式传lock=None，仅选 `-k 'postgresql and get_summary'`。**1 failed、7 deselected in 2.23s**，observer实际读到 writer PID2708 为Client/ClientRead、blockers=[]，故触发 `PG writer did not enter reader lock wait`。不是连接错误或超时异常。
2. SQLite进程临时让 `_ensure_snapshot_transaction` no-op，仅选 `-k 'sqlite and get_summary'`。**1 failed、7 deselected in 0.99s**，实际打印 `SQLITE_REAL_TRANSACTION False`，触发 `SQLite real transaction missing`。不是seed或收集错误。

每个控制进程使用pytest logreport收集实际call失败，除要求exit=1、恰好1项失败，还断言失败长文本包含对应预期数据库断言；均输出 `NEGATIVE_CONTROL_VALID`。负控制不计产品失败，不把预期红灯改成测试通过；正常组8绿证据与此互补。两进程无遗留运行句柄。

### 第2轮冻结

当前三个变更文件SHA256：

| 文件 | SHA256 |
|---|---|
| app/orchestration/profile_service.py | 021C31E38AEF4587DC119B014619AF1C47D9FF0311E74F0E4D2A14CB5E82E196 |
| tests/unit/api/test_topic_profiles_api.py | 7F81174849682BEB2C7FFA872FBB85978D63B1F4FD0476285DD18FBBE4A7F02D |
| tests/integration/test_topic_profiles_service.py | BF5D4FF8913FD0AA40DCA2D76926B581296D29385F9DE9B33E69B218C2939D60 |

第1轮router/main/schema冻结版本保持；本轮完成上述验证后产品和测试再次冻结。未重复旧profile、全量或迁移；旧Starlette警告与Retriever全量基准失败沿用第1轮记录，不宣称已修复。真实数据库锁/事务/独立连接证据已补齐，仍不代替产品上线、PG重启、连续教学和在线画像增量验收。

未改README/status/raw/plan，未提交、推送、部署或自派reviewer。主会话进行相对初审包的范围review后收尾，本报告不是Task5 DONE声明。
