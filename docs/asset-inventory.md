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

## 子项目② 实时协作流（待实现，spec 已定稿）

> spec：`docs/designs/2026-06-11-realtime-collab-stream-design.md`。下列产物为该 spec 规划的改动/新建，**尚未实现**，实现后补 file:line。

| 名字 | 归属子系统 | 功能（规划） | 三色 | 位置 |
|---|---|---|---|---|
| `run_collab_loop` on_event 钩子 | Orchestration | 循环内每 publish 一事件即回调透出，供 SSE 实时桥接 | 🟡 改动 | `app/orchestration/collab_loop.py:31` |
| `run_new_agent_session`/`build_new_stack` | Orchestration | 加可选 graph/on_event 参数，透传桥接与外部 graph | 🟡 改动 | `app/orchestration/assembly.py:131/100` |
| `project_event` | API | SSE 语义事件白名单过滤 + 转前端友好 payload | 🔴 新建 | `app/api/_sse_projection.py`（待建） |
| `MasteryNodeTable`/`MasteryEdgeTable` | Infrastructure | 掌握度节点/边的 SQLAlchemy 表（PG/SQLite 双模） | 🔴 新建 | `app/models/tables.py` |
| `SQLAlchemyMasteryStore` | Infrastructure | 复刻旧 store 4 方法契约，底层走 AsyncSession | 🔴 新建 | `app/infrastructure/storage/sqlalchemy_mastery_store.py`（待建） |
| `persist_turn` | API | 共享落库函数：会话+消息+掌握度原子提交，chat/chat_stream 复用 | 🔴 新建 | `app/api/_persist.py`（待建） |
| `chat_stream.generate_new` | API | 重写为队列桥接真流式 SSE + 流末复用落库 | 🟡 改动 | `app/api/chat_stream.py:19` |
| `chat`（非流式） | API | 改调共享 persist_turn，接掌握度落库 | 🟡 改动 | `app/api/chat.py:29` |
| `get_profile` | API | 读真实 sessions 计数 + mastery_nodes 均值（0-100） | 🟡 改动 | `app/api/profile.py:6` |
| 旧 `MasteryGraphStore` | Infrastructure | aiosqlite 掌握度 store；本子项目**不删不改**，4 测试在用 | 🟢 保持 | `app/infrastructure/storage/mastery_graph_store.py:7` |

## 项目级规则（.claude/rules）

| 名字 | 功能 | 触发 / 入口 | 位置 |
|---|---|---|---|
| `dev-standards.md` | 全局开发规范的项目级镜像（语言/命令执行/README维护/模块三层规划/规划产出物管理） | 随会话加载 | `.claude/rules/dev-standards.md` |
| `learning-docs.md` | 学习文档落地规则（Learned/ 下 QA 式记录的格式与流程） | learning-docs skill 触发 | `.claude/rules/learning-docs.md` |
| `agent-root.md` | StudyAgent 框架根规范（四层单向依赖、薄壳节点、spec 同步规则） | app/agent/ 下开发时 | `.claude/rules/agent-root.md` |
| `solution-presentation.md` | 方案呈现规范（引用即解释 + 资产清单/三色血缘默认开头） | 给用户任何方案/计划/设计时 | `.claude/rules/solution-presentation.md` |
