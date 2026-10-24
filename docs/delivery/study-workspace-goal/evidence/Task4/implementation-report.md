# Task4 第1轮实施报告：私有手动文本知识库

状态：已实现并通过本轮指定验证，产品与测试 diff 冻结，等待主会话独立 code review。未提交、推送、部署；不能据此标记 Task4 DONE 或宣称完整产品已上线。

基准分支 `codex/frontend-ui-optimization`、HEAD `7ff4c02`。依据已批准 raw `superpowers/frontend-ui/2026-10-23-final-implementation-raw.md` 的第二层 A/D/F 与第三层 LibraryStore 契约，执行已独立 PASS 的 `docs/superpowers/plans/2026-10-24-task4-round1.md` v1.1，SHA256 `0bbcf6667be7ba5c11ed291fd207958061685012a1675b727be5a4e3627c960f`。计划审查证据见 `docs/delivery/study-workspace-goal/evidence/Task4/round1-plan-review.md`。

## 实现内容

- 新增 `library_items`：整数 id、user_id、可空 profile_id、name、description、content_text、source_type、created_at、updated_at。owner 外键及 `(user_id,profile_id)` 复合外键保证真实归属；owner/id 与 owner/profile/id 索引用于列表。
- 新 DTO 禁止 extra：正文 id/user_id/source_type 任何值均422；name严格字符串、trim后1–128；description上限2000、content_text上限100000，均不接收null。profile_id为最大36字符可空字符串。PATCH用显式字段集，缺字段保留、空补丁422、profile_id:null解除关联。
- 保留 KnowledgeCreateRequest/KnowledgeResponse 公开类，复用新 DTO。旧 id/name/description 及列表数组形状保留，新增 owner/profile/text/source/time。
- LibraryStore 所有查、搜、改、删带 user_id；create/update再次核对画像属于本人。先检查目标画像再改字段，避免部分写入；方法只flush，不commit/rollback。update显式refresh数据库更新时间，避免异步响应序列化隐式IO。
- `/api/knowledge` 全部使用真实 get_current_user JWT 验签与用户存在检查。新增 GET/PATCH详情，别人或缺失资源均404；POST/PATCH/DELETE成功一次commit，异常rollback后抛出，不返回伪成功。source_type服务端固定manual。
- 列表按id DESC，limit默认50、1–100、before_id正整数；q上限256，name/description/content_text字面子串OR，反斜杠/%/_转义且绑定SQL参数；profile过滤始终与owner条件并用。
- 新迁移 `20261023_private_library` 接 Task3 head；不读取、复制、删除旧 knowledge/向量资产。新表有数据拒绝降级，空表才删除。
- 旧test_api知识CRUD仅改隔离fixture与真实注册所得JWT，原创建/列表/删除断言保留。专用knowledge_db_client在唯一物理内存SQLite连接开启并断言FK=1；原db_client及无关用例行为不改。旧迁移默认CLI测试仍调用upgrade(head)，仅成功分支版本预期更新至Task4，失败分支仍CURRENT与原结构/数据回滚断言。

## 实际验证与证据

已有 `.venv/Scripts/python.exe`，未安装依赖；API/数据库命令均经原生 require_escalated 路径，未改沙箱或系统设置。证据目录 `docs/delivery/study-workspace-goal/evidence/Task4/`。

1. 红灯：`.venv/Scripts/python.exe -m pytest tests/unit/api/test_private_knowledge_api.py -q`
   - `red.log`：24 failed in 11.39s。旧接口无登录返回200、新字段缺失、library_items不存在，确认行为尚未实现；不是收集错误。
2. 迁移红灯：设置独立 `WORKSPACE_TEST_DATABASE_URL=postgresql+asyncpg://goal_test:goal_test_local_only@127.0.0.1:55440/goal_workspace`，执行 `.venv/Scripts/python.exe -m pytest tests/integration/test_private_library_migrations.py -m 'integration or not integration' -q`。
   - `migration-red.log`：SQLite与真实PG各失败1项，仍为Task3旧head，2 failed in 3.40s。
3. 初次API绿灯组合：`.venv/Scripts/python.exe -m pytest tests/unit/api/test_private_knowledge_api.py tests/unit/api/test_api.py -q`
   - `api-final.log`：29 passed、1 failed、2 warnings in 11.40s。新API24项全通过；旧 `test_sessions_empty` 不使用隔离fixture，直接读工作区旧SQLite，报 `no such column: sessions.profile_id`。未为其迁移或写工作区旧库，未改无关测试断言。
4. 独立数据库环境回归：先显式设置全新 TEMP 路径DATABASE_URL、调用init_db按当前模型建表，再执行同组API，初次30 passed/2 warnings in 9.33s。其后按计划完善旧知识fixture FK=1与两项实际事务契约测试，执行最终同组。
   - 最终命令使用 `.venv/Scripts/python.exe -` 同进程包装：给应用engine的每个SQLite连接注册PRAGMA foreign_keys=ON；打印DATABASE_URL；`asyncio.run(init_db())`；`pytest.main(['tests/unit/api/test_private_knowledge_api.py','tests/unit/api/test_api.py','-q'])`。
   - `api-isolated-final.log`：32 passed、2 warnings in 9.71s。
   - 实际隔离默认库：`sqlite+aiosqlite:///C:/Users/A1985/AppData/Local/Temp/task4-api-96029ca1e84f4e6da28c9744d2fd9e6e.db`；未删除以便回溯。新私有库测试各例另用tmp_path文件、每连接FK ON、真实user1/user2与画像父先flush、每请求独立session；JWT真实签发且没有override get_current_user。旧sessions/profile等既有auth_headers仍沿用其历史鉴权替身，不把这些旧用例计为真实鉴权证据。
   - 覆盖：全部端点未登录401及JWT用户不存在401、跨账号读改删404、未知/外部画像404、只读字段POST/PATCH422且新连接无变化、边界类型/长度/null/empty、持久化CRUD新连接读取、同时间id游标无重复遗漏、owner/profile/字面q组合、数据库复合FK拒绝越权、SQLite触发器写失败完整回滚。
   - 两项事务契约测试验证Store create未提交对新连接不可见、create/update/delete可由caller rollback；Store再次检查画像owner；API每写一次commit，模拟commit失败后API执行rollback且新连接无残留。
5. 迁移最终组合：设置上述独立WORKSPACE_TEST_DATABASE_URL，执行 `.venv/Scripts/python.exe -m pytest tests/integration/test_private_library_migrations.py tests/integration/test_workspace_migrations.py -m 'integration or not integration' -q`。
   - `migration-final.log`：23 passed in 18.87s，无skip。现有独立容器 `studyagent-goal-test-pg`、本机55440可用，每例随机workspace_task4/workspace_task2子库，结束仅删除本例随机子库；未创建容器、未触碰另外三个业务容器。
   - 覆盖历史迁移至Task3后seed旧knowledge/用户画像、升级head，新连接确认旧数据原文不变、新表为空、合法卡片真实保存、数据库拒绝跨账号画像、新表非空拒绝降级并保持版本与数据、清空后降级仅删新表；旧Task2/3迁移和默认CLI成功/注入失败回滚均通过。
6. `git diff --check -- app/models/workspace_tables.py app/models/schemas.py app/api/knowledge.py tests/unit/api/test_api.py tests/integration/test_workspace_migrations.py` 无空白错误，仅已有Windows CRLF规范化提示。未跑Ruff，未重复全套。

两条warning分别为已有Starlette TestClient/httpx弃用和Python3.12 SQLite datetime adapter弃用，未为此升级依赖。已知前轮全量基线1060 passed、1个Retriever evaluate context_precision=None失败、18 deselected仍保留；本轮未修改无关评估、未宣称全套全绿。

## 冻结文件与边界

修改产品：`app/models/workspace_tables.py`、`app/models/schemas.py`、`app/api/knowledge.py`。

新增产品（审查包须纳入未跟踪文件）：`app/models/workspace_schemas.py`、`app/infrastructure/storage/library_store.py`、`alembic/versions/20261023_private_library.py`。

测试：新增 `tests/unit/api/test_private_knowledge_api.py`、`tests/integration/test_private_library_migrations.py`；修改 `tests/unit/api/test_api.py`、`tests/integration/test_workspace_migrations.py`。报告及Task4证据一起交付。

产品最后改动时间为本机2026-10-24 13:50:31（knowledge.py）；其余新增/修改产品均13:50:07。随后仅测试与本报告变化，最终32项回归后全部产品/测试冻结。没有未轮询运行会话。

未改README、asset inventory、status、raw、plan；保护原README142行与asset34行及无关改动。README收尾交主会话。未提交、推送、部署、自派reviewer。

本轮仅私有手动文本卡管理，不含上传、网络、自动索引、embedding、画像规划或UI；新卡片不自动成为教学检索来源。临时默认库API通过不表示工作区旧SQLite已迁移；Task13仍须真实数据库运行/重启/跨账号与页面完整验收，不能拿当前SQLite/API或PG迁移验证替代。

## 第2轮：独立物理连接证据补强

执行依据：`docs/superpowers/plans/2026-10-24-task4-round2.md`，SHA256 `6cb75eec4a79fa78299a21b2b2e12417c43280d6a3acca2abff04d284b7d83ae`，独立PASS证据 `docs/delivery/study-workspace-goal/evidence/Task4/round2-plan-review.md`。仅改测试和本报告/日志，产品继续冻结；未人为修改正确产品制造红灯。

初审所指限制确认：第1轮创建新AsyncSession可能复用同engine的物理连接，所以第1轮的“新连接读取”不应单独解释为已证明完全独立物理连接。这一轮对创建、编辑、删除后的关键持久化断言补足该证据。

- 仅测试文件 `tests/unit/api/test_private_knowledge_api.py` 新增 `read_item_independently(database_url,item_id)`。URL从原fixture factory绑定的临时文件SQLite engine获取，fixture仍返回client/headers/factory三元组；辅助函数每次建立全新异步engine，使用NullPool，每个物理连接开启并断言FK=1，finally无条件dispose，不复用API engine或池。
- 创建HTTP成功后，独立engine断言id/name/description/content_text/profile_id原值；PATCH成功后另一独立engine断言修改名称、保留原说明正文及profile清空；DELETE成功后再一独立engine断言该id不存在。没有访问生产库或变更全局配置。
- 同时间分页fixture将时间绑定改为数据库可读文本 `2026-01-01 00:00:00`，提交后先显式读取并断言全表DISTINCT updated_at只有该值，再保留原owner/profile/字面q搜索、分页去重/无遗漏和编辑中游标稳定断言。删除测试不再使用的Python datetime导入。
- 唯一测试命令：`.venv/Scripts/python.exe -m pytest tests/unit/api/test_private_knowledge_api.py -q`，经原生require_escalated执行；`docs/delivery/study-workspace-goal/evidence/Task4/round2-api.log` 为 **26 passed in 9.19s，无warnings**。SQLite日期adapter警告消失；没有升级、屏蔽依赖，也未运行含Starlette旧fixture的组合，不据此宣称Starlette警告已修复。
- 未重复旧API、PG迁移或全量测试，沿用上一轮对应证据及边界。未发现需修改产品的新缺陷，未提交/推送或派reviewer。

本轮测试最后修改时间本机2026-10-24 14:01:15；产品最后修改仍2026-10-24 13:50:31，其余产品13:50:07。测试与产品再次冻结，等待主会话相对初审快照生成测试差异并范围复审。无未轮询执行会话。
