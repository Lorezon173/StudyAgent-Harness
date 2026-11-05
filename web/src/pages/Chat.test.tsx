// @vitest-environment jsdom
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { MemoryRouter, useNavigate } from "react-router-dom";
import App from "../App";
import { AuthProvider } from "../store/auth";
import { deferred, profile, response, session, storeIdentity } from "../test/setup";
import { createLocalRecovery, getLocalRecovery } from "../store/localRecovery";
import { workspaceController } from "../store/workspaceController";
import { workspaceStore } from "../store/workspace";

const group = { groups: [{ group_key: "p1", profile: profile(), summary: null, sessions: [session("A"), session("B")], next_session_cursor: null }], next_group_cursor: null };
const ws = { last_session_id: "A", sidebar_pinned: true, sidebar_collapsed: false, progress_y_ratio: 0.5, version: 0, updated_at: null };
const snapshot = (id: string) => ({ session: session(id), teaching_state: null, teaching_state_source: "stored", profile: profile(), profile_summary: null, view_state: { draft: `草稿${id}`, reading_anchor: null, version: 0, updated_at: null }, pending_requests: [], messages: { items: [{ id: id === "A" ? 1 : 2, turn_index: 0, role: "assistant", content: `历史${id}`, created_at: null }], next_cursor: null } });
function mount(path: string) {
  storeIdentity();
  return render(<AuthProvider><MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><App /></MemoryRouter></AuthProvider>);
}
function installTransport() {
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ ...ws, last_session_id: body.last_session_id, version: body.expected_version + 1 })); }
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url.startsWith("/api/sessions/B/snapshot")) return Promise.resolve(response(snapshot("B")));
    if (url.endsWith("/view-state") && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ draft: body.draft, reading_anchor: body.reading_anchor, version: body.expected_version + 1, updated_at: null })); }
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); return fetcher;
}
it("loads the selected session's saved history and draft from the real snapshot endpoint", async () => {
  const fetcher = installTransport(); mount("/chat/A");
  expect(await screen.findByText("历史A")).toBeTruthy();
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).value).toBe("草稿A");
  expect(fetcher.mock.calls.some(([url]) => String(url).startsWith("/api/sessions/A/snapshot"))).toBe(true);
});
it("rejects a session snapshot whose linked profile belongs to another account", async () => {
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response({ ...snapshot("A"), profile: { ...profile(), user_id: 2 } }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); expect(await screen.findByRole("button", { name: "重新加载" })).toBeTruthy();
  expect(screen.queryByText("历史A")).toBeNull();
});
it("restores the last owned session on the default chat route", async () => {
  installTransport(); mount("/chat");
  expect(await screen.findByText("历史A")).toBeTruthy();
  await waitFor(() => expect(screen.getByRole("button", { name: "会话 A" }).getAttribute("aria-current")).toBe("true"));
});
it("opens the last session after retrying a failed initial workspace read", async () => {
  let reads = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method !== "PATCH") return Promise.resolve(++reads === 1 ? response({ detail: "暂时不可用" }, 503) : response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat");
  fireEvent.click(await screen.findByRole("button", { name: /重试.*最近会话/ }));
  expect(await screen.findByText("历史A")).toBeTruthy();
  expect(reads).toBe(2);
});
it("coalesces repeated recent-session load retries without duplicate navigation", async () => {
  const pending = deferred<Response>(); let reads = 0; let snapshots = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method !== "PATCH") return ++reads === 1 ? Promise.resolve(response({}, 503)) : pending.promise;
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) { snapshots++; return Promise.resolve(response(snapshot("A"))); }
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat"); const retry = await screen.findByRole("button", { name: /重试.*最近会话/ });
  fireEvent.click(retry); fireEvent.click(retry); expect(reads).toBe(2);
  await act(async () => { pending.resolve(response(ws)); }); await screen.findByText("历史A");
  expect(snapshots).toBe(1);
});
it("does not let a delayed workspace retry override a newer chosen session", async () => {
  const pending = deferred<Response>(); let reads = 0;
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ ...ws, last_session_id: body.last_session_id, version: body.expected_version + 1 })); }
    if (url === "/api/workspace-state") { reads++; return reads === 1 ? Promise.resolve(response({}, 503)) : reads === 2 ? pending.promise : Promise.resolve(response(ws)); }
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/B/snapshot")) return Promise.resolve(response(snapshot("B")));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat");
  fireEvent.click(await screen.findByRole("button", { name: /重试.*最近会话/ }));
  await waitFor(() => expect(reads).toBe(2));
  fireEvent.click(await screen.findByRole("button", { name: "会话 B" })); await screen.findByText("历史B");
  await act(async () => { pending.resolve(response(ws)); });
  await waitFor(() => expect(fetcher.mock.calls.some(([url, init]) => url === "/api/workspace-state" && init?.method === "PATCH" && JSON.parse(String(init.body)).last_session_id === "B")).toBe(true));
  expect(screen.getByText("历史B")).toBeTruthy();
  await waitFor(() => expect(workspaceStore.getSnapshot().workspace.lastSessionId).toBe("B"));
});
it("does not reuse an old retry when returning to the default route", async () => {
  const old = deferred<Response>(); let reads = 0;
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ ...ws, last_session_id: body.last_session_id, version: body.expected_version + 1 })); }
    if (url === "/api/workspace-state") { reads++; return reads === 1 ? Promise.resolve(response({}, 503)) : old.promise; }
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url.startsWith("/api/sessions/B/snapshot")) return Promise.resolve(response(snapshot("B")));
    return Promise.resolve(response({}, 404));
  });
  function Back() { const navigate = useNavigate(); return <button onClick={() => navigate(-1)}>测试返回</button>; }
  vi.stubGlobal("fetch", fetcher); storeIdentity();
  render(<AuthProvider><MemoryRouter initialEntries={["/chat"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><Back /><App /></MemoryRouter></AuthProvider>);
  fireEvent.click(await screen.findByRole("button", { name: /重试.*最近会话/ }));
  await waitFor(() => expect(reads).toBe(2));
  fireEvent.click(screen.getByRole("link", { name: "知识库" }));
  fireEvent.click(screen.getByRole("button", { name: "测试返回" }));
  expect(reads).toBe(2);
  await act(async () => { old.resolve(response({ ...ws, last_session_id: "B", version: 2 })); });
  await screen.findByText("历史B");
  expect(screen.getByText("历史B")).toBeTruthy();
  await waitFor(() => expect(workspaceStore.getSnapshot().workspace.lastSessionId).toBe("B"));
  expect(fetcher.mock.calls.some(([url]) => String(url).startsWith("/api/sessions/A/snapshot"))).toBe(false);
});
it("finishes a selected session save after its shared workspace read is superseded", async () => {
  const old = deferred<Response>(); let reads = 0;
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ ...ws, last_session_id: body.last_session_id, version: body.expected_version + 1 })); }
    if (url === "/api/workspace-state") { reads++; return reads === 1 ? Promise.resolve(response({}, 503)) : old.promise; }
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/B/snapshot")) return Promise.resolve(response(snapshot("B")));
    return Promise.resolve(response({}, 404));
  });
  function DefaultChat() { const navigate = useNavigate(); return <button onClick={() => navigate("/chat")}>测试默认入口</button>; }
  vi.stubGlobal("fetch", fetcher); storeIdentity();
  render(<AuthProvider><MemoryRouter initialEntries={["/chat"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><DefaultChat /><App /></MemoryRouter></AuthProvider>);
  fireEvent.click(await screen.findByRole("button", { name: /重试.*最近会话/ })); await waitFor(() => expect(reads).toBe(2));
  fireEvent.click(await screen.findByRole("button", { name: "会话 B" })); await screen.findByText("历史B");
  fireEvent.click(screen.getByRole("button", { name: "测试默认入口" })); expect(reads).toBe(2);
  await act(async () => { old.resolve(response(ws)); });
  await waitFor(() => expect(fetcher.mock.calls.some(([url, init]) => url === "/api/workspace-state" && init?.method === "PATCH" && JSON.parse(String(init.body)).last_session_id === "B")).toBe(true));
  await waitFor(() => expect(workspaceStore.getSnapshot().workspace.lastSessionId).toBe("B"));
  expect(fetcher.mock.calls.some(([url]) => String(url).startsWith("/api/sessions/A/snapshot"))).toBe(false);
});
it.each(["知识库", "学习画像"])("does not navigate over %s after a workspace retry finishes", async target => {
  const pending = deferred<Response>(); let reads = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return ++reads === 1 ? Promise.resolve(response({}, 503)) : pending.promise;
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat"); fireEvent.click(await screen.findByRole("button", { name: /重试.*最近会话/ }));
  await waitFor(() => expect(reads).toBe(2));
  fireEvent.click(screen.getByRole("link", { name: target }));
  await act(async () => { pending.resolve(response(ws)); });
  expect(screen.getByRole("link", { name: target }).getAttribute("aria-current")).toBe("page");
  expect(screen.queryByText("历史A")).toBeNull();
});
it("offers an owned local recent session without silently changing the server choice", async () => {
  const copy = createLocalRecovery(localStorage, "previous-tab").writeWorkspace(1, { lastSessionId: "B", baseVersion: 0, sequence: 1 }); expect(copy.ok).toBe(true);
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ ...ws, last_session_id: body.last_session_id, version: body.expected_version + 1 })); }
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url.startsWith("/api/sessions/B/snapshot")) return Promise.resolve(response(snapshot("B")));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.click(await screen.findByRole("button", { name: "仅打开本机会话 B" }));
  expect(await screen.findByText("历史B")).toBeTruthy();
  expect(fetcher.mock.calls.some(([url, init]) => url === "/api/workspace-state" && init?.method === "PATCH" && JSON.parse(String(init.body)).last_session_id === "B")).toBe(false);
});
it("offers a saved local empty recent-session choice without overwriting the server", async () => {
  expect(createLocalRecovery(localStorage, "previous-tab").writeWorkspace(1, { lastSessionId: null, baseVersion: 0, sequence: 1 }).ok).toBe(true);
  const fetcher = installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.click(await screen.findByRole("button", { name: "仅打开本机会话 无" }));
  expect(await screen.findByText("从左侧开启一段新的探索。", { exact: false })).toBeTruthy();
  expect(screen.queryByText("历史A")).toBeNull();
  expect(fetcher.mock.calls.some(([url, init]) => url === "/api/workspace-state" && init?.method === "PATCH" && JSON.parse(String(init.body)).last_session_id === null)).toBe(false);
});
it("shows both choices after a workspace version conflict without automatically overwriting the server", async () => {
  let getCount = 0;
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") return Promise.resolve(response({ detail: "conflict" }, 409));
    if (url === "/api/workspace-state") return Promise.resolve(response(++getCount === 1 ? ws : { ...ws, last_session_id: "B", version: 2 }));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  expect((await screen.findAllByText(/服务器最近会话：B/)).length).toBeGreaterThan(0);
  expect(screen.getByRole("button", { name: "使用服务器最近会话" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "保存本机最近会话" })).toBeTruthy();
  expect(fetcher.mock.calls.filter(([url, init]) => url === "/api/workspace-state" && init?.method === "PATCH")).toHaveLength(1);
});
it("shows an explicit retry when the latest-session save fails", async () => {
  let patches = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(++patches === 1 ? response({ detail: "暂时不可用" }, 503) : response({ ...ws, last_session_id: body.last_session_id, version: body.expected_version + 1 })); }
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A"); fireEvent.click(await screen.findByRole("button", { name: "重试保存最近会话" }));
  await waitFor(() => expect(workspaceStore.getSnapshot().workspace.dirty).toBe(false)); expect(patches).toBe(2);
});
it("loads only the selected session's history after a sidebar switch", async () => {
  installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.click(await screen.findByRole("button", { name: "会话 B" }));
  expect(await screen.findByText("历史B")).toBeTruthy();
  expect(screen.queryByText("历史A")).toBeNull();
});
it("persists the selected session as the latest workspace session", async () => {
  const fetcher = installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.click(await screen.findByRole("button", { name: "会话 B" })); await screen.findByText("历史B");
  await waitFor(() => expect(fetcher.mock.calls.some(([url, init]) => String(url) === "/api/workspace-state" && init?.method === "PATCH" && JSON.parse(String(init.body)).last_session_id === "B")).toBe(true));
});
it("serializes rapid B to C selection without issuing two writes at the same version", async () => {
  const pendingB = deferred<Response>();
  const expanded = { ...group, groups: [{ ...group.groups[0], sessions: [session("A"), session("B"), session("C")] }] };
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") {
      const body = JSON.parse(String(init.body));
      if (body.last_session_id === "B") return pendingB.promise;
      return Promise.resolve(response({ ...ws, last_session_id: body.last_session_id, version: body.expected_version + 1 }));
    }
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(expanded));
    for (const id of ["A", "B", "C"]) if (url.startsWith(`/api/sessions/${id}/snapshot`)) return Promise.resolve(response(snapshot(id)));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  await waitFor(() => expect(fetcher.mock.calls.some(([url, init]) => url === "/api/workspace-state" && init?.method === "PATCH")).toBe(true));
  fireEvent.click(screen.getByRole("button", { name: "会话 B" })); await screen.findByText("历史B");
  await waitFor(() => expect(fetcher.mock.calls.some(([url, init]) => url === "/api/workspace-state" && init?.method === "PATCH" && JSON.parse(String(init.body)).last_session_id === "B")).toBe(true));
  fireEvent.click(screen.getByRole("button", { name: "会话 C" })); await screen.findByText("历史C");
  await act(async () => { pendingB.resolve(response({ ...ws, last_session_id: "B", version: 2 })); });
  await waitFor(() => expect(fetcher.mock.calls.some(([url, init]) => url === "/api/workspace-state" && init?.method === "PATCH" && JSON.parse(String(init.body)).last_session_id === "C")).toBe(true));
  const writes = fetcher.mock.calls.filter(([url, init]) => url === "/api/workspace-state" && init?.method === "PATCH" && JSON.parse(String(init.body)).last_session_id === "C");
  expect(writes).toHaveLength(1); expect(JSON.parse(String(writes[0][1]?.body)).expected_version).toBe(2);
});
it("persists an edited draft against the selected session's view version", async () => {
  const fetcher = installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "新的草稿" } });
  await waitFor(() => expect(fetcher.mock.calls.some(([url, init]) => String(url).endsWith("/A/view-state") && init?.method === "PATCH" && JSON.parse(String(init.body)).draft === "新的草稿" && JSON.parse(String(init.body)).expected_version === 0)).toBe(true), { timeout: 3000 });
});
it("offers to retry a draft save after a server failure", async () => {
  let saves = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ ...ws, last_session_id: body.last_session_id, version: body.expected_version + 1 })); }
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url.endsWith("/view-state")) { const body = JSON.parse(String(init?.body)); return Promise.resolve(++saves === 1 ? response({ detail: "失败" }, 503) : response({ draft: body.draft, reading_anchor: body.reading_anchor ?? null, version: body.expected_version + 1, updated_at: null })); }
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "重试草稿" } });
  fireEvent.click(await screen.findByRole("button", { name: "重试保存草稿" }));
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.save.status).toBe("saved"));
});
it("persists only an owned visible message as the reading anchor", async () => {
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ ...ws, last_session_id: body.last_session_id, version: body.expected_version + 1 })); }
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url.endsWith("/view-state") && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ draft: body.draft, reading_anchor: body.reading_anchor, version: body.expected_version + 1, updated_at: null })); }
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  act(() => { workspaceController.setAnchor("A", { message_id: 1, offset_ratio: 0.25 }); workspaceController.setAnchor("A", { message_id: 999, offset_ratio: 0.75 }); });
  await waitFor(() => expect(fetcher.mock.calls.some(([url, init]) => String(url).endsWith("/view-state") && JSON.parse(String(init?.body)).reading_anchor?.message_id === 1)).toBe(true), { timeout: 2500 });
  expect(fetcher.mock.calls.some(([url, init]) => String(url).endsWith("/view-state") && JSON.parse(String(init?.body)).reading_anchor?.message_id === 999)).toBe(false);
});
it("throttles reading-anchor writes while continuing to save edited drafts", async () => {
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ ...ws, last_session_id: body.last_session_id, version: body.expected_version + 1 })); }
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url.endsWith("/view-state") && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ draft: body.draft, reading_anchor: body.reading_anchor ?? null, version: body.expected_version + 1, updated_at: null })); }
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  vi.useFakeTimers();
  try {
    act(() => { workspaceController.setAnchor("A", { message_id: 1, offset_ratio: 0.1 }); workspaceController.setDraft("A", "第一版"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(500); });
    act(() => { workspaceController.setAnchor("A", { message_id: 1, offset_ratio: 0.5 }); workspaceController.setDraft("A", "第二版"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(500); });
    const writes = fetcher.mock.calls.filter(([url, init]) => String(url).endsWith("/view-state") && init?.method === "PATCH").map(([, init]) => JSON.parse(String(init?.body)));
    expect(writes.filter(body => body.reading_anchor !== undefined)).toHaveLength(1);
    expect(writes.some(body => body.draft === "第二版")).toBe(true);
    await act(async () => { await vi.advanceTimersByTimeAsync(500); });
    expect(fetcher.mock.calls.some(([url, init]) => String(url).endsWith("/view-state") && JSON.parse(String(init?.body)).reading_anchor?.offset_ratio === 0.5)).toBe(true);
  } finally { vi.useRealTimers(); }
});
it("loads older messages into the selected session without duplicating existing IDs", async () => {
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ ...ws, last_session_id: body.last_session_id, version: body.expected_version + 1 })); }
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response({ ...snapshot("A"), messages: { ...snapshot("A").messages, next_cursor: "old" } }));
    if (url.startsWith("/api/sessions/A/messages?")) return Promise.resolve(response({ items: [{ id: 10, turn_index: -1, role: "user", content: "更早的提问", created_at: null }, ...snapshot("A").messages.items], next_cursor: null }));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.click(screen.getByRole("button", { name: "加载更早消息" }));
  expect(await screen.findByText("更早的提问")).toBeTruthy();
  expect(screen.getAllByText("历史A")).toHaveLength(1);
  expect(screen.queryByRole("button", { name: "加载更早消息" })).toBeNull();
});
it("retains loaded history and the older cursor when returning to a session", async () => {
  const latest = { id: 3, turn_index: 2, role: "assistant", content: "最新历史", created_at: null };
  const middle = { id: 2, turn_index: 1, role: "user", content: "中段历史", created_at: null };
  const oldest = { id: 1, turn_index: 0, role: "user", content: "最早历史", created_at: null };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ ...ws, last_session_id: body.last_session_id, version: body.expected_version + 1 })); }
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response({ ...snapshot("A"), messages: { items: [latest], next_cursor: "page-middle" } }));
    if (url.startsWith("/api/sessions/B/snapshot")) return Promise.resolve(response(snapshot("B")));
    if (url.includes("/A/messages?") && url.includes("page-middle")) return Promise.resolve(response({ items: [middle], next_cursor: "page-oldest" }));
    if (url.includes("/A/messages?") && url.includes("page-oldest")) return Promise.resolve(response({ items: [oldest], next_cursor: null }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("最新历史");
  fireEvent.click(screen.getByRole("button", { name: "加载更早消息" })); await screen.findByText("中段历史");
  fireEvent.click(screen.getByRole("button", { name: "会话 B" })); await screen.findByText("历史B");
  fireEvent.click(screen.getByRole("button", { name: "会话 A" })); await screen.findByText("最新历史");
  expect(screen.getByText("中段历史")).toBeTruthy();
  expect(workspaceStore.getSnapshot().buckets.A.nextMessageCursor).toBe("page-oldest");
  expect(workspaceStore.getSnapshot().buckets.A.visitedMessageCursors).toContain("page-middle");
  fireEvent.click(screen.getByRole("button", { name: "加载更早消息" })); await screen.findByText("最早历史");
});
it("keeps existing history when a normal snapshot conflicts by message id", async () => {
  let snapshots = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots === 1 ? snapshot("A") : { ...snapshot("A"), messages: { items: [{ ...snapshot("A").messages.items[0], content: "相同编号的不同内容" }], next_cursor: null } }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  await act(async () => { await workspaceController.loadSession("A"); });
  expect(screen.getByText("历史A")).toBeTruthy();
  expect(screen.queryByText("相同编号的不同内容")).toBeNull();
  expect(screen.getByText(/历史消息.*不一致/)).toBeTruthy();
});
it("rejects a malformed snapshot cursor without replacing loaded history", async () => {
  let snapshots = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots === 1 ? snapshot("A") : { ...snapshot("A"), messages: { ...snapshot("A").messages, next_cursor: 42 } }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  await act(async () => { await workspaceController.loadSession("A"); });
  expect(screen.getByText("历史A")).toBeTruthy();
  expect(workspaceStore.getSnapshot().buckets.A.nextMessageCursor).toBeNull();
  expect(screen.getByRole("button", { name: "重新同步历史" })).toBeTruthy();
});
it("accepts a newer profile from an older teaching snapshot without replacing current history", async () => {
  let snapshots = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots === 1 ? { ...snapshot("A"), session: { ...session("A"), state_version: 2 } } : { ...snapshot("A"), session: { ...session("A"), state_version: 1 }, profile: { ...profile(), revision: 1, name: "更新的画像" }, messages: { items: [{ id: 99, turn_index: 1, role: "assistant", content: "旧快照", created_at: null }], next_cursor: null } }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  await act(async () => { await workspaceController.loadSession("A"); });
  expect(workspaceStore.getSnapshot().buckets.A.profile?.name).toBe("更新的画像");
  expect(screen.getByText("历史A")).toBeTruthy(); expect(screen.queryByText("旧快照")).toBeNull();
});
it("keeps current history but accepts a newer profile from an older continue snapshot", async () => {
  let snapshots = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots === 1 ? { ...snapshot("A"), session: { ...session("A"), state_version: 2 } } : { ...snapshot("A"), session: { ...session("A"), state_version: 1 }, profile: { ...profile(), revision: 1, name: "更新的画像" }, messages: { items: [{ id: 99, turn_index: 1, role: "assistant", content: "旧快照", created_at: null }], next_cursor: null } }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A"); const ticket = workspaceStore.captureTicket();
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "旧问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, association: "unassociated" } }, request: { id: "r1", status: "unassociated", attempt: 1, error: null, sequence: 1 } })); });
  await act(async () => { await workspaceController.continueUnassociated("A", "r1"); });
  expect(workspaceStore.getSnapshot().buckets.A.profile?.name).toBe("更新的画像");
  expect(workspaceStore.getSnapshot().buckets.A.request.status).toBe("completed");
  expect(screen.getByText("历史A")).toBeTruthy(); expect(screen.queryByText("旧快照")).toBeNull();
});
it("bridges newer snapshot pages to the existing contiguous history without skipping the older cursor", async () => {
  const olderHead = { id: 10, turn_index: 2, role: "assistant", content: "原先最新", created_at: null };
  const intermediate = { id: 30, turn_index: 3, role: "user", content: "中间新增", created_at: null };
  const newest = { id: 40, turn_index: 4, role: "assistant", content: "新的最新", created_at: null };
  let snapshots = 0;
  const fetcher = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots === 1 ? { ...snapshot("A"), messages: { items: [olderHead], next_cursor: "oldest" } } : { ...snapshot("A"), messages: { items: [newest], next_cursor: "bridge1" } }));
    if (url.includes("/A/messages?") && url.includes("bridge1")) return Promise.resolve(response({ items: [intermediate], next_cursor: "bridge2" }));
    if (url.includes("/A/messages?") && url.includes("bridge2")) return Promise.resolve(response({ items: [olderHead], next_cursor: "oldest" }));
    if (url.includes("/A/messages?") && url.includes("oldest")) return Promise.resolve(response({ items: [{ id: 1, turn_index: 0, role: "user", content: "更早历史", created_at: null }], next_cursor: null }));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("原先最新");
  await act(async () => { await workspaceController.loadSession("A"); });
  expect(screen.getByText("原先最新")).toBeTruthy(); expect(screen.getByText("中间新增")).toBeTruthy(); expect(screen.getByText("新的最新")).toBeTruthy();
  expect(workspaceStore.getSnapshot().buckets.A.nextMessageCursor).toBe("oldest");
  fireEvent.click(screen.getByRole("button", { name: "加载更早消息" })); await screen.findByText("更早历史");
});
it("retains the old history and offers retry when a snapshot gap cannot be bridged", async () => {
  let snapshots = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots === 1 ? { ...snapshot("A"), messages: { ...snapshot("A").messages, next_cursor: "oldest" } } : { ...snapshot("A"), messages: { items: [{ id: 20, turn_index: 3, role: "assistant", content: "无交集新页", created_at: null }], next_cursor: "bridge" } }));
    if (url.includes("/A/messages?") && url.includes("bridge")) return Promise.resolve(response({}, 503));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  await act(async () => { await workspaceController.loadSession("A"); });
  expect(screen.getByText("历史A")).toBeTruthy(); expect(screen.queryByText("无交集新页")).toBeNull();
  expect(workspaceStore.getSnapshot().buckets.A.nextMessageCursor).toBe("oldest");
  expect(screen.getByRole("button", { name: "重新同步历史" })).toBeTruthy();
});
it("keeps the old paging frontier when a bridge cursor loops", async () => {
  let snapshots = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots === 1 ? { ...snapshot("A"), messages: { ...snapshot("A").messages, next_cursor: "oldest" } } : { ...snapshot("A"), messages: { items: [{ id: 20, turn_index: 3, role: "assistant", content: "无交集新页", created_at: null }], next_cursor: "bridge" } }));
    if (url.includes("/A/messages?") && url.includes("bridge")) return Promise.resolve(response({ items: [{ id: 10, turn_index: 2, role: "user", content: "桥接页", created_at: null }], next_cursor: "bridge" }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A"); await act(async () => { await workspaceController.loadSession("A"); });
  expect(screen.getByText("历史A")).toBeTruthy(); expect(screen.queryByText("桥接页")).toBeNull();
  expect(workspaceStore.getSnapshot().buckets.A.nextMessageCursor).toBe("oldest");
  expect(screen.getByRole("button", { name: "重新同步历史" })).toBeTruthy();
});
it("orders messages within a turn by server role order rather than message id", async () => {
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response({ ...snapshot("A"), messages: { items: [{ id: 2, turn_index: 1, role: "assistant", content: "先有编号的回答", created_at: null }, { id: 3, turn_index: 1, role: "user", content: "后有编号的提问", created_at: null }], next_cursor: null } }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("后有编号的提问");
  expect(workspaceStore.getSnapshot().buckets.A.messages.map(item => item.content)).toEqual(["后有编号的提问", "先有编号的回答"]);
});
it.each(["page-first", "snapshot-first"])("keeps the paging frontier when reload and an older page finish %s", async order => {
  const older = deferred<Response>(); const reload = deferred<Response>(); let snapshots = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return ++snapshots === 1 ? Promise.resolve(response({ ...snapshot("A"), messages: { ...snapshot("A").messages, next_cursor: "older" } })) : reload.promise;
    if (url.includes("/A/messages?") && url.includes("older")) return older.promise;
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  let pagePromise!: Promise<boolean>; let reloadPromise!: Promise<void>;
  act(() => { pagePromise = workspaceController.loadOlder("A"); reloadPromise = workspaceController.loadSession("A"); });
  const page = response({ items: [{ id: 20, turn_index: 0, role: "user", content: "较早内容", created_at: null }], next_cursor: "next" });
  const currentSnapshot = response({ ...snapshot("A"), messages: { ...snapshot("A").messages, next_cursor: "older" } });
  if (order === "page-first") { await act(async () => { older.resolve(page); await pagePromise; }); await act(async () => { reload.resolve(currentSnapshot); await reloadPromise; }); }
  else { await act(async () => { reload.resolve(currentSnapshot); await reloadPromise; }); await act(async () => { older.resolve(page); await pagePromise; }); }
  expect(screen.getByText("较早内容")).toBeTruthy();
  expect(workspaceStore.getSnapshot().buckets.A.nextMessageCursor).toBe("next");
  expect(workspaceStore.getSnapshot().buckets.A.visitedMessageCursors).toContain("older");
});
it("keeps loaded history and continues paging after explicitly continuing an unassociated request", async () => {
  const latest = { id: 3, turn_index: 2, role: "assistant", content: "最新历史", created_at: null };
  const middle = { id: 2, turn_index: 1, role: "user", content: "中段历史", created_at: null };
  const oldest = { id: 1, turn_index: 0, role: "user", content: "最早历史", created_at: null };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 1 }, messages: { items: [latest], next_cursor: "middle" } }));
    if (url.includes("/A/messages?") && url.includes("middle")) return Promise.resolve(response({ items: [middle], next_cursor: "oldest" }));
    if (url.includes("/A/messages?") && url.includes("oldest")) return Promise.resolve(response({ items: [oldest], next_cursor: null }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("最新历史");
  fireEvent.click(screen.getByRole("button", { name: "加载更早消息" })); await screen.findByText("中段历史");
  const ticket = workspaceStore.captureTicket();
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "旧问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, association: "unassociated" } }, request: { id: "r1", status: "unassociated", attempt: 1, error: null, sequence: 1 } })); });
  fireEvent.click(screen.getByRole("button", { name: "保留未关联记录并继续" }));
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.request.status).toBe("completed"));
  expect(screen.getByText("中段历史")).toBeTruthy();
  expect(workspaceStore.getSnapshot().buckets.A.nextMessageCursor).toBe("oldest");
  expect(workspaceStore.getSnapshot().buckets.A.visitedMessageCursors).toContain("middle");
  fireEvent.click(screen.getByRole("button", { name: "加载更早消息" })); await screen.findByText("最早历史");
});
it.each(["failure", "success"])("preserves unassociated history when continuation bridging returns %s", async outcome => {
  let snapshots = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots === 1 ? { ...snapshot("A"), session: { ...session("A"), state_version: 1 }, messages: { ...snapshot("A").messages, next_cursor: "oldest" } } : { ...snapshot("A"), session: { ...session("A"), state_version: 1 }, messages: { items: [{ id: 30, turn_index: 3, role: "assistant", content: "新内容", created_at: null }], next_cursor: "bridge" } }));
    if (url.includes("/A/messages?") && url.includes("bridge")) return Promise.resolve(outcome === "failure" ? response({}, 503) : response({ items: snapshot("A").messages.items, next_cursor: "oldest" }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A"); const ticket = workspaceStore.captureTicket();
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "旧问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, association: "unassociated" } }, request: { id: "r1", status: "unassociated", attempt: 1, error: null, sequence: 1 } })); });
  fireEvent.click(screen.getByRole("button", { name: "保留未关联记录并继续" }));
  if (outcome === "failure") {
    await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.request.error).toMatch(/同步失败/));
    expect(workspaceStore.getSnapshot().buckets.A.request.status).toBe("unassociated");
    expect(screen.queryByText("新内容")).toBeNull();
  } else {
    await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.request.status).toBe("completed"));
    expect(screen.getByText("新内容")).toBeTruthy();
  }
  expect(workspaceStore.getSnapshot().buckets.A.nextMessageCursor).toBe("oldest");
  expect(screen.getByText("历史A")).toBeTruthy();
});
it("preserves the visual position when older messages are prepended", async () => {
  const descriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollHeight");
  Object.defineProperty(HTMLElement.prototype, "scrollHeight", { configurable: true, get() { return (this as HTMLElement).querySelectorAll("[data-message-id]").length * 100; } });
  try {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/workspace-state") return Promise.resolve(response(ws));
      if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
      if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response({ ...snapshot("A"), messages: { ...snapshot("A").messages, next_cursor: "old" } }));
      if (url.startsWith("/api/sessions/A/messages?")) return Promise.resolve(response({ items: [{ id: 10, turn_index: -1, role: "user", content: "旧消息", created_at: null }], next_cursor: null }));
      return Promise.resolve(response({}, 404));
    }));
    mount("/chat/A"); const message = await screen.findByText("历史A");
    const container = message.closest<HTMLElement>("[data-message-id]")!.parentElement!; container.scrollTop = 35;
    fireEvent.click(screen.getByRole("button", { name: "加载更早消息" })); await screen.findByText("旧消息");
    expect(container.scrollTop).toBe(135);
  } finally { if (descriptor) Object.defineProperty(HTMLElement.prototype, "scrollHeight", descriptor); }
});
it("shows a retry option when an older message page fails", async () => {
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response({ ...snapshot("A"), messages: { ...snapshot("A").messages, next_cursor: "old" } }));
    if (url.startsWith("/api/sessions/A/messages?")) return Promise.resolve(response({ detail: "网络不可用" }, 503));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A"); fireEvent.click(screen.getByRole("button", { name: "加载更早消息" }));
  expect(await screen.findByText(/更早消息加载失败/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "重试加载更早消息" })).toBeTruthy();
});
it("stops an older-page cursor cycle instead of looping", async () => {
  let pages = 0;
  const fetcher = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response({ ...snapshot("A"), messages: { ...snapshot("A").messages, next_cursor: "first" } }));
    if (url.startsWith("/api/sessions/A/messages?")) return Promise.resolve(response({ items: [], next_cursor: ++pages === 1 ? "second" : "first" }));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.click(screen.getByRole("button", { name: "加载更早消息" })); await waitFor(() => expect(pages).toBe(1));
  fireEvent.click(screen.getByRole("button", { name: "加载更早消息" }));
  expect(await screen.findByText(/更早消息加载失败/)).toBeTruthy(); expect(pages).toBe(2);
});
it("loads older pages when the saved reading anchor is outside the latest page", async () => {
  const fetcher = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response({ ...snapshot("A"), view_state: { ...snapshot("A").view_state, reading_anchor: { message_id: 10, offset_ratio: 0.3 } }, messages: { ...snapshot("A").messages, next_cursor: "old" } }));
    if (url.startsWith("/api/sessions/A/messages?")) return Promise.resolve(response({ items: [{ id: 10, turn_index: -1, role: "user", content: "锚点旧消息", created_at: null }], next_cursor: null }));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A");
  expect(await screen.findByText("锚点旧消息")).toBeTruthy();
  expect(fetcher.mock.calls.some(([url]) => String(url).startsWith("/api/sessions/A/messages?"))).toBe(true);
});
it("records the message actually visible when the reader scrolls", async () => {
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url.endsWith("/view-state") && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ draft: body.draft, reading_anchor: body.reading_anchor, version: body.expected_version + 1, updated_at: null })); }
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); const text = await screen.findByText("历史A");
  const item = text.closest<HTMLElement>("[data-message-id]")!; const container = item.parentElement!;
  vi.spyOn(container, "getBoundingClientRect").mockReturnValue({ top: 50 } as DOMRect);
  vi.spyOn(item, "getBoundingClientRect").mockReturnValue({ top: 25, bottom: 125, height: 100 } as DOMRect);
  fireEvent.scroll(container);
  await waitFor(() => expect(fetcher.mock.calls.some(([url, init]) => String(url).endsWith("/view-state") && JSON.parse(String(init?.body)).reading_anchor?.offset_ratio === 0.25)).toBe(true), { timeout: 2500 });
});
it("restores the saved reading position after the session messages render", async () => {
  const top = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "offsetTop");
  const height = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "offsetHeight");
  Object.defineProperty(HTMLElement.prototype, "offsetTop", { configurable: true, get() { return (this as HTMLElement).dataset.messageId ? 100 : 10; } });
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", { configurable: true, get() { return 20; } });
  try {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/workspace-state") return Promise.resolve(response(ws));
      if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
      if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response({ ...snapshot("A"), view_state: { ...snapshot("A").view_state, reading_anchor: { message_id: 1, offset_ratio: 0.25 } } }));
      return Promise.resolve(response({}, 404));
    }));
    mount("/chat/A"); const message = await screen.findByText("历史A");
    const container = message.closest<HTMLElement>("[data-message-id]")!.parentElement!;
    expect(container.scrollTop).toBe(95);
  } finally {
    if (top) Object.defineProperty(HTMLElement.prototype, "offsetTop", top);
    if (height) Object.defineProperty(HTMLElement.prototype, "offsetHeight", height);
  }
});
it("does not put a delayed older page from session A into session B", async () => {
  const older = deferred<Response>();
  const fetcher = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response({ ...snapshot("A"), messages: { ...snapshot("A").messages, next_cursor: "old" } }));
    if (url.startsWith("/api/sessions/B/snapshot")) return Promise.resolve(response(snapshot("B")));
    if (url.startsWith("/api/sessions/A/messages?")) return older.promise;
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.click(screen.getByRole("button", { name: "加载更早消息" }));
  fireEvent.click(screen.getByRole("button", { name: "会话 B" })); await screen.findByText("历史B");
  await act(async () => { older.resolve(response({ items: [{ id: 10, turn_index: -1, role: "user", content: "A 的旧消息", created_at: null }], next_cursor: null })); });
  expect(screen.queryByText("A 的旧消息")).toBeNull(); expect(screen.getByText("历史B")).toBeTruthy();
});
it("does not silently log out while a prepared question remains unconfirmed", async () => {
  installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  const ticket = workspaceStore.captureTicket();
  act(() => workspaceStore.patchBucket(ticket, "A", value => ({ ...value, prepared: { pending: { text: "尚未确认的问题", sequence: 1 } } })));
  fireEvent.click(screen.getByRole("button", { name: /^账号：/ }));
  fireEvent.click(screen.getByRole("button", { name: "退出登录" }));
  expect(await screen.findByRole("dialog", { name: "退出登录" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "留在页面" })).toBeTruthy();
});
it("copies pending data synchronously when the page is closed", async () => {
  installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  const ticket = workspaceStore.captureTicket();
  act(() => workspaceStore.patchBucket(ticket, "A", value => ({ ...value, prepared: { close: { text: "关闭前的问题", sequence: 1 } } })));
  fireEvent(window, new Event("pagehide"));
  const copies = createLocalRecovery(localStorage, "reader").listResult(1, "A", "prepared");
  expect(copies.ok).toBe(true); expect(copies.candidates.some(item => item.text === "关闭前的问题")).toBe(true);
});
it("serializes an edit made during a view save without sending the same new version twice", async () => {
  const first = deferred<Response>();
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ ...ws, last_session_id: body.last_session_id, version: body.expected_version + 1 })); }
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url.endsWith("/view-state") && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return body.draft === "第一版" ? first.promise : Promise.resolve(response({ draft: body.draft, reading_anchor: null, version: body.expected_version + 1, updated_at: null })); }
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "第一版" } });
  void workspaceController.flush("A");
  await waitFor(() => expect(fetcher.mock.calls.some(([url, init]) => String(url).endsWith("/view-state") && JSON.parse(String(init?.body)).draft === "第一版")).toBe(true));
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "第二版" } });
  void workspaceController.flush("A");
  await act(async () => { first.resolve(response({ draft: "第一版", reading_anchor: null, version: 1, updated_at: null })); });
  await waitFor(() => expect(fetcher.mock.calls.some(([url, init]) => String(url).endsWith("/view-state") && JSON.parse(String(init?.body)).draft === "第二版")).toBe(true));
  const writes = fetcher.mock.calls.filter(([url, init]) => String(url).endsWith("/view-state") && JSON.parse(String(init?.body)).draft === "第二版");
  expect(writes).toHaveLength(1); expect(JSON.parse(String(writes[0][1]?.body)).expected_version).toBe(1);
});
it("retains both drafts after a view-state conflict and asks the reader to choose", async () => {
  let loads = 0;
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ ...ws, last_session_id: body.last_session_id, version: body.expected_version + 1 })); }
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++loads === 1 ? snapshot("A") : { ...snapshot("A"), view_state: { draft: "其他设备的草稿", reading_anchor: null, version: 2, updated_at: null } }));
    if (url.endsWith("/view-state")) return Promise.resolve(response({ detail: "conflict" }, 409));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "本机草稿" } });
  expect(await screen.findByText(/其他设备的草稿/)).toBeTruthy();
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).value).toBe("本机草稿");
  expect(screen.getByRole("button", { name: "使用服务器草稿" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "保存本机草稿" })).toBeTruthy();
  vi.useFakeTimers();
  try {
    fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "修改后的本机草稿" } });
    await act(async () => { vi.advanceTimersByTime(1000); });
    expect(fetcher.mock.calls.filter(([url, init]) => String(url).endsWith("/view-state") && init?.method === "PATCH")).toHaveLength(1);
  } finally { vi.useRealTimers(); }
});
it("sends the selected session id and fixed request id instead of generating another session", async () => {
  const fetcher = installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "一个问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(fetcher.mock.calls.some(([url, init]) => {
    if (String(url) !== "/api/chat") return false;
    const body = JSON.parse(String(init?.body));
    return body.session_id === "A" && body.profile_id === "p1" && body.expected_state_version === 0 && typeof body.request_id === "string" && body.message === "一个问题";
  })).toBe(true));
});
it("shows a failed pending request with its original question instead of inventing saved history", async () => {
  const entry = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "未完成的问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 2, status: "failed", lease_until: null, lease_expired: false, error_code: "model_failed", response_json: null, created_at: "", updated_at: "" };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response({ ...snapshot("A"), pending_requests: [entry] }));
    return Promise.resolve(response(ws));
  }));
  mount("/chat/A");
  expect(await screen.findByText("未完成的问题")).toBeTruthy();
  expect(screen.getByText("请求失败，可重试")).toBeTruthy();
  expect(screen.getByRole("button", { name: "重试请求" })).toBeTruthy();
});
it("does not offer a retry when authoritative terminal states disagree", async () => {
  const entry = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "冲突的问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "failed", lease_until: null, lease_expired: false, error_code: "failed", response_json: null, created_at: "", updated_at: "" };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response({ ...snapshot("A"), pending_requests: [entry] }));
    if (url.endsWith("/requests/r1")) return Promise.resolve(response({ ...entry, status: "interrupted" }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("冲突的问题");
  await act(async () => { await workspaceController.reconcile("A", "r1"); });
  expect(screen.getByText("请求状态不一致，请重新查询")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "重试请求" })).toBeNull();
});
it("issues only one retry when the same failed request is clicked twice", async () => {
  const get = deferred<Response>();
  const entry = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "失败的问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 2, status: "failed", lease_until: null, lease_expired: false, error_code: "model_failed", response_json: null, created_at: "", updated_at: "" };
  const fetcher = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response({ ...snapshot("A"), pending_requests: [entry] }));
    if (url.endsWith("/requests/r1")) return get.promise;
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); const retry = await screen.findByRole("button", { name: "重试请求" });
  fireEvent.click(retry); fireEvent.click(retry);
  expect(fetcher.mock.calls.filter(([url]) => String(url).endsWith("/requests/r1"))).toHaveLength(1);
  await act(async () => { get.resolve(response(entry)); });
});
it("offers the original question for a new send when retry context is stale", async () => {
  const entry = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "旧上下文问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 2, status: "failed", lease_until: null, lease_expired: false, error_code: "model_failed", response_json: null, created_at: "", updated_at: "" };
  let loads = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: ++loads === 1 ? 0 : 1 }, pending_requests: [entry] }));
    if (url.endsWith("/requests/r1")) return Promise.resolve(response(entry));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); fireEvent.click(await screen.findByRole("button", { name: "重试请求" }));
  const copy = await screen.findByRole("button", { name: "复制原文到输入框" });
  fireEvent.click(copy); expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).value).toBe("旧上下文问题");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "用户后续编辑" } });
  fireEvent.click(copy);
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).value).toBe("用户后续编辑");
});
it("shows a completed retried request without inventing its historical turn", async () => {
  const base = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "待重试的问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "failed", lease_until: null, lease_expired: false, error_code: "failed", response_json: null, created_at: "", updated_at: "" };
  const completed = { ...base, attempt: 2, status: "completed", error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 2, persisted: true, state_version: 1, reply: "结果" } };
  let checks = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response({ ...snapshot("A"), pending_requests: [base] }));
    if (url.endsWith("/requests/r1")) return Promise.resolve(response(++checks === 1 ? base : completed));
    if (url.endsWith("/requests/r1/retry") && init?.method === "POST") return Promise.resolve(response(completed.response_json));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); fireEvent.click(await screen.findByRole("button", { name: "重试请求" }));
  expect(await screen.findByRole("button", { name: "保留未关联记录并继续" })).toBeTruthy();
  expect(workspaceStore.getSnapshot().buckets.A.requests.r1.association).toBe("unassociated");
});
it("polls a running request recovered in a session snapshot", async () => {
  const entry = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "处理中问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "running", lease_until: null, lease_expired: false, error_code: null, response_json: null, created_at: "", updated_at: "" };
  const fetcher = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response({ ...snapshot("A"), session: { ...session("A"), active_request_id: "r1" }, pending_requests: [entry] }));
    if (url.endsWith("/requests/r1")) return Promise.resolve(response(entry));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("处理中问题");
  await waitFor(() => expect(fetcher.mock.calls.some(([url]) => String(url).endsWith("/requests/r1"))).toBe(true), { timeout: 4000 });
});
it("does not let an older failed recheck downgrade an already completed request", async () => {
  const pending = deferred<Response>();
  const base = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "running" as const, lease_until: null, lease_expired: false, error_code: null, response_json: null, created_at: "", updated_at: "" };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url.endsWith("/requests/r1")) return pending.promise;
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  const ticket = workspaceStore.captureTicket();
  act(() => { workspaceStore.mergeRequest(ticket, base); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, request: { id: "r1", status: "running", attempt: 1, error: null, sequence: 1 } })); });
  const old = workspaceController.reconcile("A", "r1", ticket);
  act(() => { workspaceStore.mergeRequest(ticket, { ...base, status: "completed", response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" } }); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, request: { ...value.request, status: "completed" } })); });
  await act(async () => { pending.reject(new Error("旧网络错误")); await old; });
  expect(workspaceStore.getSnapshot().buckets.A.request.status).toBe("completed");
});
it("does not replace newer persisted messages with a delayed older snapshot", async () => {
  const old = deferred<Response>(); let snapshots = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return ++snapshots === 1 ? Promise.resolve(response(snapshot("A"))) : old.promise;
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  const loading = workspaceController.loadSession("A"); const ticket = workspaceStore.captureTicket();
  act(() => workspaceStore.patchBucket(ticket, "A", value => ({ ...value, session: { ...session("A"), state_version: 2 }, teachingStateVersion: 2, messages: [{ id: 88, turn_index: 2, role: "assistant", content: "较新的真实回复", created_at: null }] })));
  await act(async () => { old.resolve(response(snapshot("A"))); await loading; });
  expect(screen.getByText("较新的真实回复")).toBeTruthy(); expect(screen.queryByText("历史A")).toBeNull();
});
it("does not replace a newer confirmed draft with an older view snapshot", async () => {
  const old = deferred<Response>(); let snapshots = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return ++snapshots === 1 ? Promise.resolve(response(snapshot("A"))) : old.promise;
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A"); const loading = workspaceController.loadSession("A"); const ticket = workspaceStore.captureTicket();
  act(() => workspaceStore.patchBucket(ticket, "A", value => ({ ...value, draft: "较新已保存草稿", draftRevision: 0, save: { ...value.save, status: "saved", viewVersion: 2 } })));
  await act(async () => { old.resolve(response(snapshot("A"))); await loading; });
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).value).toBe("较新已保存草稿");
  expect(workspaceStore.getSnapshot().buckets.A.save.viewVersion).toBe(2);
});
it("shares concurrent checks for the same request instead of issuing duplicate GETs", async () => {
  const pending = deferred<Response>();
  const fetcher = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url.endsWith("/requests/r1")) return pending.promise;
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  const one = workspaceController.reconcile("A", "r1"); const two = workspaceController.reconcile("A", "r1");
  expect(fetcher.mock.calls.filter(([url]) => String(url).endsWith("/requests/r1"))).toHaveLength(1);
  await act(async () => { pending.resolve(response({ detail: "not found" }, 404)); await Promise.all([one, two]); });
});
it("keeps a matched request complete when the same completed result is checked again", async () => {
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url.endsWith("/requests/r1")) return Promise.resolve(response(completed));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A"); const ticket = workspaceStore.captureTicket();
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, association: "matched" } }, request: { id: "r1", status: "completed", attempt: 1, error: null, sequence: 1 } })); });
  await act(async () => { await workspaceController.reconcile("A", "r1", ticket); });
  expect(workspaceStore.getSnapshot().buckets.A.request.status).toBe("completed");
  expect(workspaceStore.getSnapshot().buckets.A.requests.r1.association).toBe("matched");
});
it("ignores an older POST observation after a newer attempt is authoritative", async () => {
  const post = deferred<Response>(); let sent: Record<string, unknown> | undefined;
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url === "/api/chat") { sent = JSON.parse(String(init?.body)); return post.promise; }
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "并发问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(sent).toBeTruthy());
  const id = String(sent!.request_id); const ticket = workspaceStore.captureTicket();
  act(() => { workspaceStore.mergeRequest(ticket, { user_id: 1, session_id: "A", request_id: id, profile_id: "p1", active_node_id: null, request_payload: { message: "并发问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 2, status: "failed", lease_until: null, lease_expired: false, error_code: "failed", response_json: null, created_at: "", updated_at: "" }); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, request: { ...value.request, status: "failed", attempt: 2 } })); });
  await act(async () => { post.resolve(response({ session_id: "A", request_id: id, status: "running", attempt: 1, persisted: false })); });
  expect(fetcher.mock.calls.some(([url]) => String(url).includes(`/requests/${id}`))).toBe(false);
  expect(workspaceStore.getSnapshot().buckets.A.request).toMatchObject({ status: "failed", attempt: 2 });
});
it("records the complete pre-submit turn identity before sending", async () => {
  const post = deferred<Response>();
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url === "/api/chat") return post.promise;
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "原始问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(Object.keys(workspaceStore.getSnapshot().buckets.A.localRequests)).toHaveLength(1));
  const [id, local] = Object.entries(workspaceStore.getSnapshot().buckets.A.localRequests)[0];
  expect(local.baseline).toEqual({ owner_user_id: 1, session_id: "A", request_id: id, profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 0, provenance: "before_submit", snapshot_sequence: expect.any(Number) });
});
it("associates completed requests by trusted turn while deduplicating overlapping pages", async () => {
  let snapshots = 0; let sent: Record<string, unknown> | null = null;
  const user = { id: 42, turn_index: 42, role: "user", content: "相同问题", created_at: null };
  const assistant = { id: 43, turn_index: 42, role: "assistant", content: "真实答案", created_at: null };
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ ...ws, last_session_id: body.last_session_id, version: body.expected_version + 1 })); }
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) {
      const base = { ...snapshot("A"), session: { ...session("A"), state_version: 7, next_turn_index: 42 } };
      if (++snapshots <= 2) return Promise.resolve(response(base));
      return Promise.resolve(response({ ...base, session: { ...base.session, state_version: 8, next_turn_index: 43 }, messages: { items: [user], next_cursor: "older" } }));
    }
    if (url.startsWith("/api/sessions/A/messages?")) return Promise.resolve(response({ items: [user, assistant], next_cursor: null }));
    if (url === "/api/chat") { sent = JSON.parse(String(init?.body)); return Promise.resolve(response({ session_id: "A", request_id: sent!.request_id, status: "completed", attempt: 1, persisted: true, state_version: 8, reply: "真实答案" })); }
    if (url.includes("/requests/")) return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: sent!.request_id, profile_id: "p1", active_node_id: null, request_payload: { message: "相同问题", profile_id: "p1", active_node_id: null, base_state_version: 7 }, base_state_version: 7, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: sent!.request_id, status: "completed", attempt: 1, persisted: true, state_version: 8, reply: "真实答案" }, created_at: "", updated_at: "" }));
    if (url.endsWith("/view-state") && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ draft: body.draft, reading_anchor: body.reading_anchor, version: body.expected_version + 1, updated_at: null })); }
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "相同问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(sent).not.toBeNull());
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.requests[String(sent!.request_id)]?.association).toBe("matched"));
  expect(screen.getAllByText("相同问题")).toHaveLength(1); expect(screen.getByText("真实答案")).toBeTruthy();
});
it("marks a completed request inconsistent when the full history lacks its trusted turn", async () => {
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "缺少的用户消息", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "缺少的回答" }, created_at: "", updated_at: "" };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 1 } }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A"); const ticket = workspaceStore.captureTicket();
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, baseline: { owner_user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 2, provenance: "before_submit", snapshot_sequence: 1 } } }, request: { id: "r1", status: "pending_messages", attempt: 1, error: null, sequence: 1 } })); });
  await act(async () => { await workspaceController.confirmCompleted("A", "r1", ticket); });
  expect(workspaceStore.getSnapshot().buckets.A.requests.r1.association).toBe("inconsistent");
  expect(screen.getByText(/已保存的消息与请求不一致/)).toBeTruthy();
});
it("keeps the user signed in when exit cannot save, and offers a local-copy choice", async () => {
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url.endsWith("/view-state") && init?.method === "PATCH") return Promise.resolve(response({ detail: "网络不可用" }, 503));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "退出前草稿" } });
  fireEvent.click(screen.getByRole("button", { name: "账号：用户1" }));
  fireEvent.click(screen.getByRole("button", { name: "退出登录" }));
  expect(await screen.findByText("部分内容未保存到服务器")).toBeTruthy();
  expect(screen.getByText(/会话 A 的草稿未保存/)).toBeTruthy();
  expect(localStorage.getItem("studyagent_token")).toBe("A");
  expect(screen.getByRole("button", { name: "退出并保留本机草稿" })).toBeTruthy();
});
it("can log out after a recent-session backup has been confirmed and removed", async () => {
  const fetcher = installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  await waitFor(() => expect(fetcher.mock.calls.some(([url, init]) => String(url) === "/api/workspace-state" && init?.method === "PATCH")).toBe(true));
  await waitFor(() => expect(workspaceStore.getSnapshot().workspace.dirty).toBe(false));
  expect(workspaceStore.prepareAccountTransition(workspaceStore.captureTicket()).ok).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "账号：用户1" })); fireEvent.click(screen.getByRole("button", { name: "退出登录" }));
  await waitFor(() => expect(localStorage.getItem("studyagent_token")).toBeNull());
  expect(screen.queryByRole("dialog", { name: "退出登录" })).toBeNull();
});
it("keeps the user signed in if an existing local recovery candidate cannot be verified on exit", async () => {
  installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  await waitFor(() => expect(workspaceStore.getSnapshot().workspace.dirty).toBe(false));
  const copy = createLocalRecovery(localStorage, "other-tab").writePrepared(1, "A", "p1", { text: "本机待保留", sequence: 1 }); expect(copy.ok).toBe(true); if (!copy.ok) return;
  act(() => workspaceStore.patchBucket(workspaceStore.captureTicket(), "A", value => ({ ...value, preparedCandidates: [copy.candidate] })));
  vi.spyOn(Storage.prototype, "key").mockImplementation(() => { throw new Error("unavailable"); });
  fireEvent.click(screen.getByRole("button", { name: "账号：用户1" })); fireEvent.click(screen.getByRole("button", { name: "退出登录" }));
  expect(await screen.findByRole("dialog", { name: "退出登录" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "退出并保留本机草稿" }));
  expect(await screen.findByText("本机备份失败，请重试或留在页面")).toBeTruthy();
  expect(localStorage.getItem("studyagent_token")).toBe("A");
});
it("offers a same-account local draft after ownership is confirmed without silently replacing the server draft", async () => {
  createLocalRecovery(localStorage, "other-tab").writeDraft(1, "A", { draft: "本机待恢复", reading_anchor: null, baseVersion: 0, sequence: 1 });
  installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).value).toBe("草稿A");
  fireEvent.click(await screen.findByRole("button", { name: "恢复本机草稿" }));
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).value).toBe("本机待恢复");
});
it("restores the local reading anchor together with the selected draft", async () => {
  createLocalRecovery(localStorage, "other-tab").writeDraft(1, "A", { draft: "带位置的草稿", reading_anchor: { message_id: 1, offset_ratio: 0.4 }, baseVersion: 0, sequence: 1 });
  installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.click(await screen.findByRole("button", { name: "恢复本机草稿" }));
  expect(workspaceStore.getSnapshot().buckets.A.readingAnchor).toEqual({ message_id: 1, offset_ratio: 0.4 });
});
it("warns when local recovery storage cannot be read", async () => {
  installTransport(); vi.spyOn(Storage.prototype, "key").mockImplementation(() => { throw new Error("unavailable"); });
  mount("/chat/A"); await screen.findByText("历史A");
  expect(screen.getByText(/本机恢复内容读取失败/).getAttribute("role")).toBe("alert");
});
it("offers to recheck an unknown request after signing in again", async () => {
  const copy = createLocalRecovery(localStorage, "previous-tab").writeRequest(1, "A", "old-request", { payload: { message: "上次的问题", session_id: "A", profile_id: "p1", request_id: "old-request", expected_state_version: 0 }, baseline: null });
  expect(copy.ok).toBe(true);
  const fetcher = installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  expect(await screen.findByText("上次的问题")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "查询上次请求" }));
  await waitFor(() => expect(fetcher.mock.calls.some(([url]) => String(url).includes("/requests/old-request"))).toBe(true));
});
it("rejects a recovered GET whose original question does not match the local request", async () => {
  expect(createLocalRecovery(localStorage, "previous-tab").writeRequest(1, "A", "old-request", { payload: { message: "真正的问题", session_id: "A", profile_id: "p1", request_id: "old-request", expected_state_version: 0 }, baseline: null }).ok).toBe(true);
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url.endsWith("/requests/old-request")) return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: "old-request", profile_id: "p1", active_node_id: null, request_payload: { message: "其他内容", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 2, status: "running", lease_until: null, lease_expired: false, error_code: null, response_json: null, created_at: "", updated_at: "" }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("真正的问题"); fireEvent.click(screen.getByRole("button", { name: "查询上次请求" }));
  expect(await screen.findByText(/上次请求尚未确认/)).toBeTruthy();
  expect(workspaceStore.getSnapshot().buckets.A.requests["old-request"]).toBeUndefined();
  expect(createLocalRecovery(localStorage, "reader").listResult(1, "A", "request").candidates).toHaveLength(1);
});
it("does not accept a request lookup after its saved candidate changes during the lookup", async () => {
  const recovery = createLocalRecovery(localStorage, "other-tab");
  const payload = { message: "旧问题", session_id: "A", profile_id: "p1", request_id: "old", expected_state_version: 0 };
  const saved = recovery.writeRequest(1, "A", "old", { payload, baseline: null });
  if (!saved.ok) throw new Error("failed to create recovery candidate");
  const candidate = saved.candidate; const pending = deferred<Response>();
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url.endsWith("/requests/old")) return pending.promise;
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("旧问题");
  let checking!: Promise<void>; act(() => { checking = workspaceController.recheckCandidate("A", candidate); });
  expect(recovery.writeRequest(1, "A", "old", { payload: { ...payload, message: "新问题" }, baseline: null }).ok).toBe(true);
  await act(async () => { pending.resolve(response({ user_id: 1, session_id: "A", request_id: "old", profile_id: "p1", active_node_id: null, request_payload: { message: "旧问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "running", lease_until: null, lease_expired: false, error_code: null, response_json: null, created_at: "", updated_at: "" })); await checking; });
  expect(workspaceStore.getSnapshot().buckets.A.requests.old).toBeUndefined();
  expect(workspaceStore.getSnapshot().buckets.A.recoveryError).toMatch(/变化|重新检查/);
});
it("only resends a missing request when asked, reusing its original ID and payload", async () => {
  const payload = { message: "原始待确认问题", session_id: "A", profile_id: "p1", request_id: "old-request", expected_state_version: 0 };
  expect(createLocalRecovery(localStorage, "previous-tab").writeRequest(1, "A", "old-request", { payload, baseline: null }).ok).toBe(true);
  const post = deferred<Response>();
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url.endsWith("/requests/old-request")) return Promise.resolve(response({ detail: "not found" }, 404));
    if (url === "/api/chat" && init?.method === "POST") return post.promise;
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("原始待确认问题");
  fireEvent.click(screen.getByRole("button", { name: "查询上次请求" }));
  const resend = await screen.findByRole("button", { name: "按原请求重发" });
  expect(fetcher.mock.calls.filter(([url]) => String(url) === "/api/chat")).toHaveLength(0);
  fireEvent.click(resend); fireEvent.click(resend);
  await waitFor(() => expect(fetcher.mock.calls.filter(([url]) => String(url) === "/api/chat")).toHaveLength(1));
  const call = fetcher.mock.calls.find(([url]) => String(url) === "/api/chat")!;
  expect(JSON.parse(String(call[1]?.body))).toEqual(payload);
});
it("preserves the original and disables resend on a payload conflict", async () => {
  expect(createLocalRecovery(localStorage, "previous-tab").writeRequest(1, "A", "old-request", { payload: { message: "待保留原文", session_id: "A", profile_id: "p1", request_id: "old-request", expected_state_version: 0 }, baseline: null }).ok).toBe(true);
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url.endsWith("/requests/old-request")) return Promise.resolve(response({ detail: "not found" }, 404));
    if (url === "/api/chat" && init?.method === "POST") return Promise.resolve(response({ detail: { code: "payload_conflict", message: "内容不匹配" } }, 409));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("待保留原文"); fireEvent.click(screen.getByRole("button", { name: "查询上次请求" }));
  fireEvent.click(await screen.findByRole("button", { name: "按原请求重发" }));
  expect(await screen.findByText(/请求编号对应内容不一致/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: "按原请求重发" })).toBeNull();
  expect(createLocalRecovery(localStorage, "reader").listResult(1, "A", "request").candidates).toHaveLength(1);
});
it("lets a reader explicitly continue after an unassociated completed request without deleting its copy", async () => {
  const copy = createLocalRecovery(localStorage, "previous-tab").writeRequest(1, "A", "old-request", { payload: { message: "旧版问题", session_id: "A", profile_id: "p1", request_id: "old-request", expected_state_version: 0 }, baseline: null }); expect(copy.ok).toBe(true);
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 1, next_turn_index: 1 } }));
    if (url.endsWith("/requests/old-request")) return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: "old-request", profile_id: "p1", active_node_id: null, request_payload: { message: "旧版问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "old-request", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "旧版答案" }, created_at: "", updated_at: "" }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("旧版问题"); fireEvent.click(screen.getByRole("button", { name: "查询上次请求" }));
  fireEvent.click(await screen.findByRole("button", { name: "保留未关联记录并继续" }));
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.request.status).toBe("completed"));
  expect(createLocalRecovery(localStorage, "reader").listResult(1, "A", "request").candidates).toHaveLength(1);
});
it("keeps the current tab's uncertain send available for explicit recheck", async () => {
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url === "/api/chat") return Promise.reject(new Error("connection lost"));
    if (url.includes("/requests/")) return Promise.resolve(response({ detail: "not found" }, 404));
    if (url.endsWith("/view-state") && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ draft: body.draft, reading_anchor: body.reading_anchor, version: body.expected_version + 1, updated_at: null })); }
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "断线的问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(fetcher.mock.calls.some(([url]) => String(url).includes("/requests/"))).toBe(true));
  expect(await screen.findByRole("button", { name: "查询上次请求" })).toBeTruthy();
  expect(await screen.findByRole("button", { name: "按原请求重发" })).toBeTruthy();
});
it("still checks an uncertain send if local recovery storage cannot be written", async () => {
  const fetcher = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url === "/api/chat") return Promise.reject(new Error("connection lost"));
    if (url.includes("/requests/")) return Promise.resolve(response({ detail: "not found" }, 404));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  const original = Storage.prototype.setItem;
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, key: string, value: string) { if (key.startsWith("studyagent:recovery:")) throw new Error("unavailable"); return original.call(this, key, value); });
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "无法备份的问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(fetcher.mock.calls.some(([url]) => String(url).includes("/requests/"))).toBe(true));
  expect(screen.getByText(/本机请求恢复副本不可用/)).toBeTruthy();
});
it("offers a risk-aware copy of another tab's preparation without overwriting a current draft", async () => {
  createLocalRecovery(localStorage, "other-tab").writePrepared(1, "A", "prepare-x", { text: "原始点击", sequence: 1, phase: "prepared" });
  installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  expect(await screen.findByText("原始点击")).toBeTruthy();
  expect(screen.getByText(/另一页面可能已经发送/)).toBeTruthy();
  const recover = screen.getByRole("button", { name: "复制原文并自行决定是否重新提问" }) as HTMLButtonElement;
  expect(recover.disabled).toBe(true);
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).value).toBe("草稿A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "" } });
  fireEvent.click(recover);
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).value).toBe("原始点击");
  expect(createLocalRecovery(localStorage, "reader").listResult(1, "A", "prepared").candidates).toHaveLength(1);
});
it("clears this tab's prepared record after the original is deliberately restored", async () => {
  installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  const candidate = getLocalRecovery().writePrepared(1, "A", "p1", { text: "待恢复原文", sequence: 1, phase: "prepared" }); expect(candidate.ok).toBe(true); if (!candidate.ok) return;
  act(() => workspaceStore.patchBucket(workspaceStore.captureTicket(), "A", value => ({ ...value, draft: "", prepared: { p1: { text: "待恢复原文", sequence: 1, phase: "prepared" } }, preparedCandidates: [candidate.candidate], cancelledPreparations: [candidate.candidate.writeId] })));
  fireEvent.click(screen.getByRole("button", { name: "恢复待发送原文" }));
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).value).toBe("待恢复原文");
  expect(workspaceStore.getSnapshot().buckets.A.prepared).toEqual({});
});
it("does not clear a sent draft until the owned request payload is verified", async () => {
  const pending = deferred<Response>(); let sent: Record<string, unknown> | undefined;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url === "/api/chat") { sent = JSON.parse(String(init?.body)); return Promise.resolve(response({ session_id: "A", request_id: sent!.request_id, status: "running", attempt: 1, persisted: false })); }
    if (url.includes("/requests/")) return pending.promise;
    if (url.endsWith("/view-state")) return Promise.resolve(response({ draft: "", reading_anchor: null, version: 1, updated_at: null }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "真实问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(sent).toBeTruthy());
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).value).toBe("真实问题");
  await act(async () => { pending.resolve(response({ user_id: 1, session_id: "A", request_id: sent!.request_id, profile_id: "p1", active_node_id: null, request_payload: { message: "真实问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "running", lease_until: null, lease_expired: false, error_code: null, response_json: null, created_at: "", updated_at: "" })); });
  await waitFor(() => expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).value).toBe(""));
});
it("retains the clicked question separately when the user edits and changes sessions while send preparation is pending", async () => {
  const preparing = deferred<Response>(); let aSnapshots = 0;
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ ...ws, last_session_id: body.last_session_id, version: body.expected_version + 1 })); }
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return ++aSnapshots === 2 ? preparing.promise : Promise.resolve(response(snapshot("A")));
    if (url.startsWith("/api/sessions/B/snapshot")) return Promise.resolve(response(snapshot("B")));
    if (url.endsWith("/view-state") && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ draft: body.draft, reading_anchor: body.reading_anchor, version: body.expected_version + 1, updated_at: null })); }
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "原始提问" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(aSnapshots).toBe(2));
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "后续编辑" } });
  fireEvent.click(screen.getByRole("button", { name: "会话 B" })); await screen.findByText("历史B");
  await act(async () => { preparing.resolve(response(snapshot("A"))); });
  expect(fetcher.mock.calls.some(([url]) => url === "/api/chat")).toBe(false);
  expect(Object.values(workspaceStore.getSnapshot().buckets.A.prepared).some(item => item.text === "原始提问")).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "会话 A" })); await screen.findByText("历史A");
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).value).toBe("后续编辑");
});
it("does not disturb a newer session request when an old preparation finishes late", async () => {
  const old = deferred<Response>(); const newPost = deferred<Response>(); let aSnapshots = 0;
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ ...ws, last_session_id: body.last_session_id, version: body.expected_version + 1 })); }
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return ++aSnapshots === 2 ? old.promise : Promise.resolve(response(snapshot("A")));
    if (url.startsWith("/api/sessions/B/snapshot")) return Promise.resolve(response(snapshot("B")));
    if (url === "/api/chat") return newPost.promise;
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "A 的旧准备" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(aSnapshots).toBe(2));
  fireEvent.click(screen.getByRole("button", { name: "会话 B" })); await screen.findByText("历史B");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "B 的新问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(1));
  const newRequest = workspaceStore.getSnapshot().buckets.B.request;
  await act(async () => { old.resolve(response(snapshot("A"))); });
  expect(workspaceStore.getSnapshot().buckets.B.request.id).toBe(newRequest.id);
  expect(workspaceStore.getSnapshot().buckets.B.request.sequence).toBe(newRequest.sequence);
  expect(JSON.parse(String(fetcher.mock.calls.find(([url]) => url === "/api/chat")?.[1]?.body))).toMatchObject({ session_id: "B", message: "B 的新问题" });
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).value).toBe("B 的新问题");
});
it("does not send a pre-login continuation after the same account signs in again", async () => {
  const preparing = deferred<Response>(); let snapshots = 0;
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ ...ws, last_session_id: body.last_session_id, version: body.expected_version + 1 })); }
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return ++snapshots === 2 ? preparing.promise : Promise.resolve(response(snapshot("A")));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "换代前问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(snapshots).toBe(2));
  act(() => { expect(workspaceStore.startAccount(1, "A")).toBe(true); });
  await act(async () => { preparing.resolve(response(snapshot("A"))); });
  expect(fetcher.mock.calls.some(([url]) => String(url) === "/api/chat")).toBe(false);
});
it("cancels scheduled request polling when the account generation changes", async () => {
  const fetcher = installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  vi.useFakeTimers();
  try {
    const ticket = workspaceStore.captureTicket();
    const before = vi.getTimerCount();
    act(() => { workspaceController.schedulePoll("A", "pending", ticket); });
    expect(vi.getTimerCount()).toBe(before + 1);
    act(() => { workspaceStore.startAccount(1, "A"); });
    await act(async () => { vi.advanceTimersByTime(3001); });
    expect(fetcher.mock.calls.some(([url]) => String(url).endsWith("/requests/pending"))).toBe(false);
  } finally { vi.useRealTimers(); }
});

it("reports each unsaved session request and workspace on flush", async () => {
  storeIdentity(); workspaceStore.startAccount(1, "A", true); workspaceStore.ensureSessionBucket("A");
  const ticket = workspaceStore.captureTicket();
  workspaceStore.patchBucket(ticket, "A", value => ({ ...value, prepared: { pending: { text: "original", sequence: 1 } } }));
  const report = await workspaceController.flushAll(ticket);
  expect(report).toMatchObject({ ok: false, stale: false });
  expect(report.items).toEqual(expect.arrayContaining([{ kind: "prepared", sessionId: "A", itemId: "pending", ok: false }, expect.objectContaining({ kind: "draft", sessionId: "A" }), expect.objectContaining({ kind: "workspace", sessionId: null })]));
});
it("preserves a newer teaching snapshot while completed turn history is loading", async () => {
  const page = deferred<Response>();
  let count = 0;
  const user = { id: 20, turn_index: 2, role: "user", content: "问题", created_at: null };
  const answer = { id: 21, turn_index: 2, role: "assistant", content: "答案", created_at: null };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/messages?")) return page.promise;
    if (url.startsWith("/api/sessions/A/snapshot")) {
      count++;
      if (count === 1) return Promise.resolve(response(snapshot("A")));
      if (count === 2) return Promise.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 1 }, messages: { items: [], next_cursor: "older" } }));
      return Promise.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 2 } }));
    }
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  const ticket = workspaceStore.captureTicket();
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, baseline: { owner_user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 2, provenance: "before_submit", snapshot_sequence: 1 } } }, request: { id: "r1", status: "pending_messages", attempt: 1, error: null, sequence: 1 } })); });
  let pending!: Promise<void>;
  act(() => { pending = workspaceController.confirmCompleted("A", "r1", ticket); });
  await waitFor(() => expect(count).toBe(2));
  await act(async () => { await workspaceController.loadSession("A"); });
  await act(async () => { page.resolve(response({ items: [user, answer], next_cursor: null })); await pending; });
  expect(workspaceStore.getSnapshot().buckets.A.session?.state_version).toBe(2);
  expect(workspaceStore.getSnapshot().buckets.A.requests.r1.association).toBe("matched");
});
it.each(["attempt", "account"])("does not associate or clear an old history page after %s changes", async changed => {
  const page = deferred<Response>(); let snapshots = 0;
  const fetcher = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/messages?")) return page.promise;
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots === 1 ? snapshot("A") : { ...snapshot("A"), session: { ...session("A"), state_version: 1 }, messages: { items: [], next_cursor: "older" } }));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  const ticket = workspaceStore.captureTicket();
  const payload = { message: "问题", session_id: "A", profile_id: "p1", request_id: "r1", expected_state_version: 0 };
  const baseline = { owner_user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 2, provenance: "before_submit" as const, snapshot_sequence: 1 };
  const copy = getLocalRecovery().writeRequest(1, "A", "r1", { payload, baseline }); if (!copy.ok) throw new Error("failed to create recovery candidate");
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, localRequests: { r1: { payload, baseline } }, requestCandidates: [copy.candidate], requests: { ...value.requests, r1: { ...value.requests.r1, baseline } }, request: { id: "r1", status: "pending_messages", attempt: 1, error: null, sequence: 1 } })); });
  let confirming!: Promise<void>; act(() => { confirming = workspaceController.confirmCompleted("A", "r1", ticket); });
  await waitFor(() => expect(fetcher.mock.calls.some(([url]) => String(url).startsWith("/api/sessions/A/messages?"))).toBe(true));
  if (changed === "attempt") act(() => { workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, snapshot: { ...value.requests.r1.snapshot, attempt: 2 } } }, request: { ...value.request, attempt: 2, sequence: 2 } })); });
  else act(() => { workspaceStore.startAccount(1, "A", true); workspaceStore.ensureSessionBucket("A"); });
  await act(async () => { page.resolve(response({ items: [{ id: 20, turn_index: 2, role: "user", content: "问题", created_at: null }, { id: 21, turn_index: 2, role: "assistant", content: "答案", created_at: null }], next_cursor: null })); await confirming; });
  const bucket = workspaceStore.getSnapshot().buckets.A;
  expect(bucket.requests.r1?.association).not.toBe("matched");
  expect(bucket.messages.some(item => item.id === 20 || item.id === 21)).toBe(false);
  expect(getLocalRecovery().list(1, "A", "request").some(item => item.itemId === "r1" && JSON.stringify(item.payload) === JSON.stringify(payload))).toBe(true);
});
it("does not overwrite a conflicting existing message when confirming a completed turn", async () => {
  const page = deferred<Response>();
  let count = 0;
  const user = { id: 20, turn_index: 2, role: "user", content: "问题", created_at: null };
  const answer = { id: 21, turn_index: 2, role: "assistant", content: "答案", created_at: null };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/messages?")) return page.promise;
    if (url.startsWith("/api/sessions/A/snapshot")) {
      count++;
      if (count === 1) return Promise.resolve(response(snapshot("A")));
      if (count === 2) return Promise.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 1 }, messages: { items: [], next_cursor: "older" } }));
      return Promise.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 2 }, messages: { items: [...snapshot("A").messages.items, { ...user, content: "已有不同内容" }], next_cursor: null } }));
    }
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  const ticket = workspaceStore.captureTicket();
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, baseline: { owner_user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 2, provenance: "before_submit", snapshot_sequence: 1 } } }, request: { id: "r1", status: "pending_messages", attempt: 1, error: null, sequence: 1 } })); });
  let pending!: Promise<void>;
  act(() => { pending = workspaceController.confirmCompleted("A", "r1", ticket); });
  await waitFor(() => expect(count).toBe(2));
  await act(async () => { await workspaceController.loadSession("A"); });
  await act(async () => { page.resolve(response({ items: [user, answer], next_cursor: null })); await pending; });
  expect(workspaceStore.getSnapshot().buckets.A.messages.find(item => item.id === 20)?.content).toBe("已有不同内容");
  expect(workspaceStore.getSnapshot().buckets.A.requests.r1.association).toBe("inconsistent");
});
it("keeps newer teaching state when continuing an unassociated request", async () => {
  const delayed = deferred<Response>(); let count = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) {
      count++;
      if (count === 2) return delayed.promise;
      return Promise.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: count === 1 ? 1 : 2 } }));
    }
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  const ticket = workspaceStore.captureTicket();
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, association: "unassociated" } }, request: { id: "r1", status: "unassociated", attempt: 1, error: null, sequence: 1 } })); });
  let pending!: Promise<void>;
  act(() => { pending = workspaceController.continueUnassociated("A", "r1"); });
  await waitFor(() => expect(count).toBe(2));
  await act(async () => { await workspaceController.loadSession("A"); });
  await act(async () => { delayed.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 1 } })); await pending; });
  expect(workspaceStore.getSnapshot().buckets.A.session?.state_version).toBe(2);
  expect(workspaceStore.getSnapshot().buckets.A.teachingStateVersion).toBe(2);
});
it("preserves a newer profile while completed turn history is loading", async () => {
  const summary = (revision: number) => ({ profile_revision: revision, nodes: [], edges: [], recent_evidence: [], assessed_count: 0, total_count: 0, mastery_score: null, metric_kind: "assessed_mean", assessment_coverage: null });
  const page = deferred<Response>();
  let count = 0;
  const user = { id: 20, turn_index: 2, role: "user", content: "问题", created_at: null };
  const answer = { id: 21, turn_index: 2, role: "assistant", content: "答案", created_at: null };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/messages?")) return page.promise;
    if (url.startsWith("/api/sessions/A/snapshot")) {
      count++;
      if (count === 1) return Promise.resolve(response(snapshot("A")));
      if (count === 2) return Promise.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 1 }, profile: { ...profile(), revision: 1 }, profile_summary: summary(1), messages: { items: [], next_cursor: "older" } }));
      return Promise.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 2 }, profile: { ...profile(), revision: 2 }, profile_summary: summary(2) }));
    }
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  const ticket = workspaceStore.captureTicket();
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, baseline: { owner_user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 2, provenance: "before_submit", snapshot_sequence: 1 } } }, request: { id: "r1", status: "pending_messages", attempt: 1, error: null, sequence: 1 } })); });
  let pending!: Promise<void>;
  act(() => { pending = workspaceController.confirmCompleted("A", "r1", ticket); });
  await waitFor(() => expect(count).toBe(2));
  await act(async () => { await workspaceController.loadSession("A"); });
  await act(async () => { page.resolve(response({ items: [user, answer], next_cursor: null })); await pending; });
  expect(workspaceStore.getSnapshot().buckets.A.profileSummary?.profile_revision).toBe(2);
  expect(workspaceStore.getSnapshot().buckets.A.requests.r1.association).toBe("matched");
});
it("keeps a known profile revision when completion returns a profile without a revision", async () => {
  let snapshots = 0;
  const withoutRevision: Record<string, unknown> = { ...profile(), name: "无版本旧画像" }; delete withoutRevision.revision;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots === 1 ? { ...snapshot("A"), profile: { ...profile(), revision: 2 } } : { ...snapshot("A"), session: { ...session("A"), state_version: 1 }, profile: withoutRevision, messages: { items: [{ id: 20, turn_index: 2, role: "user", content: "问题", created_at: null }, { id: 21, turn_index: 2, role: "assistant", content: "答案", created_at: null }], next_cursor: null } }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A"); const ticket = workspaceStore.captureTicket();
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, baseline: { owner_user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 2, provenance: "before_submit", snapshot_sequence: 1 } } }, request: { id: "r1", status: "pending_messages", attempt: 1, error: null, sequence: 1 } })); });
  await act(async () => { await workspaceController.confirmCompleted("A", "r1", ticket); });
  expect(workspaceStore.getSnapshot().buckets.A.profile?.name).toBe("概率论");
  expect(workspaceStore.getSnapshot().buckets.A.profileRevision).toBe(2);
  expect(workspaceStore.getSnapshot().buckets.A.requests.r1.association).toBe("matched");
});
it("does not send after navigating A to B to A during preparation", async () => {
  const preparing = deferred<Response>(); let aSnapshots = 0;
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ ...ws, last_session_id: body.last_session_id, version: body.expected_version + 1 })); }
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return ++aSnapshots === 2 ? preparing.promise : Promise.resolve(response(snapshot("A")));
    if (url.startsWith("/api/sessions/B/snapshot")) return Promise.resolve(response(snapshot("B")));
    if (url.endsWith("/view-state") && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ draft: body.draft, reading_anchor: body.reading_anchor, version: body.expected_version + 1, updated_at: null })); }
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "原始提问" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(aSnapshots).toBe(2));
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "后续编辑" } });
  fireEvent.click(screen.getByRole("button", { name: "会话 B" })); await screen.findByText("历史B");
  fireEvent.click(screen.getByRole("button", { name: "会话 A" })); await screen.findByText("历史A");
  await act(async () => { preparing.resolve(response(snapshot("A"))); });
  expect(fetcher.mock.calls.some(([url]) => url === "/api/chat")).toBe(false);
  expect(Object.values(workspaceStore.getSnapshot().buckets.A.prepared).some(item => item.text === "原始提问")).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "会话 A" })); await screen.findByText("历史A");
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).value).toBe("后续编辑");
});
it.each(["知识库", "学习画像"])("cancels preparation when leaving chat for %s and returning", async target => {
  const pending = deferred<Response>(); let snapshots = 0;
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ ...ws, last_session_id: body.last_session_id, version: body.expected_version + 1 })); }
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return ++snapshots === 2 ? pending.promise : Promise.resolve(response(snapshot("A")));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "切页前的问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(snapshots).toBe(2));
  fireEvent.click(screen.getByRole("link", { name: target }));
  fireEvent.click(await screen.findByRole("button", { name: "会话 A" }));
  await screen.findByText("历史A");
  await act(async () => { pending.resolve(response(snapshot("A"))); });
  expect(fetcher.mock.calls.some(([url]) => url === "/api/chat")).toBe(false);
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).value).toBe("切页前的问题");
});
it("cancels preparation after browser history leaves and returns to the chat", async () => {
  const pending = deferred<Response>(); let snapshots = 0;
  const fetcher = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return ++snapshots === 2 ? pending.promise : Promise.resolve(response(snapshot("A")));
    return Promise.resolve(response({}, 404));
  });
  function Back() { const navigate = useNavigate(); return <button onClick={() => navigate(-1)}>测试返回</button>; }
  vi.stubGlobal("fetch", fetcher); storeIdentity();
  render(<AuthProvider><MemoryRouter initialEntries={["/chat/A"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><Back /><App /></MemoryRouter></AuthProvider>);
  await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "返回前问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(snapshots).toBe(2));
  fireEvent.click(screen.getByRole("link", { name: "知识库" }));
  fireEvent.click(screen.getByRole("button", { name: "测试返回" }));
  await screen.findByText("历史A");
  await act(async () => { pending.resolve(response(snapshot("A"))); });
  expect(fetcher.mock.calls.some(([url]) => url === "/api/chat")).toBe(false);
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).value).toBe("返回前问题");
});
it("cancels an old preparation when the default chat route restores the same session", async () => {
  const pending = deferred<Response>(); let snapshots = 0;
  const fetcher = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return ++snapshots === 2 ? pending.promise : Promise.resolve(response(snapshot("A")));
    return Promise.resolve(response({}, 404));
  });
  function DefaultChat() { const navigate = useNavigate(); return <button onClick={() => navigate("/chat")}>测试默认入口</button>; }
  vi.stubGlobal("fetch", fetcher); storeIdentity();
  render(<AuthProvider><MemoryRouter initialEntries={["/chat/A"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><DefaultChat /><App /></MemoryRouter></AuthProvider>);
  await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "默认入口前问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(snapshots).toBe(2));
  fireEvent.click(screen.getByRole("button", { name: "测试默认入口" }));
  await waitFor(() => expect(workspaceStore.getSnapshot().activeSessionEpoch).toBeGreaterThan(1));
  await screen.findByText("历史A");
  await act(async () => { pending.resolve(response(snapshot("A"))); });
  expect(fetcher.mock.calls.some(([url]) => url === "/api/chat")).toBe(false);
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).value).toBe("默认入口前问题");
});
it("keeps an already submitted response in its original session after switching", async () => {
  const pending = deferred<Response>(); let requestId = ""; let posted = false;
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ ...ws, last_session_id: body.last_session_id, version: body.expected_version + 1 })); }
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/B/snapshot")) return Promise.resolve(response(snapshot("B")));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(posted ? { ...snapshot("A"), session: { ...session("A"), state_version: 1, next_turn_index: 1 }, messages: { items: [{ id: 101, turn_index: 0, role: "user", content: "已提交问题", created_at: null }, { id: 102, turn_index: 0, role: "assistant", content: "A 的答案", created_at: null }], next_cursor: null } } : snapshot("A")));
    if (url === "/api/chat") { requestId = JSON.parse(String(init?.body)).request_id; posted = true; return pending.promise; }
    if (requestId && url.endsWith(`/requests/${requestId}`)) return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: requestId, profile_id: "p1", active_node_id: null, request_payload: { message: "已提交问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: requestId, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "A 的答案" }, created_at: "", updated_at: "" }));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "已提交问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(posted).toBe(true));
  fireEvent.click(screen.getByRole("button", { name: "会话 B" })); await screen.findByText("历史B");
  await act(async () => { pending.resolve(response({ session_id: "A", request_id: requestId, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "A 的答案" })); });
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.requests[requestId]?.association).toBe("matched"));
  expect(screen.queryByText("A 的答案")).toBeNull();
  expect(workspaceStore.getSnapshot().buckets.B.messages.some(message => message.content === "A 的答案")).toBe(false);
});
it("preserves a newer activity lock when an old completed snapshot returns", async () => {
  const page = deferred<Response>();
  let count = 0;
  const user = { id: 20, turn_index: 2, role: "user", content: "问题", created_at: null };
  const answer = { id: 21, turn_index: 2, role: "assistant", content: "答案", created_at: null };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/messages?")) return page.promise;
    if (url.startsWith("/api/sessions/A/snapshot")) {
      count++;
      if (count === 1) return Promise.resolve(response(snapshot("A")));
      if (count === 2) return Promise.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 1 }, messages: { items: [], next_cursor: "older" } }));
      return Promise.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 1, active_request_id: "other" } }));
    }
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  const ticket = workspaceStore.captureTicket();
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, baseline: { owner_user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 2, provenance: "before_submit", snapshot_sequence: 1 } } }, request: { id: "r1", status: "pending_messages", attempt: 1, error: null, sequence: 1 } })); });
  let pending!: Promise<void>;
  act(() => { pending = workspaceController.confirmCompleted("A", "r1", ticket); });
  await waitFor(() => expect(count).toBe(2));
  await act(async () => { await workspaceController.loadSession("A"); });
  await act(async () => { page.resolve(response({ items: [user, answer], next_cursor: null })); await pending; });
  expect(workspaceStore.getSnapshot().buckets.A.session?.active_request_id).toBe("other");
  expect(workspaceStore.getSnapshot().buckets.A.requests.r1.association).toBe("matched");
});
it("blocks sending and offers activity recheck after concurrent observations", async () => {
  const page = deferred<Response>();
  let count = 0;
  const user = { id: 20, turn_index: 2, role: "user", content: "问题", created_at: null };
  const answer = { id: 21, turn_index: 2, role: "assistant", content: "答案", created_at: null };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/messages?")) return page.promise;
    if (url.startsWith("/api/sessions/A/snapshot")) {
      count++;
      if (count === 1) return Promise.resolve(response(snapshot("A")));
      if (count === 2) return Promise.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 1 }, messages: { items: [], next_cursor: "older" } }));
      return Promise.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 1, active_request_id: "other" } }));
    }
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  const ticket = workspaceStore.captureTicket();
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, baseline: { owner_user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 2, provenance: "before_submit", snapshot_sequence: 1 } } }, request: { id: "r1", status: "pending_messages", attempt: 1, error: null, sequence: 1 } })); });
  let pending!: Promise<void>;
  act(() => { pending = workspaceController.confirmCompleted("A", "r1", ticket); });
  await waitFor(() => expect(count).toBe(2));
  await act(async () => { await workspaceController.loadSession("A"); });
  await act(async () => { page.resolve(response({ items: [user, answer], next_cursor: null })); await pending; });
  expect(workspaceStore.getSnapshot().buckets.A.session?.active_request_id).toBe("other");
  expect(screen.getByText("会话状态待确认")).toBeTruthy();
  expect(screen.getByRole("button", { name: "重新查询会话状态" })).toBeTruthy();
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).disabled).toBe(true);
});
it("keeps an in-flight older page when an unassociated continue snapshot arrives", async () => {
  const continued = deferred<Response>(); const older = deferred<Response>(); let count = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/messages?")) return older.promise;
    if (url.startsWith("/api/sessions/A/snapshot")) {
      if (++count === 2) return continued.promise;
      return Promise.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 1 }, messages: { ...snapshot("A").messages, next_cursor: "older" } }));
    }
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  const ticket = workspaceStore.captureTicket();
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, association: "unassociated" } }, request: { id: "r1", status: "unassociated", attempt: 1, error: null, sequence: 1 } })); });
  let pending!: Promise<void>; let page!: Promise<boolean>;
  act(() => { pending = workspaceController.continueUnassociated("A", "r1"); page = workspaceController.loadOlder("A"); });
  await waitFor(() => expect(count).toBe(2));
  await act(async () => { continued.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 1 }, messages: { items: [], next_cursor: null } })); await pending; });
  await act(async () => { older.resolve(response({ items: [{ id: 9, turn_index: -1, role: "user", content: "更早内容", created_at: null }], next_cursor: "next" })); expect(await page).toBe(true); });
  expect(workspaceStore.getSnapshot().buckets.A.nextMessageCursor).toBe("next");
  expect(screen.getByText("更早内容")).toBeTruthy();
});
it("keeps a private pure preparation after route cancellation and permits an explicit new send", async () => {
  const preparing = deferred<Response>(); let aSnapshots = 0;
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ ...ws, last_session_id: body.last_session_id, version: body.expected_version + 1 })); }
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return ++aSnapshots === 2 ? preparing.promise : Promise.resolve(response(snapshot("A")));
    if (url.startsWith("/api/sessions/B/snapshot")) return Promise.resolve(response(snapshot("B")));
    if (url.endsWith("/view-state") && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ draft: body.draft, reading_anchor: body.reading_anchor, version: body.expected_version + 1, updated_at: null })); }
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "原始提问" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(aSnapshots).toBe(2));
  fireEvent.click(screen.getByRole("button", { name: "会话 B" })); await screen.findByText("历史B");
  fireEvent.click(screen.getByRole("button", { name: "会话 A" })); await screen.findByText("历史A");
  await act(async () => { preparing.resolve(response(snapshot("A"))); });
  expect(fetcher.mock.calls.some(([url]) => url === "/api/chat")).toBe(false);
  expect(workspaceStore.getSnapshot().buckets.A.preparedCandidates[0]).toMatchObject({ schema: 2, phase: "prepared", text: "原始提问" });
  expect(workspaceStore.getSnapshot().buckets.A.preparedCandidates[0].requestId).toBeUndefined();
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(1));
  fireEvent.click(screen.getByRole("button", { name: "会话 A" })); await screen.findByText("历史A");
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).value).toBe("原始提问");
});
it("warns before copying an unknown preparation from another tab", async () => {
  const recovery = createLocalRecovery(localStorage, "other-tab");
  expect(recovery.writePrepared(1, "A", "prepare-other", { text: "另一页面的问题", sequence: 1, phase: "prepared" }).ok).toBe(true);
  const fetcher = installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "" } });
  expect(screen.getByText(/另一页面可能已经发送/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "复制原文并自行决定是否重新提问" }));
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).value).toBe("另一页面的问题");
  expect(fetcher.mock.calls.some(([url]) => url === "/api/chat")).toBe(false);
  expect(recovery.list(1, "A", "prepared")).toHaveLength(1);
});
it("does not send after another tab changes an acknowledged preparation", async () => {
  const writer = createLocalRecovery(localStorage, "other-tab");
  expect(writer.writePrepared(1, "A", "prepare-other", { text: "另一页面的问题", sequence: 1, phase: "prepared" }).ok).toBe(true);
  const fetcher = installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "" } });
  fireEvent.click(screen.getByRole("button", { name: "复制原文并自行决定是否重新提问" }));
  const payload = { message: "另一页面的问题", session_id: "A", profile_id: "p1", request_id: "other-request", expected_state_version: 0 };
  const baseline = { owner_user_id: 1, session_id: "A", request_id: "other-request", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 0, provenance: "before_submit", snapshot_sequence: 1 };
  expect(writer.writePrepared(1, "A", "prepare-other", { text: "另一页面的问题", sequence: 1, phase: "linked", requestId: "other-request", payload, baseline }).ok).toBe(true);
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(screen.getByText(/本机内容已变化或无法读取/)).toBeTruthy());
  expect(fetcher.mock.calls.some(([url]) => url === "/api/chat")).toBe(false);
  expect(workspaceStore.getSnapshot().buckets.A.preparedCandidates[0].phase).toBe("linked");
});
it("preserves a known preparation if storage becomes unreadable during send", async () => {
  const recovery = createLocalRecovery(localStorage, "other-tab");
  expect(recovery.writePrepared(1, "A", "other", { text: "旧副本", sequence: 1, phase: "prepared" }).ok).toBe(true);
  const fetcher = installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "" } });
  fireEvent.click(screen.getByRole("button", { name: "复制原文并自行决定是否重新提问" }));
  const originalGet = Storage.prototype.getItem;
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (this: Storage, key: string) { if (key.startsWith("studyagent:recovery:v1:prepared:")) throw new Error("unreadable"); return originalGet.call(this, key); });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  expect(fetcher.mock.calls.some(([url]) => url === "/api/chat")).toBe(false);
  expect(workspaceStore.getSnapshot().buckets.A.preparedCandidates.some(item => item.itemId === "other")).toBe(true);
  expect(workspaceStore.getSnapshot().buckets.A.acknowledgedPreparations).toHaveLength(0);
});
it.each(["prepared", "linked", "legacy"])("retains a known %s candidate when its explicit action cannot read storage", async phase => {
  const recovery = createLocalRecovery(localStorage, "other-tab");
  const payload = { message: "待保留原文", session_id: "A", profile_id: "p1", request_id: "r1", expected_state_version: 0 };
  const baseline = { owner_user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 0, provenance: "before_submit", snapshot_sequence: 1 };
  const value = phase === "legacy" ? { text: payload.message, sequence: 1 } : phase === "linked" ? { text: payload.message, sequence: 1, phase: "linked" as const, requestId: "r1", payload, baseline } : { text: payload.message, sequence: 1, phase: "prepared" as const };
  expect(recovery.writePrepared(1, "A", "candidate", value).ok).toBe(true);
  installTransport(); mount("/chat/A"); await screen.findByText("待保留原文");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "" } });
  const originalGet = Storage.prototype.getItem;
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (this: Storage, key: string) { if (key.startsWith("studyagent:recovery:v1:prepared:")) throw new Error("unreadable"); return originalGet.call(this, key); });
  fireEvent.click(screen.getByRole("button", { name: phase === "prepared" ? "复制原文并自行决定是否重新提问" : "查询原请求" }));
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.recoveryError).toMatch(/无法读取/));
  expect(workspaceStore.getSnapshot().buckets.A.preparedCandidates.some(item => item.itemId === "candidate")).toBe(true);
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).value).toBe("");
});
it("warns of possible loss while sending when recovery writes fail", async () => {
  const fetcher = installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  const original = Storage.prototype.setItem;
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, key: string, value: string) { if (key.startsWith("studyagent:recovery:")) throw new Error("unavailable"); return original.call(this, key, value); });
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "未备份的问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(fetcher.mock.calls.some(([url]) => url === "/api/chat")).toBe(true));
  expect(screen.getByText(/关闭页面或账号失效后未确认内容可能丢失/)).toBeTruthy();
});
it("preserves linked preparation identity during account transition backup", async () => {
  const pending = deferred<Response>();
  const fetcher = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url === "/api/chat") return pending.promise;
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "等待的问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(fetcher.mock.calls.some(([url]) => url === "/api/chat")).toBe(true));
  const before = getLocalRecovery().list(1, "A", "prepared")[0];
  expect(before.phase).toBe("linked");
  act(() => { workspaceStore.prepareAccountTransition(workspaceStore.captureTicket()); });
  const after = getLocalRecovery().list(1, "A", "prepared")[0];
  expect(after.phase).toBe("linked");
  expect(after.requestId).toBe(before.requestId);
  await act(async () => { pending.resolve(response({}, 503)); });
});
it("does not post if the session changes while linked preparation is being saved", async () => {
  const fetcher = installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  let switched = false;
  const unsubscribe = workspaceStore.subscribe(() => {
    if (!switched && workspaceStore.getSnapshot().buckets.A?.preparedCandidates.some(item => item.phase === "linked")) {
      switched = true; workspaceStore.setActiveSession("B");
    }
  });
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "需要保留的问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(switched).toBe(true));
  await act(async () => { await Promise.resolve(); });
  unsubscribe();
  expect(fetcher.mock.calls.some(([url]) => url === "/api/chat")).toBe(false);
  expect(getLocalRecovery().list(1, "A", "prepared")[0].phase).toBe("linked");
});
it("offers original request lookup for a linked preparation after reentry", async () => {
  const recovery = createLocalRecovery(localStorage, "previous-tab");
  const payload = { message: "原请求问题", session_id: "A", profile_id: "p1", request_id: "linked-request", expected_state_version: 0 };
  const baseline = { owner_user_id: 1, session_id: "A", request_id: "linked-request", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 0, provenance: "before_submit", snapshot_sequence: 1 };
  expect(recovery.writePrepared(1, "A", "prepare-linked", { text: "原请求问题", sequence: 1, phase: "linked", requestId: "linked-request", payload, baseline }).ok).toBe(true);
  const fetcher = installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.click(screen.getByRole("button", { name: "查询原请求" }));
  await waitFor(() => expect(fetcher.mock.calls.some(([url]) => String(url).endsWith("/requests/linked-request"))).toBe(true));
  expect(recovery.list(1, "A", "prepared")).toHaveLength(1);
  expect(fetcher.mock.calls.some(([url]) => url === "/api/chat")).toBe(false);
});
it.each(["normal", "request-readback"])("continues explicitly after matching the only surviving linked copy with %s", async mode => {
  const recovery = createLocalRecovery(localStorage, "previous-writer");
  const payload = { message: "旧请求原文", session_id: "A", profile_id: "p1", request_id: "old-linked", expected_state_version: 0 };
  const baseline = { owner_user_id: 1, session_id: "A", request_id: "old-linked", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 2, provenance: "before_submit", snapshot_sequence: 1 };
  expect(recovery.writePrepared(1, "A", "prepare-old", { text: payload.message, sequence: 1, phase: "linked", requestId: payload.request_id, payload, baseline }).ok).toBe(true);
  expect(recovery.list(1, "A", "request")).toHaveLength(0);
  let snapshots = 0;
  const fetcher = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots === 1 ? { ...snapshot("A"), view_state: { ...snapshot("A").view_state, draft: "" } } : { ...snapshot("A"), session: { ...session("A"), state_version: 1 }, messages: { items: [{ id: 20, turn_index: 2, role: "user", content: payload.message, created_at: null }, { id: 21, turn_index: 2, role: "assistant", content: "旧请求答案", created_at: null }], next_cursor: null } }));
    if (url.endsWith("/requests/old-linked")) return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: "old-linked", profile_id: "p1", active_node_id: null, request_payload: { message: payload.message, profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "old-linked", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "旧请求答案" }, created_at: "", updated_at: "" }));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("旧请求原文");
  fireEvent.click(screen.getByRole("button", { name: "查询原请求" }));
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.requests["old-linked"]?.association).toBe("matched"));
  expect(screen.getByText(/本操作只让当前页面继续/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "确认此请求已完成并继续" }));
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).disabled).toBe(false);
  expect(recovery.list(1, "A", "prepared")).toHaveLength(1);
  expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(0);
  if (mode === "request-readback") {
    const originalSet = Storage.prototype.setItem; const originalGet = Storage.prototype.getItem; let mismatch = "";
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, key: string, value: string) { originalSet.call(this, key, value); if (key.startsWith("studyagent:recovery:v1:request:")) mismatch = key; });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (this: Storage, key: string) { if (key === mismatch) { mismatch = ""; return "不一致读回"; } return originalGet.call(this, key); });
  }
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "下一问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(1));
  expect(recovery.list(1, "A", "prepared").some(item => item.writerId === "previous-writer")).toBe(true);
});
it("recovers the sole linked copy after a request write failure and a new writer starts", async () => {
  let requestId = ""; let restarted = false;
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(restarted ? { ...snapshot("A"), session: { ...session("A"), state_version: 1 }, view_state: { ...snapshot("A").view_state, draft: "" }, messages: { items: [{ id: 20, turn_index: 0, role: "user", content: "重启前问题", created_at: null }, { id: 21, turn_index: 0, role: "assistant", content: "重启前答案", created_at: null }], next_cursor: null } } : { ...snapshot("A"), messages: { items: [], next_cursor: null } }));
    if (url === "/api/chat") { if (!requestId) { requestId = JSON.parse(String(init?.body)).request_id; return Promise.reject(new Error("response lost")); } return Promise.resolve(response({}, 503)); }
    if (requestId && url.endsWith(`/requests/${requestId}`)) return Promise.resolve(response(restarted ? { user_id: 1, session_id: "A", request_id: requestId, profile_id: "p1", active_node_id: null, request_payload: { message: "重启前问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: requestId, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "重启前答案" }, created_at: "", updated_at: "" } : {}, restarted ? 200 : 404));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); const first = mount("/chat/A"); await within(first.container).findByPlaceholderText("输入学习问题…");
  const originalSet = Storage.prototype.setItem;
  const blocked = vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, key: string, value: string) { if (key.startsWith("studyagent:recovery:v1:request:")) throw new Error("blocked"); return originalSet.call(this, key, value); });
  fireEvent.change(within(first.container).getByPlaceholderText("输入学习问题…"), { target: { value: "重启前问题" } }); fireEvent.submit(within(first.container).getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.request.status).toBe("unknown"));
  expect(createLocalRecovery(localStorage, "reader").list(1, "A", "request")).toHaveLength(0);
  expect(createLocalRecovery(localStorage, "reader").list(1, "A", "prepared").some(item => item.phase === "linked" && item.requestId === requestId)).toBe(true);
  first.unmount(); blocked.mockRestore(); vi.resetModules(); restarted = true;
  const SecondApp = (await import("../App")).default; const SecondAuthProvider = (await import("../store/auth")).AuthProvider; const secondStore = (await import("../store/workspace")).workspaceStore;
  const second = render(<SecondAuthProvider><MemoryRouter initialEntries={["/chat/A"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><SecondApp /></MemoryRouter></SecondAuthProvider>);
  fireEvent.click(await within(second.container).findByRole("button", { name: "查询原请求" }));
  await waitFor(() => expect(secondStore.getSnapshot().buckets.A.requests[requestId]?.association).toBe("matched"));
  fireEvent.click(within(second.container).getByRole("button", { name: "确认此请求已完成并继续" }));
  expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(1);
  fireEvent.change(within(second.container).getByPlaceholderText("输入学习问题…"), { target: { value: "重启后新问题" } }); fireEvent.submit(within(second.container).getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(2));
  expect(createLocalRecovery(localStorage, "reader").list(1, "A", "prepared").some(item => item.requestId === requestId)).toBe(true);
});
it("removes only this page's linked copy after an unknown submission is matched", async () => {
  let requestId = ""; let completed = false;
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(completed ? { ...snapshot("A"), session: { ...session("A"), state_version: 1 }, messages: { items: [{ id: 20, turn_index: 0, role: "user", content: "本页原文", created_at: null }, { id: 21, turn_index: 0, role: "assistant", content: "本页答案", created_at: null }], next_cursor: null } } : { ...snapshot("A"), messages: { items: [], next_cursor: null } }));
    if (url === "/api/chat") { requestId = JSON.parse(String(init?.body)).request_id; return Promise.reject(new Error("response lost")); }
    if (requestId && url.endsWith(`/requests/${requestId}`)) return Promise.resolve(response(completed ? { user_id: 1, session_id: "A", request_id: requestId, profile_id: "p1", active_node_id: null, request_payload: { message: "本页原文", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: requestId, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "本页答案" }, created_at: "", updated_at: "" } : {}, completed ? 200 : 404));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByPlaceholderText("输入学习问题…");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "本页原文" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.request.status).toBe("unknown"));
  await waitFor(() => expect(screen.getByRole("button", { name: "查询上次请求" })).toBeTruthy());
  completed = true; fireEvent.click(screen.getByRole("button", { name: "查询上次请求" }));
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.requests[requestId]?.association).toBe("matched"));
  expect(getLocalRecovery().list(1, "A", "prepared").filter(item => item.requestId === requestId)).toHaveLength(0);
  expect(getLocalRecovery().list(1, "A", "request").filter(item => item.itemId === requestId)).toHaveLength(0);
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).disabled).toBe(false);
  expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(1);
});
it("keeps the linked recovery copy while an authoritative request is still running", async () => {
  let requestId = "";
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url === "/api/chat") { requestId = JSON.parse(String(init?.body)).request_id; return Promise.resolve(response({ session_id: "A", request_id: requestId, status: "running", attempt: 1, persisted: false })); }
    if (requestId && url.endsWith(`/requests/${requestId}`)) return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: requestId, profile_id: "p1", active_node_id: null, request_payload: { message: "处理中的问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "running", lease_until: null, lease_expired: false, error_code: null, response_json: null, created_at: "", updated_at: "" }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "处理中的问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.requests[requestId]?.snapshot.status).toBe("running"));
  expect(getLocalRecovery().list(1, "A", "prepared").some(item => item.phase === "linked" && item.requestId === requestId)).toBe(true);
});
it("does not delete a newer same-payload request copy when its history confirmation arrives", async () => {
  const page = deferred<Response>(); let requestId = ""; let posted = false;
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/messages?")) return page.promise;
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(posted ? { ...snapshot("A"), session: { ...session("A"), state_version: 1 }, messages: { items: [], next_cursor: "older" } } : snapshot("A")));
    if (url === "/api/chat") { requestId = JSON.parse(String(init?.body)).request_id; posted = true; return Promise.resolve(response({ session_id: "A", request_id: requestId, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" })); }
    if (requestId && url.endsWith(`/requests/${requestId}`)) return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: requestId, profile_id: "p1", active_node_id: null, request_payload: { message: "原问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: requestId, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" }));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "原问题" } }); fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(fetcher.mock.calls.some(([url]) => String(url).startsWith("/api/sessions/A/messages?"))).toBe(true));
  const local = workspaceStore.getSnapshot().buckets.A.localRequests[requestId];
  const newer = getLocalRecovery().writeRequest(1, "A", requestId, local); if (!newer.ok) throw new Error("failed to write replacement");
  await act(async () => { page.resolve(response({ items: [{ id: 20, turn_index: 0, role: "user", content: "原问题", created_at: null }, { id: 21, turn_index: 0, role: "assistant", content: "答案", created_at: null }], next_cursor: null })); });
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.requests[requestId]?.association).toBe("matched"));
  expect(getLocalRecovery().list(1, "A", "request").some(item => item.writeId === newer.candidate.writeId)).toBe(true);
});
it("retains and displays another writer's linked copy after matching this page's request", async () => {
  const post = deferred<Response>(); let requestId = ""; let completed = false;
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(completed ? { ...snapshot("A"), session: { ...session("A"), state_version: 1 }, messages: { items: [{ id: 20, turn_index: 0, role: "user", content: "共享请求", created_at: null }, { id: 21, turn_index: 0, role: "assistant", content: "答案", created_at: null }], next_cursor: null } } : { ...snapshot("A"), messages: { items: [], next_cursor: null } }));
    if (url === "/api/chat") { requestId = JSON.parse(String(init?.body)).request_id; return post.promise; }
    if (requestId && url.endsWith(`/requests/${requestId}`)) return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: requestId, profile_id: "p1", active_node_id: null, request_payload: { message: "共享请求", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: requestId, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" }));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByPlaceholderText("输入学习问题…");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "共享请求" } }); fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(requestId).not.toBe(""));
  const local = workspaceStore.getSnapshot().buckets.A.localRequests[requestId];
  const other = createLocalRecovery(localStorage, "other-writer").writePrepared(1, "A", "other-prep", { text: "共享请求", sequence: 1, phase: "linked", requestId, payload: local.payload, baseline: local.baseline });
  if (!other.ok) throw Error("write failed");
  completed = true; await act(async () => { post.resolve(response({ session_id: "A", request_id: requestId, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" })); });
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.requests[requestId]?.association).toBe("matched"));
  expect(createLocalRecovery(localStorage, "reader").list(1, "A", "prepared").some(item => item.writeId === other.candidate.writeId)).toBe(true);
  expect(workspaceStore.getSnapshot().buckets.A.preparedCandidates.some(item => item.writeId === other.candidate.writeId)).toBe(true);
  expect((screen.getByRole("button", { name: "发送" }) as HTMLButtonElement).disabled).toBe(true);
});
it("does not clean a matched local request when another writer has a different baseline", async () => {
  const payload = { message: "同编号问题", session_id: "A", profile_id: "p1", request_id: "r1", expected_state_version: 0 };
  const baseline = { owner_user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 0, provenance: "before_submit" as const, snapshot_sequence: 1 };
  const own = getLocalRecovery().writeRequest(1, "A", "r1", { payload, baseline }); if (!own.ok) throw Error("write failed");
  const foreign = createLocalRecovery(localStorage, "other-writer").writeRequest(1, "A", "r1", { payload, baseline: null }); if (!foreign.ok) throw Error("write failed");
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url.endsWith("/requests/r1")) return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: payload.message, profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A"); const ticket = workspaceStore.captureTicket();
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: payload.message, profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, localRequests: { r1: { payload, baseline } }, requests: { ...value.requests, r1: { ...value.requests.r1, baseline, association: "matched" } } })); });
  await act(async () => { await workspaceController.recheckCandidate("A", foreign.candidate); });
  expect(getLocalRecovery().list(1, "A", "request").some(item => item.writeId === own.candidate.writeId)).toBe(true);
  expect(workspaceStore.getSnapshot().buckets.A.recoveryError).toMatch(/未确认|不一致/);
});
it("does not ignore a newer local recovery write when storage becomes readable before exit", async () => {
  installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  const payload = { message: "原问题", session_id: "A", profile_id: "p1", request_id: "r1", expected_state_version: 0 };
  const baseline = { owner_user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 0, provenance: "before_submit" as const, snapshot_sequence: 1 };
  const old = getLocalRecovery().writeRequest(1, "A", "r1", { payload, baseline }); if (!old.ok) throw Error("write failed");
  const ticket = workspaceStore.captureTicket();
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: payload.message, profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, uncertainMatched: ["r1"], requestCandidates: [old.candidate], requests: { ...value.requests, r1: { ...value.requests.r1, baseline, association: "matched" } } })); });
  const newer = getLocalRecovery().writeRequest(1, "A", "r1", { payload, baseline }); if (!newer.ok) throw Error("write failed");
  const report = workspaceStore.prepareAccountTransition(ticket);
  expect(report.items.some(item => item.kind === "request" && item.itemId === "r1" && !item.ok)).toBe(true);
  expect(getLocalRecovery().list(1, "A", "request").some(item => item.writeId === newer.candidate.writeId)).toBe(true);
});
it("does not match an old linked source that changes while history is loading", async () => {
  const recovery = createLocalRecovery(localStorage, "previous-writer");
  const payload = { message: "旧原文", session_id: "A", profile_id: "p1", request_id: "old-linked", expected_state_version: 0 };
  const baseline = { owner_user_id: 1, session_id: "A", request_id: "old-linked", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 2, provenance: "before_submit", snapshot_sequence: 1 };
  expect(recovery.writePrepared(1, "A", "prepare-old", { text: payload.message, sequence: 1, phase: "linked", requestId: payload.request_id, payload, baseline }).ok).toBe(true);
  const page = deferred<Response>(); let snapshots = 0;
  const fetcher = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/messages?")) return page.promise;
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots === 1 ? snapshot("A") : { ...snapshot("A"), session: { ...session("A"), state_version: 1 }, messages: { items: [], next_cursor: "older" } }));
    if (url.endsWith("/requests/old-linked")) return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: "old-linked", profile_id: "p1", active_node_id: null, request_payload: { message: payload.message, profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "old-linked", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" }));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("旧原文");
  fireEvent.click(screen.getByRole("button", { name: "查询原请求" }));
  await waitFor(() => expect(fetcher.mock.calls.some(([url]) => String(url).startsWith("/api/sessions/A/messages?"))).toBe(true));
  expect(recovery.writePrepared(1, "A", "prepare-old", { text: payload.message, sequence: 2, phase: "linked", requestId: payload.request_id, payload, baseline }).ok).toBe(true);
  await act(async () => { page.resolve(response({ items: [{ id: 20, turn_index: 2, role: "user", content: payload.message, created_at: null }, { id: 21, turn_index: 2, role: "assistant", content: "答案", created_at: null }], next_cursor: null })); });
  expect(workspaceStore.getSnapshot().buckets.A.requests["old-linked"]?.association).not.toBe("matched");
  expect(screen.queryByRole("button", { name: "确认此请求已完成并继续" })).toBeNull();
  expect(recovery.list(1, "A", "prepared")).toHaveLength(1);
});
it("does not offer retry after a linked source changes before a 404 lookup returns", async () => {
  const recovery = createLocalRecovery(localStorage, "previous-writer");
  const payload = { message: "旧原文", session_id: "A", profile_id: "p1", request_id: "old-linked", expected_state_version: 0 };
  const baseline = { owner_user_id: 1, session_id: "A", request_id: "old-linked", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 2, provenance: "before_submit", snapshot_sequence: 1 };
  expect(recovery.writePrepared(1, "A", "prepare-old", { text: payload.message, sequence: 1, phase: "linked", requestId: payload.request_id, payload, baseline }).ok).toBe(true);
  const pending = deferred<Response>();
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url.endsWith("/requests/old-linked")) return pending.promise;
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("旧原文"); fireEvent.click(screen.getByRole("button", { name: "查询原请求" }));
  expect(recovery.writePrepared(1, "A", "prepare-old", { text: payload.message, sequence: 2, phase: "linked", requestId: payload.request_id, payload, baseline }).ok).toBe(true);
  await act(async () => { pending.resolve(response({}, 404)); });
  expect(screen.queryByRole("button", { name: "按原请求重试" })).toBeNull();
  expect(workspaceStore.getSnapshot().buckets.A.resendableRequests).not.toContain("old-linked");
});
it("queries a linked copy while request storage is unreadable without unlocking other requests", async () => {
  const recovery = createLocalRecovery(localStorage, "previous-writer");
  const payload = { message: "旧原文", session_id: "A", profile_id: "p1", request_id: "old-linked", expected_state_version: 0 };
  const baseline = { owner_user_id: 1, session_id: "A", request_id: "old-linked", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 2, provenance: "before_submit", snapshot_sequence: 1 };
  expect(recovery.writePrepared(1, "A", "prepare-old", { text: payload.message, sequence: 1, phase: "linked", requestId: payload.request_id, payload, baseline }).ok).toBe(true);
  expect(createLocalRecovery(localStorage, "other-writer").writeRequest(1, "A", "other", { payload: { ...payload, message: "另一请求", request_id: "other" }, baseline: null }).ok).toBe(true);
  let snapshots = 0; const fetcher = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots === 1 ? snapshot("A") : { ...snapshot("A"), session: { ...session("A"), state_version: 1 }, messages: { items: [{ id: 20, turn_index: 2, role: "user", content: payload.message, created_at: null }, { id: 21, turn_index: 2, role: "assistant", content: "答案", created_at: null }], next_cursor: null } }));
    if (url.endsWith("/requests/old-linked")) return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: "old-linked", profile_id: "p1", active_node_id: null, request_payload: { message: payload.message, profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "old-linked", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" }));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher);
  const originalGet = Storage.prototype.getItem;
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (this: Storage, key: string) { if (key.startsWith("studyagent:recovery:v1:request:")) throw new Error("unreadable"); return originalGet.call(this, key); });
  mount("/chat/A"); await screen.findByText("旧原文");
  fireEvent.click(screen.getByRole("button", { name: "查询原请求" }));
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.requests["old-linked"]?.association).toBe("matched"));
  expect(screen.getByText(/其他本机请求暂时无法读取/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "确认此请求已完成并继续" }));
  expect((screen.getByRole("button", { name: "发送" }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByText(/无法读取/)).toBeTruthy();
  expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(0);
});
it("does not offer an original-id retry while other request copies are unreadable", async () => {
  const recovery = createLocalRecovery(localStorage, "previous-writer");
  const payload = { message: "旧原文", session_id: "A", profile_id: "p1", request_id: "old-linked", expected_state_version: 0 };
  const baseline = { owner_user_id: 1, session_id: "A", request_id: "old-linked", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 2, provenance: "before_submit", snapshot_sequence: 1 };
  expect(recovery.writePrepared(1, "A", "prepare-old", { text: payload.message, sequence: 1, phase: "linked", requestId: payload.request_id, payload, baseline }).ok).toBe(true);
  expect(createLocalRecovery(localStorage, "other-writer").writeRequest(1, "A", "other", { payload: { ...payload, request_id: "other" }, baseline: null }).ok).toBe(true);
  const fetcher = installTransport(); const originalGet = Storage.prototype.getItem;
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (this: Storage, key: string) { if (key.startsWith("studyagent:recovery:v1:request:")) throw new Error("unreadable"); return originalGet.call(this, key); });
  mount("/chat/A"); await screen.findByText("旧原文"); fireEvent.click(screen.getByRole("button", { name: "查询原请求" }));
  await waitFor(() => expect(fetcher.mock.calls.some(([url]) => String(url).endsWith("/requests/old-linked"))).toBe(true));
  expect(screen.queryByRole("button", { name: "按原请求重试" })).toBeNull();
  expect(workspaceStore.getSnapshot().buckets.A.resendableRequests).not.toContain("old-linked");
  expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(0);
});
it("does not treat a linked request without a trusted baseline as matched", async () => {
  const payload = { message: "无基线原文", session_id: "A", profile_id: "p1", request_id: "no-baseline", expected_state_version: 0 };
  const recovery = createLocalRecovery(localStorage, "previous-writer");
  expect(recovery.writePrepared(1, "A", "prepare-old", { text: payload.message, sequence: 1, phase: "linked", requestId: payload.request_id, payload, baseline: null }).ok).toBe(true);
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url.endsWith("/requests/no-baseline")) return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: "no-baseline", profile_id: "p1", active_node_id: null, request_payload: { message: payload.message, profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "no-baseline", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("无基线原文"); fireEvent.click(screen.getByRole("button", { name: "查询原请求" }));
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.requests["no-baseline"]?.association).toBe("unassociated"));
  expect(screen.queryByRole("button", { name: "确认此请求已完成并继续" })).toBeNull();
  expect(recovery.list(1, "A", "prepared")).toHaveLength(1);
});
it("revokes linked confirmation if another writer adds an unknown request before sending", async () => {
  const recovery = createLocalRecovery(localStorage, "previous-writer");
  const payload = { message: "旧原文", session_id: "A", profile_id: "p1", request_id: "old-linked", expected_state_version: 0 };
  const baseline = { owner_user_id: 1, session_id: "A", request_id: "old-linked", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 2, provenance: "before_submit" as const, snapshot_sequence: 1 };
  const saved = recovery.writePrepared(1, "A", "prepare-old", { text: payload.message, sequence: 1, phase: "linked", requestId: payload.request_id, payload, baseline }); if (!saved.ok) throw Error("write failed");
  const fetcher = installTransport(); mount("/chat/A"); await screen.findByText("旧原文");
  const ticket = workspaceStore.captureTicket();
  const completed = { user_id: 1, session_id: "A", request_id: "old-linked", profile_id: "p1", active_node_id: null, request_payload: { message: payload.message, profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "old-linked", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, "old-linked": { ...value.requests["old-linked"], baseline, association: "matched" } } })); });
  fireEvent.click(screen.getByRole("button", { name: "确认此请求已完成并继续" }));
  expect(createLocalRecovery(localStorage, "other-writer").writeRequest(1, "A", "other", { payload: { ...payload, message: "别的请求", request_id: "other" }, baseline: null }).ok).toBe(true);
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "新问题" } }); fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(0);
  expect(workspaceStore.getSnapshot().buckets.A.acknowledgedPreparations).not.toContain(saved.candidate.writeId);
  expect(workspaceStore.getSnapshot().buckets.A.requestCandidates.some(item => item.itemId === "other")).toBe(true);
});
it("does not send when another writer adds an unknown request during preparation", async () => {
  const pending = deferred<Response>(); let snapshots = 0;
  const fetcher = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return ++snapshots === 2 ? pending.promise : Promise.resolve(response(snapshot("A")));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "本页新问题" } }); fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(snapshots).toBe(2));
  const payload = { message: "另一页未决问题", session_id: "A", profile_id: "p1", request_id: "other", expected_state_version: 0 };
  expect(createLocalRecovery(localStorage, "other-writer").writeRequest(1, "A", "other", { payload, baseline: null }).ok).toBe(true);
  await act(async () => { pending.resolve(response(snapshot("A"))); });
  expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(0);
  expect(workspaceStore.getSnapshot().buckets.A.requestCandidates.some(item => item.itemId === "other")).toBe(true);
});
it.each(["prepared-write", "linked-write", "request-write", "prepared-readback", "linked-readback", "request-readback", "prepared-throw", "linked-throw", "request-throw"])("does not retain matched in-memory work after %s fails", async scenario => {
  let requestId = ""; let posted = false;
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(posted ? { ...snapshot("A"), session: { ...session("A"), state_version: 1 }, messages: { items: [{ id: 20, turn_index: 0, role: "user", content: "内存问题", created_at: null }, { id: 21, turn_index: 0, role: "assistant", content: "内存答案", created_at: null }], next_cursor: null } } : { ...snapshot("A"), messages: { items: [], next_cursor: null } }));
    if (url === "/api/chat") { requestId = JSON.parse(String(init?.body)).request_id; posted = true; return Promise.resolve(response({ session_id: "A", request_id: requestId, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "内存答案" })); }
    if (requestId && url.endsWith(`/requests/${requestId}`)) return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: requestId, profile_id: "p1", active_node_id: null, request_payload: { message: "内存问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: requestId, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "内存答案" }, created_at: "", updated_at: "" }));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByPlaceholderText("输入学习问题…");
  const originalSet = Storage.prototype.setItem; const originalGet = Storage.prototype.getItem; let mismatchKey = "";
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, key: string, value: string) {
    const preparedKey = key.startsWith("studyagent:recovery:v1:prepared:");
    const target = scenario.startsWith("request-") && key.startsWith("studyagent:recovery:v1:request:") || scenario.startsWith("prepared-") && preparedKey && value.includes('"phase":"prepared"') || scenario.startsWith("linked-") && preparedKey && value.includes('"phase":"linked"');
    if (target && scenario.endsWith("-write")) throw new Error("blocked");
    originalSet.call(this, key, value); if (target && (scenario.endsWith("-readback") || scenario.endsWith("-throw"))) mismatchKey = key;
  });
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (this: Storage, key: string) { if (key === mismatchKey) { mismatchKey = ""; if (scenario.endsWith("-throw")) throw new Error("unreadable"); return "不一致的读回"; } return originalGet.call(this, key); });
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "内存问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.requests[requestId]?.association).toBe("matched"));
  const bucket = workspaceStore.getSnapshot().buckets.A;
  expect(bucket.localRequests[requestId]).toBeUndefined();
  expect(Object.values(bucket.prepared).some(item => item.requestId === requestId)).toBe(false);
  expect(bucket.requestCandidates.some(item => item.itemId === requestId && item.writerId === "")).toBe(false);
  expect(screen.getByText(/关闭页面或账号失效后未确认内容可能丢失|本机副本状态无法确认/)).toBeTruthy();
  const report = workspaceStore.prepareAccountTransition(workspaceStore.captureTicket());
  expect(report.items.some(item => (item.kind === "prepared" || item.kind === "request") && !item.ok)).toBe(false);
  if (scenario.startsWith("linked-")) {
    fireEvent.click(screen.getByRole("button", { name: "知悉本机状态不确定，继续本页" }));
    fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "继续新的问题" } });
    fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
    await waitFor(() => expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(2));
  }
});
it.each(["continue", "logout"])("retires matched in-memory work with unreadable recovery storage for %s", async action => {
  let requestId = ""; let posted = false;
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ ...ws, last_session_id: body.last_session_id, version: body.expected_version + 1 })); }
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.endsWith("/view-state")) { const body = JSON.parse(String(init?.body)); return Promise.resolve(response({ draft: body.draft, reading_anchor: body.reading_anchor ?? null, version: body.expected_version + 1, updated_at: null })); }
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(posted ? { ...snapshot("A"), session: { ...session("A"), state_version: 1 }, messages: { items: [{ id: 20, turn_index: 0, role: "user", content: "已保存问题", created_at: null }, { id: 21, turn_index: 0, role: "assistant", content: "已保存答案", created_at: null }], next_cursor: null } } : { ...snapshot("A"), messages: { items: [], next_cursor: null } }));
    if (url === "/api/chat") { requestId = JSON.parse(String(init?.body)).request_id; posted = true; return Promise.resolve(response({ session_id: "A", request_id: requestId, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "已保存答案" })); }
    if (requestId && url.endsWith(`/requests/${requestId}`)) return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: requestId, profile_id: "p1", active_node_id: null, request_payload: { message: "已保存问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: requestId, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "已保存答案" }, created_at: "", updated_at: "" }));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByPlaceholderText("输入学习问题…");
  const originalGet = Storage.prototype.getItem;
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (this: Storage, key: string) { if (posted && key.startsWith("studyagent:recovery:")) throw new Error("unreadable"); return originalGet.call(this, key); });
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "已保存问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.requests[requestId]?.association).toBe("matched"));
  const bucket = workspaceStore.getSnapshot().buckets.A;
  expect(bucket.localRequests[requestId]).toBeUndefined();
  expect(Object.values(bucket.prepared).some(item => item.requestId === requestId)).toBe(false);
  expect(screen.getByText(/本机副本状态无法确认/)).toBeTruthy();
  const report = workspaceStore.prepareAccountTransition(workspaceStore.captureTicket());
  expect(report.items.some(item => (item.kind === "prepared" || item.kind === "request") && !item.ok)).toBe(false);
  if (action === "logout") {
    fireEvent.click(screen.getByRole("button", { name: "账号：用户1" })); fireEvent.click(screen.getByRole("button", { name: "退出登录" }));
    await waitFor(() => expect(localStorage.getItem("studyagent_token")).toBeNull());
    return;
  }
  expect((screen.getByRole("button", { name: "发送" }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "知悉本机状态不确定，继续本页" }));
  expect((screen.getByRole("button", { name: "发送" }) as HTMLButtonElement).disabled).toBe(false);
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "用户主动的新问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(2));
});
it.each(["prepared", "linked", "request"])("recovers conservatively after restart with only the %s write persisted", async phase => {
  const recovery = createLocalRecovery(localStorage, "previous-tab");
  const payload = { message: "中断前的问题", session_id: "A", profile_id: "p1", request_id: "request-after-crash", expected_state_version: 0 };
  const baseline = { owner_user_id: 1, session_id: "A", request_id: "request-after-crash", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 0, provenance: "before_submit", snapshot_sequence: 1 };
  if (phase === "prepared") expect(recovery.writePrepared(1, "A", "prepare-before-crash", { text: payload.message, sequence: 1, phase: "prepared" }).ok).toBe(true);
  if (phase === "linked") expect(recovery.writePrepared(1, "A", "prepare-before-crash", { text: payload.message, sequence: 1, phase: "linked", requestId: payload.request_id, payload, baseline }).ok).toBe(true);
  if (phase === "request") expect(recovery.writeRequest(1, "A", payload.request_id, { payload, baseline }).ok).toBe(true);
  const fetcher = installTransport(); mount("/chat/A"); await screen.findByText("中断前的问题");
  expect((screen.getByRole("button", { name: "发送" }) as HTMLButtonElement).disabled).toBe(true);
  if (phase === "prepared") expect(screen.getByText(/另一页面可能已经发送/)).toBeTruthy();
  else expect(screen.getByRole("button", { name: phase === "linked" ? "查询原请求" : "查询上次请求" })).toBeTruthy();
  expect(fetcher.mock.calls.some(([url]) => url === "/api/chat")).toBe(false);
  expect(recovery.list(2, "A", phase === "request" ? "request" : "prepared")).toHaveLength(0);
});
it("keeps activity gate closed after recheck fails and clears it after a later idle snapshot", async () => {
  let snapshots = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(++snapshots === 2 ? response({}, 503) : response(snapshot("A")));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  act(() => workspaceStore.patchBucket(workspaceStore.captureTicket(), "A", value => ({ ...value, activityGate: "uncertain" })));
  fireEvent.click(screen.getByRole("button", { name: "重新查询会话状态" }));
  expect(await screen.findByText(/查询失败，请重试/)).toBeTruthy();
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "重新查询会话状态" }));
  await waitFor(() => expect(screen.queryByText("会话状态待确认")).toBeNull());
  expect(screen.queryByText(/查询失败，请重试/)).toBeNull();
});
it("does not let an older normal load replace a newer activity recheck", async () => {
  const old = deferred<Response>(); let snapshots = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) { snapshots++; return snapshots === 2 ? old.promise : Promise.resolve(response(snapshot("A"))); }
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  act(() => workspaceStore.patchBucket(workspaceStore.captureTicket(), "A", value => ({ ...value, activityGate: "uncertain" })));
  let pending!: Promise<void>; act(() => { pending = workspaceController.loadSession("A"); });
  await waitFor(() => expect(snapshots).toBe(2));
  await act(async () => { await workspaceController.recheckSessionActivity("A"); });
  await act(async () => { old.resolve(response({ ...snapshot("A"), session: { ...session("A"), active_request_id: "old-running" } })); await pending; });
  expect(workspaceStore.getSnapshot().buckets.A.session?.active_request_id).toBeNull();
  expect(workspaceStore.getSnapshot().buckets.A.activityGate).toBe("clear");
});
it("allows activity recheck again when a newer ordinary load supersedes an in-flight recheck", async () => {
  const old = deferred<Response>(); let snapshots = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return ++snapshots === 2 ? old.promise : Promise.resolve(response(snapshot("A")));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  const ticket = workspaceStore.captureTicket();
  act(() => { workspaceStore.patchBucket(ticket, "A", value => ({ ...value, activityGate: "uncertain" })); });
  let checking!: Promise<void>; act(() => { checking = workspaceController.recheckSessionActivity("A"); });
  await waitFor(() => expect(snapshots).toBe(2));
  await act(async () => { await workspaceController.loadSession("A"); });
  await act(async () => { old.resolve(response(snapshot("A"))); await checking; });
  expect(workspaceStore.getSnapshot().buckets.A.activityGate).not.toBe("checking");
  expect((screen.getByRole("button", { name: "重新查询会话状态" }) as HTMLButtonElement).disabled).toBe(false);
});
it("keeps a busy rejection unknown and requires the original request", async () => {
  const fetcher = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url === "/api/chat") return Promise.resolve(response({ detail: { code: "session_busy", message: "会话忙" } }, 409));
    if (url.includes("/requests/")) return Promise.resolve(response({}, 404));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "保留的问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(fetcher.mock.calls.some(([url]) => url === "/api/chat")).toBe(true));
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.request.status).toBe("unknown"));
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).value).toBe("保留的问题");
  expect(screen.getByRole("button", { name: "查询上次请求" })).toBeTruthy();
  expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(1);
});
it("recovers the original id when another client completes it after a busy response and an initial 404", async () => {
  let requestId = ""; let completed = false;
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(completed ? { ...snapshot("A"), session: { ...session("A"), state_version: 1, next_turn_index: 1 }, messages: { items: [{ id: 101, turn_index: 0, role: "user", content: "原编号问题", created_at: null }, { id: 102, turn_index: 0, role: "assistant", content: "已保存答案", created_at: null }], next_cursor: null } } : snapshot("A")));
    if (url === "/api/chat") { requestId = JSON.parse(String(init?.body)).request_id; return Promise.resolve(response({ detail: { code: "session_busy", message: "会话忙" } }, 409)); }
    if (url.endsWith(`/requests/${requestId}`)) return Promise.resolve(response(completed ? { user_id: 1, session_id: "A", request_id: requestId, profile_id: "p1", active_node_id: null, request_payload: { message: "原编号问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: requestId, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "已保存答案" }, created_at: "", updated_at: "" } : {}, completed ? 200 : 404));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "原编号问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.request.status).toBe("unknown"));
  fireEvent.click(await screen.findByRole("button", { name: "重新查询会话状态" }));
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.activityGate).toBe("clear"));
  fireEvent.click(screen.getByRole("button", { name: "查询上次请求" }));
  await screen.findByRole("button", { name: "按原请求重发" });
  expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(1);
  completed = true;
  fireEvent.click(screen.getByRole("button", { name: "查询上次请求" }));
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.requests[requestId]?.association).toBe("matched"));
  expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(1);
});
it("retries a linked preparation using its original request identity and payload", async () => {
  const recovery = createLocalRecovery(localStorage, "previous-tab");
  const payload = { message: "原请求问题", session_id: "A", profile_id: "p1", request_id: "linked-request", expected_state_version: 0 };
  const baseline = { owner_user_id: 1, session_id: "A", request_id: "linked-request", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 0, provenance: "before_submit", snapshot_sequence: 1 };
  expect(recovery.writePrepared(1, "A", "prepare-linked", { text: "原请求问题", sequence: 1, phase: "linked", requestId: "linked-request", payload, baseline }).ok).toBe(true);
  let sent: unknown;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url.endsWith("/requests/linked-request")) return Promise.resolve(response({}, 404));
    if (url === "/api/chat") { sent = JSON.parse(String(init?.body)); return Promise.resolve(response({}, 503)); }
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.click(screen.getByRole("button", { name: "查询原请求" }));
  fireEvent.click(await screen.findByRole("button", { name: "按原请求重试" }));
  await waitFor(() => expect(sent).toEqual(payload));
  expect(recovery.list(1, "A", "prepared")).toHaveLength(1);
});
it("does not continue an old request across a newer activity lock", async () => {
  const delayed = deferred<Response>(); let count = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) {
      count++;
      if (count === 2) return delayed.promise;
      return Promise.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 1, active_request_id: count === 1 ? null : "other" } }));
    }
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  const ticket = workspaceStore.captureTicket();
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, association: "unassociated" } }, request: { id: "r1", status: "unassociated", attempt: 1, error: null, sequence: 1 } })); });
  let pending!: Promise<void>;
  act(() => { pending = workspaceController.continueUnassociated("A", "r1"); });
  await waitFor(() => expect(count).toBe(2));
  await act(async () => { await workspaceController.loadSession("A"); });
  await act(async () => { delayed.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 1 } })); await pending; });
  expect(workspaceStore.getSnapshot().buckets.A.session?.active_request_id).toBe("other");
  expect(workspaceStore.getSnapshot().buckets.A.request.status).toBe("unassociated");
  expect(workspaceStore.getSnapshot().buckets.A.activityGate).toBe("uncertain");
});
it("does not write an old continue failure into a newer attempt", async () => {
  const delayed = deferred<Response>(); let count = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return ++count === 2 ? delayed.promise : Promise.resolve(response(snapshot("A")));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  const ticket = workspaceStore.captureTicket();
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, association: "unassociated" } }, request: { id: "r1", status: "unassociated", attempt: 1, error: null, sequence: 1 } })); });
  let pending!: Promise<void>; act(() => { pending = workspaceController.continueUnassociated("A", "r1"); });
  await waitFor(() => expect(count).toBe(2));
  act(() => workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, snapshot: { ...value.requests.r1.snapshot, attempt: 2 } } }, request: { ...value.request, attempt: 2, sequence: 2, error: null } })));
  await act(async () => { delayed.resolve(response({}, 503)); await pending; });
  expect(workspaceStore.getSnapshot().buckets.A.request.error).toBeNull();
  expect(workspaceStore.getSnapshot().buckets.A.request.attempt).toBe(2);
});
it("accepts newer profile independently of newer teaching state during continue", async () => {
  const summary = (revision: number) => ({ profile_revision: revision, nodes: [], edges: [], recent_evidence: [], assessed_count: 0, total_count: 0, mastery_score: null, metric_kind: "assessed_mean", assessment_coverage: null });
  const delayed = deferred<Response>(); let count = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) {
      count++;
      if (count === 2) return delayed.promise;
      return Promise.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: count === 1 ? 1 : 2 }, profile: { ...profile(), revision: 1 }, profile_summary: summary(1) }));
    }
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  const ticket = workspaceStore.captureTicket();
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, association: "unassociated" } }, request: { id: "r1", status: "unassociated", attempt: 1, error: null, sequence: 1 } })); });
  let pending!: Promise<void>;
  act(() => { pending = workspaceController.continueUnassociated("A", "r1"); });
  await waitFor(() => expect(count).toBe(2));
  await act(async () => { await workspaceController.loadSession("A"); });
  await act(async () => { delayed.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 1 }, profile: { ...profile(), revision: 2 }, profile_summary: summary(2) })); await pending; });
  expect(workspaceStore.getSnapshot().buckets.A.profileSummary?.profile_revision).toBe(2);
  expect(workspaceStore.getSnapshot().buckets.A.teachingStateVersion).toBe(2);
});
it("warns when equal profile revisions contain different values", async () => {
  const summary = (revision: number) => ({ profile_revision: revision, nodes: [], edges: [], recent_evidence: [], assessed_count: 0, total_count: 0, mastery_score: null, metric_kind: "assessed_mean", assessment_coverage: null });
  const page = deferred<Response>();
  let count = 0;
  const user = { id: 20, turn_index: 2, role: "user", content: "问题", created_at: null };
  const answer = { id: 21, turn_index: 2, role: "assistant", content: "答案", created_at: null };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/messages?")) return page.promise;
    if (url.startsWith("/api/sessions/A/snapshot")) {
      count++;
      if (count === 1) return Promise.resolve(response(snapshot("A")));
      if (count === 2) return Promise.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 1 }, profile: { ...profile(), revision: 2, name: "旧画像" }, profile_summary: summary(2), messages: { items: [], next_cursor: "older" } }));
      return Promise.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 2 }, profile: { ...profile(), revision: 2, name: "新画像" }, profile_summary: summary(2) }));
    }
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  const ticket = workspaceStore.captureTicket();
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, baseline: { owner_user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 2, provenance: "before_submit", snapshot_sequence: 1 } } }, request: { id: "r1", status: "pending_messages", attempt: 1, error: null, sequence: 1 } })); });
  let pending!: Promise<void>;
  act(() => { pending = workspaceController.confirmCompleted("A", "r1", ticket); });
  await waitFor(() => expect(count).toBe(2));
  await act(async () => { await workspaceController.loadSession("A"); });
  await act(async () => { page.resolve(response({ items: [user, answer], next_cursor: null })); await pending; });
  expect(workspaceStore.getSnapshot().buckets.A.profile?.name).toBe("新画像");
  expect(workspaceStore.getSnapshot().buckets.A.recoveryError).toMatch(/画像.*不一致/);
  expect(workspaceStore.getSnapshot().buckets.A.requests.r1.association).toBe("matched");
});
it("does not replace existing messages when a continue snapshot has a conflicting id", async () => {
  let count = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) {
      count++; return Promise.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 1 }, messages: count === 1 ? snapshot("A").messages : { items: [{ id: 1, turn_index: 0, role: "assistant", content: "冲突消息", created_at: null }], next_cursor: null } }));
    }
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A"); const ticket = workspaceStore.captureTicket();
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, association: "unassociated" } }, request: { id: "r1", status: "unassociated", attempt: 1, error: null, sequence: 1 } })); });
  await act(async () => { await workspaceController.continueUnassociated("A", "r1"); });
  expect(screen.getByText("历史A")).toBeTruthy();
  expect(workspaceStore.getSnapshot().buckets.A.request.status).toBe("unassociated");
  expect(workspaceStore.getSnapshot().buckets.A.request.error).toMatch(/不一致/);
});
it("keeps the cursor and messages when an older page conflicts by message id", async () => {
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response({ ...snapshot("A"), messages: { ...snapshot("A").messages, next_cursor: "older" } }));
    if (url.startsWith("/api/sessions/A/messages?")) return Promise.resolve(response({ items: [{ id: 1, turn_index: 0, role: "assistant", content: "冲突", created_at: null }], next_cursor: "next" }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.click(screen.getByRole("button", { name: "加载更早消息" }));
  expect(await screen.findByText(/更早消息加载失败/)).toBeTruthy();
  expect(workspaceStore.getSnapshot().buckets.A.nextMessageCursor).toBe("older");
  expect(screen.getByText("历史A")).toBeTruthy();
});
it("blocks a new question while another authoritative request is running", async () => {
  const fetcher = installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  const ticket = workspaceStore.captureTicket();
  act(() => workspaceStore.mergeRequest(ticket, { user_id: 1, session_id: "A", request_id: "other", profile_id: "p1", active_node_id: null, request_payload: { message: "其他问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "running", lease_until: null, lease_expired: false, error_code: null, response_json: null, created_at: "", updated_at: "" }));
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).disabled).toBe(true);
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  expect(fetcher.mock.calls.some(([url]) => url === "/api/chat")).toBe(false);
});
it("blocks a new question while an unrelated local request is unknown", async () => {
  const recovery = createLocalRecovery(localStorage, "previous-tab");
  const payload = { message: "未确认的问题", session_id: "A", profile_id: "p1", request_id: "unknown-other", expected_state_version: 0 };
  expect(recovery.writeRequest(1, "A", "unknown-other", { payload, baseline: null }).ok).toBe(true);
  const fetcher = installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).disabled).toBe(true);
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  expect(fetcher.mock.calls.some(([url]) => url === "/api/chat")).toBe(false);
});
it("enables a new question after explicitly continuing its matching unassociated request", async () => {
  const copy = createLocalRecovery(localStorage, "previous-tab").writeRequest(1, "A", "old-request", { payload: { message: "旧版问题", session_id: "A", profile_id: "p1", request_id: "old-request", expected_state_version: 0 }, baseline: null }); expect(copy.ok).toBe(true);
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 1, next_turn_index: 1 } }));
    if (url.endsWith("/requests/old-request")) return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: "old-request", profile_id: "p1", active_node_id: null, request_payload: { message: "旧版问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "old-request", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "旧版答案" }, created_at: "", updated_at: "" }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("旧版问题"); fireEvent.click(screen.getByRole("button", { name: "查询上次请求" }));
  fireEvent.click(await screen.findByRole("button", { name: "保留未关联记录并继续" }));
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.request.status).toBe("completed"));
  expect(createLocalRecovery(localStorage, "reader").listResult(1, "A", "request").candidates).toHaveLength(1);
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).disabled).toBe(false);
});
it("does not accept completed snapshot activity while a newer observation is in flight", async () => {
  const newer = deferred<Response>();
  const page = deferred<Response>();
  let count = 0;
  const user = { id: 20, turn_index: 2, role: "user", content: "问题", created_at: null };
  const answer = { id: 21, turn_index: 2, role: "assistant", content: "答案", created_at: null };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/messages?")) return page.promise;
    if (url.startsWith("/api/sessions/A/snapshot")) {
      count++;
      if (count === 1) return Promise.resolve(response(snapshot("A")));
      if (count === 2) return Promise.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 1 }, messages: { items: [], next_cursor: "older" } }));
      return newer.promise;
    }
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  const ticket = workspaceStore.captureTicket();
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, baseline: { owner_user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 2, provenance: "before_submit", snapshot_sequence: 1 } } }, request: { id: "r1", status: "pending_messages", attempt: 1, error: null, sequence: 1 } })); });
  let pending!: Promise<void>;
  act(() => { pending = workspaceController.confirmCompleted("A", "r1", ticket); });
  await waitFor(() => expect(count).toBe(2));
  let load!: Promise<void>; act(() => { load = workspaceController.loadSession("A"); });
  await waitFor(() => expect(count).toBe(3));
  await act(async () => { page.resolve(response({ items: [user, answer], next_cursor: null })); await pending; });
  expect(workspaceStore.getSnapshot().buckets.A.activityGate).toBe("uncertain");
  await act(async () => { newer.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 2 } })); await load; });
  expect(workspaceStore.getSnapshot().buckets.A.requests.r1.association).toBe("matched");
});
it("does not continue while a newer activity observation is still in flight", async () => {
  const delayed = deferred<Response>(); const newer = deferred<Response>(); let count = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) {
      count++;
      if (count === 2) return delayed.promise;
      if (count === 3) return newer.promise;
      return Promise.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 1 } }));
    }
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  const ticket = workspaceStore.captureTicket();
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, association: "unassociated" } }, request: { id: "r1", status: "unassociated", attempt: 1, error: null, sequence: 1 } })); });
  let pending!: Promise<void>;
  act(() => { pending = workspaceController.continueUnassociated("A", "r1"); });
  await waitFor(() => expect(count).toBe(2));
  let load!: Promise<void>; act(() => { load = workspaceController.loadSession("A"); });
  await waitFor(() => expect(count).toBe(3));
  await act(async () => { delayed.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 1 } })); await pending; });
  expect(workspaceStore.getSnapshot().buckets.A.session?.active_request_id).toBeNull();
  expect(workspaceStore.getSnapshot().buckets.A.request.status).toBe("unassociated");
  expect(workspaceStore.getSnapshot().buckets.A.activityGate).toBe("uncertain");
  await act(async () => { newer.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 1 } })); await load; });
});
it("blocks continued request when another writer has a conflicting baseline", async () => {
  const recovery = createLocalRecovery(localStorage, "other-tab");
  const payload = { message: "问题", session_id: "A", profile_id: "p1", request_id: "r1", expected_state_version: 0 };
  expect(recovery.writeRequest(1, "A", "r1", { payload, baseline: null }).ok).toBe(true);
  const fetcher = installTransport(); mount("/chat/A"); await screen.findByText("历史A"); const ticket = workspaceStore.captureTicket();
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, association: "unassociated", baseline: { owner_user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 0, provenance: "before_submit", snapshot_sequence: 1 } } }, continuedUnassociated: { r1: 1 }, request: { id: "r1", status: "completed", attempt: 1, error: null, sequence: 1 } })); });
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).disabled).toBe(true);
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  expect(fetcher.mock.calls.some(([url]) => url === "/api/chat")).toBe(false);
});
it.each(["payload", "base", "profile", "node", "turn"])("keeps same-id multiwriter %s conflicts blocked after explicit continue", async field => {
  const payload = { message: "相同请求", session_id: "A", profile_id: "p1", request_id: "r1", expected_state_version: 0 };
  const baseline = { owner_user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null as string | null, base_state_version: 0, expected_turn_index: 0, provenance: "before_submit", snapshot_sequence: 1 };
  const otherPayload = { ...payload, ...(field === "payload" ? { message: "不同内容" } : {}), ...(field === "base" ? { expected_state_version: 1 } : {}), ...(field === "profile" ? { profile_id: "p2" } : {}) };
  const otherBaseline = { ...baseline, ...(field === "base" ? { base_state_version: 1 } : {}), ...(field === "profile" ? { profile_id: "p2" } : {}), ...(field === "node" ? { active_node_id: "other-node" } : {}), ...(field === "turn" ? { expected_turn_index: 1 } : {}) };
  expect(createLocalRecovery(localStorage, "writer-one").writeRequest(1, "A", "r1", { payload, baseline }).ok).toBe(true);
  expect(createLocalRecovery(localStorage, "writer-two").writeRequest(1, "A", "r1", { payload: otherPayload, baseline: otherBaseline }).ok).toBe(true);
  const fetcher = installTransport(); mount("/chat/A"); await screen.findByText("历史A"); const ticket = workspaceStore.captureTicket();
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "相同请求", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, association: "unassociated", baseline: { ...baseline, provenance: "before_submit" } } }, continuedUnassociated: { r1: 1 }, request: { id: "r1", status: "completed", attempt: 1, error: null, sequence: 1 } })); });
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).disabled).toBe(true);
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  expect(fetcher.mock.calls.some(([url]) => url === "/api/chat")).toBe(false);
  expect(createLocalRecovery(localStorage, "reader").listResult(1, "A", "request").candidates).toHaveLength(2);
});
it("ignores a late request observation after a newer activity snapshot", async () => {
  const pending = deferred<Response>(); let snapshots = 0;
  const running = (id: string) => ({ user_id: 1, session_id: "A", request_id: id, profile_id: "p1", active_node_id: null, request_payload: { message: id, profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "running", lease_until: null, lease_expired: false, error_code: null, response_json: null, created_at: "", updated_at: "" });
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.endsWith("/requests/old")) return pending.promise;
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots === 1 ? snapshot("A") : { ...snapshot("A"), session: { ...session("A"), active_request_id: "new" }, pending_requests: [running("new")] }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  let old!: Promise<void>; act(() => { old = workspaceController.reconcile("A", "old"); });
  await act(async () => { await workspaceController.loadSession("A"); });
  await act(async () => { pending.resolve(response(running("old"))); await old; });
  expect(workspaceStore.getSnapshot().buckets.A.session?.active_request_id).toBe("new");
  expect(workspaceStore.getSnapshot().buckets.A.requests.old).toBeUndefined();
});
it("does not let a stale retry lookup overwrite the current request after a newer activity observation", async () => {
  const pending = deferred<Response>(); let snapshots = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.endsWith("/requests/old")) return pending.promise;
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots === 1 ? snapshot("A") : { ...snapshot("A"), session: { ...session("A"), active_request_id: "new" } }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  const ticket = workspaceStore.captureTicket();
  act(() => { workspaceStore.patchBucket(ticket, "A", value => ({ ...value, request: { id: "old", status: "failed", attempt: 1, error: "原错误", sequence: 1 } })); });
  let retry!: Promise<void>; act(() => { retry = workspaceController.retry("A", "old"); });
  await act(async () => { await workspaceController.loadSession("A"); });
  await act(async () => { pending.resolve(response({}, 503)); await retry; });
  expect(workspaceStore.getSnapshot().buckets.A.request.status).toBe("failed");
  expect(workspaceStore.getSnapshot().buckets.A.request.error).toBe("原错误");
  expect(workspaceStore.getSnapshot().buckets.A.session?.active_request_id).toBe("new");
});
it("does not report a stale original-request lookup after a newer activity observation", async () => {
  const payload = { message: "原问题", session_id: "A", profile_id: "p1", request_id: "old", expected_state_version: 0 };
  const saved = createLocalRecovery(localStorage, "other-tab").writeRequest(1, "A", "old", { payload, baseline: null });
  expect(saved.ok).toBe(true);
  if (!saved.ok) throw new Error("failed to create recovery candidate");
  const candidate = saved.candidate;
  const pending = deferred<Response>(); let snapshots = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.endsWith("/requests/old")) return pending.promise;
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots === 1 ? snapshot("A") : { ...snapshot("A"), session: { ...session("A"), active_request_id: "new" } }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  const ticket = workspaceStore.captureTicket();
  act(() => { workspaceStore.patchBucket(ticket, "A", value => ({ ...value, resendableRequests: ["old"], recoveryError: null })); });
  let resend!: Promise<void>; act(() => { resend = workspaceController.resendCandidate("A", candidate); });
  await act(async () => { await workspaceController.loadSession("A"); });
  await act(async () => { pending.resolve(response({}, 404)); await resend; });
  expect(workspaceStore.getSnapshot().buckets.A.recoveryError).toBeNull();
  expect(workspaceStore.getSnapshot().buckets.A.session?.active_request_id).toBe("new");
});
it("does not resend an old request after a newer activity observation supersedes its snapshot", async () => {
  const payload = { message: "原问题", session_id: "A", profile_id: "p1", request_id: "old", expected_state_version: 0 };
  const saved = createLocalRecovery(localStorage, "other-tab").writeRequest(1, "A", "old", { payload, baseline: null });
  if (!saved.ok) throw new Error("failed to create recovery candidate");
  const candidate = saved.candidate;
  const pending = deferred<Response>(); let snapshots = 0;
  const fetcher = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.endsWith("/requests/old")) return Promise.resolve(response({}, 404));
    if (url.startsWith("/api/sessions/A/snapshot")) {
      snapshots++;
      return snapshots === 2 ? pending.promise : Promise.resolve(response(snapshots === 1 ? snapshot("A") : { ...snapshot("A"), session: { ...session("A"), active_request_id: "new" } }));
    }
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  const ticket = workspaceStore.captureTicket();
  act(() => { workspaceStore.patchBucket(ticket, "A", value => ({ ...value, resendableRequests: ["old"] })); });
  let resend!: Promise<void>; act(() => { resend = workspaceController.resendCandidate("A", candidate); });
  await waitFor(() => expect(snapshots).toBe(2));
  await act(async () => { await workspaceController.loadSession("A"); });
  await act(async () => { pending.resolve(response(snapshot("A"))); await resend; });
  expect(fetcher.mock.calls.some(([url]) => url === "/api/chat")).toBe(false);
  expect(workspaceStore.getSnapshot().buckets.A.session?.active_request_id).toBe("new");
});
it("does not resend when its saved request candidate changes during the snapshot", async () => {
  const recovery = createLocalRecovery(localStorage, "other-tab");
  const payload = { message: "原问题", session_id: "A", profile_id: "p1", request_id: "old", expected_state_version: 0 };
  const saved = recovery.writeRequest(1, "A", "old", { payload, baseline: null });
  if (!saved.ok) throw new Error("failed to create recovery candidate");
  const candidate = saved.candidate; const pending = deferred<Response>(); let snapshots = 0;
  const fetcher = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.endsWith("/requests/old")) return Promise.resolve(response({}, 404));
    if (url.startsWith("/api/sessions/A/snapshot")) return ++snapshots === 2 ? pending.promise : Promise.resolve(response(snapshot("A")));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("原问题");
  act(() => { workspaceStore.patchBucket(workspaceStore.captureTicket(), "A", value => ({ ...value, resendableRequests: ["old"] })); });
  let resend!: Promise<void>; act(() => { resend = workspaceController.resendCandidate("A", candidate); });
  await waitFor(() => expect(snapshots).toBe(2));
  expect(recovery.writeRequest(1, "A", "old", { payload: { ...payload, message: "新问题" }, baseline: null }).ok).toBe(true);
  await act(async () => { pending.resolve(response(snapshot("A"))); await resend; });
  expect(fetcher.mock.calls.some(([url]) => url === "/api/chat")).toBe(false);
  expect(workspaceStore.getSnapshot().buckets.A.recoveryError).toMatch(/变化|重新检查/);
});
it("does not retry a failed request after a newer activity observation supersedes its snapshot", async () => {
  const entry = { user_id: 1, session_id: "A", request_id: "old", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "failed", lease_until: null, lease_expired: false, error_code: "failed", response_json: null, created_at: "", updated_at: "" };
  const pending = deferred<Response>(); let snapshots = 0;
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.endsWith("/requests/old") && init?.method !== "POST") return Promise.resolve(response(entry));
    if (url.startsWith("/api/sessions/A/snapshot")) {
      snapshots++;
      return snapshots === 2 ? pending.promise : Promise.resolve(response(snapshots === 1 ? { ...snapshot("A"), pending_requests: [entry] } : { ...snapshot("A"), session: { ...session("A"), active_request_id: "new" }, pending_requests: [entry] }));
    }
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("问题");
  let retry!: Promise<void>; act(() => { retry = workspaceController.retry("A", "old"); });
  await waitFor(() => expect(snapshots).toBe(2));
  await act(async () => { await workspaceController.loadSession("A"); });
  await act(async () => { pending.resolve(response(snapshot("A"))); await retry; });
  expect(fetcher.mock.calls.some(([url, init]) => String(url).includes("/requests/old/retry") && init?.method === "POST")).toBe(false);
  expect(workspaceStore.getSnapshot().buckets.A.session?.active_request_id).toBe("new");
});
it("does not retry a failed request when its fresh snapshot reports another active request", async () => {
  const entry = { user_id: 1, session_id: "A", request_id: "old", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "failed", lease_until: null, lease_expired: false, error_code: "failed", response_json: null, created_at: "", updated_at: "" };
  let snapshots = 0;
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.endsWith("/requests/old") && init?.method !== "POST") return Promise.resolve(response(entry));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots === 1 ? { ...snapshot("A"), pending_requests: [entry] } : { ...snapshot("A"), session: { ...session("A"), active_request_id: "new" } }));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("问题");
  await act(async () => { await workspaceController.retry("A", "old"); });
  expect(fetcher.mock.calls.some(([url, init]) => String(url).includes("/requests/old/retry") && init?.method === "POST")).toBe(false);
  expect(workspaceStore.getSnapshot().buckets.A.activityGate).toBe("uncertain");
});
it("queries a legacy prepared id instead of assuming it was never sent", async () => {
  const recovery = createLocalRecovery(localStorage, "old-tab");
  expect(recovery.writePrepared(1, "A", "legacy-id", { text: "旧版原文", sequence: 1 }).ok).toBe(true);
  const fetcher = installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.click(screen.getByRole("button", { name: "查询原请求" }));
  await waitFor(() => expect(fetcher.mock.calls.some(([url]) => String(url).endsWith("/requests/legacy-id"))).toBe(true));
  expect(recovery.list(1, "A", "prepared")).toHaveLength(1);
  expect(fetcher.mock.calls.some(([url]) => url === "/api/chat")).toBe(false);
});
it("does not accept a legacy request lookup after its saved preparation changes", async () => {
  const recovery = createLocalRecovery(localStorage, "old-tab");
  const saved = recovery.writePrepared(1, "A", "legacy", { text: "旧原文", sequence: 1 });
  if (!saved.ok) throw new Error("failed to create legacy candidate");
  const candidate = saved.candidate; const pending = deferred<Response>();
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url.endsWith("/requests/legacy")) return pending.promise;
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("旧原文");
  let checking!: Promise<void>; act(() => { checking = workspaceController.recheckLegacyPreparation("A", candidate); });
  expect(recovery.writePrepared(1, "A", "legacy", { text: "新原文", sequence: 2 }).ok).toBe(true);
  await act(async () => { pending.resolve(response({ user_id: 1, session_id: "A", request_id: "legacy", profile_id: "p1", active_node_id: null, request_payload: { message: "旧原文", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "running", lease_until: null, lease_expired: false, error_code: null, response_json: null, created_at: "", updated_at: "" })); await checking; });
  expect(workspaceStore.getSnapshot().buckets.A.requests.legacy).toBeUndefined();
  expect(workspaceStore.getSnapshot().buckets.A.recoveryError).toMatch(/变化|重新检查/);
});
it("checks an active request during activity refresh and accepts its terminal state", async () => {
  const running = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "running" as const, lease_until: null, lease_expired: false, error_code: null, response_json: null, created_at: "", updated_at: "" };
  const completed = { ...running, status: "completed", response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" } };
  let snapshots = 0;
  const fetcher = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots === 1 ? snapshot("A") : { ...snapshot("A"), session: { ...session("A"), active_request_id: "r1" }, pending_requests: [running] }));
    if (url.endsWith("/requests/r1")) return Promise.resolve(response(completed));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  const ticket = workspaceStore.captureTicket(); act(() => { workspaceStore.mergeRequest(ticket, running); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, activityGate: "uncertain" })); });
  fireEvent.click(screen.getByRole("button", { name: "重新查询会话状态" }));
  await waitFor(() => expect(fetcher.mock.calls.some(([url]) => String(url).endsWith("/requests/r1"))).toBe(true));
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.requests.r1.snapshot.status).toBe("completed"));
  expect(workspaceStore.getSnapshot().buckets.A.pendingRequests.some(item => item.request_id === "r1" && item.status === "running")).toBe(false);
});
it("preserves a profile and warns when a normal reload has the same revision but conflicting content", async () => {
  let snapshots = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response({ ...snapshot("A"), profile: { ...profile(), revision: 2, name: ++snapshots === 1 ? "原画像" : "冲突画像" } }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  await act(async () => { await workspaceController.loadSession("A"); });
  expect(workspaceStore.getSnapshot().buckets.A.profile?.name).toBe("原画像");
  expect(workspaceStore.getSnapshot().buckets.A.recoveryError).toMatch(/画像.*不一致/);
});
it("warns on equal profile revision conflict during continue", async () => {
  const summary = (revision: number) => ({ profile_revision: revision, nodes: [], edges: [], recent_evidence: [], assessed_count: 0, total_count: 0, mastery_score: null, metric_kind: "assessed_mean", assessment_coverage: null });
  const delayed = deferred<Response>(); let count = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) {
      count++;
      if (count === 2) return delayed.promise;
      return Promise.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: count === 1 ? 1 : 2 }, profile: { ...profile(), revision: 1 }, profile_summary: summary(1) }));
    }
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  const ticket = workspaceStore.captureTicket();
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, association: "unassociated" } }, request: { id: "r1", status: "unassociated", attempt: 1, error: null, sequence: 1 } })); });
  let pending!: Promise<void>;
  act(() => { pending = workspaceController.continueUnassociated("A", "r1"); });
  await waitFor(() => expect(count).toBe(2));
  await act(async () => { await workspaceController.loadSession("A"); });
  await act(async () => { delayed.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 1 }, profile: { ...profile(), revision: 1, name: "冲突画像" }, profile_summary: summary(1) })); await pending; });
  expect(workspaceStore.getSnapshot().buckets.A.profile?.name).toBe("概率论");
  expect(workspaceStore.getSnapshot().buckets.A.recoveryError).toMatch(/画像.*不一致/);
  expect(workspaceStore.getSnapshot().buckets.A.teachingStateVersion).toBe(2);
});
it("does not send when a shared preparation appears while its snapshot is in flight", async () => {
  const pending = deferred<Response>(); let snapshots = 0;
  const fetcher = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return ++snapshots === 2 ? pending.promise : Promise.resolve(response(snapshot("A")));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "本页问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(snapshots).toBe(2));
  const other = createLocalRecovery(localStorage, "other-tab");
  expect(other.writePrepared(1, "A", "other-prep", { text: "另一页问题", sequence: 1, phase: "prepared" }).ok).toBe(true);
  await act(async () => { pending.resolve(response(snapshot("A"))); });
  expect(fetcher.mock.calls.some(([url]) => url === "/api/chat")).toBe(false);
  expect(screen.getByText(/本机内容已变化或无法读取/)).toBeTruthy();
});
it.each([false, true])("does not send when another preparation appears after both own writes fail (damaged entry: %s)", async damaged => {
  const pending = deferred<Response>(); let snapshots = 0;
  const fetcher = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return ++snapshots === 2 ? pending.promise : Promise.resolve(response(snapshot("A")));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  const ownWriter = getLocalRecovery().writerId; const originalSet = Storage.prototype.setItem;
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, key: string, value: string) { if (key.startsWith("studyagent:recovery:v1:prepared:") && key.includes(encodeURIComponent(ownWriter))) throw new Error("blocked"); return originalSet.call(this, key, value); });
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "本页问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(snapshots).toBe(2));
  expect(createLocalRecovery(localStorage, "other-tab").writePrepared(1, "A", "other", { text: "另一页问题", sequence: 1, phase: "prepared" }).ok).toBe(true);
  if (damaged) localStorage.setItem("studyagent:recovery:v1:prepared:1:A:damaged:bad", "{");
  await act(async () => { pending.resolve(response(snapshot("A"))); });
  expect(fetcher.mock.calls.some(([url]) => url === "/api/chat")).toBe(false);
  expect(workspaceStore.getSnapshot().buckets.A.recoveryError).toMatch(/变化|重新检查/);
});
it("still sends with a warning when linked preparation readback fails", async () => {
  const fetcher = installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  const originalSet = Storage.prototype.setItem; const originalGet = Storage.prototype.getItem; let blocked = false;
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, key: string, value: string) { originalSet.call(this, key, value); if (key.startsWith("studyagent:recovery:") && value.includes('"phase":"linked"')) blocked = true; });
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (this: Storage, key: string) { if (blocked && key.startsWith("studyagent:recovery:")) throw new Error("readback unavailable"); return originalGet.call(this, key); });
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "读回失败的问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(fetcher.mock.calls.some(([url]) => url === "/api/chat")).toBe(true));
  expect(screen.getByText(/关闭页面或账号失效后未确认内容可能丢失/)).toBeTruthy();
});
it.each(["prepared", "linked", "request"])("preserves a warning and still submits when the %s recovery write fails", async failedPhase => {
  const fetcher = installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  const originalSet = Storage.prototype.setItem;
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, key: string, value: string) {
    const isRequest = key.startsWith("studyagent:recovery:v1:request:");
    const isPrepared = key.startsWith("studyagent:recovery:v1:prepared:");
    if ((failedPhase === "request" && isRequest) || (failedPhase === "prepared" && isPrepared && value.includes('"phase":"prepared"')) || (failedPhase === "linked" && isPrepared && value.includes('"phase":"linked"'))) throw new Error("unavailable");
    return originalSet.call(this, key, value);
  });
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "可能无法恢复的问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(1));
  expect(screen.getByText(/关闭页面或账号失效后未确认内容可能丢失/)).toBeTruthy();
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).value).toBe("可能无法恢复的问题");
});
it.each(["prepared", "linked", "request"])("warns and keeps sending when the %s write has inconsistent readback", async failedPhase => {
  const fetcher = installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  const originalSet = Storage.prototype.setItem; const originalGet = Storage.prototype.getItem; let mismatchKey = "";
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, key: string, value: string) {
    originalSet.call(this, key, value);
    const prepared = key.startsWith("studyagent:recovery:v1:prepared:");
    if ((failedPhase === "request" && key.startsWith("studyagent:recovery:v1:request:")) || (failedPhase === "prepared" && prepared && value.includes('"phase":"prepared"')) || (failedPhase === "linked" && prepared && value.includes('"phase":"linked"'))) mismatchKey = key;
  });
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (this: Storage, key: string) { if (key === mismatchKey) { mismatchKey = ""; return "不一致的读回"; } return originalGet.call(this, key); });
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "读回不一致的问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(1));
  expect(screen.getByText(/关闭页面或账号失效后未确认内容可能丢失/)).toBeTruthy();
  expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).value).toBe("读回不一致的问题");
});
it("visibly blocks sending an unknown preparation until the user acknowledges its risk", async () => {
  const recovery = createLocalRecovery(localStorage, "other-tab");
  expect(recovery.writePrepared(1, "A", "other", { text: "待确认原文", sequence: 1, phase: "prepared" }).ok).toBe(true);
  installTransport(); mount("/chat/A"); await screen.findByText("历史A");
  expect((screen.getByRole("button", { name: "发送" }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "" } });
  fireEvent.click(screen.getByRole("button", { name: "复制原文并自行决定是否重新提问" }));
  expect((screen.getByRole("button", { name: "发送" }) as HTMLButtonElement).disabled).toBe(false);
});
it("two isolated controllers reject a cached preparation after its owner links it", async () => {
  const pending = deferred<Response>(); let snapshots = 0;
  const fetcher = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return ++snapshots === 2 ? pending.promise : Promise.resolve(response({ ...snapshot("A"), view_state: { ...snapshot("A").view_state, draft: "" } }));
    if (url === "/api/chat") return Promise.resolve(response({}, 503));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "双页原文" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(snapshots).toBe(2));
  vi.resetModules();
  const isolatedStore = (await import("../store/workspace")).workspaceStore;
  const isolatedController = (await import("../store/workspaceController")).workspaceController;
  expect(isolatedStore.startAccount(1, "A")).toBe(true);
  isolatedStore.ensureSessionBucket("A"); isolatedStore.setActiveSession("A");
  await isolatedController.loadSession("A");
  const cached = isolatedStore.getSnapshot().buckets.A.preparedCandidates[0];
  expect(cached.phase).toBe("prepared");
  await act(async () => { pending.resolve(response(snapshot("A"))); });
  await waitFor(() => expect(fetcher.mock.calls.some(([url]) => url === "/api/chat")).toBe(true));
  isolatedController.acknowledgePreparedRisk("A", cached);
  expect(isolatedStore.getSnapshot().buckets.A.draft).toBe("");
  expect(isolatedStore.getSnapshot().buckets.A.recoveryError).toMatch(/已变化/);
  expect(isolatedStore.getSnapshot().buckets.A.preparedCandidates[0].phase).toBe("linked");
  expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(1);
});
it("two providers sharing storage keep a cached preparation blocked after its owner links and sends", async () => {
  const pending = deferred<Response>(); let snapshots = 0; let requestId = "";
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) {
      if (++snapshots === 2) return pending.promise;
      if (requestId) return Promise.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 1, next_turn_index: 1 }, messages: { items: [{ id: 101, turn_index: 0, role: "user", content: "双窗口问题", created_at: null }, { id: 102, turn_index: 0, role: "assistant", content: "已保存答案", created_at: null }], next_cursor: null } }));
      return Promise.resolve(response({ ...snapshot("A"), view_state: { ...snapshot("A").view_state, draft: "" } }));
    }
    if (url === "/api/chat") { requestId = JSON.parse(String(init?.body)).request_id; return Promise.resolve(response({ session_id: "A", request_id: requestId, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "已保存答案" })); }
    if (url.endsWith(`/requests/${requestId}`)) return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: requestId, profile_id: "p1", active_node_id: null, request_payload: { message: "双窗口问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: requestId, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "已保存答案" }, created_at: "", updated_at: "" }));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); const first = mount("/chat/A"); await within(first.container).findByText("历史A");
  fireEvent.change(within(first.container).getByPlaceholderText("输入学习问题…"), { target: { value: "双窗口问题" } });
  fireEvent.submit(within(first.container).getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(snapshots).toBe(2));
  vi.resetModules();
  const SecondApp = (await import("../App")).default;
  const SecondAuthProvider = (await import("../store/auth")).AuthProvider;
  const second = render(<SecondAuthProvider><MemoryRouter initialEntries={["/chat/A"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><SecondApp /></MemoryRouter></SecondAuthProvider>);
  expect(await within(second.container).findByText("双窗口问题")).toBeTruthy();
  expect(within(second.container).getByText(/另一页面可能已经发送/)).toBeTruthy();
  await act(async () => { pending.resolve(response(snapshot("A"))); });
  await waitFor(() => expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(1));
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.requests[requestId]?.association).toBe("matched"));
  fireEvent.click(within(second.container).getByRole("button", { name: "复制原文并自行决定是否重新提问" }));
  expect((within(second.container).getByPlaceholderText("输入学习问题…") as HTMLInputElement).value).toBe("");
  expect(within(second.container).getByText(/本机内容已变化或无法读取/)).toBeTruthy();
  expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(1);
});
it("two controllers retain risk when linking fails but the owner posts", async () => {
  const pending = deferred<Response>(); let snapshots = 0;
  const fetcher = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return ++snapshots === 2 ? pending.promise : Promise.resolve(response({ ...snapshot("A"), view_state: { ...snapshot("A").view_state, draft: "" } }));
    if (url === "/api/chat") return Promise.resolve(response({}, 503));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  const originalSet = Storage.prototype.setItem;
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, key: string, value: string) { if (key.startsWith("studyagent:recovery:") && value.includes('"phase":"linked"')) throw Error("blocked"); originalSet.call(this, key, value); });
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "共享原文" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(snapshots).toBe(2));
  vi.resetModules(); const isolatedStore = (await import("../store/workspace")).workspaceStore; const isolatedController = (await import("../store/workspaceController")).workspaceController;
  expect(isolatedStore.startAccount(1, "A")).toBe(true); isolatedStore.ensureSessionBucket("A"); isolatedStore.setActiveSession("A"); await isolatedController.loadSession("A");
  const cached = isolatedStore.getSnapshot().buckets.A.preparedCandidates[0]; expect(cached.phase).toBe("prepared");
  await act(async () => { pending.resolve(response(snapshot("A"))); });
  await waitFor(() => expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(1));
  expect(isolatedStore.getSnapshot().buckets.A.acknowledgedPreparations).toHaveLength(0);
  expect(isolatedStore.getSnapshot().buckets.A.draft).toBe("");
  isolatedController.acknowledgePreparedRisk("A", cached);
  expect(isolatedStore.getSnapshot().buckets.A.draft).toBe("共享原文");
  expect(isolatedStore.getSnapshot().buckets.A.preparedCandidates).toHaveLength(1);
  expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(1);
});
it("two providers keep the duplication warning when linking fails before the owner sends", async () => {
  const pending = deferred<Response>(); let snapshots = 0;
  const fetcher = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return ++snapshots === 2 ? pending.promise : Promise.resolve(response({ ...snapshot("A"), view_state: { ...snapshot("A").view_state, draft: "" } }));
    if (url === "/api/chat") return Promise.resolve(response({}, 503));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); const first = mount("/chat/A"); await within(first.container).findByText("历史A");
  const originalSet = Storage.prototype.setItem;
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, key: string, value: string) { if (key.startsWith("studyagent:recovery:") && value.includes('"phase":"linked"')) throw new Error("blocked"); originalSet.call(this, key, value); });
  fireEvent.change(within(first.container).getByPlaceholderText("输入学习问题…"), { target: { value: "两页共享原文" } });
  fireEvent.submit(within(first.container).getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(snapshots).toBe(2));
  vi.resetModules();
  const SecondApp = (await import("../App")).default;
  const SecondAuthProvider = (await import("../store/auth")).AuthProvider;
  const second = render(<SecondAuthProvider><MemoryRouter initialEntries={["/chat/A"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><SecondApp /></MemoryRouter></SecondAuthProvider>);
  expect(await within(second.container).findByText("两页共享原文")).toBeTruthy();
  await act(async () => { pending.resolve(response(snapshot("A"))); });
  await waitFor(() => expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(1));
  expect(within(second.container).getByText(/重新提问可能产生重复回复/)).toBeTruthy();
  expect((within(second.container).getByRole("button", { name: "发送" }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(within(second.container).getByRole("button", { name: "复制原文并自行决定是否重新提问" }));
  expect((within(second.container).getByPlaceholderText("输入学习问题…") as HTMLInputElement).value).toBe("两页共享原文");
  expect(createLocalRecovery(localStorage, "reader").listResult(1, "A", "prepared").candidates).toHaveLength(1);
  expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(1);
});
it("invalidates the account on 401 and retains a loss warning when request backup fails", async () => {
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url === "/api/chat") return Promise.resolve(response({ detail: "expired" }, 401));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  const original = Storage.prototype.setItem;
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, key: string, value: string) { if (key.startsWith("studyagent:recovery:")) throw Error("unavailable"); return original.call(this, key, value); });
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "未确认内容" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(localStorage.getItem("studyagent_token")).toBeNull());
  expect(workspaceStore.getSnapshot().account.userId).toBeNull();
  expect(workspaceStore.recoveryWarning()).toBe(true);
});
it("does not post when another authoritative request starts during preparation", async () => {
  const pending = deferred<Response>(); let snapshots = 0;
  const fetcher = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return ++snapshots === 2 ? pending.promise : Promise.resolve(response(snapshot("A")));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "本页问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(snapshots).toBe(2));
  const ticket = workspaceStore.captureTicket();
  act(() => workspaceStore.mergeRequest(ticket, { user_id: 1, session_id: "A", request_id: "other", profile_id: "p1", active_node_id: null, request_payload: { message: "其他问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "running", lease_until: null, lease_expired: false, error_code: null, response_json: null, created_at: "", updated_at: "" }));
  await act(async () => { pending.resolve(response(snapshot("A"))); });
  expect(fetcher.mock.calls.some(([url]) => url === "/api/chat")).toBe(false);
  expect(workspaceStore.getSnapshot().buckets.A.activityGate).toBe("uncertain");
});
it("keeps the old account and unresolved request when account-switch backup fails", async () => {
  const pending = deferred<Response>();
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A")));
    if (url === "/api/chat") return pending.promise;
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "原账号未确认" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(Object.keys(workspaceStore.getSnapshot().buckets.A.localRequests)).toHaveLength(1));
  const original = Storage.prototype.setItem;
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, key: string, value: string) { if (key.startsWith("studyagent:recovery:")) throw Error("unavailable"); return original.call(this, key, value); });
  let changed = true; act(() => { changed = workspaceStore.startAccount(2, "B"); });
  expect(changed).toBe(false); expect(workspaceStore.getSnapshot().account.userId).toBe(1);
  expect(Object.keys(workspaceStore.getSnapshot().buckets.A.localRequests)).toHaveLength(1);
  await act(async () => { pending.resolve(response({}, 503)); });
});
it.each(["first page", "after one page"])("keeps activity and profile when history bridging fails: %s", async failurePoint => {
  const old = { id: 10, turn_index: 0, role: "assistant", content: "旧历史", created_at: null };
  const newest = { id: 20, turn_index: 1, role: "assistant", content: "新历史", created_at: null };
  const middle = { id: 15, turn_index: 1, role: "user", content: "临时桥接页", created_at: null };
  const running = { user_id: 1, session_id: "A", request_id: "active", profile_id: "p1", active_node_id: null, request_payload: { message: "进行中的问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "running", lease_until: null, lease_expired: false, error_code: null, response_json: null, created_at: "", updated_at: "" };
  let count = 0; let bridgeFails = true;
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") return Promise.resolve(response({ ...ws, version: 1 }));
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++count === 1 ? { ...snapshot("A"), messages: { items: [old], next_cursor: "old-cursor" } } : { ...snapshot("A"), session: { ...session("A"), active_request_id: "active" }, profile: { ...profile(), revision: 2, name: "新画像" }, pending_requests: [running], messages: { items: [newest], next_cursor: "bridge" } }));
    if (url.includes("/A/messages?") && url.includes("bridge-next")) return Promise.resolve(bridgeFails ? response({}, 503) : response({ items: [old], next_cursor: "old-cursor" }));
    if (url.includes("/A/messages?") && url.includes("bridge")) return Promise.resolve(failurePoint === "after one page" ? response({ items: [middle], next_cursor: "bridge-next" }) : bridgeFails ? response({}, 503) : response({ items: [old], next_cursor: "old-cursor" }));
    if (url.startsWith("/api/sessions/B/snapshot")) return Promise.resolve(response(snapshot("B")));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("旧历史");
  fireEvent.click(screen.getByRole("button", { name: "会话 B" })); await screen.findByText("历史B");
  fireEvent.click(screen.getByRole("button", { name: "会话 A" }));
  await screen.findByRole("button", { name: "重新同步历史" });
  const state = workspaceStore.getSnapshot().buckets.A;
  expect(screen.getByText("旧历史")).toBeTruthy(); expect(screen.queryByText("新历史")).toBeNull();
  expect(screen.queryByText("临时桥接页")).toBeNull();
  expect(state.nextMessageCursor).toBe("old-cursor");
  expect(state.profile?.name).toBe("新画像");
  expect(state.pendingRequests.some(item => item.request_id === "active" && item.status === "running")).toBe(true);
  expect((screen.getByRole("textbox") as HTMLTextAreaElement).disabled).toBe(true);
  expect(fetcher.mock.calls.filter(([url, init]) => String(url) === "/api/chat" && init?.method === "POST")).toHaveLength(0);
  bridgeFails = false;
  fireEvent.click(screen.getByRole("button", { name: "重新同步历史" }));
  await screen.findByText("新历史");
  expect(screen.getByText("旧历史")).toBeTruthy();
  expect(workspaceStore.getSnapshot().buckets.A.nextMessageCursor).toBe("old-cursor");
  expect(workspaceStore.getSnapshot().buckets.A.historySyncError).toBeNull();
});
it("preserves the unassociated request but updates independent fields on continue bridge failure", async () => {
  const old = { id: 10, turn_index: 0, role: "assistant", content: "继续前历史", created_at: null };
  const newest = { id: 20, turn_index: 1, role: "assistant", content: "未连接历史", created_at: null };
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "旧问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  const running = { ...completed, request_id: "other", status: "running" as const, response_json: null };
  let count = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++count === 1 ? { ...snapshot("A"), messages: { items: [old], next_cursor: "old" } } : { ...snapshot("A"), session: { ...session("A"), state_version: 1, active_request_id: "other" }, profile: { ...profile(), revision: 2, name: "继续时新画像" }, pending_requests: [running], messages: { items: [newest], next_cursor: "bridge" } }));
    if (url.includes("/A/messages?") && url.includes("bridge")) return Promise.resolve(response({}, 503));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("继续前历史"); const ticket = workspaceStore.captureTicket();
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, association: "unassociated" } }, request: { id: "r1", status: "unassociated", attempt: 1, error: null, sequence: 1 } })); });
  fireEvent.click(screen.getByRole("button", { name: "保留未关联记录并继续" }));
  await screen.findByRole("button", { name: "重新同步历史" });
  const state = workspaceStore.getSnapshot().buckets.A;
  expect(state.nextMessageCursor).toBe("old"); expect(state.requests.r1.association).toBe("unassociated"); expect(state.continuedUnassociated.r1).toBeUndefined();
  expect(state.profile?.name).toBe("继续时新画像"); expect(state.pendingRequests.some(item => item.request_id === "other" && item.status === "running")).toBe(true);
  expect(screen.getByText("继续前历史")).toBeTruthy(); expect(screen.queryByText("未连接历史")).toBeNull();
});
it("does not publish a bridge-failure snapshot after bridge 401 invalidates the account", async () => {
  let count = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++count === 1 ? { ...snapshot("A"), messages: { ...snapshot("A").messages, next_cursor: "old" } } : { ...snapshot("A"), profile: { ...profile(), revision: 2, name: "不应发布的画像" }, messages: { items: [{ id: 99, turn_index: 1, role: "assistant", content: "不应发布", created_at: null }], next_cursor: "bridge" } }));
    if (url.includes("/A/messages?") && url.includes("bridge")) return Promise.resolve(response({ detail: "expired" }, 401));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  await act(async () => { await workspaceController.loadSession("A"); });
  expect(workspaceStore.getSnapshot().account.userId).toBeNull();
  const after = workspaceStore.getSnapshot().buckets.A;
  expect(after?.profile ?? null).toBeNull(); expect(after?.historySyncError ?? null).toBeNull(); expect(after?.messages ?? []).toEqual([]);
  expect(localStorage.getItem("studyagent_token")).toBeNull();
});
it("does not apply an expired bridge observation over newer activity", async () => {
  const bridge = deferred<Response>(); let count = 0;
  const running = { user_id: 1, session_id: "A", request_id: "newer", profile_id: "p1", active_node_id: null, request_payload: { message: "新活动", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "running" as const, lease_until: null, lease_expired: false, error_code: null, response_json: null, created_at: "", updated_at: "" };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++count === 1 ? { ...snapshot("A"), messages: { ...snapshot("A").messages, next_cursor: "old" } } : count === 2 ? { ...snapshot("A"), messages: { items: [{ id: 99, turn_index: 1, role: "assistant", content: "断链", created_at: null }], next_cursor: "bridge" } } : { ...snapshot("A"), session: { ...session("A"), active_request_id: "newer" }, pending_requests: [running], messages: { ...snapshot("A").messages, next_cursor: "old" } }));
    if (url.includes("/A/messages?") && url.includes("bridge")) return bridge.promise;
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  let old!: Promise<void>; act(() => { old = workspaceController.loadSession("A"); });
  await waitFor(() => expect(count).toBe(2));
  await act(async () => { await workspaceController.loadSession("A"); });
  await act(async () => { bridge.resolve(response({}, 503)); await old; });
  const state = workspaceStore.getSnapshot().buckets.A;
  expect(state.session?.active_request_id).toBe("newer"); expect(state.pendingRequests.some(item => item.request_id === "newer" && item.status === "running")).toBe(true);
  expect(state.historySyncError).toBeNull(); expect(state.nextMessageCursor).toBe("old");
});
it.each(["completed", "failed lookup", "not found", "running"])("reconciles a superseded sent-request lookup: %s", async outcome => {
  const delayed = deferred<Response>(); let sent: Record<string, unknown> | undefined; let gets = 0; let snapshots = 0;
  const user = { id: 10, turn_index: 1, role: "user", content: "竞态问题", created_at: null };
  const answer = { id: 11, turn_index: 1, role: "assistant", content: "竞态答案", created_at: null };
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ ...ws, last_session_id: body.last_session_id, version: body.expected_version + 1 })); }
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/B/snapshot")) return Promise.resolve(response(snapshot("B")));
    if (url.startsWith("/api/sessions/A/snapshot")) { snapshots++; return Promise.resolve(response(snapshots <= 3 ? { ...snapshot("A"), session: { ...session("A"), next_turn_index: 1 } } : { ...snapshot("A"), session: { ...session("A"), state_version: 1, next_turn_index: 2 }, messages: { items: [...snapshot("A").messages.items, user, answer], next_cursor: null } })); }
    if (url === "/api/chat") { sent = JSON.parse(String(init?.body)); return Promise.resolve(response({ session_id: "A", request_id: sent!.request_id, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "竞态答案" })); }
    if (url.includes("/requests/")) { gets++; if (gets === 1) return delayed.promise; if (outcome === "failed lookup" || outcome === "not found") return Promise.resolve(response({}, outcome === "not found" ? 404 : 503)); return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: sent!.request_id, profile_id: "p1", active_node_id: null, request_payload: { message: "竞态问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: outcome === "running" ? "running" : "completed", lease_until: null, lease_expired: false, error_code: null, response_json: outcome === "running" ? null : { session_id: "A", request_id: sent!.request_id, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "竞态答案" }, created_at: "", updated_at: "" })); }
    if (url.startsWith("/api/sessions/A/messages?")) return Promise.resolve(response({ items: [user, answer], next_cursor: null }));
    if (url.endsWith("/view-state")) return Promise.resolve(response({ draft: "", reading_anchor: null, version: 1, updated_at: null }));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "竞态问题" } });
  fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(gets).toBe(1));
  fireEvent.click(screen.getByRole("button", { name: "会话 B" })); await screen.findByText("历史B");
  fireEvent.click(screen.getByRole("button", { name: "会话 A" })); await screen.findByText("历史A");
  await act(async () => { delayed.resolve(response({ user_id: 1, session_id: "A", request_id: sent!.request_id, profile_id: "p1", active_node_id: null, request_payload: { message: "竞态问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: sent!.request_id, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "竞态答案" }, created_at: "", updated_at: "" })); });
  if (outcome === "completed") {
    await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.requests[String(sent!.request_id)]?.association).toBe("matched"), { timeout: 1500 });
    expect(screen.getByText("竞态答案")).toBeTruthy();
  } else if (outcome === "running") {
    await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.request.status).toBe("running"));
    expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).disabled).toBe(true);
  } else {
    await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.request.error).toBe("原请求尚未确认，请重新查询"));
    expect(workspaceStore.getSnapshot().buckets.A.request.status).toBe("unknown");
    expect(workspaceStore.getSnapshot().buckets.A.localRequests[String(sent!.request_id)]).toBeTruthy();
    expect(getLocalRecovery().listResult(1, "A", "prepared").candidates.some(item => item.requestId === sent!.request_id)).toBe(true);
    expect(screen.getByRole("button", { name: "重新查询" })).toBeTruthy();
  }
  expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(1);
});
it("does not let automatic request recovery steal a newer in-flight activity observation", async () => {
  const firstGet = deferred<Response>(); const newerSnapshot = deferred<Response>(); let snapshots = 0; let sent: Record<string, unknown> | undefined;
  const running = { user_id: 1, session_id: "A", request_id: "other", profile_id: "p1", active_node_id: null, request_payload: { message: "其他活动", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "running", lease_until: null, lease_expired: false, error_code: null, response_json: null, created_at: "", updated_at: "" };
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ ...ws, last_session_id: body.last_session_id, version: body.expected_version + 1 })); }
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/B/snapshot")) return Promise.resolve(response(snapshot("B")));
    if (url.startsWith("/api/sessions/A/snapshot")) { snapshots++; return snapshots === 3 ? newerSnapshot.promise : Promise.resolve(response(snapshot("A"))); }
    if (url === "/api/chat") { sent = JSON.parse(String(init?.body)); return Promise.resolve(response({ session_id: "A", request_id: sent!.request_id, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" })); }
    if (url.includes("/requests/")) return firstGet.promise;
    if (url.endsWith("/view-state")) return Promise.resolve(response({ draft: "", reading_anchor: null, version: 1, updated_at: null }));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "原请求" } }); fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(fetcher.mock.calls.some(([url]) => String(url).includes("/requests/"))).toBe(true));
  fireEvent.click(screen.getByRole("button", { name: "会话 B" })); await screen.findByText("历史B");
  fireEvent.click(screen.getByRole("button", { name: "会话 A" })); await waitFor(() => expect(snapshots).toBe(3));
  await act(async () => { firstGet.resolve(response({ ...running, request_id: sent!.request_id })); });
  await act(async () => { newerSnapshot.resolve(response({ ...snapshot("A"), session: { ...session("A"), active_request_id: "other" }, pending_requests: [running] })); });
  await screen.findByText("历史A");
  expect(workspaceStore.getSnapshot().buckets.A.session?.active_request_id).toBe("other");
  expect(workspaceStore.getSnapshot().buckets.A.pendingRequests.some(item => item.request_id === "other" && item.status === "running")).toBe(true);
  expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(1);
});
it("keeps a newer activity check when a still-current load has a stale bridge observation", async () => {
  const bridge = deferred<Response>(); let snapshots = 0;
  const running = { user_id: 1, session_id: "A", request_id: "newer", profile_id: "p1", active_node_id: null, request_payload: { message: "较新活动", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "running", lease_until: null, lease_expired: false, error_code: null, response_json: null, created_at: "", updated_at: "" };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots === 1 ? { ...snapshot("A"), messages: { ...snapshot("A").messages, next_cursor: "old" } } : snapshots === 2 ? { ...snapshot("A"), profile: { ...profile(), revision: 2, name: "独立画像" }, messages: { items: [{ id: 99, turn_index: 1, role: "assistant", content: "未连接", created_at: null }], next_cursor: "bridge" } } : { ...snapshot("A"), session: { ...session("A"), active_request_id: "newer" }, pending_requests: [running] }));
    if (url.includes("/A/messages?") && url.includes("bridge")) return bridge.promise;
    if (url.endsWith("/requests/newer")) return Promise.resolve(response(running));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  let load!: Promise<void>; act(() => { load = workspaceController.loadSession("A"); }); await waitFor(() => expect(snapshots).toBe(2));
  await act(async () => { await workspaceController.recheckSessionActivity("A"); });
  await act(async () => { bridge.resolve(response({}, 503)); await load; });
  const state = workspaceStore.getSnapshot().buckets.A;
  expect(state.profile?.name).toBe("独立画像"); expect(state.pendingRequests.some(item => item.request_id === "newer" && item.status === "running")).toBe(true);
  expect(state.activityGate).not.toBe("clear"); expect(state.historySyncError).toBeTruthy(); expect(state.nextMessageCursor).toBe("old");
});
it("retries a failed continue bridge without losing its older history cursor", async () => {
  const old = { id: 10, turn_index: 0, role: "assistant", content: "继续旧历史", created_at: null };
  const added = { id: 20, turn_index: 1, role: "assistant", content: "继续新增历史", created_at: null };
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "旧问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  let snapshots = 0; let fail = true;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots === 1 ? { ...snapshot("A"), messages: { items: [old], next_cursor: "old" } } : { ...snapshot("A"), session: { ...session("A"), state_version: 1 }, messages: { items: [added], next_cursor: "bridge" } }));
    if (url.includes("/A/messages?") && url.includes("bridge")) return Promise.resolve(fail ? response({}, 503) : response({ items: [old], next_cursor: "old" }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("继续旧历史"); const ticket = workspaceStore.captureTicket();
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, association: "unassociated" } }, request: { id: "r1", status: "unassociated", attempt: 1, error: null, sequence: 1 } })); });
  fireEvent.click(screen.getByRole("button", { name: "保留未关联记录并继续" })); await screen.findByRole("button", { name: "重新同步历史" });
  fail = false; fireEvent.click(screen.getByRole("button", { name: "保留未关联记录并继续" }));
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.continuedUnassociated.r1).toBe(1));
  expect(screen.getByText("继续旧历史")).toBeTruthy(); expect(screen.getByText("继续新增历史")).toBeTruthy();
  expect(workspaceStore.getSnapshot().buckets.A.nextMessageCursor).toBe("old"); expect(workspaceStore.getSnapshot().buckets.A.historySyncError).toBeNull();
});
it.each(["attempt", "account"])("drops a continue bridge failure after %s changes", async changed => {
  const page = deferred<Response>(); let snapshots = 0; let requested = false;
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "旧问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots === 1 ? { ...snapshot("A"), messages: { ...snapshot("A").messages, next_cursor: "old" } } : snapshots === 2 ? { ...snapshot("A"), profile: { ...profile(), revision: 2, name: "迟到画像" }, session: { ...session("A"), state_version: 1 }, messages: { items: [{ id: 99, turn_index: 1, role: "assistant", content: "迟到历史", created_at: null }], next_cursor: "bridge" } } : snapshot("A")));
    if (url.includes("/A/messages?") && url.includes("bridge")) { requested = true; return page.promise; }
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A"); const ticket = workspaceStore.captureTicket();
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, association: "unassociated" } }, request: { id: "r1", status: "unassociated", attempt: 1, error: null, sequence: 1 } })); });
  let continuing!: Promise<void>; act(() => { continuing = workspaceController.continueUnassociated("A", "r1"); }); await waitFor(() => expect(requested).toBe(true));
  if (changed === "attempt") act(() => { workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, snapshot: { ...value.requests.r1.snapshot, attempt: 2 } } }, request: { ...value.request, attempt: 2, sequence: 2, error: null } })); });
  else act(() => { workspaceStore.startAccount(1, "A", true); workspaceStore.ensureSessionBucket("A"); });
  await act(async () => { page.resolve(response({}, 503)); await continuing; });
  const state = workspaceStore.getSnapshot().buckets.A;
  expect(state.profile?.name).not.toBe("迟到画像"); expect(state.historySyncError).toBeNull(); expect(state.request.error).toBeNull();
  if (changed === "attempt") expect(state.request.attempt).toBe(2);
});
it("does not show an old continue bridge error after a newer load succeeds", async () => {
  const bridge = deferred<Response>(); let snapshots = 0; let requested = false;
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "旧问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots === 2 ? { ...snapshot("A"), session: { ...session("A"), state_version: 1 }, messages: { items: [{ id: 99, turn_index: 1, role: "assistant", content: "旧断链页", created_at: null }], next_cursor: "bridge" } } : { ...snapshot("A"), messages: { ...snapshot("A").messages, next_cursor: "old" } }));
    if (url.includes("/A/messages?") && url.includes("bridge")) { requested = true; return bridge.promise; }
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A"); const ticket = workspaceStore.captureTicket();
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, association: "unassociated" } }, request: { id: "r1", status: "unassociated", attempt: 1, error: null, sequence: 1 } })); });
  fireEvent.click(screen.getByRole("button", { name: "保留未关联记录并继续" })); await waitFor(() => expect(requested).toBe(true));
  await act(async () => { await workspaceController.loadSession("A"); });
  expect(screen.getByText("历史A")).toBeTruthy(); expect(workspaceStore.getSnapshot().buckets.A.historySyncError).toBeNull();
  await act(async () => { bridge.resolve(response({}, 503)); });
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.request.error).toBeNull());
  expect(workspaceStore.getSnapshot().buckets.A.historySyncError).toBeNull();
  expect(screen.queryByRole("button", { name: "重新同步历史" })).toBeNull();
  expect(workspaceStore.getSnapshot().buckets.A.nextMessageCursor).toBe("old");
});
it.each([["success", "running"], ["bridge failure", "running"], ["success", "idle"], ["bridge failure", "idle"]])( "keeps session and teaching versions together after a newer activity check: %s / %s", async (history, activity) => {
  const olderLoad = deferred<Response>(); let count = 0;
  const running = { user_id: 1, session_id: "A", request_id: "new-activity", profile_id: "p1", active_node_id: null, request_payload: { message: "较新活动", profile_id: "p1", active_node_id: null, base_state_version: 1 }, base_state_version: 1, attempt: 1, status: "running", lease_until: null, lease_expired: false, error_code: null, response_json: null, created_at: "", updated_at: "" };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) { count++; return count === 2 ? olderLoad.promise : Promise.resolve(response(count === 1 ? { ...snapshot("A"), session: { ...session("A"), title: "已确认标题", created_at: "created-old", updated_at: "updated-old", state_version: 1, next_turn_index: 1 }, teaching_state: { step: "v1" }, messages: { ...snapshot("A").messages, next_cursor: "old" } } : { ...snapshot("A"), session: { ...session("A"), state_version: 1, next_turn_index: 1, active_request_id: activity === "running" ? "new-activity" : null }, pending_requests: activity === "running" ? [running] : [] })); }
    if (url.endsWith("/requests/new-activity")) return Promise.resolve(response(running));
    if (url.includes("/A/messages?") && url.includes("bridge")) return Promise.resolve(response({}, 503));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  let pending!: Promise<void>; act(() => { pending = workspaceController.loadSession("A"); }); await waitFor(() => expect(count).toBe(2));
  await act(async () => { await workspaceController.recheckSessionActivity("A"); });
  expect(workspaceStore.getSnapshot().buckets.A.pendingRequests.some(item => item.request_id === "new-activity")).toBe(activity === "running");
  await act(async () => { olderLoad.resolve(response({ ...snapshot("A"), session: { ...session("A"), title: "旧活动观察标题", created_at: "other-created", updated_at: "other-updated", state_version: 2, active_node_id: "node-v2", next_turn_index: 2, active_request_id: "obsolete" }, teaching_state: { step: "v2" }, teaching_state_source: "legacy", messages: history === "success" ? { ...snapshot("A").messages, next_cursor: "old" } : { items: [{ id: 99, turn_index: 2, role: "assistant", content: "断链内容", created_at: null }], next_cursor: "bridge" } })); await pending; });
  const state = workspaceStore.getSnapshot().buckets.A;
  expect(state.session?.state_version).toBe(state.teachingStateVersion); expect(state.session?.state_version).toBe(2);
  expect(state.session?.active_node_id).toBe("node-v2"); expect(state.session?.next_turn_index).toBe(2);
  expect(state.session?.session_id).toBe("A"); expect(state.session?.user_id).toBe(1); expect(state.session?.profile_id).toBe("p1"); expect(state.session?.title).toBe("已确认标题"); expect(state.session?.created_at).toBe("created-old"); expect(state.session?.updated_at).toBe("updated-old");
  expect(state.teachingState).toEqual({ step: "v2" }); expect(state.teachingStateSource).toBe("legacy");
  expect(state.session?.active_request_id).not.toBe("obsolete"); expect(state.pendingRequests.some(item => item.request_id === "new-activity")).toBe(activity === "running"); if (activity === "running") expect(state.activityGate).not.toBe("clear");
  expect(state.nextMessageCursor).toBe("old"); expect(screen.getByText("历史A")).toBeTruthy();
  if (history === "bridge failure") expect(state.historySyncError).toBeTruthy();
});
it.each(["replaced", "newer attempt", "newer attempt error", "newer completed", "newer completed error", "newer matched", "foreign identical", "foreign conflicting", "foreign baseline", "foreign linked"])("protects a %s during automatic original-request recheck", async change => {
  const first = deferred<Response>(); const second = deferred<Response>(); let gets = 0; let snapshots = 0; let sent: Record<string, unknown> | undefined;
  const user = { id: 10, turn_index: 1, role: "user", content: "复核问题", created_at: null }; const answer = { id: 11, turn_index: 1, role: "assistant", content: "复核答案", created_at: null };
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ ...ws, last_session_id: body.last_session_id, version: body.expected_version + 1 })); }
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/B/snapshot")) return Promise.resolve(response(snapshot("B")));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots <= 3 ? { ...snapshot("A"), session: { ...session("A"), next_turn_index: 1 } } : { ...snapshot("A"), session: { ...session("A"), state_version: 1, next_turn_index: 2 }, messages: { items: [...snapshot("A").messages.items, user, answer], next_cursor: null } }));
    if (url === "/api/chat") { sent = JSON.parse(String(init?.body)); return Promise.resolve(response({ session_id: "A", request_id: sent!.request_id, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "复核答案" })); }
    if (url.includes("/requests/")) return ++gets === 1 ? first.promise : second.promise;
    if (url.endsWith("/view-state")) return Promise.resolve(response({ draft: "", reading_anchor: null, version: 1, updated_at: null }));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "复核问题" } }); fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(gets).toBe(1)); fireEvent.click(screen.getByRole("button", { name: "会话 B" })); await screen.findByText("历史B"); fireEvent.click(screen.getByRole("button", { name: "会话 A" })); await screen.findByText("历史A");
  const requestId = String(sent!.request_id); const responseData = { user_id: 1, session_id: "A", request_id: requestId, profile_id: "p1", active_node_id: null, request_payload: { message: "复核问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: requestId, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "复核答案" }, created_at: "", updated_at: "" };
  await act(async () => { first.resolve(response(responseData)); }); await waitFor(() => expect(gets).toBe(2));
  const ticket = workspaceStore.captureTicket(); const local = workspaceStore.getSnapshot().buckets.A.localRequests[requestId]; let foreignId = "";
  if (change === "replaced") act(() => { workspaceStore.patchBucket(ticket, "A", value => ({ ...value, request: { id: "replacement", status: "running", attempt: 1, error: null, sequence: value.request.sequence + 1 } })); });
  else if (change.startsWith("newer")) act(() => { workspaceStore.mergeRequest(ticket, change.startsWith("newer attempt") ? { ...responseData, attempt: 2, status: "running", response_json: null } : { ...responseData, attempt: 2, response_json: { ...responseData.response_json, attempt: 2 } }); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, ...(change === "newer matched" ? { requests: { ...value.requests, [requestId]: { ...value.requests[requestId], association: "matched" as const } } } : {}), request: { ...value.request, status: change.startsWith("newer attempt") ? "running" : change === "newer matched" ? "completed" : "pending_messages", attempt: 2 } })); });
  else {
    const payload = change === "foreign conflicting" ? { ...local.payload, message: "不同的问题" } : local.payload;
    const baseline = change === "foreign baseline" && local.baseline && typeof local.baseline === "object" ? { ...local.baseline, expected_turn_index: local.baseline.expected_turn_index + 1 } : local.baseline;
    const writer = createLocalRecovery(localStorage, "other-writer");
    const other = change === "foreign linked" ? writer.writePrepared(1, "A", "foreign-prep", { text: "复核问题", sequence: 1, phase: "linked", requestId, payload, baseline }) : writer.writeRequest(1, "A", requestId, { payload, baseline }); if (!other.ok) throw Error("foreign write failed"); foreignId = other.candidate.writeId;
  }
  await act(async () => { second.resolve(change.endsWith("error") ? response({}, 503) : response(responseData)); });
  if (change === "replaced") { expect(workspaceStore.getSnapshot().buckets.A.request.id).toBe("replacement"); expect(workspaceStore.getSnapshot().buckets.A.requests[requestId]).toBeUndefined(); }
  else if (change.startsWith("newer")) { expect(workspaceStore.getSnapshot().buckets.A.requests[requestId].snapshot.attempt).toBe(2); expect(workspaceStore.getSnapshot().buckets.A.request.status).toBe(change.startsWith("newer attempt") ? "running" : change === "newer matched" ? "completed" : "pending_messages"); if (change === "newer matched") expect(workspaceStore.getSnapshot().buckets.A.requests[requestId].association).toBe("matched"); }
  else { await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.requests[requestId]?.association).toBe("matched")); expect(createLocalRecovery(localStorage, "reader").list(1, "A", change === "foreign linked" ? "prepared" : "request").some(item => item.writeId === foreignId)).toBe(true); if (change === "foreign conflicting" || change === "foreign baseline") { expect((screen.getByRole("button", { name: "发送" }) as HTMLButtonElement).disabled).toBe(true); expect(screen.getByText("上次请求结果待确认")).toBeTruthy(); } }
  expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(1);
});
it("keeps the teaching group and asks for recheck on equal-version teaching conflict", async () => {
  let count = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++count === 1 ? { ...snapshot("A"), session: { ...session("A"), state_version: 1, next_turn_index: 1, active_node_id: "node-1" }, teaching_state: { step: "v1" } } : { ...snapshot("A"), session: { ...session("A"), state_version: count >= 4 ? 2 : 1, next_turn_index: 2, active_node_id: "node-2" }, teaching_state: { step: "conflict" } }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A"); await act(async () => { await workspaceController.loadSession("A"); });
  const state = workspaceStore.getSnapshot().buckets.A;
  expect(state.session?.active_node_id).toBe("node-1"); expect(state.session?.next_turn_index).toBe(1); expect(state.teachingState).toEqual({ step: "v1" }); expect(state.teachingStateVersion).toBe(1);
  expect(state.activityGate).not.toBe("clear"); expect(screen.getByRole("button", { name: "重新查询会话状态" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "重新查询会话状态" }));
  await waitFor(() => expect(count).toBe(3));
  expect(workspaceStore.getSnapshot().buckets.A.activityGate).not.toBe("clear");
  expect((screen.getByRole("button", { name: "发送" }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "重新查询会话状态" }));
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.teachingStateVersion).toBe(2));
  expect(workspaceStore.getSnapshot().buckets.A.activityGate).not.toBe("clear");
  fireEvent.click(screen.getByRole("button", { name: "重新查询会话状态" }));
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.activityGate).toBe("clear"));
});
it.each(["state_version", "next_turn_index"])("keeps the teaching group when the incoming %s is invalid", async field => {
  let count = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++count === 1 ? { ...snapshot("A"), session: { ...session("A"), state_version: 1, next_turn_index: 1 }, teaching_state: { step: "v1" } } : { ...snapshot("A"), session: { ...session("A"), state_version: 2, next_turn_index: 2, [field]: -1 }, teaching_state: { step: "invalid" } }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A"); await act(async () => { await workspaceController.loadSession("A"); });
  const state = workspaceStore.getSnapshot().buckets.A;
  expect(state.session?.state_version).toBe(1); expect(state.session?.next_turn_index).toBe(1); expect(state.teachingState).toEqual({ step: "v1" }); expect(state.activityGate).not.toBe("clear");
});
it("keeps teaching and session together when completed-message confirmation meets newer activity", async () => {
  const page = deferred<Response>(); let count = 0;
  const user = { id: 20, turn_index: 2, role: "user", content: "确认问题", created_at: null }; const answer = { id: 21, turn_index: 2, role: "assistant", content: "确认答案", created_at: null };
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "确认问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "确认答案" }, created_at: "", updated_at: "" };
  const running = { ...completed, request_id: "other", status: "running" as const, response_json: null };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/messages?")) return page.promise;
    if (url.endsWith("/requests/other")) return Promise.resolve(response(running));
    if (url.startsWith("/api/sessions/A/snapshot")) { count++; return Promise.resolve(response(count === 1 ? snapshot("A") : count === 2 ? { ...snapshot("A"), session: { ...session("A"), state_version: 2, next_turn_index: 3, active_node_id: "v2" }, teaching_state: { step: "v2" }, messages: { items: [], next_cursor: "older" } } : { ...snapshot("A"), session: { ...session("A"), active_request_id: "other" }, pending_requests: [running] })); }
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A"); const ticket = workspaceStore.captureTicket();
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, baseline: { owner_user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 2, provenance: "before_submit", snapshot_sequence: 1 } } }, request: { id: "r1", status: "pending_messages", attempt: 1, error: null, sequence: 1 } })); });
  let confirming!: Promise<void>; act(() => { confirming = workspaceController.confirmCompleted("A", "r1", ticket); }); await waitFor(() => expect(count).toBe(2));
  await act(async () => { await workspaceController.recheckSessionActivity("A"); });
  await act(async () => { page.resolve(response({ items: [user, answer], next_cursor: null })); await confirming; });
  const state = workspaceStore.getSnapshot().buckets.A;
  expect(state.requests.r1.association).toBe("matched"); expect(state.session?.state_version).toBe(state.teachingStateVersion); expect(state.session?.state_version).toBe(2); expect(state.session?.active_node_id).toBe("v2"); expect(state.session?.next_turn_index).toBe(3);
  expect(state.pendingRequests.some(item => item.request_id === "other")).toBe(true); expect(state.activityGate).not.toBe("clear");
});
it("does not continue with conflicting equal-version teaching fields", async () => {
  let count = 0;
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++count === 1 ? { ...snapshot("A"), session: { ...session("A"), state_version: 1, active_node_id: "node-1", next_turn_index: 1 }, teaching_state: { step: "v1" } } : { ...snapshot("A"), session: { ...session("A"), state_version: 1, active_node_id: "node-2", next_turn_index: 2 }, teaching_state: { step: "conflict" } }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A"); const ticket = workspaceStore.captureTicket();
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, association: "unassociated" } }, request: { id: "r1", status: "unassociated", attempt: 1, error: null, sequence: 1 } })); });
  fireEvent.click(screen.getByRole("button", { name: "保留未关联记录并继续" }));
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.activityGate).toBe("uncertain"));
  const state = workspaceStore.getSnapshot().buckets.A;
  expect(state.continuedUnassociated.r1).toBeUndefined(); expect(state.request.status).toBe("unassociated");
  expect(state.session?.active_node_id).toBe("node-1"); expect(state.session?.next_turn_index).toBe(1); expect(state.teachingState).toEqual({ step: "v1" });
});
it("keeps a newer activity observation while reporting a still-current continue history failure", async () => {
  const bridge = deferred<Response>(); let snapshots = 0; let requested = false;
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "旧问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  const running = { ...completed, request_id: "other", status: "running" as const, response_json: null };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots === 1 ? { ...snapshot("A"), messages: { ...snapshot("A").messages, next_cursor: "old" } } : snapshots === 2 ? { ...snapshot("A"), session: { ...session("A"), state_version: 1 }, profile: { ...profile(), revision: 2, name: "新画像" }, messages: { items: [{ id: 99, turn_index: 1, role: "assistant", content: "未连接页", created_at: null }], next_cursor: "bridge" } } : { ...snapshot("A"), session: { ...session("A"), active_request_id: "other" }, pending_requests: [running] }));
    if (url.includes("/A/messages?") && url.includes("bridge")) { requested = true; return bridge.promise; }
    if (url.endsWith("/requests/other")) return Promise.resolve(response(running));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A"); const ticket = workspaceStore.captureTicket();
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, association: "unassociated" } }, request: { id: "r1", status: "unassociated", attempt: 1, error: "已有请求提示", sequence: 1 } })); });
  fireEvent.click(screen.getByRole("button", { name: "保留未关联记录并继续" })); await waitFor(() => expect(requested).toBe(true));
  await act(async () => { await workspaceController.recheckSessionActivity("A"); });
  await act(async () => { bridge.resolve(response({}, 503)); });
  await screen.findByRole("button", { name: "重新同步历史" });
  const state = workspaceStore.getSnapshot().buckets.A;
  expect(state.request.error).toBe("已有请求提示"); expect(state.profile?.name).toBe("新画像");
  expect(state.pendingRequests.some(item => item.request_id === "other" && item.status === "running")).toBe(true); expect(state.activityGate).not.toBe("clear");
  expect(state.historySyncError).toBeTruthy(); expect(state.nextMessageCursor).toBe("old"); expect(screen.getByText("历史A")).toBeTruthy();
});
it.each([1, 2, 3])( "does not mix a different profile into a loaded session at revision %s", async revision => {
  let count = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++count === 1 ? { ...snapshot("A"), profile: { ...profile(), revision: 2 }, messages: { ...snapshot("A").messages, next_cursor: "old" } } : { ...snapshot("A"), session: { ...session("A", "p2"), state_version: 1 }, profile: { ...profile("p2", "其他画像"), revision }, teaching_state: { wrong: true }, messages: { items: [{ id: 99, turn_index: 1, role: "assistant", content: "其他画像消息", created_at: null }], next_cursor: "old" } }));
    if (url.includes("/A/messages?")) return Promise.resolve(response({ items: snapshot("A").messages.items, next_cursor: "old" }));
    return Promise.resolve(response({}, 404));
  }));
  mount("/chat/A"); await screen.findByText("历史A");
  await act(async () => { await workspaceController.loadSession("A"); });
  const state = workspaceStore.getSnapshot().buckets.A;
  expect(state.session?.profile_id).toBe("p1"); expect(state.profile?.id).toBe("p1"); expect(state.teachingState).toBeNull(); expect(state.nextMessageCursor).toBe("old");
  expect(screen.getByText("历史A")).toBeTruthy(); expect(screen.queryByText("其他画像消息")).toBeNull(); expect(state.activityGate).not.toBe("clear");
  expect(screen.getByRole("button", { name: "重新查询会话状态" })).toBeTruthy();
});
it("keeps same-profile evidence from two sessions in the loaded store", async () => {
  const node = { id: "n1", profile_id: "p1", title: "节点", description: "", mastery: null, last_practiced_at: 0, practice_count: 0, rationale: "", revision: 0, archived: false };
  const evidence = (id: string, session_id: string) => ({ id, node_id: "archived", session_id, request_id: `r-${id}`, message_id: Number(id), score: 1, rationale: "", created_at: "2026-01-01" });
  const summary = { profile_revision: 0, nodes: [node], edges: [{ profile_id: "p1", from_node_id: "n1", to_node_id: "n1", type: "related", weight: 1, confidence: 1, source: "test" }], recent_evidence: [evidence("1", "A"), evidence("2", "B")], assessed_count: 0, total_count: 1, mastery_score: null, metric_kind: "assessed_mean", assessment_coverage: 0 };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => { const url = String(input); if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group)); if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response({ ...snapshot("A"), profile_summary: summary })); return Promise.resolve(response({}, 404)); }));
  mount("/chat/A"); await screen.findByText("历史A");
  expect(workspaceStore.getSnapshot().buckets.A.profileSummary?.recent_evidence.map(item => item.session_id)).toEqual(["A", "B"]);
});
it.each(["node", "edge", "request-user", "request-profile", "request-session"])("rejects a visibly inconsistent %s without contaminating a loaded session", async field => {
  let count = 0;
  const node = { id: "n1", profile_id: field === "node" ? "p2" : "p1", title: "节点", description: "", mastery: null, last_practiced_at: 0, practice_count: 0, rationale: "", revision: 0, archived: false };
  const edge = { profile_id: field === "edge" ? "p2" : "p1", from_node_id: "n1", to_node_id: "n1", type: "related", weight: 1, confidence: 1, source: "test" };
  const summary = { profile_revision: 1, nodes: [node], edges: [edge], recent_evidence: [], assessed_count: 0, total_count: 1, mastery_score: null, metric_kind: "assessed_mean", assessment_coverage: 0 };
  const request = { user_id: field === "request-user" ? 2 : 1, session_id: field === "request-session" ? "B" : "A", request_id: "bad", profile_id: field === "request-profile" ? "p2" : "p1", active_node_id: null, request_payload: { message: "坏请求", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "running", lease_until: null, lease_expired: false, error_code: null, response_json: null, created_at: "", updated_at: "" };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => { const url = String(input); if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group)); if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++count === 1 ? { ...snapshot("A"), messages: { ...snapshot("A").messages, next_cursor: "old" } } : { ...snapshot("A"), session: { ...session("A"), state_version: 1 }, profile: { ...profile(), revision: 1 }, profile_summary: summary, pending_requests: field.startsWith("request") ? [request] : [] })); return Promise.resolve(response({}, 404)); }));
  mount("/chat/A"); await screen.findByText("历史A"); await act(async () => { await workspaceController.loadSession("A"); });
  const state = workspaceStore.getSnapshot().buckets.A;
  expect(state.profileSummary).toBeNull(); expect(state.profile?.revision).toBe(0); expect(state.requests.bad).toBeUndefined(); expect(state.nextMessageCursor).toBe("old");
  expect(state.activityGate).not.toBe("clear"); expect(screen.getByRole("button", { name: "重新查询会话状态" })).toBeTruthy();
});
it("does not send a loaded p1 conversation using a p2 preparation snapshot", async () => {
  let count = 0;
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input); if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++count === 1 ? snapshot("A") : { ...snapshot("A"), session: { ...session("A", "p2") }, profile: profile("p2", "其他画像") }));
    if (url.endsWith("/view-state")) return Promise.resolve(response({ draft: "准备问题", reading_anchor: null, version: 1, updated_at: null }));
    if (url === "/api/chat" && init?.method === "POST") return Promise.resolve(response({}, 503));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "准备问题" } }); fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(count).toBe(2));
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.request.status).not.toBe("preparing"));
  expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(0); expect(workspaceStore.getSnapshot().buckets.A.session?.profile_id).toBe("p1");
  expect(workspaceStore.getSnapshot().buckets.A.activityGate).not.toBe("clear"); expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).value).toBe("准备问题");
});
it("does not associate or erase a p1 request from a p2 confirmation snapshot", async () => {
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "原问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  let count = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => { const url = String(input); if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group)); if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++count === 1 ? snapshot("A") : { ...snapshot("A"), session: { ...session("A", "p2"), state_version: 1 }, profile: profile("p2"), messages: { items: [{ id: 20, turn_index: 1, role: "user", content: "原问题", created_at: null }, { id: 21, turn_index: 1, role: "assistant", content: "答案", created_at: null }], next_cursor: null } })); return Promise.resolve(response({}, 404)); }));
  mount("/chat/A"); await screen.findByText("历史A"); const ticket = workspaceStore.captureTicket();
  const payload = { message: "原问题", session_id: "A", profile_id: "p1", request_id: "r1", expected_state_version: 0 }; const baseline = { owner_user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 1, provenance: "before_submit" as const, snapshot_sequence: 1 };
  const copy = getLocalRecovery().writeRequest(1, "A", "r1", { payload, baseline }); if (!copy.ok) throw Error("backup failed");
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, localRequests: { r1: { payload, baseline } }, requestCandidates: [copy.candidate], requests: { ...value.requests, r1: { ...value.requests.r1, baseline } }, request: { id: "r1", status: "pending_messages", attempt: 1, error: null, sequence: 1 } })); });
  await act(async () => { await workspaceController.confirmCompleted("A", "r1", ticket); });
  const state = workspaceStore.getSnapshot().buckets.A;
  expect(state.requests.r1.association).not.toBe("matched"); expect(state.session?.profile_id).toBe("p1"); expect(state.profile?.id).toBe("p1");
  expect(state.messages.some(item => item.id === 20 || item.id === 21)).toBe(false); expect(getLocalRecovery().list(1, "A", "request").some(item => item.writeId === copy.candidate.writeId)).toBe(true);
  expect(state.activityGate).not.toBe("clear");
});
it("keeps the identity gate through incompatible rechecks and recovers on the original profile", async () => {
  let count = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => { const url = String(input); if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group)); if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++count === 1 || count >= 4 ? snapshot("A") : { ...snapshot("A"), session: session("A", "p2"), profile: profile("p2") })); return Promise.resolve(response({}, 404)); }));
  mount("/chat/A"); await screen.findByText("历史A"); await act(async () => { await workspaceController.loadSession("A"); });
  expect(workspaceStore.getSnapshot().buckets.A.activityGate).toBe("uncertain");
  fireEvent.click(screen.getByRole("button", { name: "重新查询会话状态" })); await waitFor(() => expect(count).toBe(3));
  expect(workspaceStore.getSnapshot().buckets.A.activityGate).toBe("uncertain"); expect(workspaceStore.getSnapshot().buckets.A.session?.profile_id).toBe("p1");
  fireEvent.click(screen.getByRole("button", { name: "重新查询会话状态" })); await waitFor(() => expect(count).toBe(4));
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.activityError).toBeNull());
  expect(workspaceStore.getSnapshot().buckets.A.session?.profile_id).toBe("p1");
});
it("does not continue or mix a p2 snapshot into a p1 unassociated request", async () => {
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  let count = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => { const url = String(input); if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group)); if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++count === 1 ? snapshot("A") : { ...snapshot("A"), session: { ...session("A", "p2"), state_version: 1 }, profile: { ...profile("p2"), revision: 2 } })); return Promise.resolve(response({}, 404)); }));
  mount("/chat/A"); await screen.findByText("历史A"); const ticket = workspaceStore.captureTicket();
  act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, association: "unassociated" } }, request: { id: "r1", status: "unassociated", attempt: 1, error: null, sequence: 1 } })); });
  fireEvent.click(screen.getByRole("button", { name: "保留未关联记录并继续" })); await waitFor(() => expect(count).toBe(2));
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.activityGate).toBe("uncertain"));
  const state = workspaceStore.getSnapshot().buckets.A; expect(state.profile?.id).toBe("p1"); expect(state.session?.profile_id).toBe("p1"); expect(state.continuedUnassociated.r1).toBeUndefined(); expect(state.request.status).toBe("unassociated");
  expect(state.activityError).toMatch(/画像/);
});
it.each(["first null", "first empty summary", "p1 to null", "null to p1"])("handles profile null binding explicitly: %s", async scenario => {
  let count = 0; const nullSnapshot = { ...snapshot("A"), session: { ...session("A"), profile_id: null }, profile: null, profile_summary: null };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => { const url = String(input); if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group)); if (url.startsWith("/api/sessions/A/snapshot")) { count++; return Promise.resolve(response(scenario === "first null" ? nullSnapshot : scenario === "first empty summary" ? snapshot("A") : scenario === "p1 to null" ? count === 1 ? snapshot("A") : nullSnapshot : count === 1 ? nullSnapshot : snapshot("A"))); } return Promise.resolve(response({}, 404)); }));
  mount("/chat/A"); await screen.findByText("历史A");
  if (scenario === "p1 to null" || scenario === "null to p1") await act(async () => { await workspaceController.loadSession("A"); });
  const state = workspaceStore.getSnapshot().buckets.A;
  expect(state.session?.profile_id).toBe(scenario === "first null" || scenario === "null to p1" ? null : "p1");
  if (scenario === "p1 to null" || scenario === "null to p1") expect(state.activityGate).toBe("uncertain"); else expect(state.load.status).toBe("ready");
  expect(screen.getByText("历史A")).toBeTruthy();
});
it("does not offer a different-profile draft when resolving a view conflict", async () => {
  let snapshots = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => { const url = String(input); if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group)); if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots === 1 ? snapshot("A") : { ...snapshot("A"), session: session("A", "p2"), profile: profile("p2"), view_state: { draft: "其他画像草稿", reading_anchor: null, version: 1, updated_at: null } })); if (url.endsWith("/view-state") && init?.method === "PATCH") return Promise.resolve(response({}, 409)); return Promise.resolve(response({}, 404)); }));
  mount("/chat/A"); await screen.findByText("历史A");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "原画像草稿" } });
  await act(async () => { await workspaceController.flush("A"); });
  expect(workspaceStore.getSnapshot().buckets.A.conflictView).toBeNull(); expect(screen.queryByText(/服务器草稿：其他画像草稿/)).toBeNull(); expect((screen.getByPlaceholderText("输入学习问题…") as HTMLInputElement).value).toBe("原画像草稿");
  expect(screen.getByRole("button", { name: "重试保存草稿" })).toBeTruthy();
});
it("does not retry when a fresh snapshot contains a foreign pending request", async () => {
  const entry = { user_id: 1, session_id: "A", request_id: "old", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "failed", lease_until: null, lease_expired: false, error_code: "failed", response_json: null, created_at: "", updated_at: "" }; let count = 0;
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => { const url = String(input); if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group)); if (url.endsWith("/requests/old") && init?.method !== "POST") return Promise.resolve(response(entry)); if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++count === 1 ? { ...snapshot("A"), pending_requests: [entry] } : { ...snapshot("A"), pending_requests: [{ ...entry, user_id: 2 }] })); return Promise.resolve(response({}, 503)); });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("问题"); await act(async () => { await workspaceController.retry("A", "old"); });
  expect(fetcher.mock.calls.some(([url, init]) => String(url).includes("/requests/old/retry") && init?.method === "POST")).toBe(false);
  expect(workspaceStore.getSnapshot().buckets.A.activityGate).not.toBe("clear");
});
it("does not resend a linked request with a foreign pending request in its fresh snapshot", async () => {
  const recovery = createLocalRecovery(localStorage, "previous-tab"); const payload = { message: "原请求问题", session_id: "A", profile_id: "p1", request_id: "linked-request", expected_state_version: 0 }; const baseline = { owner_user_id: 1, session_id: "A", request_id: "linked-request", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 0, provenance: "before_submit", snapshot_sequence: 1 };
  expect(recovery.writePrepared(1, "A", "prepare-linked", { text: "原请求问题", sequence: 1, phase: "linked", requestId: "linked-request", payload, baseline }).ok).toBe(true);
  const foreign = { user_id: 2, session_id: "A", request_id: "foreign", profile_id: "p1", active_node_id: null, request_payload: { message: "坏请求", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "running", lease_until: null, lease_expired: false, error_code: null, response_json: null, created_at: "", updated_at: "" }; let snapshots = 0;
  const fetcher = vi.fn((input: RequestInfo | URL) => { const url = String(input); if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group)); if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots === 1 ? snapshot("A") : { ...snapshot("A"), pending_requests: [foreign] })); if (url.endsWith("/requests/linked-request")) return Promise.resolve(response({}, 404)); return Promise.resolve(response({}, 503)); });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByText("历史A"); fireEvent.click(screen.getByRole("button", { name: "查询原请求" })); fireEvent.click(await screen.findByRole("button", { name: "按原请求重试" }));
  await waitFor(() => expect(snapshots).toBe(2)); await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.activityGate).toBe("uncertain"));
  expect(fetcher.mock.calls.some(([url]) => url === "/api/chat")).toBe(false); expect(recovery.list(1, "A", "prepared")).toHaveLength(1);
});
it("rejects a saved recent-session candidate when its loaded profile has changed", async () => {
  const copy = createLocalRecovery(localStorage, "previous-tab").writeWorkspace(1, { lastSessionId: "A", baseVersion: 0, sequence: 1 }); if (!copy.ok) throw Error("backup failed"); let count = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => { const url = String(input); if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group)); if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++count === 1 ? snapshot("A") : { ...snapshot("A"), session: session("A", "p2"), profile: profile("p2") })); return Promise.resolve(response({}, 404)); }));
  mount("/chat/A"); await screen.findByText("历史A");
  const validated = await workspaceController.validateWorkspaceCandidate(copy.candidate);
  expect(validated).toBeNull(); expect(workspaceStore.getSnapshot().buckets.A.profile?.id).toBe("p1");
});
it("ignores a late incompatible profile snapshot after a newer valid load", async () => {
  const delayed = deferred<Response>(); let count = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => { const url = String(input); if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group)); if (url.startsWith("/api/sessions/A/snapshot")) { count++; return count === 2 ? delayed.promise : Promise.resolve(response(snapshot("A"))); } return Promise.resolve(response({}, 404)); }));
  mount("/chat/A"); await screen.findByText("历史A"); let old!: Promise<void>; act(() => { old = workspaceController.loadSession("A"); }); await waitFor(() => expect(count).toBe(2));
  await act(async () => { await workspaceController.loadSession("A"); });
  await act(async () => { delayed.resolve(response({ ...snapshot("A"), session: session("A", "p2"), profile: profile("p2") })); await old; });
  const state = workspaceStore.getSnapshot().buckets.A; expect(state.profile?.id).toBe("p1"); expect(state.session?.profile_id).toBe("p1"); expect(state.activityError).toBeNull(); expect(state.activityGate).toBe("clear"); expect(screen.getByText("历史A")).toBeTruthy();
});
it("keeps an in-flight newer activity check while an older continue bridge fails", async () => {
  const bridge = deferred<Response>(); const activity = deferred<Response>(); let snapshots = 0; let bridgeStarted = false;
  const completed = { user_id: 1, session_id: "A", request_id: "r1", profile_id: "p1", active_node_id: null, request_payload: { message: "旧问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed" as const, lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r1", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => { const url = String(input); if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group)); if (url.startsWith("/api/sessions/A/snapshot")) { snapshots++; return snapshots === 3 ? activity.promise : Promise.resolve(response(snapshots === 1 ? { ...snapshot("A"), messages: { ...snapshot("A").messages, next_cursor: "old" } } : { ...snapshot("A"), session: { ...session("A"), state_version: 1 }, messages: { items: [{ id: 99, turn_index: 1, role: "assistant", content: "未连接", created_at: null }], next_cursor: "bridge" } })); } if (url.includes("/A/messages?") && url.includes("bridge")) { bridgeStarted = true; return bridge.promise; } return Promise.resolve(response({}, 404)); }));
  mount("/chat/A"); await screen.findByText("历史A"); const ticket = workspaceStore.captureTicket(); act(() => { workspaceStore.mergeRequest(ticket, completed); workspaceStore.patchBucket(ticket, "A", value => ({ ...value, requests: { ...value.requests, r1: { ...value.requests.r1, association: "unassociated" } }, request: { id: "r1", status: "unassociated", attempt: 1, error: "原请求提示", sequence: 1 } })); });
  fireEvent.click(screen.getByRole("button", { name: "保留未关联记录并继续" })); await waitFor(() => expect(bridgeStarted).toBe(true));
  let check!: Promise<void>; act(() => { check = workspaceController.recheckSessionActivity("A"); }); await waitFor(() => expect(snapshots).toBe(3));
  await act(async () => { bridge.resolve(response({}, 503)); });
  expect(workspaceStore.getSnapshot().buckets.A.activityGate).toBe("checking"); expect(workspaceStore.getSnapshot().buckets.A.request.error).toBe("原请求提示"); expect(screen.getByRole("button", { name: "重新同步历史" })).toBeTruthy();
  await act(async () => { activity.resolve(response(snapshot("A"))); await check; });
});
it("does not let a late mismatched profile overwrite a newer activity error", async () => {
  const delayed = deferred<Response>(); let count = 0;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => { const url = String(input); if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group)); if (url.startsWith("/api/sessions/A/snapshot")) { count++; return count === 2 ? delayed.promise : Promise.resolve(count === 3 ? response({}, 503) : response(snapshot("A"))); } return Promise.resolve(response({}, 404)); }));
  mount("/chat/A"); await screen.findByText("历史A"); let old!: Promise<void>; act(() => { old = workspaceController.loadSession("A"); }); await waitFor(() => expect(count).toBe(2));
  await act(async () => { await workspaceController.recheckSessionActivity("A"); }); expect(workspaceStore.getSnapshot().buckets.A.activityError).toBe("查询失败，请重试");
  await act(async () => { delayed.resolve(response({ ...snapshot("A"), session: session("A", "p2"), profile: profile("p2") })); await old; });
  const state = workspaceStore.getSnapshot().buckets.A; expect(state.activityError).toBe("查询失败，请重试"); expect(state.activityGate).not.toBe("clear"); expect(state.session?.profile_id).toBe("p1");
});
it.each(["network", "cursor loop", "message conflict"])("keeps a newer matched result when an older association ends with %s", async failure => {
  const oldPage = deferred<Response>(); let snapshots = 0; let pageRequests = 0; let requestGets = 0; let sent: Record<string, unknown> | undefined;
  const user = { id: 10, turn_index: 0, role: "user", content: "关联问题", created_at: null }; const answer = { id: 11, turn_index: 0, role: "assistant", content: "关联答案", created_at: null };
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) { snapshots++; return Promise.resolve(response(snapshots <= 2 ? { ...snapshot("A"), messages: { items: [], next_cursor: null } } : snapshots === 3 ? { ...snapshot("A"), session: { ...session("A"), state_version: 1, next_turn_index: 1 }, messages: { items: [], next_cursor: "older" } } : { ...snapshot("A"), session: { ...session("A"), state_version: 1, next_turn_index: 1 }, messages: { items: [user, answer], next_cursor: null } })); }
    if (url.startsWith("/api/sessions/A/messages?")) { pageRequests++; return oldPage.promise; }
    if (url === "/api/chat") { sent = JSON.parse(String(init?.body)); return Promise.resolve(response({ session_id: "A", request_id: sent!.request_id, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "关联答案" })); }
    if (url.includes("/requests/")) { requestGets++; return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: sent!.request_id, profile_id: "p1", active_node_id: null, request_payload: { message: "关联问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: sent!.request_id, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "关联答案" }, created_at: "", updated_at: "" })); }
    if (url.endsWith("/view-state")) return Promise.resolve(response({ draft: "", reading_anchor: null, version: 1, updated_at: null })); return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByPlaceholderText("输入学习问题…");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "关联问题" } }); fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(pageRequests).toBe(1)); await screen.findByText("回复已保存，正在同步");
  const requestId = String(sent!.request_id); const ownBefore = getLocalRecovery().list(1, "A", "request").filter(item => item.itemId === requestId); expect(ownBefore.length).toBeGreaterThan(0);
  const local = workspaceStore.getSnapshot().buckets.A.localRequests[requestId];
  const foreign = createLocalRecovery(localStorage, "review6-other-writer").writeRequest(1, "A", requestId, local); if (!foreign.ok) throw Error("foreign backup failed");
  fireEvent.click(screen.getByRole("button", { name: "重新查询" }));
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.requests[requestId]?.association).toBe("matched"));
  expect(screen.getByText("关联答案")).toBeTruthy(); expect(requestGets).toBe(2); expect(snapshots).toBe(4);
  expect(getLocalRecovery().list(1, "A", "request").some(item => ownBefore.some(own => own.writeId === item.writeId))).toBe(false);
  const oldResult = failure === "network" ? response({}, 503) : failure === "cursor loop" ? response({ items: [], next_cursor: "older" }) : response({ items: [user, { ...user, content: "冲突内容" }, answer], next_cursor: null });
  await act(async () => { oldPage.resolve(oldResult); });
  const state = workspaceStore.getSnapshot().buckets.A; expect(state.requests[requestId].association).toBe("matched"); expect(state.request.status).toBe("completed"); expect(state.request.error).toBeNull(); expect(screen.getByText("关联答案")).toBeTruthy();
  expect(createLocalRecovery(localStorage, "reader").list(1, "A", "request").some(item => item.writeId === foreign.candidate.writeId)).toBe(true);
  expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(1);
});
it.each(["conflict", "network"])("handles %s in a new user-initiated verification after matching", async result => {
  let snapshots = 0; let sent: Record<string, unknown> | undefined;
  const user = { id: 10, turn_index: 0, role: "user", content: "验证问题", created_at: null }; const answer = { id: 11, turn_index: 0, role: "assistant", content: "原答案", created_at: null };
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => { const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ ...ws, last_session_id: body.last_session_id, version: body.expected_version + 1 })); }
    if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group)); if (url.startsWith("/api/sessions/B/snapshot")) return Promise.resolve(response(snapshot("B")));
    if (url.startsWith("/api/sessions/A/snapshot")) { snapshots++; if (snapshots <= 2) return Promise.resolve(response({ ...snapshot("A"), messages: { items: [], next_cursor: null } })); if (snapshots === 4) return Promise.resolve(response({ ...snapshot("A"), session: session("A", "p2"), profile: profile("p2") })); return Promise.resolve(response({ ...snapshot("A"), session: { ...session("A"), state_version: 1, next_turn_index: 1, active_request_id: snapshots === 5 ? sent!.request_id : null }, messages: result === "network" && snapshots >= 6 ? { items: [], next_cursor: "failure" } : { items: [user, snapshots >= 6 ? { ...answer, content: "矛盾答案" } : answer], next_cursor: null } })); }
    if (url.startsWith("/api/sessions/A/messages?")) return Promise.resolve(response({}, 503));
    if (url === "/api/chat") { sent = JSON.parse(String(init?.body)); return Promise.resolve(response({ session_id: "A", request_id: sent!.request_id, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "原答案" })); }
    if (url.includes("/requests/")) return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: sent!.request_id, profile_id: "p1", active_node_id: null, request_payload: { message: "验证问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: sent!.request_id, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "原答案" }, created_at: "", updated_at: "" }));
    if (url.endsWith("/view-state")) return Promise.resolve(response({ draft: "", reading_anchor: null, version: 1, updated_at: null })); return Promise.resolve(response({}, 404)); });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByPlaceholderText("输入学习问题…"); fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "验证问题" } }); fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.requests[String(sent?.request_id)]?.association).toBe("matched")); expect(screen.getByText("原答案")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "会话 B" })); await screen.findByText("历史B"); fireEvent.click(screen.getByRole("button", { name: "会话 A" }));
  fireEvent.click(await screen.findByRole("button", { name: "重新查询会话状态" }));
  if (result === "conflict") await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.requests[String(sent!.request_id)]?.association).toBe("inconsistent"));
  else { await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.activityError).toMatch(/复核|查询/)); expect(workspaceStore.getSnapshot().buckets.A.requests[String(sent!.request_id)]?.association).toBe("matched"); expect(workspaceStore.getSnapshot().buckets.A.request.status).toBe("completed"); expect(screen.getByRole("button", { name: "重新查询会话状态" })).toBeTruthy(); }
  expect(screen.getByText("原答案")).toBeTruthy(); expect(screen.queryByText("矛盾答案")).toBeNull(); expect((screen.getByRole("button", { name: "发送" }) as HTMLButtonElement).disabled).toBe(true);
});
it("keeps a current association failure visible and lets the user retry successfully", async () => {
  let snapshots = 0; let gets = 0; let sent: Record<string, unknown> | undefined;
  const user = { id: 10, turn_index: 0, role: "user", content: "重查问题", created_at: null }; const answer = { id: 11, turn_index: 0, role: "assistant", content: "重查答案", created_at: null };
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => { const url = String(input); if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots <= 2 ? { ...snapshot("A"), messages: { items: [], next_cursor: null } } : snapshots === 3 ? { ...snapshot("A"), session: { ...session("A"), state_version: 1, next_turn_index: 1 }, messages: { items: [], next_cursor: "older" } } : { ...snapshot("A"), session: { ...session("A"), state_version: 1, next_turn_index: 1 }, messages: { items: [user, answer], next_cursor: null } }));
    if (url.startsWith("/api/sessions/A/messages?")) return Promise.resolve(response({}, 503));
    if (url === "/api/chat") { sent = JSON.parse(String(init?.body)); return Promise.resolve(response({ session_id: "A", request_id: sent!.request_id, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "重查答案" })); }
    if (url.includes("/requests/")) { gets++; return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: sent!.request_id, profile_id: "p1", active_node_id: null, request_payload: { message: "重查问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: sent!.request_id, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "重查答案" }, created_at: "", updated_at: "" })); }
    if (url.endsWith("/view-state")) return Promise.resolve(response({ draft: "", reading_anchor: null, version: 1, updated_at: null })); return Promise.resolve(response({}, 404)); });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByPlaceholderText("输入学习问题…"); fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "重查问题" } }); fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await screen.findByText("回复已保存，消息尚未确认，请重试"); expect(workspaceStore.getSnapshot().buckets.A.request.status).toBe("pending_messages");
  fireEvent.click(screen.getByRole("button", { name: "重新查询" })); await screen.findByText("重查答案");
  const state = workspaceStore.getSnapshot().buckets.A; expect(state.requests[String(sent!.request_id)].association).toBe("matched"); expect(state.request.status).toBe("completed"); expect(gets).toBe(2); expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(1);
});
it.each(["new sequence", "different request", "account"])("does not apply an old association failure after %s", async change => {
  const oldPage = deferred<Response>(); let snapshots = 0; let pages = 0; let sent: Record<string, unknown> | undefined;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => { const url = String(input); if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots <= 2 ? { ...snapshot("A"), messages: { items: [], next_cursor: null } } : { ...snapshot("A"), session: { ...session("A"), state_version: 1, next_turn_index: 1 }, messages: { items: [], next_cursor: "older" } }));
    if (url.startsWith("/api/sessions/A/messages?")) { pages++; return oldPage.promise; }
    if (url === "/api/chat") { sent = JSON.parse(String(init?.body)); return Promise.resolve(response({ session_id: "A", request_id: sent!.request_id, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" })); }
    if (url.includes("/requests/")) return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: sent!.request_id, profile_id: "p1", active_node_id: null, request_payload: { message: "原问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: sent!.request_id, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" }));
    if (url.endsWith("/view-state")) return Promise.resolve(response({ draft: "", reading_anchor: null, version: 1, updated_at: null })); return Promise.resolve(response({}, 404)); }));
  mount("/chat/A"); await screen.findByPlaceholderText("输入学习问题…"); fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "原问题" } }); fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!); await waitFor(() => expect(pages).toBe(1));
  const ticket = workspaceStore.captureTicket();
  if (change === "account") act(() => { workspaceStore.startAccount(1, "A", true); workspaceStore.ensureSessionBucket("A"); });
  else act(() => { workspaceStore.patchBucket(ticket, "A", value => ({ ...value, request: { ...value.request, id: change === "different request" ? "other" : value.request.id, sequence: value.request.sequence + 1, status: "running", error: "较新请求提示" } })); });
  await act(async () => { oldPage.resolve(response({}, 503)); }); const state = workspaceStore.getSnapshot().buckets.A;
  if (change === "account") { expect(state.request.error).toBeNull(); expect(state.requests[String(sent!.request_id)]).toBeUndefined(); }
  else { expect(state.request.status).toBe("running"); expect(state.request.error).toBe("较新请求提示"); }
});
it("two providers preserve another writer while one page resolves overlapping associations", async () => {
  const oldPage = deferred<Response>(); let snapshots = 0; let sent: Record<string, unknown> | undefined; let pages = 0;
  const user = { id: 10, turn_index: 0, role: "user", content: "双页关联问题", created_at: null }; const answer = { id: 11, turn_index: 0, role: "assistant", content: "双页关联答案", created_at: null };
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => { const url = String(input); if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots <= 2 ? { ...snapshot("A"), messages: { items: [], next_cursor: null } } : snapshots === 3 ? { ...snapshot("A"), session: { ...session("A"), state_version: 1, next_turn_index: 1 }, messages: { items: [], next_cursor: "older" } } : { ...snapshot("A"), session: { ...session("A"), state_version: 1, next_turn_index: 1 }, messages: { items: [user, answer], next_cursor: null } }));
    if (url.startsWith("/api/sessions/A/messages?")) { pages++; return oldPage.promise; }
    if (url === "/api/chat") { sent = JSON.parse(String(init?.body)); return Promise.resolve(response({ session_id: "A", request_id: sent!.request_id, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "双页关联答案" })); }
    if (url.includes("/requests/")) return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: sent!.request_id, profile_id: "p1", active_node_id: null, request_payload: { message: "双页关联问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: sent!.request_id, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "双页关联答案" }, created_at: "", updated_at: "" }));
    if (url.endsWith("/view-state")) return Promise.resolve(response({ draft: "", reading_anchor: null, version: 1, updated_at: null })); return Promise.resolve(response({}, 404)); });
  vi.stubGlobal("fetch", fetcher); const first = mount("/chat/A"); await within(first.container).findByPlaceholderText("输入学习问题…"); fireEvent.change(within(first.container).getByPlaceholderText("输入学习问题…"), { target: { value: "双页关联问题" } }); fireEvent.submit(within(first.container).getByPlaceholderText("输入学习问题…").closest("form")!); await waitFor(() => expect(pages).toBe(1));
  const requestId = String(sent!.request_id); const local = workspaceStore.getSnapshot().buckets.A.localRequests[requestId]; const other = createLocalRecovery(localStorage, "review6-second-writer").writeRequest(1, "A", requestId, local); if (!other.ok) throw Error("foreign backup failed");
  vi.resetModules(); const SecondApp = (await import("../App")).default; const SecondProvider = (await import("../store/auth")).AuthProvider;
  const second = render(<SecondProvider><MemoryRouter initialEntries={["/chat/A"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><SecondApp /></MemoryRouter></SecondProvider>);
  await within(second.container).findByText("双页关联答案");
  fireEvent.click(within(first.container).getByRole("button", { name: "重新查询" })); await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.requests[requestId]?.association).toBe("matched"));
  await act(async () => { oldPage.resolve(response({}, 503)); });
  expect(workspaceStore.getSnapshot().buckets.A.requests[requestId].association).toBe("matched"); expect(workspaceStore.getSnapshot().buckets.A.request.status).toBe("completed");
  expect(createLocalRecovery(localStorage, "reader").list(1, "A", "request").some(item => item.writeId === other.candidate.writeId)).toBe(true);
  expect(within(second.container).getAllByText("上次请求结果待确认").length).toBeGreaterThan(0); expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(1);
});
it("two different recovered requests associate independently without replacing the active request", async () => {
  const pageA = deferred<Response>(); const pageB = deferred<Response>(); let snapshots = 0; let pageACalls = 0; let pageBCalls = 0;
  const userA = { id: 10, turn_index: 0, role: "user", content: "独立问题A", created_at: null }; const answerA = { id: 11, turn_index: 0, role: "assistant", content: "独立答案A", created_at: null };
  const userB = { id: 20, turn_index: 1, role: "user", content: "独立问题B", created_at: null }; const answerB = { id: 21, turn_index: 1, role: "assistant", content: "独立答案B", created_at: null };
  for (const [rid, text, base, turn] of [["ra", "独立问题A", 0, 0], ["rb", "独立问题B", 1, 1]] as const) {
    const payload = { message: text, session_id: "A", profile_id: "p1", request_id: rid, expected_state_version: base }; const baseline = { owner_user_id: 1, session_id: "A", request_id: rid, profile_id: "p1", active_node_id: null, base_state_version: base, expected_turn_index: turn, provenance: "before_submit", snapshot_sequence: 1 };
    expect(createLocalRecovery(localStorage, `writer-${rid}`).writeRequest(1, "A", rid, { payload, baseline }).ok).toBe(true);
  }
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => { const url = String(input); if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) { snapshots++; return Promise.resolve(response(snapshots === 1 ? { ...snapshot("A"), messages: { items: [], next_cursor: null } } : { ...snapshot("A"), session: { ...session("A"), state_version: snapshots === 2 ? 1 : 2, next_turn_index: snapshots === 2 ? 1 : 2 }, messages: { items: [], next_cursor: snapshots === 2 ? "a" : "b" } })); }
    if (url.startsWith("/api/sessions/A/messages?") && url.includes("cursor=a")) { pageACalls++; return pageA.promise; } if (url.startsWith("/api/sessions/A/messages?") && url.includes("cursor=b")) { pageBCalls++; return pageB.promise; }
    if (url.includes("/requests/")) { const b = url.endsWith("/rb"); const rid = b ? "rb" : "ra"; const base = b ? 1 : 0; return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: rid, profile_id: "p1", active_node_id: null, request_payload: { message: b ? "独立问题B" : "独立问题A", profile_id: "p1", active_node_id: null, base_state_version: base }, base_state_version: base, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: rid, status: "completed", attempt: 1, persisted: true, state_version: base + 1, reply: b ? "独立答案B" : "独立答案A" }, created_at: "", updated_at: "" })); }
    return Promise.resolve(response({}, 404)); }));
  mount("/chat/A"); await screen.findByText("独立问题A");
  fireEvent.click(within(screen.getByText("独立问题A").closest("section")!).getByRole("button", { name: "查询上次请求" })); await waitFor(() => expect(pageACalls).toBe(1));
  fireEvent.click(within(screen.getByText("独立问题B").closest("section")!).getByRole("button", { name: "查询上次请求" })); await waitFor(() => expect(pageBCalls).toBe(1));
  await act(async () => { pageB.resolve(response({ items: [userB, answerB], next_cursor: null })); }); await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.requests.rb?.association).toBe("matched"));
  await act(async () => { pageA.resolve(response({ items: [userA, answerA], next_cursor: null })); });
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.requests.ra?.association).toBe("matched"));
  const state = workspaceStore.getSnapshot().buckets.A; expect(state.request.id).toBe("rb"); expect(state.request.status).toBe("completed"); expect(screen.getByText("独立答案A")).toBeTruthy(); expect(screen.getByText("独立答案B")).toBeTruthy();
});
it.each(["network", "cursor loop"])("accepts a valid older association after the newer recheck fails: %s", async failure => {
  const oldPage = deferred<Response>(); let snapshots = 0; let oldPages = 0; let sent: Record<string, unknown> | undefined;
  const user = { id: 10, turn_index: 0, role: "user", content: "逆序问题", created_at: null }; const answer = { id: 11, turn_index: 0, role: "assistant", content: "逆序答案", created_at: null };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => { const url = String(input); if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots <= 2 ? { ...snapshot("A"), messages: { items: [], next_cursor: null } } : { ...snapshot("A"), session: { ...session("A"), state_version: 1, next_turn_index: 1 }, messages: { items: [], next_cursor: snapshots === 3 ? "old" : "new" } }));
    if (url.startsWith("/api/sessions/A/messages?") && url.includes("old")) { oldPages++; return oldPage.promise; }
    if (url.startsWith("/api/sessions/A/messages?") && url.includes("new")) return Promise.resolve(failure === "network" ? response({}, 503) : response({ items: [], next_cursor: "new" }));
    if (url === "/api/chat") { sent = JSON.parse(String(init?.body)); return Promise.resolve(response({ session_id: "A", request_id: sent!.request_id, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "逆序答案" })); }
    if (url.includes("/requests/")) return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: sent!.request_id, profile_id: "p1", active_node_id: null, request_payload: { message: "逆序问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: sent!.request_id, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "逆序答案" }, created_at: "", updated_at: "" }));
    if (url.endsWith("/view-state")) return Promise.resolve(response({ draft: "", reading_anchor: null, version: 1, updated_at: null })); return Promise.resolve(response({}, 404)); }));
  mount("/chat/A"); await screen.findByPlaceholderText("输入学习问题…"); fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "逆序问题" } }); fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!); await waitFor(() => expect(oldPages).toBe(1));
  fireEvent.click(screen.getByRole("button", { name: "重新查询" })); await screen.findByText("回复已保存，消息尚未确认，请重试");
  await act(async () => { oldPage.resolve(response({ items: [user, answer], next_cursor: null })); });
  await screen.findByText("逆序答案"); expect(workspaceStore.getSnapshot().buckets.A.requests[String(sent!.request_id)].association).toBe("matched"); expect(workspaceStore.getSnapshot().buckets.A.request.status).toBe("completed");
});
it("does not show an older association failure while a newer recheck is still in flight", async () => {
  const oldPage = deferred<Response>(); const newPage = deferred<Response>(); let snapshots = 0; let oldPages = 0; let newPages = 0; let sent: Record<string, unknown> | undefined;
  const user = { id: 10, turn_index: 0, role: "user", content: "等待问题", created_at: null }; const answer = { id: 11, turn_index: 0, role: "assistant", content: "等待答案", created_at: null };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => { const url = String(input); if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots <= 2 ? { ...snapshot("A"), messages: { items: [], next_cursor: null } } : { ...snapshot("A"), session: { ...session("A"), state_version: 1, next_turn_index: 1 }, messages: { items: [], next_cursor: snapshots === 3 ? "old" : "new" } }));
    if (url.startsWith("/api/sessions/A/messages?") && url.includes("old")) { oldPages++; return oldPage.promise; } if (url.startsWith("/api/sessions/A/messages?") && url.includes("new")) { newPages++; return newPage.promise; }
    if (url === "/api/chat") { sent = JSON.parse(String(init?.body)); return Promise.resolve(response({ session_id: "A", request_id: sent!.request_id, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "等待答案" })); }
    if (url.includes("/requests/")) return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: sent!.request_id, profile_id: "p1", active_node_id: null, request_payload: { message: "等待问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: sent!.request_id, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "等待答案" }, created_at: "", updated_at: "" }));
    if (url.endsWith("/view-state")) return Promise.resolve(response({ draft: "", reading_anchor: null, version: 1, updated_at: null })); return Promise.resolve(response({}, 404)); }));
  mount("/chat/A"); await screen.findByPlaceholderText("输入学习问题…"); fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "等待问题" } }); fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!); await waitFor(() => expect(oldPages).toBe(1));
  fireEvent.click(screen.getByRole("button", { name: "重新查询" })); await waitFor(() => expect(newPages).toBe(1));
  await act(async () => { oldPage.resolve(response({}, 503)); }); expect(workspaceStore.getSnapshot().buckets.A.request.error).toBeNull(); expect(screen.queryByText("回复已保存，消息尚未确认，请重试")).toBeNull();
  await act(async () => { newPage.resolve(response({ items: [user, answer], next_cursor: null })); }); await screen.findByText("等待答案");
});
it.each(["backed up", "backup unavailable"])("does not let an older valid association erase a newer verified conflict: %s", async backup => {
  const oldPage = deferred<Response>(); let snapshots = 0; let pages = 0; let sent: Record<string, unknown> | undefined;
  const user = { id: 10, turn_index: 0, role: "user", content: "冲突问题", created_at: null }; const answer = { id: 11, turn_index: 0, role: "assistant", content: "正确答案", created_at: null };
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => { const url = String(input); if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots <= 2 ? { ...snapshot("A"), messages: { items: [], next_cursor: null } } : snapshots === 3 ? { ...snapshot("A"), session: { ...session("A"), state_version: 1, next_turn_index: 1 }, messages: { items: [], next_cursor: "old" } } : { ...snapshot("A"), session: { ...session("A"), state_version: 1, next_turn_index: 1 }, messages: snapshots === 6 ? { items: [], next_cursor: "retry-failure" } : { items: [user, snapshots >= 7 ? answer : { ...answer, content: "矛盾答案" }], next_cursor: null } }));
    if (url.startsWith("/api/sessions/A/messages?")) { if (url.includes("retry-failure")) return Promise.resolve(response({}, 503)); pages++; return oldPage.promise; }
    if (url === "/api/chat") { sent = JSON.parse(String(init?.body)); return Promise.resolve(response({ session_id: "A", request_id: sent!.request_id, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "正确答案" })); }
    if (url.includes("/requests/")) return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: sent!.request_id, profile_id: "p1", active_node_id: null, request_payload: { message: "冲突问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: sent!.request_id, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "正确答案" }, created_at: "", updated_at: "" }));
    if (url.endsWith("/view-state")) return Promise.resolve(response({ draft: "", reading_anchor: null, version: 1, updated_at: null })); return Promise.resolve(response({}, 404)); });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByPlaceholderText("输入学习问题…");
  if (backup === "backup unavailable") { const original = Storage.prototype.setItem; vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, key: string, value: string) { if (key.startsWith("studyagent:recovery:")) throw Error("unavailable"); return original.call(this, key, value); }); }
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "冲突问题" } }); fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!); await waitFor(() => expect(pages).toBe(1));
  const requestId = String(sent!.request_id); const copies = getLocalRecovery().list(1, "A", "request"); if (backup === "backed up") expect(copies.some(item => item.itemId === requestId)).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "重新查询" })); await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.requests[requestId]?.association).toBe("inconsistent"));
  expect(screen.getByText("已保存的消息与请求不一致，请检查")).toBeTruthy();
  await act(async () => { oldPage.resolve(response({ items: [user, answer], next_cursor: null })); });
  if (backup === "backup unavailable") act(() => { workspaceStore.patchBucket(workspaceStore.captureTicket(), "A", value => ({ ...value, requestCandidates: [], preparedCandidates: [] })); });
  const state = workspaceStore.getSnapshot().buckets.A;
  expect(state.requests[requestId].association).toBe("inconsistent"); expect(state.request.status).toBe("inconsistent"); expect(screen.getByText("已保存的消息与请求不一致，请检查")).toBeTruthy(); if (backup === "backed up") expect(getLocalRecovery().list(1, "A", "request").some(item => copies.some(copy => copy.writeId === item.writeId))).toBe(true); else expect(state.recoveryError).toMatch(/不可用/); expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(1);
  expect((screen.getByRole("button", { name: "发送" }) as HTMLButtonElement).disabled).toBe(true); expect(screen.getByRole("button", { name: "重新查询" })).toBeTruthy();
  if (backup === "backup unavailable") { await act(async () => { workspaceController.setDraft("A", "不应发送"); await workspaceController.send("A"); }); expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(1); }
  fireEvent.click(screen.getByRole("button", { name: "重新查询" })); await waitFor(() => expect(snapshots).toBe(5)); expect(workspaceStore.getSnapshot().buckets.A.requests[requestId].association).toBe("inconsistent");
  fireEvent.click(screen.getByRole("button", { name: "重新查询" })); await screen.findByText("回复复核失败，请重新查询"); expect(workspaceStore.getSnapshot().buckets.A.requests[requestId].association).toBe("inconsistent"); expect((screen.getByRole("button", { name: "发送" }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "重新查询" })); await screen.findByText("正确答案"); await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.requests[requestId].association).toBe("matched")); expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(1);
});
it("shows a recoverable warning when a newer writer source vanishes before an older association fails", async () => {
  const oldPage = deferred<Response>(); const newPage = deferred<Response>(); let snapshots = 0; let oldPages = 0; let newPages = 0;
  const payload = { message: "多来源问题", session_id: "A", profile_id: "p1", request_id: "same", expected_state_version: 0 }; const baseline = { owner_user_id: 1, session_id: "A", request_id: "same", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 0, provenance: "before_submit", snapshot_sequence: 1 };
  const writerA = createLocalRecovery(localStorage, "review7-writer-a"); const writerB = createLocalRecovery(localStorage, "review7-writer-b");
  const a = writerA.writePrepared(1, "A", "a", { text: payload.message, sequence: 1, phase: "linked", requestId: "same", payload, baseline }); const b = writerB.writePrepared(1, "A", "b", { text: payload.message, sequence: 1, phase: "linked", requestId: "same", payload, baseline }); if (!a.ok || !b.ok) throw Error("backup failed");
  const fetcher = vi.fn((input: RequestInfo | URL) => { const url = String(input); if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots === 1 ? { ...snapshot("A"), messages: { items: [], next_cursor: null } } : { ...snapshot("A"), session: { ...session("A"), state_version: 1, next_turn_index: 1 }, messages: { items: [], next_cursor: snapshots === 2 ? "old" : "new" } }));
    if (url.startsWith("/api/sessions/A/messages?") && url.includes("old")) { oldPages++; return oldPage.promise; } if (url.startsWith("/api/sessions/A/messages?") && url.includes("new")) { newPages++; return newPage.promise; }
    if (url.endsWith("/requests/same")) return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: "same", profile_id: "p1", active_node_id: null, request_payload: { message: payload.message, profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "same", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" })); return Promise.resolve(response({}, 404)); });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findAllByText("多来源问题");
  fireEvent.click(screen.getAllByRole("button", { name: "查询原请求" })[0]); await waitFor(() => expect(oldPages).toBe(1));
  fireEvent.click(screen.getAllByRole("button", { name: "查询原请求" })[1]); await waitFor(() => expect(newPages).toBe(1));
  expect(writerB.remove(b.candidate)).toBe(true);
  await act(async () => { newPage.resolve(response({ items: [{ id: 10, turn_index: 0, role: "user", content: payload.message, created_at: null }, { id: 11, turn_index: 0, role: "assistant", content: "答案", created_at: null }], next_cursor: null })); });
  await screen.findByText("本机内容已变化或无法读取，请重新检查");
  await act(async () => { oldPage.resolve(response({}, 503)); });
  expect(screen.getByText("本机内容已变化或无法读取，请重新检查")).toBeTruthy(); expect(screen.getByRole("button", { name: "查询原请求" })).toBeTruthy(); expect(writerA.list(1, "A", "prepared")).toHaveLength(1); expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(0);
  expect(workspaceStore.getSnapshot().buckets.A.request.error).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "查询原请求" }));
  await waitFor(() => expect(workspaceStore.getSnapshot().buckets.A.requests.same?.association).toBe("matched"));
  expect(writerA.list(1, "A", "prepared")).toHaveLength(1); expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(0);
});
it("does not publish a conflict from a writer source changed before its page returns", async () => {
  const page = deferred<Response>(); let snapshots = 0; let pages = 0;
  const payload = { message: "来源问题", session_id: "A", profile_id: "p1", request_id: "r-source", expected_state_version: 0 }; const baseline = { owner_user_id: 1, session_id: "A", request_id: "r-source", profile_id: "p1", active_node_id: null, base_state_version: 0, expected_turn_index: 0, provenance: "before_submit", snapshot_sequence: 1 };
  const writer = createLocalRecovery(localStorage, "review7-source"); expect(writer.writePrepared(1, "A", "source", { text: payload.message, sequence: 1, phase: "linked", requestId: payload.request_id, payload, baseline }).ok).toBe(true);
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => { const url = String(input); if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group)); if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(++snapshots === 1 ? { ...snapshot("A"), messages: { items: [], next_cursor: null } } : { ...snapshot("A"), session: { ...session("A"), state_version: 1, next_turn_index: 1 }, messages: { items: [], next_cursor: "old" } })); if (url.startsWith("/api/sessions/A/messages?")) { pages++; return page.promise; } if (url.endsWith("/requests/r-source")) return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: "r-source", profile_id: "p1", active_node_id: null, request_payload: { message: payload.message, profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: "r-source", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" })); return Promise.resolve(response({}, 404)); }));
  mount("/chat/A"); await screen.findByText("来源问题"); fireEvent.click(screen.getByRole("button", { name: "查询原请求" })); await waitFor(() => expect(pages).toBe(1));
  expect(writer.writePrepared(1, "A", "source", { text: payload.message, sequence: 2, phase: "linked", requestId: payload.request_id, payload, baseline }).ok).toBe(true);
  await act(async () => { page.resolve(response({ items: [{ id: 10, turn_index: 0, role: "user", content: payload.message, created_at: null }, { id: 11, turn_index: 0, role: "assistant", content: "错误答案", created_at: null }], next_cursor: null })); });
  expect(workspaceStore.getSnapshot().buckets.A.requests["r-source"].association).not.toBe("inconsistent"); expect(screen.getByText("本机内容已变化或无法读取，请重新检查")).toBeTruthy(); expect(writer.list(1, "A", "prepared")).toHaveLength(1);
});
it.each(["conflict", "network", "cursor loop"])("handles a newer %s when two rechecks start from an existing conflict", async outcome => {
  const oldPage = deferred<Response>(); const newPage = deferred<Response>(); let snapshots = 0; let oldPages = 0; let newPages = 0; let sent: Record<string, unknown> | undefined;
  const user = { id: 10, turn_index: 0, role: "user", content: "双重查问题", created_at: null }; const answer = { id: 11, turn_index: 0, role: "assistant", content: "正确回答", created_at: null };
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => { const url = String(input);
    if (url === "/api/workspace-state") return Promise.resolve(response(ws)); if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) { snapshots++; return Promise.resolve(response(snapshots <= 2 ? { ...snapshot("A"), messages: { items: [], next_cursor: null } } : { ...snapshot("A"), session: { ...session("A"), state_version: 1, next_turn_index: 1 }, messages: snapshots === 4 ? { items: [], next_cursor: "old" } : snapshots === 5 ? { items: [], next_cursor: "new" } : { items: [user, snapshots >= 6 ? answer : { ...answer, content: "矛盾回答" }], next_cursor: null } })); }
    if (url.startsWith("/api/sessions/A/messages?") && url.includes("old")) { oldPages++; return oldPage.promise; }
    if (url.startsWith("/api/sessions/A/messages?") && url.includes("new")) { newPages++; return outcome === "conflict" ? newPage.promise : Promise.resolve(outcome === "network" ? response({}, 503) : response({ items: [], next_cursor: "new" })); }
    if (url === "/api/chat") { sent = JSON.parse(String(init?.body)); return Promise.resolve(response({ session_id: "A", request_id: sent!.request_id, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "正确回答" })); }
    if (url.includes("/requests/")) return Promise.resolve(response({ user_id: 1, session_id: "A", request_id: sent!.request_id, profile_id: "p1", active_node_id: null, request_payload: { message: "双重查问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "A", request_id: sent!.request_id, status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "正确回答" }, created_at: "", updated_at: "" }));
    if (url.endsWith("/view-state")) return Promise.resolve(response({ draft: "", reading_anchor: null, version: 1, updated_at: null })); return Promise.resolve(response({}, 404)); });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A"); await screen.findByPlaceholderText("输入学习问题…");
  fireEvent.change(screen.getByPlaceholderText("输入学习问题…"), { target: { value: "双重查问题" } }); fireEvent.submit(screen.getByPlaceholderText("输入学习问题…").closest("form")!);
  await screen.findByText("已保存的消息与请求不一致，请检查"); const requestId = String(sent!.request_id); const copies = getLocalRecovery().list(1, "A", "request"); expect(copies.some(item => item.itemId === requestId)).toBe(true);
  const otherWriter = createLocalRecovery(localStorage, "goal-recovery-other-writer"); const other = otherWriter.writeRequest(1, "A", requestId, workspaceStore.getSnapshot().buckets.A.localRequests[requestId]); if (!other.ok) throw Error("other writer backup failed");
  fireEvent.click(screen.getByRole("button", { name: "重新查询" })); await waitFor(() => expect(oldPages).toBe(1));
  expect(workspaceStore.getSnapshot().buckets.A.requests[requestId].association).toBe("inconsistent");
  fireEvent.click(screen.getByRole("button", { name: "重新查询" })); await waitFor(() => expect(newPages).toBeGreaterThan(0));
  if (outcome === "conflict") { await act(async () => { newPage.resolve(response({ items: [user, { ...answer, content: "矛盾回答" }], next_cursor: null })); }); expect(screen.getByText("已保存的消息与请求不一致，请检查")).toBeTruthy(); }
  else await screen.findByText("回复复核失败，请重新查询");
  await act(async () => { oldPage.resolve(response({ items: [user, answer], next_cursor: null })); });
  if (outcome === "conflict") {
    expect(workspaceStore.getSnapshot().buckets.A.requests[requestId].association).toBe("inconsistent"); expect(screen.getByText("已保存的消息与请求不一致，请检查")).toBeTruthy(); expect((screen.getByRole("button", { name: "发送" }) as HTMLButtonElement).disabled).toBe(true);
    expect(getLocalRecovery().list(1, "A", "request").some(item => copies.some(copy => copy.writeId === item.writeId))).toBe(true);
    expect(otherWriter.list(1, "A", "request").some(item => item.writeId === other.candidate.writeId)).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "重新查询" })); await screen.findByText("正确回答");
  } else await screen.findByText("正确回答");
  expect(workspaceStore.getSnapshot().buckets.A.requests[requestId].association).toBe("matched"); expect(fetcher.mock.calls.filter(([url]) => url === "/api/chat")).toHaveLength(1);
});
it("shows the current session's real profile summary without extra reads on expansion", async () => {
  const summary = { profile_revision: 0, nodes: [], edges: [], recent_evidence: [], assessed_count: 1, total_count: 2, mastery_score: 42, metric_kind: "assessed_mean", assessment_coverage: 0.5 };
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ ...ws, ...body, version: body.expected_version + 1 })); }
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response({ ...snapshot("A"), profile_summary: summary }));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/chat/A");
  await screen.findByText("历史A");
  const trigger = screen.getByRole("button", { name: "学习画像" });
  expect(trigger.textContent).toContain("42%");
  const reads = fetcher.mock.calls.filter(([url]) => String(url).includes("snapshot") || String(url).includes("messages") || String(url).includes("summary")).length;
  fireEvent.click(trigger);
  expect(screen.getByRole("link", { name: "查看完整画像" }).getAttribute("href")).toContain("session_id=A");
  expect(fetcher.mock.calls.filter(([url]) => String(url).includes("snapshot") || String(url).includes("messages") || String(url).includes("summary"))).toHaveLength(reads);
});
it("serializes preference and recent-session edits with consecutive versions", async () => {
  const first = deferred<Response>(); const writes: Record<string, unknown>[] = [];
  let server = { ...ws, last_session_id: null };
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") {
      const body = JSON.parse(String(init.body)); writes.push(body);
      if (writes.length === 1) return first.promise;
      server = { ...server, ...body, version: body.expected_version + 1 }; return Promise.resolve(response(server));
    }
    if (url === "/api/workspace-state") return Promise.resolve(response(server));
    if (url.startsWith("/api/sessions?")) return Promise.resolve(response(group));
    if (url.startsWith("/api/sessions/B/snapshot")) return Promise.resolve(response(snapshot("B")));
    return Promise.resolve(response({}, 404));
  });
  vi.stubGlobal("fetch", fetcher); mount("/knowledge");
  await waitFor(() => expect(workspaceStore.getSnapshot().workspace.version).toBe(0));
  void workspaceController.savePreference(0.7);
  await waitFor(() => expect(writes).toHaveLength(1));
  workspaceController.selectSession("B"); void workspaceController.savePreference(0.9);
  expect(writes[0]).toEqual({ expected_version: 0, progress_y_ratio: 0.7 });
  server = { ...server, progress_y_ratio: 0.7, version: 1 };
  await act(async () => { first.resolve(response(server)); });
  await waitFor(() => expect(writes).toHaveLength(2));
  await waitFor(() => expect(workspaceStore.getSnapshot().workspace.prefs.dirtyFields).toEqual([]));
  expect(writes[1]).toEqual({ expected_version: 1, last_session_id: "B", progress_y_ratio: 0.9 });
  expect(workspaceStore.getSnapshot().workspace.lastSessionId).toBe("B");
});
it("keeps a local sidebar gesture when the initial preference read is late", async () => {
  const pending = deferred<Response>();
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method !== "PATCH") return pending.promise;
    if (url === "/api/workspace-state") { const body = JSON.parse(String(init?.body)); return Promise.resolve(response({ ...ws, ...body, version: body.expected_version + 1 })); }
    return Promise.resolve(response(url.startsWith("/api/sessions?") ? group : url.startsWith("/api/knowledge") ? [] : { items: [], next_cursor: null }));
  }));
  mount("/knowledge"); fireEvent.click(await screen.findByRole("button", { name: "收起会话导航" }));
  await act(async () => { pending.resolve(response(ws)); });
  await waitFor(() => expect(workspaceStore.getSnapshot().sidebar).toMatchObject({ pinned: false, collapsed: true }));
});
it("keeps a preference after a conflict until explicit retry without changing recent session", async () => {
  let patches = 0; let server = { ...ws, version: 0 };
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") {
      const body = JSON.parse(String(init.body)); patches++;
      if (patches === 1) { server = { ...server, version: 1 }; return Promise.resolve(response({ detail: "conflict" }, 409)); }
      server = { ...server, ...body, version: body.expected_version + 1 }; return Promise.resolve(response(server));
    }
    if (url === "/api/workspace-state") return Promise.resolve(response(server));
    return Promise.resolve(response(url.startsWith("/api/sessions?") ? group : url.startsWith("/api/knowledge") ? [] : { items: [], next_cursor: null }));
  });
  vi.stubGlobal("fetch", fetcher); mount("/knowledge");
  await waitFor(() => expect(workspaceStore.getSnapshot().workspace.version).toBe(0));
  fireEvent.click(screen.getByRole("button", { name: "收起会话导航" }));
  const retry = await screen.findByRole("button", { name: "重试保存界面偏好" });
  expect(workspaceStore.getSnapshot().sidebar.collapsed).toBe(true); expect(patches).toBe(1);
  fireEvent.click(retry); await waitFor(() => expect(workspaceStore.getSnapshot().workspace.prefs.dirtyFields).toEqual([]));
  expect(patches).toBe(2); expect(server.last_session_id).toBe("A");
});
it("waits for an unconfirmed preference on logout and reports it separately on failure", async () => {
  const pending = deferred<Response>();
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") return pending.promise;
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    return Promise.resolve(response(url.startsWith("/api/sessions?") ? group : url.startsWith("/api/knowledge") ? [] : { items: [], next_cursor: null }));
  }));
  mount("/knowledge"); await waitFor(() => expect(workspaceStore.getSnapshot().workspace.version).toBe(0));
  void workspaceController.savePreference(0.8); const ticket = workspaceStore.captureTicket();
  let settled = false; const result = workspaceController.flushAll(ticket).then(value => { settled = true; return value; });
  await act(async () => { await Promise.resolve(); }); expect(settled).toBe(false);
  await act(async () => { pending.resolve(response({}, 503)); });
  const report = await result; expect(report.ok).toBe(false);
  expect(report.items).toContainEqual({ kind: "preferences", sessionId: null, ok: false });
  expect(workspaceStore.getSnapshot().workspace.prefs.localValues.progressYRatio).toBe(0.8);
});
it("retries a failed preference initialization without navigating or writing a recent session", async () => {
  let reads = 0;
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method !== "PATCH") return Promise.resolve(++reads === 1 ? response({}, 503) : response({ ...ws, sidebar_pinned: false, sidebar_collapsed: true }));
    return Promise.resolve(response(url.startsWith("/api/sessions?") ? group : url.startsWith("/api/knowledge") ? [] : { items: [], next_cursor: null }));
  });
  vi.stubGlobal("fetch", fetcher); mount("/knowledge");
  fireEvent.click(await screen.findByRole("button", { name: "重试加载界面偏好" }));
  await waitFor(() => expect(workspaceStore.getSnapshot().sidebar.collapsed).toBe(true));
  expect(fetcher.mock.calls.some(([url, init]) => String(url) === "/api/workspace-state" && init?.method === "PATCH")).toBe(false);
});
it("queues a new preference behind an in-flight recent-session save", async () => {
  const first = deferred<Response>(); const writes: Record<string, unknown>[] = []; let server = { ...ws };
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") {
      const body = JSON.parse(String(init.body)); writes.push(body);
      if (writes.length === 1) return first.promise;
      server = { ...server, ...body, version: body.expected_version + 1 }; return Promise.resolve(response(server));
    }
    if (url === "/api/workspace-state") return Promise.resolve(response(server));
    return Promise.resolve(response(url.startsWith("/api/sessions?") ? group : url.startsWith("/api/knowledge") ? [] : { items: [], next_cursor: null }));
  }));
  mount("/knowledge"); await waitFor(() => expect(workspaceStore.getSnapshot().workspace.version).toBe(0));
  workspaceController.selectSession("B"); await waitFor(() => expect(writes).toHaveLength(1));
  void workspaceController.savePreference(0.25);
  server = { ...server, last_session_id: "B", version: 1 };
  await act(async () => { first.resolve(response(server)); });
  await waitFor(() => expect(writes).toHaveLength(2));
  await waitFor(() => expect(workspaceStore.getSnapshot().workspace.prefs.dirtyFields).toEqual([]));
  expect(writes).toEqual([{ expected_version: 0, last_session_id: "B" }, { expected_version: 1, progress_y_ratio: 0.25 }]);
  expect(workspaceStore.getSnapshot().workspace.lastSessionId).toBe("B");
});
it("waits for a successful preference save before normal logout completes", async () => {
  const pending = deferred<Response>();
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/workspace-state" && init?.method === "PATCH") return pending.promise;
    if (url === "/api/workspace-state") return Promise.resolve(response(ws));
    return Promise.resolve(response(url.startsWith("/api/sessions?") ? group : url.startsWith("/api/knowledge") ? [] : { items: [], next_cursor: null }));
  }));
  mount("/knowledge"); await waitFor(() => expect(workspaceStore.getSnapshot().workspace.version).toBe(0));
  void workspaceController.savePreference(0.8); const ticket = workspaceStore.captureTicket();
  let settled = false; const result = workspaceController.flushAll(ticket).then(value => { settled = true; return value; });
  await act(async () => { await Promise.resolve(); }); expect(settled).toBe(false);
  await act(async () => { pending.resolve(response({ ...ws, progress_y_ratio: 0.8, version: 1 })); });
  expect((await result).ok).toBe(true);
  expect(workspaceStore.getSnapshot().workspace.prefs.dirtyFields).toEqual([]);
});
