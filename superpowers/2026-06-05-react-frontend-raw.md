# React 前端搭建 — Brainstorming 原始材料

> **性质**：raw 规划材料（按 dev-standards.md 归档），用于留存与回溯
> **日期**：2026-06-05
> **对应 spec**：`docs/superpowers/specs/2026-06-05-react-frontend-design.md`
> **方法**：superpowers:brainstorming 技能

---

## 1. 原始诉求（用户原话）

> 我想采用 vue/react 这样的成熟架构搭建一个前端，不考虑老栈的 chainlit

背景：用户已完成新栈 LLM key 接线修复，新栈（事件驱动 5-Agent）可调真实 LLM（火山方舟 doubao），`/api/chat` 实测返回 `stack:"new"` 真实教学回复。现在要一个图形前端来手动测试教学对话。

---

## 2. 前端现状排查（实测穷举，非臆测）

| 候选 | 状态 | 实测证据 |
|---|---|---|
| Vue/React `web/` 前端 | ❌ 不存在 | 无 `web/` 目录、无 `package.json`、无 `.vue/.tsx`。`main.py:40` 的 `web/dist` 挂载是预留代码 |
| Chainlit UI | ⚠️ 空壳 | `app/ui/` 两文件占位（`on_message` 是 `pass`，后端返回"暂未配置"），依赖未装 |
| FastAPI Swagger | ✅ 可用 | `/docs` 已实测能调 `/api/chat` |

结论：项目无可用图形前端，需从零建。

---

## 3. 澄清问题与决策

| # | 问题 | 选项 | 决策 |
|---|---|---|---|
| 1 | 技术栈 | React / Vue / 你帮我选 | **你帮我选 → React + Vite + TS**（流式生态大、markdown/代码高亮库丰富、web/dist 可直接挂） |
| 2 | UI 范围 | 最小纯聊天 / 标准 / 完整含登录画像知识库 | **完整版** |
| 3 | 认证 | 轻量 user_id 存本地 / 后端补 JWT / 跳过写死 | **轻量：user_id 存 localStorage**（不改后端） |
| 4 | 对话端点 | /api/chat 非流式 / /chat/stream 伪流式 / 后端改真流式 | **后端改真流式 → 经分析改为非流式 + 真流式拆独立项目** |
| 5 | 真流式排序 | 先前端 / 先后端流式 / 并行 | **先前端，流式后续** |
| 6 | 范围校准（画像/会话页无数据） | 缩到有数据的页 / 后端补持久化 / 占位页先搭骨架 | **占位页先搭骨架** |

---

## 4. 设计过程中暴露的两个后端约束（关键，影响范围）

### 约束 1：真流式与单线程事件循环架构冲突

用户初选"后端改真流式"。分析发现：新栈核心是单线程事件循环（spec §3.5.1），Agent 是"事件 handler 短任务"，reply 只在所有 Agent 协同算完后产生。真流式需把 Tutor 的 token 穿过 `collab_loop → assembly → API` 透出，要把 Tutor handler 改成生成器/回调，**违背 spec §3.5 的可回放设计**。

→ 决策：真流式是架构级后端改造，拆为独立项目。前端先用 `/api/chat` 非流式（字段更全，含 mastery_score/mode_path/turn_count）。

### 约束 2：新栈不持久化，画像/会话历史端点无数据

实测 `run_new_agent_session` 用内存 EventStore（`:memory:`），用完即弃，不写 session_store/user_profile。实测：
- `GET /api/sessions?user_id=1` → `[]`
- `GET /api/sessions/manual1` → `会话不存在`
- `GET /api/profile/1` → `{sessions:0, avg_mastery:0}`
- `GET /api/knowledge` → `[]`（但 knowledge CRUD 端点真实，只是没创建过）

→ 决策：画像页、会话历史侧栏做占位骨架，标注「待后端持久化」，不脑补假数据。

---

## 5. 端点真实性盘点（决定每页是真实还是占位）

| 端点 | 真实性 | 用途 |
|---|---|---|
| POST /api/auth/register, /login | ✅ 真实（返回 user_id，无 token） | 登录页 |
| POST /api/chat | ✅ 真实（新栈，字段全） | 聊天页（核心） |
| POST/GET/DELETE /api/knowledge | ✅ 真实 CRUD（KnowledgeStore 持久化） | 知识库页 |
| GET /api/profile/{user_id} | ⏳ 端点在但数据空 | 画像页（占位） |
| GET /api/sessions | ⏳ 端点在但返回 [] | 会话侧栏（占位） |

---

## 6. 跨域处理决策（设计中直接定，无需问）

- 开发：vite dev proxy 转发 `/api/*` → `:8001`，零改后端
- 生产：`npm run build` → `web/dist`，FastAPI 同源伺服（main.py:40 预留），无跨域
- 后端当前无 CORS 中间件——靠上述两模式规避，不强加 CORS

---

## 7. 后续独立项目（本次不做，留待 brainstorm）

- **后端真流式改造**：改 collab_loop 支持 Tutor token 透传 + SSE，需与 spec §3.5 协调
- **后端新栈持久化**：chat 后写 session_store + user_profile，让画像/会话页有真实数据
