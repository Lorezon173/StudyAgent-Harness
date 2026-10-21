# Docker 执行计划独立审查

审查日期：2026-10-21。审查对象：`docs/superpowers/plans/2026-10-21-docker-deployment-fix.md`（180行）。实现依据：独立工作区 `codex/docker-deployment-fix` 中 Dockerfile、Compose、Alembic、config、assembly、迁移链、pyproject、CI/Release 和 URL 测试草稿；补充读取主仓库 `git show 433b336:<path>`。设计依据为 `superpowers/docker-deployment-next-step-raw.md` 与 `docs/delivery/2026-10-20-docker-next-step-plan.md`。未修改计划、代码或工作流，未运行 Docker/数据库/模型验收。

此前中断是工具返回“aborted by user”，未见代码或审批失败依据；恢复后未重做已完成的外部工作区读取。

## 结论

方案A的核心已覆盖：backend 分别交付 ini 与完整迁移目录；runtime 保持消费路径；Alembic 显式 psycopg、SQLite 回归、百分号与密码保真、空库和存量库分开验收。当前 init 确实已建 mastery 两表，不能再以历史缺表推断当前空库必败；迁移链静态终点是 `20260729_chunk_id`。URL 测试草稿尚未实现纯函数，因此目前不是已通过的修复证据。

任务0–3可按计划实施，Docker部分仍以引擎真实结果为前提。任务4的隔离迁移也可独立推进。任务5需先明确验收子集接口与配置；任务6应先修正下面的发布策略及接口矛盾。没有发现必须重写RAG架构或预先新增迁移的依据。

## 发现

### 1. P1（阻塞任务6）：真实教学阻塞时，正式发布是否允许没有确定契约

计划行号：138、145–148、152、169。

事实依据：raw的“业务与发布验收”要求健康、认证、教学、持久化来自同一镜像，“任一门禁失败停止发布”；分层验收第5项要求候选SHA的Docker验收先完成再发布。执行计划145行只要求结构、正常库迁移和认证，138行允许真实教学因缺模型配置阻塞，148行则在validate成功后推送GHCR。152行区分服务器上线，不能直接回答GHCR正式发布是否允许绕过已批准的业务门禁。

影响：在没有真实模型凭据时，实施者可以合理写出两种相反行为：阻塞发布，或照常更新正式标签。属于授权设计与可执行门禁之间的实质歧义，并非已发生的工作流绕过。

可落地修订：增加发布决策表，明确PR检查、候选归档、正式镜像推送、服务器切换各自必要证据。保持raw严格口径时，模型阻塞只允许生成候选归档，正式push job必须检查同一候选image ID的业务验收结果为passed；若希望允许仅技术验收的候选镜像推送，应明确候选标签及禁止晋升正式标签的条件，并由主会话确认这项策略细化。不要把缺配置转成skip后仍声称业务门禁通过。

### 2. P2（重要）：单一api阶段无法表达CI只验认证与完整业务阻塞

计划行号：50–51、101、128–138、145。

事实依据：脚本仅定义 `--phase structure|migration|api`，状态契约规定“非通过返回非零”。任务5的api阶段包括注册登录、真实chat、会话持久化、重启和跨用户隔离；任务6又要求复用同一脚本，仅运行无模型依赖的认证。实现中 `app/orchestration/assembly.py` 的在线入口构造 `PgVectorProvider` 并要求pgvector/PostgreSQL；现有 `tests/unit/api/test_chat_persist.py` 使用monkeypatch替换 `run_online_agent_session` 与数据库会话，不能提供容器内免模型教学路径。

影响：严格执行单一api契约，无凭据CI必定blocked并返回非零；为使CI通过而跳过chat，则api=passed会掩盖未执行业务项。问题是缺少阶段选择及聚合协议，不是认证本身依赖模型。

可落地修订：把接口细化为 `api-auth` 与 `api-teaching`，或增加 `--checks auth|teaching|all`；manifest逐检查记录状态、退出码及必要项集合。CI只调用auth；all在teaching阻塞时必须非零。任务6的正式发布按发现1的决策表消费这些独立结果。补充“auth通过且teaching阻塞”与“auth失败”的脚本定向测试。

### 3. P2（重要，服务器配置前置）：Compose没有JWT密钥透传，认证验收会在公开默认密钥下通过

计划行号：131、134、136、167。

事实依据：`app/core/config.py` 的 `jwt_secret_key` 默认值为 `dev-secret-change-me-in-production`；`app/core/security.py` 使用该字段进行HS256签发和验签。`docker-compose.yml` app.environment仅传数据库URL和三个OpenAI字段，没有JWT_SECRET_KEY；Dockerfile没有复制.env，.dockerignore也排除.env。因此仅在Compose宿主.env填写JWT_SECRET_KEY并不会自动进入app容器。计划136行明确提出RAG透传补丁，却没有把JWT透传列为认证/服务器配置核查的明确项。

影响：隔离测试可正常登录、权限测试也可通过，但这不证明服务器令牌签名安全；若服务器直接采用此Compose默认配置，公开密钥允许伪造已有用户身份。尚无服务器配置，不能断言真实部署已经暴露。

可落地修订：配置修补任务明确列出JWT_SECRET_KEY透传；隔离验收使用专用随机测试密钥；服务器预检必须确认运行容器的有效密钥非空且不同于公开默认值，证据只记录布尔检查结果、不输出密钥。配置变更保持既有API行为，不需扩大为认证重构。

## 已核对但不报缺陷的事项

- COPY路径问题与当前Dockerfile相符；scratch负例/正例无需引入基础镜像。
- psycopg[binary]已在依赖中，旧env.py剥离asyncpg后得到裸PostgreSQL URL，计划选择显式psycopg有依据，不需新增驱动。
- 迁移样本中的缺表、非数字和孤儿外键分类合理；异常结果必须在隔离副本记录。SQLite实际约束执行仍待测试，不能凭静态代码声称已通过。
- CI当前确实没有workflow_call，Release当前直接build/push；保存、校验并load已验收镜像的方向正确。archive ID与registry digest分字段也合理；这只证明产物一致性，不能补足缺失业务门禁。
- 测试草稿含真实Alembic EnvironmentContext读回断言，优于只测字符串；仍须按计划获得红绿证据。
- 没有真实Docker、Actions或模型运行结果，本报告不对其可用性作结论。

本报告为只读审查产物；README由主会话按本任务最终交付统一检查维护，避免在共享主仓库并行改写。

## v2 定向复核（2026-10-21）

仅复核原三项发现及相关修订；本轮只读202行的v2执行计划，没有重新扫描实现或运行测试。原发现保留为历史，以下状态仅表示设计问题关闭，不代表实现或运行验收通过。

| 原发现 | 复核结论 | v2准确行号与依据 |
|---|---|---|
| P1 发布门禁歧义 | 已关闭 | 13、59–66、158、168–172、191行：明确任何真实教学非通过均不推GHCR任何标签，只允许保留技术验收通过的候选归档；validate/business-gate/push分层，审批不能替代业务测试。 |
| P2 api阶段冲突 | 已关闭 | 115–117、148、150–154、165行：阶段分为api-auth/api-teaching/all；退出码和聚合优先级明确；技术required_checks与正式all分开；auth通过且teaching阻塞的定向测试已列出。 |
| P2 JWT配置前置缺口 | 已关闭 | 31、144–150、169、189、191行：明确Compose透传、每轮随机测试密钥、运行容器有效配置检查、拒绝空值/公开默认值；证据不存密钥，并要求保持db-only用法。 |

在本次限定复核范围内，未发现新实质矛盾。167、168、170行进一步绑定实际checkout SHA、image ID与归档校验和，避免跨候选结果拼接。任务可进入既定执行流程；是否真正实现上述拒绝行为、受保护模型环境是否可用及远端Actions是否通过，仍须执行阶段提供证据，不能由计划复核推定。
