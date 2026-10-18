# 历史聊天 MVP 核查与 CI/CD 三层计划（raw）

日期：2026-10-18（Asia/Shanghai）。状态：历史核查已记录；用户随后已确认历史 MVP 与三层实施方向，并明确稳定线使用 `main`、RAG 开发线新建为 **`feature-rag`**。本轮按“先检查 CI/CD 缺漏”完成下方第 11 节核查，尚未编码或重组分支。以下先前的“待确认”文字保留原讨论语境，最新授权与命名以本段及第 11 节为准，不重复请求批准已确认方案。

## 1. 结论与本次需求修正

用户希望采用已经完成普通聊天功能的历史版本作为 MVP，把当前版本保留为 RAG 功能线，在历史 MVP 上建设 CI/CD。本稿据此修订先前“从当前 main 候选收敛”的建议；先前文档保留为讨论快照。

**推荐历史功能起点为 `d83c505c0d948ea9ceea9db81fd5508f8ad3ed65`，2026-07-31。** 它已经包含登录/JWT、真实 LLM 五 Agent 教学、会话消息持久化、普通与 SSE 入口、旧栈清理、初版 GitHub Actions / Docker，以及静态伺服修复。它还包含早期 RAG 代码，但普通聊天没有后续加入的在线 PG + pgvector composition 强制校验。准确称呼为“本轮 RAG Foundation 接入前的普通聊天基线候选”，不能称为完全没有 RAG 代码。

该提交适合作为**功能起点**，暂不能称为已经验证的干净发布版本：本轮未复现全量历史测试成功，并发现迁移与镜像构建的静态缺口。建议 MVP 发布基线 = 该历史起点 + 最小运行修补 + CI/CD 门禁，通过新环境验证后再固定版本。

本次范围不新增历史侧栏、完整连续上下文、检索、评测或复习功能。后端会话保存/读取已存在；历史侧栏未集成、模型上下文未完整恢复作为已知限制。不能将这两项增强冒称已经完成，也不把它们临时扩大为本次 CI/CD 建设任务。

## 2. 资产与影响地图

表中的未来改动均尚未执行。历史引用均针对 `d83c505`，不是将当前工作区文件冒充旧版本。

| 资产 | 归属 / 功能 | 入口与位置 | 影响 |
|---|---|---|---|
| 本 raw 文档 | 项目规划；保存历史证据、分支方案、三层计划 | 本目录；根 README 进入 | 🔴 本轮新增 |
| README / 资产清单 | 项目文档；提供当前建议入口与归属登记 | `README.md`、`docs/asset-inventory.md` | 🟡 本轮仅登记本稿 |
| 历史聊天与装配 | API / Orchestration；登录后执行真实教学并保存消息 | 历史 `app/api/chat.py`、`chat_stream.py`、`app/orchestration/assembly.py` | 🟢 保留普通聊天行为 |
| 历史鉴权与会话接口 | API；注册登录、JWT、所有权及消息读取 | 历史 `app/api/auth.py`、`sessions.py`、`_persist.py` | 🟢 复用，回归保护 |
| 历史数据库迁移 | 存储结构；空库创建及类型转换 | 历史 `alembic/env.py`、`alembic/versions/` | 🟡 后续拟定向修补 |
| 历史 Dockerfile / Compose | 构建与部署；镜像目录、应用与 PG 编排 | 历史 `Dockerfile`、`docker-compose.yml` | 🟡 后续拟修补与验证 |
| 历史 CI / Release | 工程交付；后端检查、GHCR 镜像推送 | 历史 `.github/workflows/ci.yml`、`release.yml` | 🟡 后续补强门禁 |
| 服务器部署工作流 | 工程交付；测试环境、正式晋级与恢复 | 拟建 `.github/workflows/deploy.yml` | 🔴 后续拟新增，非本轮已创建 |
| 当前 RAG 成果 | RAG；当前 HEAD 及所有未提交实现/计划/证据 | 当前 `codex/rag-mvp-first-wave` 与工作区 | 🟢 先保全，后续独立开发 |

## 3. 历史提交链与候选对照

| 提交 / 日期 | 已核对的变化 | 适合作为基底的判断 |
|---|---|---|
| `8bd7b54` / 2026-07-07 | 鉴权后的测试 fixture 修复；此前已有后端登录、前端 JWT、持久化和 SSE | 接近用户记忆中的聊天功能收尾；提交说明仍有 1 个测试失败，且仍处于双栈阶段 |
| `ddb0838` / 2026-07-17 | 增加 CI、Release、Docker 多阶段构建和 Compose 应用部署 | 初版交付配置在此引入，不必从零重写 |
| `5045878` / 2026-07-21 | 跟踪 uv.lock，修复 setup-uv 缓存问题 | 锁文件补充已包含在更晚候选中 |
| `f7d2582` / 2026-07-22 | 删除旧栈与 feature flag，普通聊天统一新栈 | 更简单的运行主体；历史 README 记录默认测试全绿 |
| **`d83c505` / 2026-07-31** | 静态路径、API 回退、缺失资源和根路径修复 | **推荐功能起点，保留上述后续修复** |
| `2971e3e` / 2026-08-03 | 中间加入 RAG 规划/资料并补 README | 与 d83c505 对比，app/web/tests/alembic/.github/Docker/依赖锁等本轮核对路径无差异；代码起点等价，但附带更多规划文档 |
| `459f28d` / 2026-09-02 | RAG Gate 0：摄入、可见性、EPUB，以及在线 composition fail-fast 等 | 放在 RAG 功能线，不作为普通聊天基线的整体前置 |
| `6324b94` / 2026-09-02 | 当前 HEAD；后续 RAG 文档交接 | 当前 RAG 线已提交起点，还必须包含未提交成果才能完整保存 |

本地完整日志、`git show <sha>:<path>` 与指定路径 diff 是上述判断来源；未 fetch，不能将本地远端跟踪引用当作实时远端状态。历史链接：[推荐提交](https://github.com/Lorezon173/StudyAgent-Harness/commit/d83c505c0d948ea9ceea9db81fd5508f8ad3ed65)、[RAG 接入提交](https://github.com/Lorezon173/StudyAgent-Harness/commit/459f28d3d849add193f41f185d590dd0fbb58d3f)。

## 4. 本轮验证证据与界限

1. `git archive` 导出 d83c505 到 `.pytest_cache/history-audit-20261018/d83c505-source/`；该快照不含 `.env`，没有 checkout/reset 当前工作区，且被 Git 忽略。导出不是创建可继续开发的正式 worktree。
2. 用当前项目 Python 3.12.11 / pytest 9.0.3 对该快照运行默认全量测试；强制使用快照内 SQLite 文件、fake RAG、禁用 Langfuse、清空模型 key / 测试 PG URL，并将 PYTHONPATH 指向快照，避免使用当前代码或业务配置。
3. 实测结果：**8 deselected、15 collection errors，exit 2**。错误为当前解释器缺少 `pgvector`、`bcrypt`。收集阶段终止，不能表述为 15 个产品行为测试失败，也不能声称候选已全绿。日志：`.pytest_cache/history-audit-20261018/d83c505-pytest.log`。
4. 原 README 的 `494 passed / 1 skipped / 8 deselected` 是历史声明，本轮没有重新验证成功。`8bd7b54` 提交信息中的残留 1 failed 属于更早提交，不能沿用为 d83c505 当前失败数。
5. 尝试用历史锁文件离线建立独立环境：首次 uv 默认缓存写入被拒；切换项目内缓存后成功解析锁，但离线缓存缺少 `numpy==2.4.6` 等所需 wheel，安装停止。没有修改当前 `.venv` 或依赖锁，没有再反复重试。
6. 另启动的核心子集检查未取得输出，已主动中断；无可用通过数，不能作为验证证据。
7. `gh api` 查询该提交 Actions 运行记录时网络连接失败，远端 CI 状态未知；没有将 workflow 文件存在等同于运行通过。
8. Docker CLI 存在，但 Docker Desktop Linux engine 命名管道不存在；本轮未构建镜像、启动 PG 或运行真实 LLM。

## 5. 静态核对发现的最小运行缺口

### 5.1 空库迁移缺少掌握度建表

历史初始迁移创建 users/knowledge/sessions/evals/messages；其他早期迁移增加 vector_chunks、评估列与消息约束，但未创建 `mastery_nodes` / `mastery_edges`。`m3_unify_user_id_type.py` 的 upgrade 却先对这两表 SELECT，再修改类型与外键。

历史 `app/core/database.py` 对 PG 只创建 vector 扩展，不执行全表 create_all。空库按正式迁移启动存在明确结构缺口。后续 `459f28d` 在初始迁移中补了这两张表，可作为定向回移的代码来源；不能整包 cherry-pick 而顺带引入 RAG 在线约束。本轮未在真实 PG 重现该缺口。

### 5.2 迁移同步驱动未明确对应已声明依赖

历史 `alembic/env.py` 将 `postgresql+asyncpg` 去掉 `+asyncpg` 后交给 SQLAlchemy；项目声明的是 `psycopg[binary]`。需要确认并显式指定所安装的 psycopg 驱动，以避免默认 PostgreSQL dialect 寻找另一驱动。这是配置契约缺口，实际异常仍需在独立完整环境复现。

### 5.3 Docker 内 Alembic 路径不一致

历史 Dockerfile backend 阶段使用 `COPY alembic.ini alembic/ ./`，runtime 阶段却要求从 `/app/alembic` 复制目录。Docker 的 COPY 对目录源复制其内容，不自动保留源目录本身；据此推断 backend 目录布局无法满足该引用。应定向修复并通过实际 build 验证，本轮没有 Docker 运行证据。[Docker COPY 官方规则](https://docs.docker.com/reference/dockerfile/#copying-from-the-build-context)

### 5.4 既有发布未受 CI 成功结果约束

CI 与 Release 独立触发，CI 没有前端检查和专用 PG 迁移验证；Release 只构建/推送，不部署服务器。不应把该历史版本的初版 CI/CD 认定为完整发布体系。

## 6. 第一层：模块总览

**目标边界**：以 d83c505 普通聊天功能为起点，保全 RAG 线；只修复阻止可重复构建、空库迁移和普通聊天运行的必要问题，建立 CI、版本化镜像、本机 Docker 验收及单服务器交付。既有产品能力不扩张。

**技术选择**：保留 FastAPI、React/Vite、uv/锁文件、Alembic、Docker Compose、GitHub Actions 和 GHCR，降低换工具成本；数据库部署继续 PG，软件单测可用 SQLite 与模型替身。真实发布验证使用真实模型，不将 fake RAG / FakeLLM 混为同一种能力。

**架构衔接**：不改五 Agent 职责与事件契约；历史聊天不引入当前 RAG 的强制装配；基础修补、CI/CD 各自形成可审阅小提交，并在后续向 RAG 线同步公共修复。

**数据库范围**：本次先支持新建隔离数据库的基线验收，不迁移或重置现有学习数据。对历史初始迁移的定向补全仅作为新基线修订方案；若要求升级已运行的存量数据库，必须先补兼容迁移设计，不能直接重跑旧修订。

## 7. 第二层：子模块概述

| 子模块 | 职责 | 接口 / 数据流 / 状态 | 失败策略 |
|---|---|---|---|
| A 成果保全与基线隔离 | 固定 RAG 成果，建立历史候选 worktree | 输入当前 HEAD、暂存/工作区/未跟踪清单；输出可恢复引用与候选 SHA | 归属不明或备份不完整，不执行切换/覆盖 |
| B 最小运行修补 | 修复空库迁移、同步驱动和镜像目录，验证普通聊天 | 输入候选源码与新建专用库；输出迁移 revision、构建与聊天证据 | 失败保存原始错误；不以 create_all 或忽略错误伪造正式迁移成功 |
| C 持续集成 | 检查后端、前端、PG 和镜像 | PR / 基线分支提交 → 固定版本检查 → 对应 SHA 的明确结论 | 必需检查失败、缺环境或未执行不能成为绿灯 |
| D 镜像发布与服务器交付 | 推送合格产物，测试后晋级生产 | 验证通过的 SHA → image digest → 测试环境 → 正式环境 → 发布记录 | 同环境串行；失败不晋级，恢复上一兼容镜像并核对数据 |

## 8. 第三层：子模块详细实施计划（文字，无代码）

### A. 成果保全与隔离

- 先确认没有其他会话继续写共享目录。记录 staged、unstaged、untracked 三类内容，区分源代码/计划/证据与 pytest 临时文件；记录 Git SHA 和必要文件摘要。
- 已提交 RAG 历史从 6324b94 保留；未提交 T02/T03/T04、后续计划及证据按明确文件保存为可恢复快照或逻辑提交。不得只建分支指针就声称保存了工作区；不得把密钥与私有正文纳入版本控制。
- 当前 RAG 分支可继续使用，或经确认命名为 `codex/feature-rag`；从完整 d83c505 SHA 建 `codex/mvp-baseline` 候选，并从候选开 `codex/mvp-cicd` 实施分支。使用独立 worktree，避免在当前脏目录 checkout。
- 数据字段：候选 SHA、RAG 保存 SHA、未提交资产清单、工作目录、归属与备份位置。它们是项目证据记录，不引入新运行时 API 或数据库表。
- 回归与构建完成后才固定 MVP 标签。默认分支角色迁移见下一节，不能强推回退已发布 main。

### B. 最小运行修补

- `alembic/env.py` 的 URL 转换：输入配置中的异步数据库 URL，输出显式同步驱动 URL；PostgreSQL 使用已声明 psycopg，SQLite 保持对应同步 URL；错误信息不输出凭据。离线/在线入口共用转换结果。
- 掌握度建表补全：核对历史模型与 m3 迁移前所需字段，补全新空库迁移链所需的两表、键、索引。参考 459f28d 中相应建表片段，不引入摄入代码、chunk_id 迁移或新的在线 composition。
- Dockerfile：分别保证迁移配置与迁移目录的确定位置，runtime 包含完整 env.py、versions 与配置；构建时校验路径，使用实际镜像运行迁移。同步锁文件选择和 Python 版本，避免用当前开发环境替代镜像验证。
- 配置：为测试、本机部署、服务器环境区分数据库/凭据；服务器 JWT secret 显式配置，不使用开发默认。保留真实 LLM 配置，普通聊天不要求书籍资产或正式 embedding baseline。
- 验证函数/入口仍为既有 `register`、`login`、`chat`、`chat_stream`、`persist_turn`、`get_session_messages`，不为流程重组新增产品端点。输入是认证用户、会话 ID 与文本；输出为回复、保存状态及只能由会话 owner 读取的消息。
- 用临时空库运行完整 Alembic 迁移，并检查必需表及 revision；再验证登录、普通聊天和会话消息保存。已有接口读写隔离与 SSE 行为加入回归，不扩建历史侧栏。

### C. 持续集成

- 后端检查 job：按历史锁文件建立环境，明确 Python 与 Ruff 版本；检查必需依赖和测试收集，再执行 lint 与现有非外部服务回归。是否需要 eval extra 依据真实导入确定，不能用新增 skip 隐藏依赖问题。
- 前端检查 job：使用锁文件安装，执行现有 Vitest 和 TypeScript/Vite build，保留退出码与结果。
- PG job：使用专用服务容器和明确测试数据库，运行完整正式迁移；确定性模型替身验证登录、消息写入/读取、所有权与失败回滚。不得使用现有业务库或基线数据。
- 镜像 job：依赖必要软件检查成功，在 PR 上只构建验证；对受信候选提交构建发布镜像。显式检查迁移目录，容器健康检查之外验证数据库与关键 API。
- 汇总状态：记录 `source_sha`、检查名、结果、执行/跳过计数与报告位置；只有全部必需 job 成功才输出可发布状态。工作流触发先覆盖候选基线分支，默认分支迁移时同步规则，不能只写 main 而漏掉候选验证。
- 不新增通用测试框架；必要回归围绕真实缺陷与关键行为。PR 不访问生产密钥，真实 LLM 冒烟另放受信环境。

### D. 镜像、交付与恢复

- Release job 接收已验证的同一 SHA，输出不可变 `image_digest` 与可读版本标签。推送必须依赖该提交检查成功；手动或 tag 触发也核对来源，不允许绕过。
- 本机先验收 Docker 镜像与新建专用 PG；服务器阶段复用已验收产物，单机测试与生产实例的数据卷、配置和凭据隔离。
- 部署 job 输入环境、digest、允许来源；依次检查配置、迁移、启动与 API 冒烟。每环境设置串行并发组，不能同时运行两个迁移/部署。
- 正式晋级使用测试过的同一 digest，经显式发布动作触发。记录 Git SHA、digest、迁移 revision、时间、健康结果和上一兼容 digest。
- 恢复动作以记录中的上一兼容版本为输入；核对 schema 兼容后切回。涉及不兼容数据变更时必须有备份/恢复设计，不自动执行数据库降级。
- 初期接受可控重启窗口，不新增 Kubernetes、百分比灰度或复杂发布平台。服务器地址、域名/HTTPS、凭据来源和现有数据到实际部署设计时核对，不编造当前环境。

## 9. 分支拓扑与 main 的迁移边界

```text
d83c505 ── 最小运行修补 ── CI/CD ── 验收后的 MVP 稳定线
    └──── 后续 RAG 提交 ── 6324b94 ── 保存当前未提交成果 ── RAG 功能线
```

两线共享历史起点，MVP 上的公共修补后续合入 RAG 线，RAG 的摄入/检索变更逐包 PR 回稳定线。

**当前本地 main / origin/main 跟踪引用已是 RAG 后的 6324b94。** 老提交上的新分支不能靠一次普通合并把 main 自动“变回旧版本”；也不能默认 `reset --hard` 或 force-push。

建议先在候选分支完成验证，保留原 main 与 RAG 保存引用。通过后单独确认默认稳定分支命名/迁移：可先把候选设置为默认稳定线；若最终必须叫 main，则通过保留旧分支的重命名与默认分支设置完成一次性迁移，并同步 PR 基底、保护规则、Actions 过滤和部署引用。本次不进行这项远端设置变更，也不以内容回退 PR 代替分支迁移而忽略后续 RAG 重合并问题。

## 10. 放行顺序与需确认的具体方案

顺序：A 保存并隔离 → B 最小运行修补 → C CI 全绿与本机 Docker 验证 → D 单服务器交付 → 固定 MVP 版本/迁移默认分支角色 → RAG 逐包开发。

请求确认的方案是：**以 d83c505 为历史功能起点，只补必要运行缺口并建设 CI/CD；当前 RAG 完整保留独立开发；不新增聊天产品能力，不改写远端 main 历史；本次先针对新建隔离数据库验收。** 确认后再进入编码，遵循用户的“规划必须经用户确认后，方可进入编码阶段”。

环境受限时可手动复核：在未来正式候选 worktree 中使用可联网环境执行 `uv sync --locked --extra dev`（按实际测试导入补已确认 extra）、`uv run pytest tests/ -v`；启动 Docker 后再执行镜像构建和独立 PG 验证。未完成这些步骤前，不发布“候选已全绿/可上线”的结论。

## 11. 用户确认后的 CI/CD 缺漏核查

### 11.1 确认范围与核查方法

用户已确认：“mvp放在main分支，rag模块放到新开的feature-rag分支继续开发。对于main分支，要先搭建起完整的CI/CD，先检查一下CI/CD的缺漏”。这确认了第 6～10 节总体实施方向；实际分支名采用用户指定的 `feature-rag`，不再使用先前建议名 `codex/feature-rag`。

本轮先交付缺口检查，不触发 push、构建发布或服务器部署，也不在尚未保全当前工作区时切换 main。检查对象是 **d83c505 历史候选的文件内容**；另执行指定路径比较，确认其 `.github/workflows/`、Dockerfile、Compose、.dockerignore、.env.example、pyproject.toml、uv.lock、web/package.json 与当前 HEAD 内容无差异（`git diff --quiet` 退出 0）。这不表示两个版本的应用、迁移或测试代码相同。

历史候选只有 `ci.yml` 和 `release.yml` 两份工作流。当前可确认的交付链是：PR/main push → 后端 lint/默认 pytest；main/tag push → 独立构建/推送 GHCR。**它是 CI 雏形与镜像发布流程，尚未形成完整持续交付。**

优先级含义：P0 为发布前必须解决的阻断或门禁缺口；P1 为形成可用回归/交付闭环所需能力；“静态推断”仍必须以实际运行验证关闭。远端未知项单独列出，不冒称缺失。

### 11.2 P0：发布阻断与关键门禁

| ID | 缺口与证据（路径均为历史 d83c505） | 影响 | 关闭条件 |
|---|---|---|---|
| C01 | Release 与 CI 独立触发，只有 build-and-push job，无依赖成功检查的步骤；`release.yml:3-9` | CI 失败也没有显式规则阻止镜像发布；任意匹配 v* 的 tag 也会触发 | 所有发布入口核对同一受信 SHA 的必需检查成功；失败与未跑均不能推送/晋级 |
| C02 | backend 使用 `COPY alembic.ini alembic/ ./`，runtime 却从 `/app/alembic` 复制；`Dockerfile:25,38` | 按 Docker COPY 语义推断目录布局不匹配，镜像构建存在阻断；本轮未实际 build | 修补后实际构建镜像，检查配置、env.py、versions 的位置，并成功运行迁移命令 |
| C03 | 初始/中间迁移未创建两张 mastery 表，m3 upgrade 却直接 SELECT；初始迁移及 `m3_unify_user_id_type.py:26-27` | 空数据库无法完整按该历史迁移链建立所需结构；已有 SQLite create_all 测试掩盖此路径 | 新建专用 PG 从零完成正式迁移并核对所有必需表；已有数据兼容升级另行验证 |
| C04 | URL 转换去掉 +asyncpg，未显式选择已声明的 psycopg；`alembic/env.py:21-22`、`pyproject.toml:19` | 同步迁移驱动契约未对齐，可能寻找未安装的默认 PostgreSQL 驱动；待实际复现 | 在锁定依赖与实际镜像中使用明确同步驱动，PG 连接和迁移成功 |
| C05 | Compose 没有将 JWT secret 传给应用；代码存在开发默认 secret；`docker-compose.yml:38-42`、`app/core/config.py:26` | 按现有提供的配置启动生产实例会沿用开发签名配置，生产配置尚不完整 | 正式环境显式注入独立 JWT secret 和数据库凭据，缺失时发布前校验失败；不把密钥写入仓库/镜像/日志 |

C02 的规则依据是 [Docker COPY 官方说明](https://docs.docker.com/reference/dockerfile/#copying-from-the-build-context)。C03/C04 的运行修补不是增加 RAG 功能，而是让普通聊天所依赖的数据库能从空环境建立。

### 11.3 P1：回归与持续交付闭环缺漏

| ID | 缺口与证据 | 关闭条件 |
|---|---|---|
| C06 | CI 未执行前端 test/build；已有 Vitest 与 tsc/Vite scripts（`ci.yml:jobs`、`web/package.json:8-10`） | PR 必跑前端测试与类型/构建；失败阻止合并 |
| C07 | pytest 默认排除 integration；CI 无 PG service 或正式迁移步骤（`pyproject.toml:64`、`ci.yml`） | 专用 PG 执行空库迁移、普通聊天保存/读取、所有权与回滚验证；模型使用确定性替身 |
| C08 | 镜像只在 Release 构建，PR 无镜像验证（两工作流触发与 steps） | PR 构建真实 Dockerfile，并验证容器路径/启动；发布前验证对应提交的产物 |
| C09 | 依赖安装未使用 locked 模式，uv 与 Ruff 未固定版本；Docker 额外装 rag，但 CI 仅 dev（`ci.yml:21,25`、`Dockerfile:18,22,26`） | 固定 Python/Node/uv/Ruff 策略，按锁文件安装；明确测试与运行依赖集合，并在最终镜像验证实际依赖。是否保留 rag extra 以普通聊天导入实测决定 |
| C10 | 可选 RAGAS 路径可因未装依赖而 skip；CI 未输出 skip 分类（`test_retriever.py:368-369`） | 显式区分可选后置评测与 MVP 必需行为；必需验证缺依赖/被 skip 不能算完成。不把后置 RAGAS 变为普通 MVP 的新前置 |
| C11 | 没有测试环境/服务器部署工作流；Compose 使用 local 镜像与 build，而非发布 digest（`docker-compose.yml:33-34`） | 提供明确服务器部署入口，消费已检查的 GHCR digest；测试通过后晋级同一产物，服务器不重新构建源码 |
| C12 | v* 触发只产出 latest 和短 SHA 标签；没有版本晋级、发布记录与恢复步骤（`release.yml:6,34-36`） | 版本关联 SHA/digest/迁移 revision/冒烟结果；保留上一兼容版本，完成一次恢复演练。版本标签仅作可读引用，digest 为精确产物标识 |
| C13 | `/health` 固定返回 ok；Compose 只请求该地址（`app/main.py:36-38`、`docker-compose.yml:46-47`） | 保留存活检查，增加数据库/迁移就绪与关键 API 冒烟；真实 LLM 另做少量受信环境验证，不让每次健康探针都产生模型调用 |
| C14 | 无部署 concurrency；启动每个应用容器都自动迁移（`Dockerfile:45`） | 同环境部署串行，迁移执行权明确；服务器发布采用一次性迁移步骤或等价串行保障，避免重复并发 DDL |
| C15 | 工作流未持久化测试/构建报告，也无明确 job 超时（两工作流 steps/jobs） | 保存必要测试计数、失败/skip、日志和构建信息；设置合理超时。可由 Actions 运行结果承担通知，不强制引入外部消息服务 |

### 11.4 待核实项：未知不等于缺失

- **main 保护与规则集**：本轮 `gh api .../branches/main/protection` 网络连接失败；尚未读取规则集，也无法确认 required checks、PR 审阅、绕过和强推限制。实施时需要核对实际设置，而非仅修改 YAML。
- **远端 CI/Release 运行证据**：上一轮 Actions 查询同样未成功；不能声称历史 workflow 跑通过，也不能声称从未跑过。
- **部署环境配置**：GitHub Environments、GHCR 访问、服务器地址/权限、域名与 HTTPS、测试/生产隔离、备份位置未知。配置要在发布前落实，当前不编造服务器条件。
- **真实环境就绪**：前轮 Docker 引擎未运行、锁依赖未还原；本轮未重复进行安装、测试、镜像或 PG 执行，避免把静态审查写成运行通过。
- **RAG 分支开发检查**：现有 CI push 仅监听 main，feature-rag 在没有 PR 时不会因 push 运行；是否增加 feature-rag push 作为便捷反馈可在实施时决定，所有合并稳定线的 PR 必须有检查。稳定发布只能来自受信 main/版本，不因 RAG push 上线。

### 11.5 已授权实施的推荐批次

1. **保全与隔离**：保存当前未提交内容，建立用户指定的 feature-rag；main 的历史基底迁移与远端设置采用保留历史的方式实施，不 force-push。未保全前不切换当前脏目录。
2. **运行基底与 CI**：先关闭 C02/C03/C04；同时落实 C06/C07/C08/C09/C10/C15。以新建专用 PG、确定性模型测试和真实镜像为证据，不新增聊天产品功能。
3. **发布门禁**：关闭 C01，核对 main 必需检查和保护；让 PR 检查、main 对应提交验证、镜像推送有明确依赖。
4. **单服务器交付**：关闭 C05/C11/C12/C13/C14，确认实际环境信息；本机 Docker 验收后测试环境部署、真实模型冒烟、正式晋级与恢复演练。

目标链路：`PR 必需检查 → main 同 SHA 验证 → GHCR digest → 测试环境 → 冒烟/验收 → 同 digest 正式晋级 → 版本记录与恢复`。只有四批证据齐全才称 CI/CD 闭环建成；本轮交付是缺口核查。
