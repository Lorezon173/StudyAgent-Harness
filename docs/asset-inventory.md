# 资产清单（Asset Inventory）

> 本项目所有「方案会碰到的产物」的 master 活文档，由 Claude 随时维护更新，供随时查阅。
> 形态约定与维护规则见 `.claude/rules/solution-presentation.md`（方案呈现规范）。
> 本文件只存**项目事实**（本项目具体有哪些产物），不存跨项目规矩。

## 字段说明

- **名字**：产物名（脚本/文档/hook/skill/模块/配置等）
- **归属子系统**：它属于哪一块
- **功能**：现在干嘛（真读过实现才照实填；未读实现标 `⏳`）
- **触发 / 入口**：从哪被调用或进入
- **位置**：`file:line`，可点跳转

---

## 自进化捕获子系统（.evolve）

| 名字 | 功能 | 触发 / 入口 | 位置 |
|---|---|---|---|
| `.evolve/config.json` | 存 `remind_threshold`（默认 3）：_inbox 待审条数达此值触发审核提醒 | 被 evolve-capture skill 读取 | `.evolve/config.json` |
| `.evolve/_inbox/` | 待审捕获草稿暂存区 | evolve-capture 场景 B 写入 | `.evolve/_inbox/` |
| `.evolve/_inbox/.session-<id>.on` | 会话开启捕获的标记文件；存在即本会话监测晋升暗示词 | evolve-capture 场景 A，用户答"开"后 `touch` | `.evolve/_inbox/.session-current.on` |
| `.evolve/local/` | 审核判为 local 的捕获落地区（skill 类可软链到 .claude/skills 生效） | evolve-capture 场景 C 用户选 local | `.evolve/local/` |
| `.evolve/global/` | 审核判为 global 的候选草稿区（待跨会话二次晋升进 self-evolution 仓库，🔴 红区） | evolve-capture 场景 C 用户选 global | `.evolve/global/` |

> 注：以上功能描述源自 evolve-capture skill 正文，hook 脚本（session-capture-ask / capture-gate）实现 ⏳ 未读，后续涉及时补。

## 子项目② 实时协作流（已落地，仍有后续演进项）

> 设计来源：`docs/designs/2026-06-11-realtime-collab-stream-design.md`。下列条目记录实际代码资产及仍待实现的后续项；“待建”仅表示对应条目尚未落地。

| 名字 | 归属子系统 | 功能（规划） | 三色 | 位置 |
|---|---|---|---|---|
| `run_collab_loop` on_event 钩子 | Orchestration | 循环内每 publish 一事件即回调透出，供 SSE 实时桥接 | 🟡 改动 | `app/orchestration/collab_loop.py:31` |
| `run_new_agent_session`/`build_new_stack` | Orchestration | 加可选 graph/on_event 参数，透传桥接与外部 graph | 🟡 改动 | `app/orchestration/assembly.py:131/100` |
| `project_event` | API | SSE 语义事件白名单过滤 + 转前端友好 payload | 🔴 新建 | `app/api/_sse_projection.py`（待建） |
| `MasteryNodeTable`/`MasteryEdgeTable` | Infrastructure | 掌握度节点/边的 SQLAlchemy 表（PG/SQLite 双模），新栈 chat 加载与持久化的事实源 | chat/chat_stream + `persist_turn` | `app/models/tables.py:64-89` | 🟢 已建 |
| `SQLAlchemyMasteryStore` | Infrastructure | 复刻旧 store 的节点/边读写契约，底层走 `AsyncSession`；新栈 chat 使用 | `app/api/chat.py:26-46`、`chat_stream.py` | `app/infrastructure/storage/sqlalchemy_mastery_store.py:7-88` | 🟢 已建 |
| `persist_turn` | API | 共享落库函数：会话+消息+掌握度一次事务提交，chat/chat_stream 复用 | chat / chat_stream 完成协作环后 | `app/api/_persist.py:14-118` | 🟢 已建 |
| `chat`（非流式） | API | 加载 SQLAlchemy 掌握图→运行协作环→重新绑定 store 后持久化 | `POST /api/chat` | `app/api/chat.py:20-61` | 🟢 已建 |
| `get_profile` | API | 读真实 sessions 计数 + SQLAlchemy `mastery_nodes` 均值（0-100） | `GET /api/profile/` | `app/api/profile.py:9-27` | 🟢 已建 |
| 旧 `MasteryGraphStore` | Legacy Infrastructure | aiosqlite 掌握度/`user_profile_l3` store；新栈 API 不读写，旧图谱与画像测试仍用 | 旧 `UserProfile`、单元测试 | `app/infrastructure/storage/mastery_graph_store.py:7-155` | 🟢 保持 |

## 阶段 B-②：掌握度时序化 + 用户主动复习（规划待实现）

> 主 spec：`docs/designs/2026-07-03-phase-b2-mastery-temporal-review-spec.md`。当前只记录已验证的现有资产和计划中的三色影响；尚未实现 Review API。

| 名字 | 归属子系统 | 功能 | 触发 / 入口 | 位置 | 三色 |
|---|---|---|---|---|---|
| `FEATURE_USE_NEW_AGENT_GRAPH` / `use_new_agent_graph()` | Core Runtime Flag | 新旧 Agent Graph 路径的请求时开关；B-② 仅在 flag 为 true 时可用 | `/api/chat`、`/api/chat/stream`，未来 review router | `app/core/feature_flags.py:1-17` | 🟡 约束扩展 |
| Alembic mastery 历史链 | Migration | 当前 PG 迁移链缺少 mastery 两表创建责任；B-② 要先修复该链 | `alembic upgrade head` | `alembic/versions/m3_unify_user_id_type.py` | 🟡 修复 |
| `ReviewPreferenceTable` / `ReviewPreferenceStore` | Models / Infrastructure | 新栈用户的持久化复习偏好 | 未来 review router | `app/models/tables.py` / `app/infrastructure/storage/`（新） | 🔴 新建 |
| `MasteryDecayService` / `ReviewTriggerService` | Harness | 只读 mastery 投影和主动建议筛选 | 未来 `POST /api/review/trigger` | `app/harness/`（新） | 🔴 新建 |
| review router | API | 新栈限定的偏好 GET/PUT 与主动 trigger | 未来 `/api/review/*` | `app/api/review.py`（新） | 🔴 新建 |

## 研究调研文档（docs/research）

| 名字 | 功能 | 位置 |
|---|---|---|
| `2026-06-15-rag-memory-frameworks-survey.md` | RAG/Memory 框架调研 | `docs/research/2026-06-15-rag-memory-frameworks-survey.md` |
| `2026-06-16-current-vs-frameworks-decision-report.md` | 当前实现 vs 框架决策报告 | `docs/research/2026-06-16-current-vs-frameworks-decision-report.md` |
| `2026-06-22-deepeval-vs-ragas-adoption-report.md` | DeepEval vs RAGAS 对比与本项目借鉴报告；推荐**混合方案**（Retriever 用 RAGAS + Tutor 用 DeepEval G-Eval） | `docs/research/2026-06-22-deepeval-vs-ragas-adoption-report.md` |

## L2 评估体系（app/eval + Agent.evaluate）

> spec：`docs/superpowers/specs/2026-05-29-multi-agent-redesign-design.md` §5（母 spec）+ `docs/designs/2026-06-22-hybrid-evaluation-ragas-deepeval.md`（混合方案，实际执行）+ `docs/designs/2026-06-22-deepeval-component-metrics.md`（DeepEval 落地，备选方案）+ `docs/research/2026-06-22-deepeval-vs-ragas-adoption-report.md`（混合方案，推荐）

| 名字 | 归属子系统 | 功能 | 三色 | 位置 |
|---|---|---|---|---|
| `ComponentBench` | L2 eval | 对 Agent.evaluate() 跑黄金用例、按 expected 阈值判 passed | 🟢 保持（不改调度） | `app/eval/component_bench.py:23` |
| `Retriever.evaluate()` | Agent 部件 | 已替换为 **RAGAS** 三件套（faithfulness / answer_relevancy / context_precision），4 层降级（Phase 1，`fc210d4`） | 🟢 已完成 | `app/agents/retriever.py:105-265` |
| `Tutor.evaluate()` | Agent 部件 | 当前字符 Counter 占位算解释完整性，待替换为 **DeepEval G-Eval**（推荐） | 🟡 改动（替换指标段） | `app/agents/tutor.py:99` |
| `golden_cases.py` | eval fixtures | Retriever/Tutor 黄金用例 + expected 阈值 | 🟡 改动（补字段 + 扩充到 50+ 用例） | `app/eval/fixtures/golden_cases.py:19` |
| `JudgeProvider` 适配层 | L2 eval | 把项目 LLM 配置包成 RAGAS/DeepEval 通用 model + §5.1.1 不同族校验（Phase 1 已建） | 🟢 已建 | `app/eval/judge.py:36`（`build_judge`），`:17`（`infer_family`） |
| `ragas` 库 | 外部依赖 | RAG 专用评估（分阶段诊断 + 合成测试集），**已在依赖** | 🟢 已有（`pyproject.toml:33`） | `ragas>=0.2.0` |
| `deepeval` 库 | 外部依赖 | 通用 LLM 评估（G-Eval 自定义指标），待加 eval extra | 🔴 新建（可选依赖） | pyproject eval extra（待加） |
| `test_judge.py` | 测试 | judge 适配层 + 不同族校验 + 降级单测（Phase 1 已建，9 例） | 🟢 已建 | `tests/eval/test_judge.py` |
| `generate_ragas_testset.py` | scripts | 从知识库文档自动演化生成测试集（RAGAS 合成） | 🔴 新建 | `scripts/generate_ragas_testset.py`（待建） |

## 项目级规则（.claude/rules）


| 名字 | 功能 | 触发 / 入口 | 位置 |
|---|---|---|---|
| `dev-standards.md` | 全局开发规范的项目级镜像（语言/命令执行/README维护/模块三层规划/规划产出物管理） | 随会话加载 | `.claude/rules/dev-standards.md` |
| `learning-docs.md` | 学习文档落地规则（Learned/ 下 QA 式记录的格式与流程） | learning-docs skill 触发 | `.claude/rules/learning-docs.md` |
| `agent-root.md` | StudyAgent 框架根规范（四层单向依赖、薄壳节点、spec 同步规则） | app/agent/ 下开发时 | `.claude/rules/agent-root.md` |
| `solution-presentation.md` | 方案呈现规范（引用即解释 + 资产清单/三色血缘默认开头） | 给用户任何方案/计划/设计时 | `.claude/rules/solution-presentation.md` |

## 项目入口文档

| 名字 | 功能 | 触发 / 入口 | 位置 |
|---|---|---|---|
| `CLAUDE.md` | Claude 每会话自动加载的项目入口：单栈方向（新栈 `app/` 唯一主体 / 老栈 `app_old/` 待删）+ 四层架构 + 关键目录地图 + 五 Agent 点名 + 时效性地标 + 载体路标 | 会话启动自动加载 | `CLAUDE.md`（根目录） |

## CI/CD 与 Docker 部署

| 名字 | 归属子系统 | 功能 | 触发 / 入口 | 位置 | 三色 |
|---|---|---|---|---|---|
| `Dockerfile` | 部署 | 多阶段镜像：node 构建前端 → uv 装后端（`--extra rag`）→ 精简 runtime；启动自跑 `alembic upgrade head` + uvicorn | `docker build` / release.yml | `Dockerfile` | 🔴 新建 |
| `.dockerignore` | 部署 | 构建上下文裁剪 + 密钥防泄漏（排除 .env/node_modules/.venv/tests/docs） | `docker build` | `.dockerignore` | 🔴 新建 |
| `docker-compose.yml` | 部署 | db（pgvector/pg16）+ app（`profiles:[deploy]`）；默认 `up` 仅起 db 保本地开发，`--profile deploy` 起全栈 | `docker compose [--profile deploy] up` | `docker-compose.yml` | 🟡 改动（原仅 db，加 app profile） |
| `ci.yml` | CI | push main / 任意 PR → `uvx ruff check` + `uv run pytest`（默认排除 integration） | git push / PR | `.github/workflows/ci.yml` | 🔴 新建 |
| `release.yml` | CD | push main / `v*` tag → 多阶段构建 → 推 ghcr.io（tag `latest`+sha），用仓库自带 `GITHUB_TOKEN` | git push main / 打 tag | `.github/workflows/release.yml` | 🔴 新建 |
| `psycopg[binary]` | 迁移驱动 | alembic 同步引擎迁移所需（async→sync，见 env.py:22）；原仅有 asyncpg | `uv sync` / 镜像内 `alembic upgrade` | `pyproject.toml` 主依赖 | 🟡 新增 |
