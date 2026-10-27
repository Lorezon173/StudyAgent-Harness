// @vitest-environment jsdom
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { MemoryRouter, useLocation } from "react-router-dom";
import App from "../../App";
import { AuthProvider, useAuth } from "../../store/auth";
import { workspaceStore } from "../../store/workspace";
import { deferred, profile, response, session, storeIdentity } from "../../test/setup";
let switchAccount: () => void;
function Probe() { const auth = useAuth(); const location = useLocation(); switchAccount = () => auth.login(2, "用户2", "B"); return <output data-testid="location">{location.pathname}</output>; }
function mockServer(post: (url: string, init: RequestInit) => Promise<Response>, more = false) {
  const fetcher = vi.fn((url: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === "POST") return post(String(url), init);
    if (String(url).startsWith("/api/topic-profiles")) return Promise.resolve(response({ items: [String(url).includes("cursor=") ? profile("p2", "第二页主题") : profile()], next_cursor: more && !String(url).includes("cursor=") ? "p+/=" : null }));
    return Promise.resolve(response({ groups: [], next_group_cursor: null }));
  }); vi.stubGlobal("fetch", fetcher); return fetcher;
}
async function open() { storeIdentity(); render(<AuthProvider><MemoryRouter initialEntries={["/chat"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><Probe /><App /></MemoryRouter></AuthProvider>); const trigger = await screen.findByRole("button", { name: "开启一段新的探索" }); trigger.focus(); fireEvent.click(trigger); const dialog = await screen.findByRole("dialog", { name: "从一个好问题开始" }); await within(dialog).findByRole("option", { name: "概率论" }); return { trigger, dialog }; }
const chooseNew = () => { fireEvent.change(screen.getByLabelText("所属主题画像"), { target: { value: "__new" } }); fireEvent.change(screen.getByLabelText("新主题名称"), { target: { value: "新主题" } }); fireEvent.change(screen.getByLabelText("学习范围"), { target: { value: "范围描述" } }); };
const submit = () => fireEvent.submit(screen.getByRole("form", { name: "新建会话" }));
it("loads real profile pages and rejects a forged option before POST", async () => {
  const fetcher = mockServer(async () => response(session()), true); await open();
  fireEvent.click(screen.getByRole("button", { name: "加载更多主题选项" })); await screen.findByRole("option", { name: "第二页主题" });
  const select = screen.getByLabelText("所属主题画像") as HTMLSelectElement; const rogue = new Option("伪造主题", "foreign"); select.add(rogue);
  fireEvent.change(select, { target: { value: "foreign" } }); submit();
  expect((await screen.findByRole("alert")).textContent).toContain("请选择本人主题");
  expect(fetcher.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0);
  expect(fetcher.mock.calls.some(([url]) => String(url).includes("cursor=p%2B%2F%3D"))).toBe(true);
});
it("creates from an existing profile with the real response id, protects double submit and adds no fake messages", async () => {
  const pending = deferred<Response>(); const fetcher = mockServer(() => pending.promise); await open();
  fireEvent.change(screen.getByLabelText("所属主题画像"), { target: { value: "p1" } });
  fireEvent.change(screen.getByLabelText("会话标题"), { target: { value: "真实标题" } });
  act(() => { submit(); submit(); });
  expect(fetcher.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
  expect(JSON.parse(fetcher.mock.calls.find(([, init]) => init?.method === "POST")![1]!.body as string)).toEqual({ profile_id: "p1", title: "真实标题", active_node_id: null });
  await act(async () => { pending.resolve(response({ ...session("real/id"), title: "真实标题" })); });
  await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/chat/real%2Fid"));
  expect(workspaceStore.getSnapshot().activeSessionId).toBe("real/id");
  expect(workspaceStore.getSnapshot().buckets["real/id"].messages).toEqual([]);
  expect(workspaceStore.getSnapshot().buckets["real/id"].load.status).toBe("idle");
  expect(screen.getByText("此会话的内容暂不可用")).toBeTruthy();
});
it("shows a real server 403 without inventing a successful session", async () => {
  mockServer(async () => response({ detail: { code: "forbidden", message: "无权访问此主题" } }, 403)); await open();
  fireEvent.change(screen.getByLabelText("所属主题画像"), { target: { value: "p1" } }); submit();
  expect((await screen.findByRole("alert")).textContent).toContain("无权访问此主题");
  expect((screen.getByLabelText("所属主题画像") as HTMLSelectElement).value).toBe("p1");
  expect(workspaceStore.getSnapshot().groups).toEqual([]); expect(screen.getByTestId("location").textContent).toBe("/chat");
});
it("uses ProfileDetail.profile.id and reuses the locked successful profile when session creation fails", async () => {
  let profilePosts = 0; let sessionPosts = 0; const bodies: unknown[] = [];
  mockServer(async (url, init) => {
    if (url === "/api/topic-profiles") { profilePosts++; return response({ profile: profile("created", "新主题"), profile_revision: 0, nodes: [], edges: [] }); }
    bodies.push(JSON.parse(init.body as string)); return ++sessionPosts === 1 ? response({ detail: "会话创建失败" }, 500) : response(session("created-session", "created"));
  }); await open(); chooseNew(); submit();
  await screen.findByRole("alert");
  expect((screen.getByLabelText("新主题名称") as HTMLInputElement).disabled).toBe(true);
  expect((screen.getByLabelText("学习范围") as HTMLTextAreaElement).disabled).toBe(true);
  submit(); await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/chat/created-session"));
  expect(profilePosts).toBe(1); expect(sessionPosts).toBe(2);
  expect(bodies).toEqual([{ profile_id: "created", title: "新会话", active_node_id: null }, { profile_id: "created", title: "新会话", active_node_id: null }]);
});
it("explicitly resets the binding before a changed theme can create another profile", async () => {
  let posts = 0; const selected: string[] = [];
  mockServer(async (url, init) => {
    if (url === "/api/topic-profiles") return response({ profile: profile(++posts === 1 ? "first" : "second", JSON.parse(init.body as string).name), profile_revision: 0, nodes: [], edges: [] });
    selected.push(JSON.parse(init.body as string).profile_id); return response({ detail: "会话创建失败" }, 500);
  }); await open(); chooseNew(); submit(); await screen.findByRole("alert");
  fireEvent.click(screen.getByRole("button", { name: "重新选择主题" }));
  expect((screen.getByLabelText("新主题名称") as HTMLInputElement).disabled).toBe(false);
  fireEvent.change(screen.getByLabelText("新主题名称"), { target: { value: "另一个主题" } }); submit();
  await waitFor(() => expect(selected).toEqual(["first", "second"])); expect(posts).toBe(2);
});
it("checks the generation between profile POST completion and session POST, even before React cleanup", async () => {
  const first = deferred<Response>(); let secondPosts = 0;
  mockServer(async url => { if (url === "/api/topic-profiles") return first.promise; secondPosts++; return response(session()); });
  await open(); chooseNew(); submit();
  await act(async () => { first.resolve({ ok: true, status: 200, json: async () => { switchAccount(); return { profile: profile("old-profile"), profile_revision: 0, nodes: [], edges: [] }; } } as Response); });
  await waitFor(() => expect(workspaceStore.getSnapshot().account.userId).toBe(2));
  expect(secondPosts).toBe(0); expect(localStorage.getItem("studyagent_token")).toBe("B");
  expect(screen.queryByDisplayValue("新主题")).toBeNull(); expect(screen.getByTestId("location").textContent).toBe("/chat");
});
it("drops a session result after account change and closes Escape/cancel back to the trigger", async () => {
  const pending = deferred<Response>(); mockServer(() => pending.promise); const { trigger, dialog } = await open();
  fireEvent(dialog, new Event("cancel", { bubbles: false, cancelable: true }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull()); expect(document.activeElement).toBe(trigger);
  fireEvent.click(trigger); await screen.findByRole("option", { name: "概率论" });
  fireEvent.change(screen.getByLabelText("所属主题画像"), { target: { value: "p1" } }); submit();
  act(() => switchAccount()); await act(async () => { pending.resolve(response(session("old-result"))); });
  expect(workspaceStore.getSnapshot().groups).toEqual([]); expect(screen.getByTestId("location").textContent).toBe("/chat");
});
