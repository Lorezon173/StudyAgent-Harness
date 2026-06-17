# 前端重设计 + 后端持久化升级 · Brainstorming Raw 材料

> 日期：2026-06-09
> 用途：本次 brainstorming 的完整决策链原始记录，供 docs/designs 下的 spec 追溯
> 对应 spec：
> - `docs/designs/2026-06-09-redesign-decomposition-overview.md`（分解总览）
> - `docs/designs/2026-06-09-storage-foundation-design.md`（子项目①）

## 触发

用户手动测试现有 React 前端 + 新栈后端后，一次性提出 7 项需求/缺陷（见下）。

## 7 项原始需求（用户原话要点）

1. 前端页面没有任何设计，要帮设计前端，风格简约大气
2. 切换模块卡时之前任务丢失（会话→数据库→会话，聊天过程消失）
3. 知识库新建应鼓励提交文件（文本/图片/代码等），文本至少支持 txt、markdown 解析
4. 画像部分看不到学习情况；讨论是否给用户自主更新后端持久化的权限（用户催促立刻执行持久化）
5. 聊天界面缺少多会话框，新增会话后无法切回之前的会话
6. 发起对话后只有静止「AI 思考中」，希望前端展示可缩放的各 agent 简单输出/评价/思考过程；为此需先做流式输出
7. 对话后回合次数一直显示 11 回合

## 根因探索结论（带 file:line，已写入分解总览）

- 需求2/5：`Chat.tsx:16` 纯内存 useState；`chat.py:15-31` 新栈不碰 SessionStore；sessions 表空
- 需求4：`profile.py:6` 写死 `{sessions:0,avg_mastery:0}`；掌握度只在内存 EventStore（`assembly.py:110` `:memory:`）
- 需求6：`chat_stream.py:19` 假流式，run_new_agent_session 整体跑完才 yield
- 需求7：`collab_loop.py:74` turn_count = 事件循环 pop 次数，非教学回合数
- 需求3：`knowledge.py:10` 仅收 name/description；extractor 已存在未接 API
- 存储现状：`database.py:9` engine 硬编码 sqlite 未读 settings；Store 双模式已写但实例化不传 db

## 可视化伴侣决策（浏览器样稿）

- **整体布局**：用户选 **A**（左侧深色栏会话列表+导航 + 主聊天）。备选 B（三栏带右 Agent 面板）、C（顶部切换全宽）
- **思考过程展示**：用户选 **B**（底部可伸缩抽屉，实时滚动 Agent 事件）。备选 A（气泡内联折叠条）、C（时间线卡片流）

## 技术决策（AskUserQuestion 收集）

| 问题 | 用户选择 |
|---|---|
| 会话持久化 | 后端落库；用更成熟架构 PostgreSQL + pgvector（pgvector 做 RAG 向量库），方案后续详谈 |
| 文件解析范围 | 文本类（含 markdown、代码，纯文本直读）+ PDF/Word；图片 OCR 暂不接 |
| 画像持久化 | 自动落库 + 手动保存按钮 |
| 流式深度 | Agent 事件级流式 |
| PG 迁移范围 | 业务表 + 向量都上 PG |
| PG 运行方式 | Docker pgvector 镜像 |
| 迁移过渡 | SQLite/PG 双模式共存 |
| 交付节奏 | 分子项目逐个交付（推荐方案） |

## 4 子项目分解（用户认可）

1. 存储底座：PG + pgvector + 会话持久化（地基）
2. 实时协作流：Agent 事件级 SSE + 掌握度落库 + 回合数修复
3. 知识库文件上传：txt/md/代码 + PDF/Word 解析入库
4. 前端整体重设计（消费①②③）

依赖：① → ②③（并行）→ ④

## 子项目① 三层设计确认链

- **第1节 总览**：根因诊断用户认可；对话历史存哪 → 选 (b) 新建 messages 表
- **第2节 子模块**：会话标题 → 选 (a) SessionTable 加 title 字段；state_json → 选 (a) 暂存 `{}`
- **第3节 实施计划**：PG 驱动 → asyncpg；写库失败容错（仅记日志仍返回 reply）→ 认同；整体计划无遗漏

## 待续

子项目 ②③④ 待 ① 实现验证后，各自再走 brainstorming → spec → 实现闭环。
