# React 前端搭建 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 StudyAgent 新栈搭建一个 React + Vite + TypeScript 前端，手动测试教学对话（登录/聊天/画像/知识库四页，对话走 `/api/chat` 非流式）。

**Architecture:** 前端建在项目根 `web/`，开发期 vite proxy 转发 `/api/*` 到后端（规避 CORS），生产期 `npm run build` 产物落 `web/dist` 由 FastAPI 同源伺服（main.py:40 已预留挂载）。认证轻量化——`user_id` 存 localStorage。状态用 React Context + useState，不引 Redux。

**Tech Stack:** React 18 + Vite + TypeScript + react-router-dom + react-markdown + Vitest。后端零改动。

**对应 spec:** `docs/superpowers/specs/2026-06-05-react-frontend-design.md`

---

## 环境前置（执行前必读）

- **Node v24 / npm v11 已就绪**（实测）。所有前端命令在 `web/` 目录下跑。
- **后端端口**：spec 定 8000（跟随 README 默认）。但**本机 8000 当前被一个来路不明的遗留 python 进程占用**（PID 可能变化），且可用的新栈实例在 8001。本计划用**可配置 proxy target**化解：`vite.config.ts` 的 proxy target 读环境变量 `VITE_API_TARGET`，默认 `http://127.0.0.1:8000`。开发者按 Task 0 确认后端实际端口，必要时设 `VITE_API_TARGET=http://127.0.0.1:8001`。
- **后端启动方式**（确保新栈生效）：
  ```bash
  cd <项目根> && set -a && source .env && set +a && PYTHONPATH=. .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
  ```
- **git**：分支 `main`，可正常 commit。commit message 末尾加 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`。只 `git add <明确文件>`，不用 `git add -A`。
- **前端不写重单测**（spec §3.2）：仅 `api/client.ts` 用 Vitest TDD；页面/组件以"`npm run build` 类型检查通过 + 手动验证点"为验收，不强求组件级 TDD。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `web/package.json` | 依赖与脚本（dev/build/test） |
| `web/vite.config.ts` | dev proxy（可配 target）+ build outDir=dist + vitest 配置 |
| `web/tsconfig.json` / `web/tsconfig.node.json` | TS 配置 |
| `web/index.html` | SPA 入口 HTML |
| `web/src/main.tsx` | React 挂载 + Router |
| `web/src/types.ts` | 与后端 schemas.py 对应的 TS 类型（含 §2.3 字段精度） |
| `web/src/api/client.ts` | 统一 fetch 封装：注入 user_id、错误处理、120s 超时 |
| `web/src/store/auth.tsx` | AuthContext：user_id 的 localStorage 读写（number 转换） |
| `web/src/App.tsx` | 路由骨架 + 受保护路由 |
| `web/src/pages/Login.tsx` | 登录/注册（真实） |
| `web/src/pages/Chat.tsx` | 聊天（真实，核心） |
| `web/src/pages/Knowledge.tsx` | 知识库 CRUD（真实） |
| `web/src/pages/Profile.tsx` | 用户画像（占位骨架） |
| `web/src/components/Sidebar.tsx` | 会话历史侧栏（占位骨架） |
| `web/src/components/MessageBubble.tsx` | 消息气泡 + markdown 渲染 |
| `web/src/components/TeachingStatus.tsx` | mastery/mode_path/turn_count 展示 |
| `web/src/index.css` | 基础样式 |

---

## Task 0: 环境确认（前置，无代码产出）

**目的**：确认后端实际可用端口，避免 proxy 指向遗留进程。

- [ ] **Step 1: 确认当前目录有 .env 且新栈已配 key**

Run:
```bash
cd <项目根> && grep -c '^OPENAI_API_KEY=ark\|^OPENAI_API_KEY=sk-[A-Za-z0-9]' .env && grep '^FEATURE_USE_NEW_AGENT_GRAPH=true' .env
```
Expected: 输出 `1` 和 `FEATURE_USE_NEW_AGENT_GRAPH=true`（key 已填真实值、flag 开）。若输出 `0`，先填 `.env` 的 `OPENAI_API_KEY`。

- [ ] **Step 2: 确认后端在哪个端口、是不是当前 app**

Run:
```bash
for p in 8000 8001; do echo "--- :$p ---"; curl -s -m 3 -X POST http://127.0.0.1:$p/api/chat -H "Content-Type: application/json" -d '{"message":"ping","session_id":"probe","user_id":1}' 2>&1 | head -c 200; echo; done
```
Expected: 当前 app 的端口返回含 `"stack":"new"` 的 JSON；遗留进程端口返回 `Method Not Allowed` 或连接失败。**记下返回 `stack:new` 的端口号**——后续 `VITE_API_TARGET` 用它。

- [ ] **Step 3: 若 8000 不是当前 app，记录用 8001**

无命令。结论：若 Step 2 显示 8000 是遗留进程、8001 是新栈，则后续所有 `npm run dev` 前先 `export VITE_API_TARGET=http://127.0.0.1:8001`。若 8000 就是新栈，则用默认、无需 export。

---

## Task 1: 脚手架（package.json / vite / tsconfig / 入口）

**Files:**
- Create: `web/package.json`
- Create: `web/vite.config.ts`
- Create: `web/tsconfig.json`
- Create: `web/tsconfig.node.json`
- Create: `web/index.html`
- Create: `web/src/main.tsx`
- Create: `web/src/index.css`
- Create: `web/.gitignore`

- [ ] **Step 1: 创建 `web/package.json`**

```json
{
  "name": "studyagent-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "test": "vitest run"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.0",
    "react-markdown": "^9.0.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.5.4",
    "vite": "^5.4.0",
    "vitest": "^2.0.5"
  }
}
```

- [ ] **Step 2: 创建 `web/vite.config.ts`（可配 proxy target）**

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// proxy target 默认 8000，可用 VITE_API_TARGET 覆盖（如 8000 被占时指 8001）
const apiTarget = process.env.VITE_API_TARGET || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: apiTarget, changeOrigin: true },
      "/health": { target: apiTarget, changeOrigin: true },
    },
  },
  build: { outDir: "dist" },
  test: { environment: "node" },
});
```

- [ ] **Step 3: 创建 `web/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **Step 4: 创建 `web/tsconfig.node.json`**

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 5: 创建 `web/index.html`**

```html
<!doctype html>
<html lang="zh">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>StudyAgent</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 6: 创建 `web/src/index.css`**

```css
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
  background: #f5f6f8; color: #1a1a1a; }
button { cursor: pointer; }
.container { max-width: 960px; margin: 0 auto; padding: 16px; }
```

- [ ] **Step 7: 创建 `web/src/main.tsx`（临时最小入口，Task 5 接路由）**

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <div className="container">
      <h1>StudyAgent 前端脚手架已就绪</h1>
    </div>
  </React.StrictMode>,
);
```

- [ ] **Step 8: 创建 `web/.gitignore`**

```
node_modules/
dist/
*.local
```

- [ ] **Step 9: 安装依赖并验证 dev server 起来**

Run:
```bash
cd web && npm install 2>&1 | tail -3 && timeout 8 npm run dev 2>&1 | head -8 || true
```
Expected: `npm install` 成功；`npm run dev` 输出含 `Local: http://localhost:5173/`（timeout 主动结束属正常）。

- [ ] **Step 10: 验证生产构建通过**

Run: `cd web && npm run build 2>&1 | tail -5`
Expected: 输出含 `dist/index.html` 等，无 TS 错误。

- [ ] **Step 11: Commit**

```bash
cd <项目根> && git add web/package.json web/package-lock.json web/vite.config.ts web/tsconfig.json web/tsconfig.node.json web/index.html web/src/main.tsx web/src/index.css web/.gitignore && git commit -m "$(cat <<'EOF'
feat(web): scaffold React + Vite + TS frontend

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: TS 类型定义（types.ts）

**Files:**
- Create: `web/src/types.ts`

按 spec §2.3 字段精度定义，与后端 `app/models/schemas.py` 对应。

- [ ] **Step 1: 创建 `web/src/types.ts`**

```typescript
// 与后端 app/models/schemas.py 对应。字段精度见 spec §2.3。

export interface ChatRequest {
  message: string;
  session_id: string;
  user_id: number | null;   // 后端是 int
}

export interface ChatResponse {
  reply: string;
  session_id: string;       // 勿漏（schemas.py:14）
  mastery_score?: number | null;
  turn_count?: number | null;
  mode_path?: string[] | null;
  cost_est_usd?: number | null;
  stack?: "new" | "legacy" | null;
}

export interface AuthResponse {
  user_id: number;          // int
  username: string;
  token?: string | null;    // 字段存在但端点不填，恒 null
}

export interface KnowledgeResponse {
  id: number;
  name: string;
  description: string;
}

export interface SessionResponse {
  session_id: string;
  user_id: number | null;
  state_json: string;       // 仅这三个字段，无 title/created_at
}

// 前端聊天消息（内存维护，非后端类型）
export interface ChatMessage {
  role: "user" | "assistant" | "error";
  content: string;
}
```

- [ ] **Step 2: 验证类型编译通过**

Run: `cd web && npx tsc --noEmit 2>&1 | tail -5`
Expected: 无输出（types.ts 无语法/类型错误；未被引用的导出不报错因 isolatedModules）。

- [ ] **Step 3: Commit**

```bash
cd <项目根> && git add web/src/types.ts && git commit -m "$(cat <<'EOF'
feat(web): add TS types matching backend schemas (spec §2.3)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: API 客户端（client.ts）— TDD

**Files:**
- Create: `web/src/api/client.ts`
- Test: `web/src/api/client.test.ts`

封装 fetch：注入 user_id、统一错误、120s 超时。这是唯一走 TDD 的模块。

- [ ] **Step 1: 写失败测试 `web/src/api/client.test.ts`**

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiGet, apiPost, ApiError } from "./client";

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("apiPost", () => {
  it("posts JSON and returns parsed body", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({ reply: "hi", session_id: "s1" }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const result = await apiPost("/api/chat", { message: "x", session_id: "s1", user_id: 1 });
    expect(result).toEqual({ reply: "hi", session_id: "s1" });
    const [url, opts] = mockFetch.mock.calls[0];
    expect(url).toBe("/api/chat");
    expect(opts.method).toBe("POST");
    expect(JSON.parse(opts.body)).toEqual({ message: "x", session_id: "s1", user_id: 1 });
  });

  it("throws ApiError with status on non-ok response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false, status: 401,
      json: async () => ({ detail: "用户名或密码错误" }),
    }));
    await expect(apiPost("/api/auth/login", {})).rejects.toMatchObject({
      status: 401, message: "用户名或密码错误",
    });
  });
});

describe("apiGet", () => {
  it("returns parsed body on success", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true, status: 200, json: async () => [{ id: 1, name: "k", description: "" }],
    }));
    const result = await apiGet("/api/knowledge");
    expect(result).toEqual([{ id: 1, name: "k", description: "" }]);
  });

  it("throws ApiError on 500", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false, status: 500, json: async () => ({ detail: "server error" }),
    }));
    await expect(apiGet("/api/profile/1")).rejects.toBeInstanceOf(ApiError);
  });
});
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd web && npm run test 2>&1 | tail -10`
Expected: FAIL（`client.ts` 不存在 / 导出未定义）。

- [ ] **Step 3: 实现 `web/src/api/client.ts`**

```typescript
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const TIMEOUT_MS = 120_000;   // 对话是长耗时操作（协作环多次 LLM），见 spec §3.1

async function request<T>(url: string, init: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let resp: Response;
  try {
    resp = await fetch(url, { ...init, signal: controller.signal });
  } catch (e) {
    clearTimeout(timer);
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new ApiError(0, "响应超时，教学协作环可能较慢");
    }
    throw new ApiError(0, "连接失败");
  }
  clearTimeout(timer);
  let body: unknown = null;
  try {
    body = await resp.json();
  } catch {
    body = null;
  }
  if (!resp.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : `请求失败（${resp.status}）`;
    throw new ApiError(resp.status, detail);
  }
  return body as T;
}

export function apiGet<T>(url: string): Promise<T> {
  return request<T>(url, { method: "GET" });
}

export function apiPost<T>(url: string, payload: unknown): Promise<T> {
  return request<T>(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function apiDelete<T>(url: string): Promise<T> {
  return request<T>(url, { method: "DELETE" });
}
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd web && npm run test 2>&1 | tail -8`
Expected: 4 个测试全 PASS。

- [ ] **Step 5: Commit**

```bash
cd <项目根> && git add web/src/api/client.ts web/src/api/client.test.ts && git commit -m "$(cat <<'EOF'
feat(web): add API client with timeout + error handling (TDD)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: 认证 Context（auth.tsx）

**Files:**
- Create: `web/src/store/auth.tsx`

AuthContext：user_id 存 localStorage（number ↔ string 转换点，spec §2.3 P2-3）。

- [ ] **Step 1: 创建 `web/src/store/auth.tsx`**

```tsx
import { createContext, useContext, useState, ReactNode } from "react";

interface AuthState {
  userId: number | null;
  username: string | null;
  login: (userId: number, username: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

const KEY_ID = "studyagent_user_id";
const KEY_NAME = "studyagent_username";

function readStoredId(): number | null {
  const raw = localStorage.getItem(KEY_ID);   // localStorage 只存字符串
  if (raw === null) return null;
  const n = Number(raw);                       // 转回 number（spec §2.3）
  return Number.isFinite(n) ? n : null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [userId, setUserId] = useState<number | null>(readStoredId());
  const [username, setUsername] = useState<string | null>(
    localStorage.getItem(KEY_NAME),
  );

  function login(id: number, name: string) {
    localStorage.setItem(KEY_ID, String(id));  // number → string
    localStorage.setItem(KEY_NAME, name);
    setUserId(id);
    setUsername(name);
  }

  function logout() {
    localStorage.removeItem(KEY_ID);
    localStorage.removeItem(KEY_NAME);
    setUserId(null);
    setUsername(null);
  }

  return (
    <AuthContext.Provider value={{ userId, username, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth 必须在 AuthProvider 内使用");
  return ctx;
}
```

- [ ] **Step 2: 验证类型编译通过**

Run: `cd web && npx tsc --noEmit 2>&1 | tail -5`
Expected: 无输出。

- [ ] **Step 3: Commit**

```bash
cd <项目根> && git add web/src/store/auth.tsx && git commit -m "$(cat <<'EOF'
feat(web): add AuthContext with localStorage user_id (number conversion)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 路由骨架（App.tsx + main.tsx 接线）

**Files:**
- Create: `web/src/App.tsx`
- Modify: `web/src/main.tsx`（替换临时入口）

- [ ] **Step 1: 创建 `web/src/App.tsx`（带受保护路由 + 临时占位页）**

```tsx
import { Routes, Route, Navigate, Link } from "react-router-dom";
import { useAuth } from "./store/auth";
import { ReactNode } from "react";

function RequireAuth({ children }: { children: ReactNode }) {
  const { userId } = useAuth();
  return userId === null ? <Navigate to="/login" replace /> : <>{children}</>;
}

function Placeholder({ name }: { name: string }) {
  const { username, logout } = useAuth();
  return (
    <div className="container">
      <nav style={{ display: "flex", gap: 12, marginBottom: 16 }}>
        <Link to="/chat">聊天</Link>
        <Link to="/knowledge">知识库</Link>
        <Link to="/profile">画像</Link>
        <span style={{ marginLeft: "auto" }}>{username}</span>
        <button onClick={logout}>退出</button>
      </nav>
      <h2>{name}（占位，Task 6-10 实装）</h2>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Placeholder name="登录" />} />
      <Route path="/chat" element={<RequireAuth><Placeholder name="聊天" /></RequireAuth>} />
      <Route path="/knowledge" element={<RequireAuth><Placeholder name="知识库" /></RequireAuth>} />
      <Route path="/profile" element={<RequireAuth><Placeholder name="画像" /></RequireAuth>} />
      <Route path="*" element={<Navigate to="/chat" replace />} />
    </Routes>
  );
}
```

- [ ] **Step 2: 替换 `web/src/main.tsx`**

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./store/auth";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
```

- [ ] **Step 3: 验证构建通过**

Run: `cd web && npm run build 2>&1 | tail -5`
Expected: 构建成功，无 TS 错误。

- [ ] **Step 4: 手动验证路由（描述，无自动断言）**

启动 `npm run dev`，浏览器访问 `http://localhost:5173`：未登录访问 `/chat` 应重定向到 `/login`；`/login` 显示占位页。（此时无真实登录，下一 Task 实装。）

- [ ] **Step 5: Commit**

```bash
cd <项目根> && git add web/src/App.tsx web/src/main.tsx && git commit -m "$(cat <<'EOF'
feat(web): add router skeleton with protected routes

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: 登录/注册页（Login.tsx）

**Files:**
- Create: `web/src/pages/Login.tsx`
- Modify: `web/src/App.tsx`（接入真实 Login）

- [ ] **Step 1: 创建 `web/src/pages/Login.tsx`**

```tsx
import { useState, FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { apiPost, ApiError } from "../api/client";
import { useAuth } from "../store/auth";
import { AuthResponse } from "../types";

export default function Login() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const path = mode === "login" ? "/api/auth/login" : "/api/auth/register";
      const resp = await apiPost<AuthResponse>(path, { username, password });
      login(resp.user_id, resp.username);
      navigate("/chat");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "请求失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="container" style={{ maxWidth: 360, marginTop: 80 }}>
      <h1>StudyAgent</h1>
      <div style={{ margin: "16px 0" }}>
        <button onClick={() => setMode("login")} disabled={mode === "login"}>登录</button>
        <button onClick={() => setMode("register")} disabled={mode === "register"}>注册</button>
      </div>
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <input placeholder="用户名" value={username}
          onChange={(e) => setUsername(e.target.value)} required />
        <input placeholder="密码" type="password" value={password}
          onChange={(e) => setPassword(e.target.value)} required />
        <button type="submit" disabled={busy}>
          {busy ? "提交中…" : mode === "login" ? "登录" : "注册"}
        </button>
      </form>
      {error && <p style={{ color: "#c0392b", marginTop: 8 }}>{error}</p>}
    </div>
  );
}
```

- [ ] **Step 2: 在 `web/src/App.tsx` 接入真实 Login**

将 `App.tsx` 顶部加导入，并替换 `/login` 路由元素：

加导入（文件顶部）：
```tsx
import Login from "./pages/Login";
```

替换 login 路由行（原 `<Route path="/login" element={<Placeholder name="登录" />} />`）：
```tsx
<Route path="/login" element={<Login />} />
```

- [ ] **Step 3: 验证构建通过**

Run: `cd web && npm run build 2>&1 | tail -5`
Expected: 构建成功。

- [ ] **Step 4: 手动验证登录（描述）**

确保后端在跑（Task 0 确定的端口；若 8001 则 `export VITE_API_TARGET=http://127.0.0.1:8001`）。`npm run dev` → `/login` 注册一个新用户 → 成功跳转 `/chat` 占位页，顶部显示用户名。

- [ ] **Step 5: Commit**

```bash
cd <项目根> && git add web/src/pages/Login.tsx web/src/App.tsx && git commit -m "$(cat <<'EOF'
feat(web): add real login/register page wired to /api/auth

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: 聊天子组件（MessageBubble + TeachingStatus）

**Files:**
- Create: `web/src/components/MessageBubble.tsx`
- Create: `web/src/components/TeachingStatus.tsx`

- [ ] **Step 1: 创建 `web/src/components/MessageBubble.tsx`**

```tsx
import ReactMarkdown from "react-markdown";
import { ChatMessage } from "../types";

export default function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  const isError = msg.role === "error";
  const align = isUser ? "flex-end" : "flex-start";
  const bg = isError ? "#fdecea" : isUser ? "#dcf0ff" : "#ffffff";
  const color = isError ? "#c0392b" : "#1a1a1a";
  return (
    <div style={{ display: "flex", justifyContent: align, margin: "8px 0" }}>
      <div style={{ maxWidth: "75%", background: bg, color,
        padding: "10px 14px", borderRadius: 12, border: "1px solid #e3e6ea" }}>
        {isUser ? msg.content : <ReactMarkdown>{msg.content}</ReactMarkdown>}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 创建 `web/src/components/TeachingStatus.tsx`**

```tsx
import { ChatResponse } from "../types";

export default function TeachingStatus({ last }: { last: ChatResponse | null }) {
  if (!last) return null;
  const score = last.mastery_score ?? null;
  const modes = last.mode_path ?? [];
  return (
    <div style={{ display: "flex", gap: 16, alignItems: "center",
      padding: "8px 12px", background: "#fff", borderBottom: "1px solid #e3e6ea",
      fontSize: 13, flexWrap: "wrap" }}>
      <span>掌握度：
        <progress max={100} value={score ?? 0} style={{ verticalAlign: "middle" }} />
        {score === null ? " —" : ` ${score}`}
      </span>
      <span>模式：{modes.length ? modes.map((m, i) => (
        <span key={i} style={{ background: "#eef2f7", borderRadius: 4,
          padding: "1px 6px", marginLeft: 4 }}>{m}</span>
      )) : " —"}</span>
      <span>回合：{last.turn_count ?? "—"}</span>
      <span style={{ marginLeft: "auto", color: "#888" }}>栈：{last.stack ?? "—"}</span>
    </div>
  );
}
```

- [ ] **Step 3: 验证构建通过**

Run: `cd web && npm run build 2>&1 | tail -5`
Expected: 构建成功（组件未被引用，但类型应通过）。

- [ ] **Step 4: Commit**

```bash
cd <项目根> && git add web/src/components/MessageBubble.tsx web/src/components/TeachingStatus.tsx && git commit -m "$(cat <<'EOF'
feat(web): add MessageBubble (markdown) + TeachingStatus components

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: 聊天页（Chat.tsx）— 核心

**Files:**
- Create: `web/src/pages/Chat.tsx`
- Modify: `web/src/App.tsx`（接入真实 Chat）

- [ ] **Step 1: 创建 `web/src/pages/Chat.tsx`**

```tsx
import { useState, FormEvent } from "react";
import { Link } from "react-router-dom";
import { apiPost, ApiError } from "../api/client";
import { useAuth } from "../store/auth";
import { ChatMessage, ChatResponse } from "../types";
import MessageBubble from "../components/MessageBubble";
import TeachingStatus from "../components/TeachingStatus";

function newSessionId(): string {
  return "s-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
}

export default function Chat() {
  const { userId, username, logout } = useAuth();
  const [sessionId, setSessionId] = useState(newSessionId());
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [lastResp, setLastResp] = useState<ChatResponse | null>(null);

  async function send(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: text }]);
    setBusy(true);
    try {
      const resp = await apiPost<ChatResponse>("/api/chat", {
        message: text, session_id: sessionId, user_id: userId,
      });
      setLastResp(resp);
      setMessages((m) => [...m, { role: "assistant", content: resp.reply }]);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "请求失败";
      setMessages((m) => [...m, { role: "error", content: msg }]);
    } finally {
      setBusy(false);
    }
  }

  function resetSession() {
    setSessionId(newSessionId());
    setMessages([]);
    setLastResp(null);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <nav style={{ display: "flex", gap: 12, padding: "8px 12px",
        background: "#fff", borderBottom: "1px solid #e3e6ea", alignItems: "center" }}>
        <strong>聊天</strong>
        <Link to="/knowledge">知识库</Link>
        <Link to="/profile">画像</Link>
        <button onClick={resetSession}>新建会话</button>
        <span style={{ marginLeft: "auto" }}>{username}</span>
        <button onClick={logout}>退出</button>
      </nav>
      <TeachingStatus last={lastResp} />
      <div style={{ flex: 1, overflowY: "auto", padding: "12px 16px" }}>
        {messages.length === 0 && (
          <p style={{ color: "#888" }}>输入一个学习问题开始（如「我想学二分查找」）。</p>
        )}
        {messages.map((m, i) => <MessageBubble key={i} msg={m} />)}
        {busy && <p style={{ color: "#888", margin: "8px 0" }}>AI 思考中…（协作环可能 10-40s）</p>}
      </div>
      <form onSubmit={send} style={{ display: "flex", gap: 8, padding: 12,
        background: "#fff", borderTop: "1px solid #e3e6ea" }}>
        <input style={{ flex: 1, padding: "8px 12px" }} value={input}
          placeholder="输入学习问题…" onChange={(e) => setInput(e.target.value)} />
        <button type="submit" disabled={busy}>发送</button>
      </form>
    </div>
  );
}
```

- [ ] **Step 2: 在 `web/src/App.tsx` 接入真实 Chat**

加导入：
```tsx
import Chat from "./pages/Chat";
```

替换 chat 路由行（原 `<Route path="/chat" element={<RequireAuth><Placeholder name="聊天" /></RequireAuth>} />`）：
```tsx
<Route path="/chat" element={<RequireAuth><Chat /></RequireAuth>} />
```

- [ ] **Step 3: 验证构建通过**

Run: `cd web && npm run build 2>&1 | tail -5`
Expected: 构建成功。

- [ ] **Step 4: 手动验证多轮教学对话（描述，核心验收）**

后端在跑（正确端口 + 新栈 flag）。`npm run dev` → 登录 → 聊天页发「我想学二分查找」→ loading 后出现 AI markdown 回复，顶部 TeachingStatus 显示 mastery/mode/turn/stack=new → 同会话继续回复几轮，观察 mode_path 是否变化 → 「新建会话」清空。

- [ ] **Step 5: Commit**

```bash
cd <项目根> && git add web/src/pages/Chat.tsx web/src/App.tsx && git commit -m "$(cat <<'EOF'
feat(web): add chat page (core) — /api/chat + teaching status + markdown

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: 知识库页（Knowledge.tsx）

**Files:**
- Create: `web/src/pages/Knowledge.tsx`
- Modify: `web/src/App.tsx`

- [ ] **Step 1: 创建 `web/src/pages/Knowledge.tsx`**

```tsx
import { useState, useEffect, FormEvent, useCallback } from "react";
import { Link } from "react-router-dom";
import { apiGet, apiPost, apiDelete, ApiError } from "../api/client";
import { KnowledgeResponse } from "../types";

export default function Knowledge() {
  const [items, setItems] = useState<KnowledgeResponse[]>([]);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      setItems(await apiGet<KnowledgeResponse[]>("/api/knowledge"));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "加载失败");
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function create(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      await apiPost<KnowledgeResponse>("/api/knowledge", { name, description: desc });
      setName(""); setDesc("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "创建失败");
    }
  }

  async function remove(id: number) {
    try {
      await apiDelete(`/api/knowledge/${id}`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "删除失败");
    }
  }

  return (
    <div className="container">
      <nav style={{ display: "flex", gap: 12, marginBottom: 16 }}>
        <Link to="/chat">聊天</Link><strong>知识库</strong><Link to="/profile">画像</Link>
      </nav>
      <form onSubmit={create} style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <input placeholder="名称" value={name} onChange={(e) => setName(e.target.value)} />
        <input placeholder="描述" value={desc} onChange={(e) => setDesc(e.target.value)} />
        <button type="submit">创建</button>
      </form>
      {error && <p style={{ color: "#c0392b" }}>{error}</p>}
      {items.length === 0 ? <p style={{ color: "#888" }}>暂无知识库</p> : (
        <ul style={{ listStyle: "none" }}>
          {items.map((k) => (
            <li key={k.id} style={{ display: "flex", gap: 8, padding: 8,
              background: "#fff", marginBottom: 4, borderRadius: 6 }}>
              <strong>{k.name}</strong><span style={{ color: "#888" }}>{k.description}</span>
              <button style={{ marginLeft: "auto" }} onClick={() => remove(k.id)}>删除</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

- [ ] **Step 2: 在 `web/src/App.tsx` 接入**

加导入：
```tsx
import Knowledge from "./pages/Knowledge";
```

替换 knowledge 路由行：
```tsx
<Route path="/knowledge" element={<RequireAuth><Knowledge /></RequireAuth>} />
```

- [ ] **Step 3: 验证构建通过**

Run: `cd web && npm run build 2>&1 | tail -5`
Expected: 构建成功。

- [ ] **Step 4: 手动验证 CRUD（描述）**

后端在跑。知识库页创建一个 → 列表出现 → 删除 → 列表消失。

- [ ] **Step 5: Commit**

```bash
cd <项目根> && git add web/src/pages/Knowledge.tsx web/src/App.tsx && git commit -m "$(cat <<'EOF'
feat(web): add knowledge CRUD page wired to /api/knowledge

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: 画像页 + 会话侧栏（占位骨架）

**Files:**
- Create: `web/src/pages/Profile.tsx`
- Create: `web/src/components/Sidebar.tsx`
- Modify: `web/src/App.tsx`

按 spec §2.2 做占位骨架——UI 结构完整，数据区标注「待后端持久化」。

- [ ] **Step 1: 创建 `web/src/pages/Profile.tsx`**

```tsx
import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { apiGet } from "../api/client";
import { useAuth } from "../store/auth";

interface ProfileResp {
  user_id: number;
  stats: { sessions: number; avg_mastery: number };
}

export default function Profile() {
  const { userId } = useAuth();
  const [stats, setStats] = useState<ProfileResp["stats"] | null>(null);

  useEffect(() => {
    if (userId === null) return;
    apiGet<ProfileResp>(`/api/profile/${userId}`)
      .then((r) => setStats(r.stats))
      .catch(() => setStats(null));
  }, [userId]);

  const placeholder = { color: "#aaa", fontStyle: "italic" as const };
  return (
    <div className="container">
      <nav style={{ display: "flex", gap: 12, marginBottom: 16 }}>
        <Link to="/chat">聊天</Link><Link to="/knowledge">知识库</Link><strong>画像</strong>
      </nav>
      <section style={{ background: "#fff", padding: 16, borderRadius: 8, marginBottom: 12 }}>
        <h3>学习进度</h3>
        <p>会话数：{stats?.sessions ?? 0} ｜ 平均掌握度：{stats?.avg_mastery ?? 0}</p>
      </section>
      <section style={{ background: "#fff", padding: 16, borderRadius: 8, marginBottom: 12 }}>
        <h3>掌握点图谱</h3>
        <p style={placeholder}>待后端持久化后填充（新栈当前用内存 EventStore，不写画像）</p>
      </section>
      <section style={{ background: "#fff", padding: 16, borderRadius: 8 }}>
        <h3>学习偏好</h3>
        <p style={placeholder}>待后端持久化后填充</p>
      </section>
    </div>
  );
}
```

- [ ] **Step 2: 创建 `web/src/components/Sidebar.tsx`**

```tsx
import { useState, useEffect } from "react";
import { apiGet } from "../api/client";
import { useAuth } from "../store/auth";
import { SessionResponse } from "../types";

export default function Sidebar({ onNew }: { onNew: () => void }) {
  const { userId } = useAuth();
  const [sessions, setSessions] = useState<SessionResponse[]>([]);

  useEffect(() => {
    if (userId === null) return;
    apiGet<SessionResponse[]>(`/api/sessions?user_id=${userId}`)
      .then(setSessions)
      .catch(() => setSessions([]));
  }, [userId]);

  return (
    <aside style={{ width: 200, background: "#fff", borderRight: "1px solid #e3e6ea",
      padding: 12 }}>
      <button onClick={onNew} style={{ width: "100%", marginBottom: 12 }}>+ 新建会话</button>
      {sessions.length === 0 ? (
        <p style={{ color: "#aaa", fontSize: 13 }}>暂无历史会话（新栈未持久化）</p>
      ) : (
        <ul style={{ listStyle: "none" }}>
          {sessions.map((s) => (
            <li key={s.session_id} style={{ padding: 6, fontSize: 13 }}>{s.session_id}</li>
          ))}
        </ul>
      )}
    </aside>
  );
}
```

- [ ] **Step 3: 在 `web/src/App.tsx` 接入 Profile**

加导入：
```tsx
import Profile from "./pages/Profile";
```

替换 profile 路由行：
```tsx
<Route path="/profile" element={<RequireAuth><Profile /></RequireAuth>} />
```

并删除不再使用的 `Placeholder` 函数（Task 5 定义的）——此时所有路由都已接真实页/占位页，`Placeholder` 成为孤儿。删除其定义。

- [ ] **Step 4: 验证构建通过（含 noUnusedLocals 检查孤儿清理）**

Run: `cd web && npm run build 2>&1 | tail -5`
Expected: 构建成功。若报 `Placeholder is declared but never used`，说明 Step 3 的孤儿删除未做，补删。

- [ ] **Step 5: 手动验证占位页（描述）**

Profile 页显示三个区，进度区有真实 stats（0/0），图谱/偏好区显示占位文案。（Sidebar 暂未挂到 Chat，留作可选增强，不阻塞。）

- [ ] **Step 6: Commit**

```bash
cd <项目根> && git add web/src/pages/Profile.tsx web/src/components/Sidebar.tsx web/src/App.tsx && git commit -m "$(cat <<'EOF'
feat(web): add profile + sidebar placeholder skeletons (spec §2.2)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: 生产构建接入 FastAPI + README 同步

**Files:**
- Modify: `README.md`（快速开始补前端构建步骤）
- 验证：`web/dist` 经 `main.py:40` 同源伺服

- [ ] **Step 1: 构建前端产物**

Run: `cd web && npm run build 2>&1 | tail -5`
Expected: `web/dist/index.html` + `web/dist/assets/` 生成。

- [ ] **Step 2: 验证 FastAPI 同源伺服前端**

后端用 8000（或确认端口）启动，浏览器访问后端根（如 `http://127.0.0.1:8000/`）。
Expected: 返回前端 `index.html`（main.py:40 的 web/dist 挂载生效）；访问 `/chat` 刷新不 404���catch-all 返回 index.html，兼容 React Router）。

> 注：若后端已在跑需重启才能加载新 dist（main.py 在模块加载期检查 web/dist 存在性）。

- [ ] **Step 3: README 快速开始补前端步骤**

在 `README.md` 的「快速开始」代码块（`uv run uvicorn` 之后）追加前端说明。定位 `# 运行测试` 之前，插入：

```markdown

# —— 前端（React，可选）——
cd web && npm install
npm run dev          # 开发：localhost:5173，proxy 转发 /api 到后端
# 若后端不在 8000（如 8000 被占用 8001）：
#   VITE_API_TARGET=http://127.0.0.1:8001 npm run dev
npm run build        # 生产：产物落 web/dist，由 FastAPI 同源伺服（重启后端加载）
cd ..
```

- [ ] **Step 4: 验证 README 渲染无误**

Run: `cd <项目根> && grep -n "VITE_API_TARGET\|web && npm" README.md`
Expected: 能匹配到新增的前端步骤行。

- [ ] **Step 5: Commit**

```bash
cd <项目根> && git add README.md && git commit -m "$(cat <<'EOF'
docs(readme): add frontend dev/build steps to quickstart

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## 验收标准（对应 spec §5）

1. `npm run dev` 启动前端，vite proxy 正常转发到后端（Task 0 确定端口）— Task 1/8
2. 登录页能注册/登录，user_id 存 localStorage — Task 6
3. 聊天页多轮对话，AI 回复 markdown 渲染，教学状态（mastery/mode_path/turn_count/stack）显示 — Task 7/8
4. 知识库页能创建/列出/删除 — Task 9
5. 画像页/会话侧栏 UI 完整，占位文案正确 — Task 10
6. `npm run build` 产物落 web/dist，uvicorn 同源访问前端正常 — Task 11
7. `client.ts` 单测通过 — Task 3

---

## 注意事项（执行者必读）

- **端口陷阱**：8000 当前被遗留进程占（返回 health 但路由错），Task 0 必须先确认真实后端端口，用 `VITE_API_TARGET` 对齐。
- **对话慢**：协作环一轮 10-40s，loading 态正常，勿误判超时。
- **不持久化**：刷新页面聊天记录丢失（内存维护），画像/会话页空是预期。
- **后端零改**：本计划不动任何后端文件，纯新增 `web/`。

---

## 附录：App.tsx 最终形态（Task 10 完成后核对用）

`App.tsx` 被 Task 5/6/8/9/10 增量修改。全部完成后应与下面**完全一致**（无 `Placeholder` 残留）。执行 Task 10 后用此核对：

```tsx
import { Routes, Route, Navigate } from "react-router-dom";
import { useAuth } from "./store/auth";
import { ReactNode } from "react";
import Login from "./pages/Login";
import Chat from "./pages/Chat";
import Knowledge from "./pages/Knowledge";
import Profile from "./pages/Profile";

function RequireAuth({ children }: { children: ReactNode }) {
  const { userId } = useAuth();
  return userId === null ? <Navigate to="/login" replace /> : <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/chat" element={<RequireAuth><Chat /></RequireAuth>} />
      <Route path="/knowledge" element={<RequireAuth><Knowledge /></RequireAuth>} />
      <Route path="/profile" element={<RequireAuth><Profile /></RequireAuth>} />
      <Route path="*" element={<Navigate to="/chat" replace />} />
    </Routes>
  );
}
```

注：`Link` 导入在最终形态中移除了——导航条已下放到各页面内部（Chat/Knowledge/Profile 各自有 nav）。若 Task 5 的 `Link` 导入残留会触发 `noUnusedLocals` 报错，按提示删除即可。
