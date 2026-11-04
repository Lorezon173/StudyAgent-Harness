// @vitest-environment jsdom
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import App from "../../App";
import { AuthProvider, useAuth } from "../../store/auth";
import { workspaceStore } from "../../store/workspace";
import { deferred, mockViewport, profile, response, session, storeIdentity } from "../../test/setup";
const groups = { groups: [{ group_key: "p1", profile: profile(), summary: null, sessions: [session("A"), session("B")], next_session_cursor: null }], next_group_cursor: null };
function Controls() { const auth = useAuth(); const navigate = useNavigate(); const location = useLocation(); return <><output data-testid="location">{location.pathname}</output><button onClick={() => navigate("/chat")}>返回默认会话</button><button onClick={() => navigate(-1)}>浏览器后退</button><button onClick={() => auth.login(2, "用户2", "B")}>切换账号B</button><button onClick={() => auth.login(1, "用户1", "A")}>重新登录A</button></>; }
function mount(path = "/chat") { storeIdentity(); return render(<AuthProvider><MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><Controls /><App /></MemoryRouter></AuthProvider>); }
const workspace = { last_session_id: null, sidebar_pinned: true, sidebar_collapsed: false, progress_y_ratio: 0.5, version: 0, updated_at: null };
const snapshot = (id: string) => ({ session: session(id), profile: profile(), profile_summary: null, teaching_state: null, teaching_state_source: "stored", view_state: { draft: "", reading_anchor: null, version: 0, updated_at: null }, pending_requests: [], messages: { items: [{ id: id === "A" ? 1 : 2, role: "assistant", content: `真实历史 ${id}`, turn_index: 0, created_at: null }], next_cursor: null } });
function transport() { vi.stubGlobal("fetch", vi.fn((url: RequestInfo | URL, init?: RequestInit) => { const path = String(url); if (path === "/api/workspace-state" && init?.method === "PATCH") { const body = JSON.parse(String(init.body)); return Promise.resolve(response({ ...workspace, last_session_id: body.last_session_id, version: body.expected_version + 1 })); } if (path === "/api/workspace-state") return Promise.resolve(response(workspace)); if (path.startsWith("/api/sessions/A/snapshot")) return Promise.resolve(response(snapshot("A"))); if (path.startsWith("/api/sessions/B/snapshot")) return Promise.resolve(response(snapshot("B"))); return Promise.resolve(response(path.startsWith("/api/sessions?") ? groups : path.startsWith("/api/topic-profiles") ? { items: [], next_cursor: null } : [])); })); }
it.each(["/chat", "/chat/A", "/knowledge", "/profile"])("shares one navigation and keeps account below session groups on %s", async path => {
  transport(); mount(path);
  const sidebar = await screen.findByRole("complementary", { name: "会话导航" });
  expect(screen.getAllByRole("navigation")).toHaveLength(1);
  const nav = screen.getByRole("navigation", { name: "工作区导航" });
  expect(within(nav).getByRole("link", { name: "知识库" })).toBeTruthy();
  expect(within(nav).getByRole("link", { name: "学习画像" })).toBeTruthy();
  expect(within(sidebar).queryByRole("link", { name: "知识库" })).toBeNull();
  expect(within(sidebar).getByRole("button", { name: "账号：用户1" }).closest("footer")).toBeTruthy();
});
it("starts pinned, collapses manually, pins open and keeps selection open", async () => {
  transport(); mount(); await screen.findByRole("button", { name: "会话 A" });
  expect(workspaceStore.getSnapshot().sidebar).toMatchObject({ pinned: true, collapsed: false });
  fireEvent.click(screen.getByRole("button", { name: "收起会话导航" }));
  expect(workspaceStore.getSnapshot().sidebar).toMatchObject({ pinned: false, collapsed: true });
  expect(screen.queryByRole("complementary", { name: "会话导航" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "展开会话导航" }));
  fireEvent.click(screen.getByRole("button", { name: "固定侧栏，保持展开" }));
  fireEvent.click(screen.getByRole("button", { name: "会话 A" }));
  await waitFor(() => expect(workspaceStore.getSnapshot().activeSessionId).toBe("A"));
  expect(workspaceStore.getSnapshot().sidebar).toMatchObject({ pinned: true, collapsed: false });
  expect(screen.getByRole("button", { name: "会话 A" }).getAttribute("aria-current")).toBe("true");
  fireEvent.click(screen.getByRole("button", { name: "返回默认会话" }));
  await waitFor(() => expect(workspaceStore.getSnapshot().activeSessionId).toBeNull());
  expect(workspaceStore.getSnapshot().buckets.A).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "浏览器后退" }));
  await waitFor(() => expect(workspaceStore.getSnapshot().activeSessionId).toBe("A"));
  expect(screen.getByRole("button", { name: "会话 A" }).getAttribute("aria-current")).toBe("true");
  await screen.findByText("真实历史 A");
  expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes("/A/snapshot"))).toBe(true);
});
it.each([481, 760])("keeps a separate desktop sidebar at width %s", async width => {
  mockViewport(width); transport(); mount();
  const sidebar = await screen.findByRole("complementary", { name: "会话导航" });
  expect(sidebar.getAttribute("data-mode")).toBe("desktop");
});
it("uses only <=480 as a drawer, retains it on selection and closes it with Escape", async () => {
  mockViewport(480); transport(); mount(); await waitFor(() => expect(workspaceStore.getSnapshot().groupsLoad.status).toBe("ready"));
  expect(screen.queryByRole("complementary", { name: "会话导航" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "打开会话导航" }));
  expect(screen.getByRole("complementary", { name: "会话导航" }).getAttribute("data-mode")).toBe("mobile");
  fireEvent.click(screen.getByRole("button", { name: "会话 A" }));
  expect(workspaceStore.getSnapshot().sidebar.mobileOpen).toBe(true);
  fireEvent.keyDown(window, { key: "Escape" });
  expect(screen.queryByRole("complementary", { name: "会话导航" })).toBeNull();
  expect(workspaceStore.getSnapshot().sidebar.pinned).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "打开会话导航" }));
  fireEvent.click(screen.getByRole("button", { name: "关闭会话导航遮罩" }));
  expect(workspaceStore.getSnapshot().sidebar.mobileOpen).toBe(false);
  expect(workspaceStore.getSnapshot().sidebar.pinned).toBe(true);
});
it("opens the real account actions and logs out without a saved-state claim", async () => {
  transport(); mount(); await screen.findByRole("button", { name: "会话 A" });
  fireEvent.click(screen.getByRole("button", { name: "账号：用户1" })); fireEvent.click(screen.getByRole("button", { name: "退出登录" }));
  await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/login"));
  expect(localStorage.getItem("studyagent_token")).toBeNull(); expect(workspaceStore.getSnapshot().groups).toEqual([]);
  expect(screen.queryByText("已保存")).toBeNull();
});
it.each(["切换账号B", "重新登录A"])("does not refill groups with a delayed previous generation after %s", async action => {
  const ownerId = action === "切换账号B" ? 2 : 1;
  const old = deferred<Response>(); let calls = 0; const tickets: ReturnType<typeof workspaceStore.captureTicket>[] = [];
  vi.stubGlobal("fetch", vi.fn((url: RequestInfo | URL) => { if (String(url) === "/api/workspace-state") return Promise.resolve(response(workspace)); tickets.push(workspaceStore.captureTicket()); return ++calls === 1 ? old.promise : Promise.resolve(response({ groups: [{ group_key: "p2", profile: { ...profile("p2", "新代主题"), user_id: ownerId }, summary: null, sessions: [{ ...session("new", "p2"), user_id: ownerId }], next_session_cursor: null }], next_group_cursor: null })); }));
  mount(); await waitFor(() => expect(calls).toBe(1));
  expect(tickets[0]).toMatchObject({ userId: 1, token: "A" });
  fireEvent.click(screen.getByRole("button", { name: action }));
  await screen.findByRole("button", { name: "会话 new" });
  await act(async () => { old.resolve(response(groups)); });
  expect(screen.queryByRole("button", { name: "会话 A" })).toBeNull();
  expect(workspaceStore.getSnapshot().groups.map(g => g.group_key)).toEqual(["p2"]);
  expect(tickets[1].generation).toBe(tickets[0].generation + 1);
});
it("loads selected URL histories independently from their real snapshots", async () => {
  transport(); mount("/chat/A"); await screen.findByText("真实历史 A");
  fireEvent.click(screen.getByRole("button", { name: "会话 B" }));
  await screen.findByText("真实历史 B");
  expect(screen.queryByText("真实历史 A")).toBeNull();
  expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes("/B/snapshot"))).toBe(true);
});

it('carries the verified current session and profile to the portrait link', async () => {
  transport(); mount('/chat/A'); await screen.findByText('真实历史 A');
  const link = screen.getByRole('link', { name: '学习画像' });
  expect(link.getAttribute('href')).toBe('/profile?profile_id=p1&session_id=A');
});

