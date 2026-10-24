# StudyAgent调整与审批记录

当前无实施变更，规程v1.0待批准。本轮设计规程不代表用户已批准其中的所有技术默认值。

## 变更单模板

- 编号：ADJ-递增序号；关联任务、状态、规程/计划版本。
- 类别：A范围内修正 / B契约或范围变化 / C外部或不可逆动作。
- 触发事实：证据路径、命令结果或用户明确要求。
- 原规则与建议新规则：逐条对照。
- 影响：功能、文件、接口、数据/迁移、顺序、验证标准与成本。
- 方案与替代方案：最小实现、失败代价、回退方式。
- 批准要求：是否需要；用户决定的原始消息引用。未收到不得填“同意”。
- 实施记录：修订编号、提交SHA、检查命令/结果、审查和README位置。
- 收尾：通过/拒绝/撤回；重开任务、批准manifest更新及下一检查点。

实施后以追加记录保留历史；不覆盖已拒绝或已生效的旧决策。

## ADJ-001：恢复锁定依赖以完成Task0基线（A类，2026-10-24）

- 事实：普通uv run在依赖同步阶段报files.pythonhosted.org DNS错误，alembic/pytest尚未执行；前端缺vitest与tsc。
- 决定：通过原生审批通道执行uv sync --extra dev --frozen及npm --prefix web ci --no-audit --no-fund，仅恢复现有锁文件依赖，不改功能/版本/全局配置。
- 范围：项目.venv、web/node_modules与运行缓存；代码和锁文件不应改变。
- 验证：安装完成后重跑四项Task0检查，保留初次失败与恢复后证据。
- 批准依据：用户已明确授权计划实施；范围内可逆依赖准备，不涉及需求或验收标准变更。原生工具审批照常执行。
- 当前：进行中，未将基线或产品任务标完成。

### ADJ-001 修订1：备用现有Python运行时（A类）

- 锁定uv同步仍在运行，不重复安装；原生只读进程检查确认进程存在。
- 已只读验证C:/Users/A1985/.codex/worktrees/mvp-cicd/StudyAgent-Harness/.venv/Scripts/python.exe依赖齐全，import app指向当前D:/backup/basic_file/Program/LearningAgent/StudyAgent-Harness/app。
- 允许该解释器在当前cwd以PYTHONDONTWRITEBYTECODE=1运行补充alembic/pytest；不改备用环境、不运行其仓库代码，不把备用验证冒称当前uv命令成功。
- 最终依赖和真实验收仍需可复现，当前环境下载完成后登记实际结果。

## ADJ-002：本轮基线超时及报告日期（A类）

- Task0报告使用实际执行日期2026-10-24，路径docs/delivery/2026-10-24-workspace-baseline.md，替代计划中预设2026-10-23文件名，任务内容不变。
- 备用环境完整pytest在00:08:02启动，超过五分钟日志仍0B；两次原生进程检查显示python49272/50488仍存在，CPU未继续增长。主会话核对名称及同一StartTime后定点终止这两进程，不停止其他Python。
- 此结果是超时/人工终止，无通过数，根因未证；不改变Task13完整回归门槛。测试工具本身与编排模块的单独collect-only已成功收集12项。
- Task0责任是建立真实基线并归因已知问题，不要求修复整个旧基线；前端三项失败归Task9客户端测试，后端无结果后续定点诊断，最终验收前必须解决。

## ADJ-003：TestClient验证改用原生审批路径（A类）

- 证据：Task1/testclient-execution-path-probe.log，空FastAPI的404请求无项目路由/数据库，普通沙箱15秒超时，同脚本原生路径2.63秒返回404。
- 修正：API行为测试走require_escalated，保留独立SQLite/FK/用户种子；不修改产品代码或依赖来压掉该环境现象。
- 原Task0完整pytest超时仍是未通过记录；本诊断说明一个可重现的执行路径问题，不推断所有旧超时唯一根因。
- 无需求/接口/顺序/验收降低，测试本身不skip。范围内测试环境修正，无新增全局权限或配置。

## ADJ-004：新会话父记录显式flush（A类）

- 事实：Task1原生聚焦回归208通过、1失败；开启SQLite外键后，原新会话E2E在消息插入时报FOREIGN KEY constraint failed，turn_count为空。保留原断言，不预存该会话掩盖缺陷。
- Ruling: 允许app/api/_persist.py在两处session_store.save之后、MessageStore.add之前显式await db.flush()，补充顺序及失败回滚验证；这是满足项目父先flush硬约束的最小既有接口修正。若判断错误，代价为撤回两处flush并重新诊断。
- 边界：不新增API、幂等架构或commit；Task8仍按原序完整验收事务、并发与幂等。未降低验收标准，按已批准规程范围内修正执行。
- 状态：实施中，待原样回归及独立审阅，未标完成。

## ADJ-005：Task2画像归属与兼容写入保护（A类）

- Ruling: 按raw节点字段保留profile_id而不冗余user_id，画像(user_id,id)唯一、节点(profile_id,id)唯一及边同画像复合外键；Store每个方法验证调用用户与画像归属，Task3继续构成会话归属链。若判断错误，代价是补迁移扩展约束，不能以应用层检查替代数据库边界。
- Ruling: 兼容Graph.load/save未传节点revision，由Store记录读取版本并条件更新；未读取的既有节点必须带显式revision，否则拒绝覆盖；边使用已读画像版本保护陈旧写入。若判断错误，代价为兼容调用需重新加载，不能静默覆盖新状态。
- Ruling: 旧边缺少端点时迁移明确失败并回滚，不删除原数据或编造节点。若真实历史存在此类脏数据，需列出数量和修复方案再实施，代价是迁移被阻塞。
- 环境：创建无持久卷、仅本机55440端口的studyagent-goal-test-pg独立测试容器，pg_isready通过；不接触现有3个容器。用于后续真实PG验收，非部署。
- 顺序与验收不变；Task2进行中，未提前创建evidence/session扩展。

### ADJ-005补充：历史来源与边版本

- 旧边source保留原枚举值，历史来源由所属画像kind=legacy标识；不强塞MasteryGraph不接受的legacy边枚举，不虚构消息证据。若判断错误，代价为后续补显式来源元数据，原数据仍可追溯。
- 边更新用已读profile revision条件更新，节点/边同一Store依次保存时同步本实例新版本；未读取已有边拒绝覆盖，初始化新边允许。冲突/失败由调用方整事务回滚，不新增commit。
- Task2红灯12项失败已产生，正在最小实现，尚未通过或完成。

## ADJ-006：Task2兼容图谱接口审查修复（A类）

- 独立审查发现两项Important：兼容save缺字段会清说明/解除归档；未评估null作为PREREQ节点触发数值比较异常。Task2未完成，不进入Task3。
- Ruling: 已有节点仅更新输入明确提供的description/archived，新节点保留数据库默认；允许最小扩展mastery_graph.py类型与薄弱查询，未评估null跳过数值薄弱判断，不转换0、不伪造分数，已评估低分行为不变。满足已批准“未评估不是0”和兼容四方法契约。若判断错误，代价为后续调整未知节点推荐策略，但真实null与归档数据仍保留。
- 任务顺序/接口路径/验收不变；在线上下文与未知节点教学流程仍Task7，Task8增量提交不提前。
- fix round1/5：先加入真实Graph往返与null前置行为失败测试，再最小修复，覆盖Task2 Store与Graph，范围复审后才允许提交。

## ADJ-007：Task3 SQLite带子消息重建父表（A类）

- 实现者验证SQLite sessions重建时messages引用导致删除父表失败，单纯defer_foreign_keys在commit仍保留删除计数；原Store16项已绿，迁移尚未验收。
- Ruling: 允许迁移事务内延迟外键，foreign_keys始终ON，重建完成必须全库foreign_key_check为空才解除延迟；非空立即失败并整事务回滚，不手动提交调用方事务。PG使用正常ALTER约束。若判断错误，代价为重设计SQLite重建路径；不可牺牲现有消息或约束。
- 验证必须实际commit后新连接读历史消息和约束，并注入重建中故障确认旧session/message及迁移版本全恢复。不以同连接临时结果代替迁移成功。
- 不变更业务契约、顺序或验收，不关闭外键。Task3进行中。

### ADJ-007补充：默认Alembic SQLite连接

- 默认Alembic连接原未启用SQLite外键，新迁移因此会明确拒绝；不能仅测试专用provided连接通过就称迁移可用。
- Ruling: 允许env.py在默认SQLite连接BEGIN前启用foreign_keys并核实实际值为1；provided连接不擅自提交，若在事务内不能启用则明确拒绝，不谎称约束开启。只启用、不关闭。若判断错误，代价为调整迁移连接入口，不修改历史数据。
- 补默认CLI路径红灯与最小修复后验收，不重复已通过的全部迁移测试。属于范围内迁移可靠性修正，未改变业务范围。

## ADJ-008：Task5初审证据与游标规范（A类）

Ruling: 依round2已审计划补数据库实际等待/真实事务及独立物理连接证据；产品读保护不变，仅收紧_decode_cursor到既有生成器规范格式，拒绝非规范Base64/仅日期。符合原strict cursor契约，不改变正常客户端游标或排序。若判断错误，代价为调整非规范客户端输入兼容，owner过滤不受影响。两Important未修前Task5不标完成，无范围/顺序/验收降低。
