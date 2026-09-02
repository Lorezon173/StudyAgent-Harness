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

## RAG Foundation 下一阶段主控核心资产

> 下一阶段唯一核心计划：`docs/rag-work/plans/2026-07-24-rag-foundation-parallel-todolist.md`。它汇总四路独立核验、稳定 blocker 账本、主控冻结边界和 Phase 0-6 TodoList；各 RAG-X 窗口仍只回写自己的状态片段。

| 名字 | 归属子系统 | 功能 | 触发 / 入口 | 位置 | 三色 |
|---|---|---|---|---|---|
| RAG Foundation 主清单 | 研发治理 / RAG 基础能力 | 下一阶段唯一核心计划与合流门禁：记录 A/B/C/D 真实状态、BLK-001~013、P0 裁决、已冻结/后置边界和分阶段 TodoList | 主控派工、状态合流、复核与验收 | `docs/rag-work/plans/2026-07-24-rag-foundation-parallel-todolist.md:1` | 🟡 改动 |
| RAG P0 决策面板（源） | 研发治理 / 决策辅助 | 将 BLK-001/002 已确认裁决与 BLK-003/005 待确认项按事实→方案→影响→验收组织；HTML 的 canonical source | P0 逐项讨论与用户决策 | `docs/rag-work/decision-canvas/2026-07-25-rag-p0-decision-dashboard.md:1` | 🔴 新建 |
| RAG P0 决策面板（HTML） | 研发治理 / 决策辅助 | 主清单裁决的可视化单文件阅读视图，嵌入源路径与 SHA；不作为事实源 | 浏览器直接打开 | `docs/rag-work/decision-canvas/2026-07-25-rag-p0-decision-dashboard.html` | 🔴 生成视图 |
| RAG P0 已确认决策记录 | 研发治理 / RAG 基础能力 | 只记录用户已确认的 P0 裁决、冻结边界、解除条件和禁止提前实现事项 | P0 讨论确认后留存 | `docs/rag-work/plans/2026-07-27-rag-p0-confirmed-decisions.md` | 🔴 新建 |
| RAG Foundation 执行顺序 | 研发治理 / RAG 基础能力 | 将下一阶段拆为 Phase 0-6，定义并行、等待、越权边界、阶段产物与复核触发条件 | 主控排期、任务分发与验收 | `docs/rag-work/plans/2026-07-27-rag-foundation-execution-order.md` | 🔴 新建 |
| RAG Foundation 状态同步协议 | 研发治理 / RAG 基础能力 | 约束主清单单写者及 RAG-A/B/C/D 各自状态片段唯一写者 | 每轮任务回写与主控合流 | `docs/rag-work/status/README.md:6-53` | 🟢 保持 |
| RAG-A/B/C/D 状态片段 | 各任务状态面 | 各窗口记录执行范围、证据、blocker、共享裁决请求和未做事项；主控只读 | 各任务窗口完成 Todo 后回写 | `docs/rag-work/status/RAG-A.md` 等 | 🟢 保持 |

## 在线 RAG P0 修复规范

| 名字 | 归属子系统 | 功能 | 触发 / 入口 | 位置 | 三色 |
|---|---|---|---|---|---|
| `2026-07-24-online-rag-p0-repair-spec.md` | 在线 RAG / 编排与检索 | RAG-C P0 修复 spec：检索先行启动、evidence→Tutor 投影、visibility 过滤、五态 outcome、在线 composition 校验；已对齐 DEC-001/003/004/007/008/009，Phase 1C 修订完成，待主控复核（C-08）后可编码 | 在线 RAG P0 断点审计后的设计入口；RAG-C 窗口唯一写者 | `docs/rag-work/specs/2026-07-24-online-rag-p0-repair-spec.md` | 🟡 Phase 1C 修订完成（待复核） |

## RAG 决策画布（治理辅助）

| 名字 | 归属子系统 | 功能 | 触发 / 入口 | 位置 | 三色 |
|---|---|---|---|---|---|
| BLK-004 决策画布（源 + HTML） | 研发治理 / 决策辅助 | BLK-004 chunk identity/provenance 的决策阅读视图：目标追溯→子框架位置→数据流→方案对照→DEC-005/006 已确认裁决；HTML 由 render-html 渲染，非事实源 | BLK-004 逐项讨论与用户裁决 | `docs/rag-work/decision-canvas/2026-07-27-rag-blk004-decision-dashboard.md` / `.html` | 🔴 新建 |
| BLK-006 决策画布（源 + HTML） | 研发治理 / 决策辅助 | BLK-006 backend/outcome 真实性的决策阅读视图：断点事实→三项裁决对照→DEC-007/008/009 已确认裁决；HTML 由 render-html 渲染，非事实源 | BLK-006 逐项讨论与用户裁决 | `docs/rag-work/decision-canvas/2026-07-29-rag-blk006-decision-dashboard.md` / `.html` | 🔴 新建 |
| BLK-007 决策画布（源 + HTML） | 研发治理 / 决策辅助 | BLK-007 baseline admission 的决策阅读视图：准入 gate 六项版（DEC-010）与 containment proxy 口径（DEC-011）已确认裁决；HTML 由 render-html 渲染，非事实源 | BLK-007 逐项讨论与用户裁决 | `docs/rag-work/decision-canvas/2026-07-29-rag-blk007-decision-dashboard.md` / `.html` | 🔴 新建 |

## RAG 主控派工提示词（Phase 0 分发）

| 名字 | 归属子系统 | 功能 | 触发 / 入口 | 位置 | 三色 |
|---|---|---|---|---|---|
| RAG-A/B/C/D 派工提示词 | 研发治理 / 多窗口协作 | 四份子窗口启动提示词：角色边界 + 必读文件路径（回应包在 §9）+ 任务清单 + 回写纪律；以文件为媒介传达主清单 §9 回应包 | 用户复制粘贴到对应 RAG-X 窗口 | `docs/rag-work/dispatch/2026-07-29-dispatch-rag-{a,b,c,d}-prompt.md` | 🔴 新建 |
| RAG-A/B/C/D 第二轮派工提示词 | 研发治理 / 多窗口协作 | Phase 2 / Phase 1D 派工：A 线验收通过待命 Phase 4；B 线 B-04 冻结进 Phase 2 编码；C 线 C-08 provisional 通过进编码；D 线进 Phase 1D 只读工具 | 用户复制粘贴到对应 RAG-X 窗口 | `docs/rag-work/dispatch/2026-07-29-dispatch-rag-{a,b,c,d}-round2.md` | 🔴 新建 |

## 多窗口协作 skill 包（multi-window-orchestration，已安装）

| 名字 | 归属子系统 | 功能 | 触发 / 入口 | 位置 | 三色 |
|---|---|---|---|---|---|
| orchestrator | 多窗口协作 / 主控 | 主控全流程：建档目录、blocker 账本（冻结≠解除）、单写者、分流派工（窗口初始化包 + subagent 三件套）、回执独立复核 | 用户要求多单元并行 / 指定主控 / 大功能块拆分 | `.claude/skills/orchestrator` → `.evolve/local/skills/multi-window-orchestration/orchestrator/SKILL.md` | 🔴 新建（已软链生效） |
| task-splitter | 多窗口协作 / 并行检测 | spec → 依赖图 + 写冲突 + 契约检查 → 三准则判定 → 分流（需交互→窗口，纯执行→subagent）+ parallel-plan | 实现大功能块前问"能否并行/怎么拆" | `.claude/skills/task-splitter` → 同上目录 `task-splitter/SKILL.md` | 🔴 新建（已软链生效） |
| decision-canvas | 多窗口协作 / 决策 | 共享契约决策：HTML-first 决策视图（目标→事实→对照→验收）→ 用户确认 → MD 固化 | 需用户拍板的共享契约 / 用户反馈细节淹没目标 | `.claude/skills/decision-canvas` → 同上目录 `decision-canvas/SKILL.md` | 🔴 新建（已软链生效） |

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

## EPUB Extractor 正式接入（已实施）

> spec：`docs/rag-work/specs/2026-07-24-epub-extractor-spec.md`。范围只含 Extractor 层；chunking、ingestion、上传 API 与黄金集由其他工作项负责。实现：RAG-A（A-01~A-07）。

| 名字 | 归属子系统 | 功能 | 触发 / 入口 | 位置 | 三色 |
|---|---|---|---|---|---|
| `EpubExtractor` | RAG 基础设施 | 已实现：按 OPF spine 顺序将 `.epub` 提取为纯文本（严格 UTF-8、`<br>` 归一化、任一 spine 资源失败整体空串）；实现现有 `Extractor` 契约，只返回 `str` | `get_extractor("*.epub")` | `app/infrastructure/rag/extractors/epub_extractor.py` | 🟢 已建 |
| `get_extractor()` | RAG 基础设施 | 扩展名工厂；已注册 `.epub/.EPUB` 路由至 `EpubExtractor` | 文件摄入调用方 | `app/infrastructure/rag/extractors/base.py:20-28` | 🟢 已建 |
| `extract_epub.py` | benchmark | 特定本地书籍 EPUB → paragraph JSONL 的离线脚本；只作标准库解析行为参考，禁止生产路径导入 | benchmark CLI | `benchmarks/rag/books/the-myth-of-sisyphus/extract_epub.py:1-159` | 🟢 保持 |
| `test_extractors.py` | 单元测试 | 已含 EPUB 动态 fixture 测试：工厂路由、spine 顺序对抗、`<br>` 归一化精确表、HTML entity、块分隔、href 解析与失败降级 | pytest | `tests/unit/infrastructure/test_extractors.py` | 🟢 已建 |

## 项目级规则（.claude/rules）


| 名字 | 功能 | 触发 / 入口 | 位置 |
|---|---|---|---|
| `dev-standards.md` | 全局开发规范的项目级镜像（语言/命令执行/README维护/模块三层规划/规划产出物管理） | 随会话加载 | `.claude/rules/dev-standards.md` |
| `learning-docs.md` | 学习文档落地规则（Learned/ 下 QA 式记录的格式与流程） | learning-docs skill 触发 | `.claude/rules/learning-docs.md` |
| `solution-presentation.md` | 方案呈现规范（引用即解释 + 资产清单/三色血缘默认开头） | 给用户任何方案/计划/设计时 | `.claude/rules/solution-presentation.md` |

## 项目入口文档

| 名字 | 功能 | 触发 / 入口 | 位置 |
|---|---|---|---|
| `CLAUDE.md` | Claude 每会话自动加载的项目入口：单栈方向（`app/` 为唯一主体）+ 四层架构 + 关键目录地图 + 五 Agent 点名 + 时效性地标 + 载体路标 | 会话启动自动加载 | `CLAUDE.md`（根目录） |

## 项目级 ChunkingService（规划中）

| 名字 | 归属子系统 | 功能 | 触发 / 入口 | 位置 | 三色 |
|---|---|---|---|---|---|
| `2026-07-24-project-chunking-service-spec.md` | RAG Gate 0 设计 | 项目级统一 chunking 的正式 spec：定义 ChunkDocument、ChunkingService、摄入编排、metadata、评测边界与 Gate 0 验收 | 用户确认后作为实现依据 | `docs/rag-work/specs/2026-07-24-project-chunking-service-spec.md` | 🟡 规划 |
| `ChunkingService` | Harness | 拟议无状态纯服务：线性/结构化元素 → 供 `RAGCoordinator.index_documents` 消费的 docs；不写库、不检索、不依赖 benchmark | `KnowledgeIngestionService` 调用 | `app/harness/chunking_service.py`（待建） | 🔴 新建 |
| `KnowledgeIngestionService` | Harness / 编排边界 | 拟议摄入编排：提取/适配/切块后委托现有 `RAGCoordinator.index_documents` | 后续 API 或脚本入口 | `app/harness/knowledge_ingestion.py`（待建） | 🔴 新建 |
| `EpubExtractor`（依赖引用） | Infrastructure / RAG extractors | 依赖 EPUB 提取能力；唯一事实源与 spec 见「EPUB Extractor 正式接入（已实施）」节，本行不作为独立事实登记 | — | 见「EPUB Extractor 正式接入（已实施）」节 | 🟢 引用 |

## CI/CD 与 Docker 部署

| 名字 | 归属子系统 | 功能 | 触发 / 入口 | 位置 | 三色 |
|---|---|---|---|---|---|
| `Dockerfile` | 部署 | 多阶段镜像：node 构建前端 → uv 装后端（`--extra rag`）→ 精简 runtime；启动自跑 `alembic upgrade head` + uvicorn | `docker build` / release.yml | `Dockerfile` | 🔴 新建 |
| `.dockerignore` | 部署 | 构建上下文裁剪 + 密钥防泄漏（排除 .env/node_modules/.venv/tests/docs） | `docker build` | `.dockerignore` | 🔴 新建 |
| `docker-compose.yml` | 部署 | db（pgvector/pg16）+ app（`profiles:[deploy]`）；默认 `up` 仅起 db 保本地开发，`--profile deploy` 起全栈 | `docker compose [--profile deploy] up` | `docker-compose.yml` | 🟡 改动（原仅 db，加 app profile） |
| `ci.yml` | CI | push main / 任意 PR → `uvx ruff check` + `uv run pytest`（默认排除 integration） | git push / PR | `.github/workflows/ci.yml` | 🔴 新建 |
| `release.yml` | CD | push main / `v*` tag → 多阶段构建 → 推 ghcr.io（tag `latest`+sha），用仓库自带 `GITHUB_TOKEN` | git push main / 打 tag | `.github/workflows/release.yml` | 🔴 新建 |
| `psycopg[binary]` | 迁移驱动 | alembic 同步引擎迁移所需（async→sync，见 env.py:22）；原仅有 asyncpg | `uv sync` / 镜像内 `alembic upgrade` | `pyproject.toml` 主依赖 | 🟡 新增 |
