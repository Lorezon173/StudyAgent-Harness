# StudyAgent 前端重设计 + 后端持久化升级 · 项目分解总览

> 创建日期：2026-06-09
> 类型：总览设计（Decomposition Overview）
> 状态：已与用户对齐拆分��待逐子项目细化 spec

## 背景

用户在手动测试现有 React 前端 + 新栈（事件驱动 5-Agent）后端后，提出 7 项需求/缺陷。经源码探索定位根因，确认这是一次**跨多个独立子系统**的大型改造，按 brainstorming 规范先分解为可独立交付的子项目，再逐个走「设计 → 计划 → 实现 → 验证」闭环。

## 7 项原始需求与根因（基于源码事实）

| # | 需求/缺陷 | 根因（file:line） |
|---|---|---|
| 1 | 前端无设计，要简约大气 | `web/src/pages/*` 全内联 style，无设计系统 |
| 2 | 切模块卡后会话丢失 | `Chat.tsx:16` messages 纯 `useState` 内存态，路由切走即销毁；后端 `sessions` 表为空 |
| 3 | 知识库新建应支持文件上传解析 | `app/api/knowledge.py:10` 仅收 name/description；已有 extractor 未接 API |
| 4 | 画像看不到学习情况 | `app/api/profile.py:6` 返回写死 `{sessions:0, avg_mastery:0}`；掌握度只存内存 EventStore |
| 5 | 新增会话后无法切回旧会话 | `Chat.tsx:42 resetSession` 直接清空内存，无多会话列表 |
| 6 | 思考过程要可视化、需先做流式 | `app/api/chat_stream.py:19` 假流式——`run_new_agent_session` 整体跑完才一次性 yield |
| 7 | 回合数恒显示 11 | `app/orchestration/collab_loop.py:74` `ws.turn_count = turn`，turn 是事件循环 pop 次数，非教学回合数 |

## 关键决策（已与用户对齐）

- **持久化架构**：PostgreSQL + pgvector（Docker 镜像），业务表与 RAG 向量都上 PG
- **过渡策略**：SQLite/PG 双模式共存（`DATABASE_URL` 切换；开发测试用 SQLite，生产用 PG）
- **不迁旧数据**：现有 SQLite 几乎无真实数据（users 空、sessions 空、知识库内存），PG 重建 schema 即可
- **会话持久化**：chat 每轮把会话 + 完整对话历史写库；前端从后端拉列表与历史
- **掌握度持久化**：自动落库 + 画像页「手动保存」按钮
- **文件上传范围**：txt/markdown/代码（纯文本直读）+ PDF/Word（复用已有 extractor）；图片 OCR 暂不接
- **流式深度**：Agent 事件级 SSE——改造 collab_loop 让每个 Agent 产出实时推送
- **前端布局**：方案 A（左侧深色栏会话列表+导航 + 主聊天区）+ 思考过程方案 B（底部可伸缩抽屉，实时滚动 Agent 事件）
- **交付节奏**：分子项目逐个交付，每个可独立验证

## 子项目分解（按依赖顺序）

### ① 存储底座：PostgreSQL + pgvector + 会话持久化

**目标**：把持久化地基从「双模式但未接 db」改为真正落库，支撑后续一切持久化需求。

- Docker 起 pgvector 镜像（内置 pgvector 扩展）
- `DATABASE_URL` 双模式：指 PG 走 PG，指 sqlite 走 SQLite（测试）
- 所有 Store 实例化时接上 db（修「`_store = SessionStore()` 没传 db」导致全程内存的根因）
- chat 每轮写会话 + 完整对话历史入库
- Alembic 在 PG 重建 schema
- 新增 API：会话列表 / 会话历史拉取（撑需求 2、5 的后端侧）

**独立验证**：发起对话后，能在 PG 查到会话记录与完整消息历史。

**依赖**：无（地基）。

### ② 实时协作流：Agent 事件级 SSE + 掌握度落库 + 回合数修复

**目标**：把假流式改成逐 Agent 事件真流式，掌握度落库，修回合数语义。

- 改造 `collab_loop` 让每个 Agent 产出实时推送（事件回调/异步队列）
- `chat_stream` 改成逐 Agent 事件 SSE，每个事件含 agent 名 / 类型 / 内容 / 评价
- MasteryGraph 掌握度自动落库（撑需求 4 的真实数据���源）
- 修 `turn_count`：区分「事件循环迭代次数」与「教学回合数」（需求 7）
- `profile` 接口读真实数据，替换写死值

**独立验证**：curl 流式接口能看到逐 Agent 事件分���到达；profile 返回真实会话数与掌握度。

**依赖**：① 的库（掌握度落库、profile 读库）。

### ③ 知识库文件上传：txt/md/代码 + PDF/Word 解析入库

**目标**：知识库从纯元数据升级为「上传文件 → 解析 → 向量化入库 → 可检索」。

- knowledge API 新增文件上传端点
- 接已有 extractor（text / pdf / docx）；txt/md/代码走纯文本直读
- 解析内容向量化入 pgvector（依赖 ① 的 pgvector）
- Retriever 检索源从 FakeRAGStore 切到真实库

**独立验证**：上传一个 markdown/PDF，能在知识库看到，且对话时 Retriever 能检索到其内容。

**依赖**：① 的 pgvector。

### ④ 前端整体重设计（简约大气）

**目标**：按方案 A + 抽屉 B 重做整个前端，消费 ①②③ 的后端能力。

- 布局 A：左侧深色栏（会话列表 + 导航）+ 主聊天区，建立设计系统（配色/间距/组件）
- 多会话切换（消费 ① 的会话 API，修需求 2、5）
- 思考过程抽屉 B（消费 ② 的 SSE 事件流，撑需求 6，可伸缩高度）
- 画像页真实数据 + 手动保存按钮（消费 ②，撑需求 4）
- 知识库上传 UI（消费 ③，撑需求 3）
- 回合数正确显示（需求 7）

**独立验证**：前端完整可用——多会话切换不丢、思考抽屉随流式逐步显示、画像有真实数据、知识库可上传。

**依赖**：①②③ 的后端能力，放最后整体收口。

## 依赖关系图

```
①存储底座 ──┬──> ②实时协作流 ──┐
            └──> ③知识库上传 ──┼──> ④前端重设计
                              ──┘
```

① 是地基；②③ 可在 ① 完成后并行；④ 收口，消费前三者。

## 子项目 spec 索引

- 子项目①：`docs/designs/2026-06-09-storage-foundation-design.md`（已完成实现）
- 子项目②：`docs/designs/2026-06-11-realtime-collab-stream-design.md`（spec 已定稿，待实现）
- 子项目③：待 ① 完成后 brainstorm
- 子项目④：待 ②③ 完成后 brainstorm
