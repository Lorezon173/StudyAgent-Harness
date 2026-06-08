# React 前端搭建 — 设计文档

> **用途**：为 StudyAgent 新栈（事件驱动 5-Agent）搭建一个 React 图形前端，用于手动测试教学对话
> **日期**：2026-06-05
> **技术栈**：React + Vite + TypeScript
> **重构策略**：纯新增前端，不改后端在线逻辑（仅靠 vite proxy + 生产同源规避 CORS）
> **raw 材料**：`superpowers/2026-06-05-react-frontend-raw.md`

---

## 0. 决策快照

| # | 维度 | 决策 |
|---|---|---|
| 1 | 技术栈 | React + Vite + TypeScript |
| 2 | UI 范围 | 完整版（登录/聊天/画像/知识库），但画像/会话历史为占位骨架 |
| 3 | 认证 | 轻量——user_id 存 localStorage，不改后端 |
| 4 | 对话端点 | `/api/chat` 非流式（字段全） |
| 5 | 真流式 | 拆为独立后端项目，本次不做 |
| 6 | 跨域 | 开发 vite proxy + 生产同源，不加后端 CORS |
| 7 | 状态管理 | React Context + useState，不引 Redux/Zustand |

### 0.1 否决项及理由

| 被否方案 | 否决理由 |
|---|---|
| Vue | React 流式/markdown 生态更大，配套 LLM 应用例子多 |
| 后端改真流式（本次） | 违背 spec §3.5 单线程事件循环可回放设计，是架构级改造，拆独立项目 |
| `/chat/stream` 伪流式 | 新栈 stream 实际等算完才一次性返回，且只有 reply、无 mastery/mode_path |
| 后端补 JWT 鉴权 | 当前测试为主，user_id 存本地够用，YAGNI |
| 画像/会话页展示真实数据 | 新栈用内存 EventStore 不持久化，后端无数据，做占位骨架 |
| axios / Redux | 原生 fetch + Context 够这个规模，YAGNI |
| 后端加 CORS 中间件 | vite proxy（开发）+ 同源伺服（生产）已规避，不必改后端 |

---

## 1. 整体架构

### 1.1 目录结构

```
web/                              # 建在项目根，与 main.py:40 的 web/dist 挂载点对齐
├── package.json
├── vite.config.ts                # 含 dev proxy + build outDir=dist
├── tsconfig.json
├── index.html
└── src/
    ├── main.tsx                  # React 入口
    ├── App.tsx                   # 路由骨架（react-router-dom）
    ├── api/
    │   └── client.ts             # 统一 fetch 封装（注入 user_id + 错误处理）
    ├── store/
    │   └── auth.tsx              # AuthContext：user_id 的 localStorage 读写 + 全局共享
    ├── pages/
    │   ├── Login.tsx             # 登录/注册（真实）
    │   ├── Chat.tsx              # 聊天（真实，核心）
    │   ├── Knowledge.tsx         # 知识库 CRUD（真实）
    │   └── Profile.tsx           # 用户画像（占位骨架）
    ├── components/
    │   ├── Sidebar.tsx           # 会话历史侧栏（占位骨架）
    │   ├── MessageBubble.tsx     # 消息气泡 + markdown 渲染
    │   └── TeachingStatus.tsx    # mastery/mode_path/turn_count 展示
    └── types.ts                  # 与后端 schema 对应的 TS 类型
```

### 1.2 运行模式（规避后端无 CORS）

| 模式 | 命令 | 端口 | 跨域处理 |
|---|---|---|---|
| 开发 | `npm run dev` | vite :5173 | vite proxy：`/api/*` → `http://127.0.0.1:8000` |
| 生产 | `npm run build` | 产物落 `web/dist` | FastAPI 同源伺服（main.py:40 已挂载），无跨域 |

### 1.3 与后端的依赖

- 前端**只依赖 HTTP API**，不依赖后端任何内部实现
- 后端**零改动**（main.py 的 web/dist 挂载是既有预留逻辑）
- 后端需以 `set -a && source .env && set +a` 启动（确保新栈 flag 生效），**端口 8000**（跟随 README 默认 `uvicorn app.main:app` 无 `--port`）。vite proxy target 与验收均钉死 8000。若本机 8000 被占（如遗留进程），用 `--port` 指定其他端口并同步改 proxy target。

---

## 2. 页面设计与数据流

### 2.1 真实数据页

#### 登录/注册页（`pages/Login.tsx`）

- **职责**：用户登录或注册，拿到 user_id 存本地
- **端点**：`POST /api/auth/login` 或 `/register` → `{user_id, username}`（无 token）
- **数据流**：表单提交 → client.ts → 后端 → 成功则 `AuthContext.setUser(user_id, username)` 写 localStorage → 跳转 `/chat`
- **错误**：409 用户名已存在（注册）、401 用户名或密码错误（登录）→ 表单下方红字提示

#### 聊天页（`pages/Chat.tsx`）— 核心

- **职责**：多轮教学对话，展示 AI 回复与教学状态
- **端点**：`POST /api/chat {message, session_id, user_id}` → `ChatResponse{reply, mastery_score, turn_count, mode_path, cost_est_usd, stack}`
- **会话 id**：进入页面时前端生成 uuid 作为 session_id；侧栏「新建会话」生成新 id
- **组件构成**：
  - 消息列表：`MessageBubble`（用户右对齐，AI 左对齐）
  - AI 回复经 `react-markdown` 渲染（教学回复含 `**加粗**` 等格式）
  - `TeachingStatus`：mastery_score 进度条、mode_path 模式徽章序列、turn_count、stack 标识
  - 底部输入框 + 发送按钮
- **数据流**：输入 → 显示用户气泡 + loading 态 → client.ts POST（超时 120s）→ 收到 reply → 显示 AI 气泡 + 更新 TeachingStatus
- **关键约束**：消息列表前端内存维护（useState），刷新即丢——后端不持久化，诚实反映，不假装持久
- **错误**：500（如空 key OpenAIError）→ AI 气泡位置显示错误提示，不白屏；超时 → 提示「响应超时，教学协作环可能较慢」

#### 知识库页（`pages/Knowledge.tsx`）

- **职责**：知识库的增删查
- **端点**：`GET /api/knowledge`（列表）、`POST /api/knowledge {name, description}`（创建）、`DELETE /api/knowledge/{id}`（删除）
- **数据流**：进入加载列表 → 表格展示 → 新建表单提交后刷新列表 → 删除按钮调 DELETE 后刷新
- **备注**：KnowledgeStore 单测单独跑通过、CRUD 真实可用（默认 sqlite+aiosqlite 持久化）。test_stores.py 在全量跑时的失败是测试自身 event-loop 写法陈旧所致，非 Store bug，不影响知识库页对接

### 2.2 占位骨架页（后端暂无数据）

#### 用户画像页（`pages/Profile.tsx`）

- **端点**：`GET /api/profile/{user_id}` → 当前仅 `{user_id, stats:{sessions:0, avg_mastery:0}}`
- **UI 结构**：搭好三个区——掌握度图谱区、学习偏好区、学习进度区
- **数据区**：显示「待后端持久化后填充」占位文案 + 已有的 stats（sessions/avg_mastery）
- **目的**：UI 结构完整，后端补持久化后直接填数据

#### 会话历史侧栏（`components/Sidebar.tsx`）

- **端点**：`GET /api/sessions?user_id` → 当前 `[]`
- **UI 结构**：会话列表区 + 「新建会话」按钮
- **空态**：「暂无历史会话（新栈未持久化）」
- **「新建会话」**：可用——前端生成新 session_id，切换聊天页上下文

### 2.3 统一数据流原则

- 所有请求经 `api/client.ts`：自动从 AuthContext 注入 user_id、统一错误处理（401 → 跳登录、5xx → 抛给调用方显示）
- TS 类型（`types.ts`）与后端 `schemas.py` 对应，**注意以下字段精度**：
  - `ChatResponse` 含 `session_id`（勿漏）、`reply`、`mastery_score?: number`、`turn_count?: number`、`mode_path?: string[]`、`cost_est_usd?: number`、`stack?: "new"|"legacy"`
  - `AuthResponse` 含 `token?: string | null`（字段存在但端点不填，恒为 null）
  - `user_id` 是 **number**（非 string）。localStorage 只存字符串，`client.ts` 注入请求时须 `Number(...)` 转回，AuthContext 读取时同理——这是必须显式处理的类型转换点
  - `SessionResponse` 仅 `{session_id, user_id, state_json}`，**无** title/created_at。占位侧栏无碍；§4 持久化项解锁真实侧栏时，后端需先补这些字段

---

## 3. 错误处理、测试、构建接入

### 3.1 错误处理（`api/client.ts` 统一）

| 场景 | 处理 |
|---|---|
| 对话慢（协作环多次 LLM，实测一轮 10-40s） | 聊天页 loading 态 + fetch 超时 **120s** |
| 401 未授权 | 跳转登录页 |
| 5xx 后端报错（如空 key OpenAIError） | 调用方显示错误，不白屏 |
| 网络断 | toast「连接失败」 |

**关键**：对话是长耗时操作，长超时 + loading 态是必须的，不用默认短超时。

### 3.2 测试方式（轻量）

- `api/client.ts` 加少量 vitest 单测（user_id 注入、错误分支）
- 页面手动测：`npm run dev` → 登录 → 聊天 → 看教学状态 → 知识库 CRUD
- 后端已有 457 测试保障，前端只验证 HTTP 对接正确

### 3.3 构建产物接入 FastAPI

- vite 配 `build.outDir = "dist"`，`npm run build` → `web/dist`
- `main.py:40` 已预留：存在 `web/dist` 则挂载 `/assets` + catch-all 返回 `index.html`
- catch-all 正好兼容 React Router history 模式（前端路由刷新不 404）
- 生产同源伺服，无跨域

### 3.4 依赖选型（最小）

| 用途 | 库 |
|---|---|
| 路由 | react-router-dom |
| markdown 渲染 | react-markdown |
| 请求 | 原生 fetch（不引 axios） |
| 状态 | React Context + useState（不引 Redux） |
| 构建 | Vite |
| 测试 | Vitest |

---

## 4. 后续独立项目（本次不做）

| 项目 | 范围 | 解锁什么 |
|---|---|---|
| 后端真流式改造 | 改 collab_loop 支持 Tutor token 透传 + SSE，与 spec §3.5 协调 | 聊天打字机效果 |
| 后端新栈持久化 | chat 后写 session_store + user_profile；并为 SessionResponse 补 title/created_at 字段 | 画像页/会话侧栏的真实数据 |

---

## 5. 验收标准

1. `npm run dev` 启动前端，vite proxy 正常转发到后端 8000
2. 登录页能注册/登录，user_id 存入 localStorage
3. 聊天页能多轮对话，AI 回复 markdown 渲染，教学状态（mastery/mode_path/turn_count）正确显示
4. 知识库页能创建/列出/删除知识库
5. 画像页/会话侧栏 UI 结构完整，占位文案正确
6. `npm run build` 产物落 web/dist，`uvicorn` 同源访问前端正常
7. client.ts 单测通过
