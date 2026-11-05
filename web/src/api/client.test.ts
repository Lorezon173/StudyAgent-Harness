import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiGet, apiPost, ApiError } from "./client";
import * as client from "./client";
import { workspaceStore } from "../store/workspace";

function browserStorage() {
  const data = new Map<string, string>();
  vi.stubGlobal("localStorage", { getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => data.set(k, v), removeItem: (k: string) => data.delete(k) });
  vi.stubGlobal("window", { location: { pathname: "/login", href: "/login" } });
}

beforeEach(() => {
  vi.restoreAllMocks();
  browserStorage();
  workspaceStore.clearAccount();
});

describe("workspace HTTP contracts", () => {
  it("hides server tracebacks while preserving a readable status and structured code", () => {
    const trace = "Traceback (most recent call last):\n  File private_module.py, line 7\nRuntimeError: internal details";
    expect(client.extractApiError(500, { detail: trace })).toMatchObject({ status: 500, message: "请求失败（500）" });
    expect(client.extractApiError(500, { error_code: "server_error", message: trace })).toMatchObject({ status: 500, code: "server_error", message: "请求失败（500）" });
  });
  it("exports PATCH and multipart helpers", () => {
    expect(client).toHaveProperty("apiPatch", expect.any(Function));
    expect(client).toHaveProperty("apiPostForm", expect.any(Function));
  });
  it("renders structured conflicts and validation fields without object coercion", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 409,
      json: async () => ({ detail: { code: "state_version_conflict", message: "版本已更新" } }) }));
    await expect(apiGet("/api/sessions")).rejects.toMatchObject({ status: 409, code: "state_version_conflict", message: "版本已更新" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 422,
      json: async () => ({ detail: [{ loc: ["body", "title"], msg: "必填" }] }) }));
    await expect(apiPost("/api/sessions", {})).rejects.toMatchObject({ message: "body.title: 必填" });
  });
  it("accepts 204 and rejects malformed successful JSON", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 204, json: async () => { throw Error(); } }));
    await expect(apiGet("/empty")).resolves.toBeUndefined();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => { throw Error(); } }));
    await expect(apiGet("/broken")).rejects.toMatchObject({ status: 200, code: "invalid_json" });
  });
  it("sends PATCH JSON and lets FormData supply its own boundary", async () => {
    workspaceStore.startAccount(1, "test-token"); localStorage.setItem("studyagent_user_id", "1"); localStorage.setItem("studyagent_token", "test-token");
    const transport = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ version: 1 }) });
    vi.stubGlobal("fetch", transport);
    await client.apiPatch("/api/workspace-state", { expected_version: 0, sidebar_pinned: false });
    expect(transport.mock.calls[0][1]).toMatchObject({ method: "PATCH", headers: { Authorization: "Bearer test-token", "Content-Type": "application/json" }, body: '{"expected_version":0,"sidebar_pinned":false}' });
    const form = new FormData(); form.set("name", "学习资料");
    await client.apiPostForm("/upload", form);
    expect(transport.mock.calls[1][1].body).toBe(form);
    expect(transport.mock.calls[1][1].headers).toEqual({ Authorization: "Bearer test-token" });
  });
  it("keeps a new account safe from a delayed old 401", async () => {
    window.location.pathname = "/chat";
    workspaceStore.startAccount(1, "A"); localStorage.setItem("studyagent_token", "A"); localStorage.setItem("studyagent_user_id", "1");
    let resolve!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(r => { resolve = r; })));
    const pending = apiGet("/api/sessions");
    workspaceStore.startAccount(2, "B"); localStorage.setItem("studyagent_token", "B"); localStorage.setItem("studyagent_user_id", "2");
    window.location.href = "/chat/B";
    resolve({ ok: false, status: 401, json: async () => ({ detail: "旧凭证过期" }) } as Response);
    await expect(pending).rejects.toMatchObject({ status: 401 });
    expect(localStorage.getItem("studyagent_token")).toBe("B");
    expect(workspaceStore.getSnapshot().account.userId).toBe(2);
    expect(window.location.href).toBe("/chat/B");
  });
  it("invalidates the matching current credential and redirects when no Provider is mounted", async () => {
    workspaceStore.startAccount(1, "A"); localStorage.setItem("studyagent_user_id", "1"); localStorage.setItem("studyagent_username", "用户1"); localStorage.setItem("studyagent_token", "A");
    window.location.pathname = "/chat"; window.location.href = "/chat/A";
    const generation = workspaceStore.getSnapshot().account.generation;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 401, json: async () => ({ detail: "登录过期" }) }));
    await expect(apiGet("/api/sessions")).rejects.toMatchObject({ status: 401 });
    expect(localStorage.getItem("studyagent_token")).toBeNull(); expect(localStorage.getItem("studyagent_user_id")).toBeNull(); expect(localStorage.getItem("studyagent_username")).toBeNull();
    expect(workspaceStore.getSnapshot().account.generation).toBe(generation + 1);
    expect(window.location.href).toBe("/login");
  });
  it("preserves network and timeout errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(Error("offline")));
    await expect(apiGet("/offline")).rejects.toMatchObject({ status: 0, message: "连接失败" });
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("aborted", "AbortError")));
    await expect(apiGet("/slow")).rejects.toMatchObject({ status: 0, message: "响应超时，教学协作环可能较慢" });
  });
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

it.each([{ id: '2', token: 'A' }, { id: '1', token: 'B' }, { id: null, token: 'A' }, { id: '1', token: '' }])('blocks mismatched shared credentials before fetch: $id / $token', async ({ id, token }) => {
  workspaceStore.startAccount(1, 'A'); if (id !== null) localStorage.setItem('studyagent_user_id', id); if (token !== null) localStorage.setItem('studyagent_token', token);
  const fetcher = vi.fn(); const invalidated = vi.fn(); const remove = client.registerAuthInvalidation(invalidated); vi.stubGlobal('fetch', fetcher);
  await expect(apiGet('/api/knowledge')).rejects.toMatchObject({ status: 0, code: 'account_changed', message: '账号已在其他页面变更，本次请求未发送，请重新登录' });
  expect(fetcher).not.toHaveBeenCalled(); expect(invalidated).not.toHaveBeenCalled(); expect(workspaceStore.captureTicket()).toMatchObject({ userId: 1, token: 'A' }); expect(localStorage.getItem('studyagent_user_id')).toBe(id); expect(localStorage.getItem('studyagent_token')).toBe(token); remove();
});
it('keeps public credential POSTs free of shared authorization even on mismatch', async () => {
  workspaceStore.startAccount(1, 'A'); localStorage.setItem('studyagent_user_id', '2'); localStorage.setItem('studyagent_token', 'B');
  const fetcher = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({}) }); vi.stubGlobal('fetch', fetcher);
  await apiPost('/api/auth/login', {}); await apiPost('/api/auth/register', {});
  expect(fetcher.mock.calls.map(([, init]) => init.headers.Authorization)).toEqual([undefined, undefined]);
});
it('keeps shared B credentials when a dispatched A request later returns 401', async () => {
  workspaceStore.startAccount(1, 'A'); localStorage.setItem('studyagent_user_id', '1'); localStorage.setItem('studyagent_token', 'A'); let resolve!: (r: Response) => void;
  const fetcher = vi.fn((_url: string, _init: RequestInit) => new Promise<Response>(r => { resolve = r; })); vi.stubGlobal('fetch', fetcher); const pending = apiGet('/api/knowledge');
  localStorage.setItem('studyagent_user_id', '2'); localStorage.setItem('studyagent_token', 'B'); resolve({ ok: false, status: 401, json: async () => ({}) } as Response);
  await expect(pending).rejects.toMatchObject({ status: 401 }); expect(fetcher.mock.calls[0][1].headers).toMatchObject({ Authorization: 'Bearer A' }); expect(workspaceStore.captureTicket()).toMatchObject({ userId: 1, token: 'A' }); expect(localStorage.getItem('studyagent_token')).toBe('B');
});

it.each([{ id: 1, token: 'A' }, { id: 2, token: 'B' }])('uses the matching page ticket for user $id', async ({ id, token }) => {
  workspaceStore.startAccount(id, token); localStorage.setItem('studyagent_user_id', String(id)); localStorage.setItem('studyagent_token', token);
  const fetcher = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({}) }); vi.stubGlobal('fetch', fetcher);
  await apiGet('/api/knowledge'); await apiPost('/api/knowledge', { name: 'x' }); expect(fetcher.mock.calls.map(([, init]) => init.headers.Authorization)).toEqual([`Bearer ${token}`, `Bearer ${token}`]);
});
it('allows fully anonymous requests but blocks incomplete shared credentials', async () => {
  const fetcher = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({}) }); vi.stubGlobal('fetch', fetcher);
  await apiGet('/anonymous'); expect(fetcher.mock.calls[0][1].headers.Authorization).toBeUndefined();
  localStorage.setItem('studyagent_user_id', '1'); await expect(apiGet('/api/knowledge')).rejects.toMatchObject({ code: 'account_changed' }); expect(fetcher).toHaveBeenCalledTimes(1);
  localStorage.removeItem('studyagent_user_id'); localStorage.setItem('studyagent_token', 'A'); await expect(apiPost('/api/knowledge', {})).rejects.toMatchObject({ code: 'account_changed' }); expect(fetcher).toHaveBeenCalledTimes(1);
});
