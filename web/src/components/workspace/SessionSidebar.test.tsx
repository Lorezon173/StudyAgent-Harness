// @vitest-environment jsdom
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import App from "../../App";
import { AuthProvider } from "../../store/auth";
import { workspaceStore } from "../../store/workspace";
import { deferred, profile, response, session, storeIdentity } from "../../test/setup";
const group = (id: string, ids: string[], cursor: string | null) => ({ group_key: id, profile: profile(id, "同名主题"), summary: null, sessions: ids.map(sid => session(sid, id)), next_session_cursor: cursor });
function mount() { storeIdentity(); render(<AuthProvider><MemoryRouter initialEntries={["/chat"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><App /></MemoryRouter></AuthProvider>); }
it("keeps same-name groups and their concurrent pages independent, deduplicates sessions and preserves root pagination", async () => {
  const a = deferred<Response>(); let bAttempts = 0;
  const fetcher = vi.fn((url: RequestInfo | URL) => {
    const query = new URL(String(url), "https://test").searchParams;
    if (query.get("group_key") === "p1") return a.promise;
    if (query.get("group_key") === "p2") return Promise.resolve(++bAttempts === 1 ? response({ detail: "B页加载失败" }, 500) : response({ groups: [group("p2", ["b", "b2"], null)], next_group_cursor: null }));
    if (query.get("cursor") === "ROOT") return Promise.resolve(response({ groups: [group("p3", [], null)], next_group_cursor: null }));
    return Promise.resolve(response({ groups: [group("p1", ["a"], "A"), group("p2", ["b"], "B")], next_group_cursor: "ROOT" }));
  }); vi.stubGlobal("fetch", fetcher); mount();
  await screen.findByRole("button", { name: "会话 a" });
  const regions = screen.getAllByRole("region", { name: "主题：同名主题" }); expect(regions).toHaveLength(2);
  fireEvent.click(within(regions[0]).getByRole("button", { name: "加载更多会话" }));
  fireEvent.click(within(regions[1]).getByRole("button", { name: "加载更多会话" }));
  await within(regions[1]).findByRole("alert");
  expect(within(regions[0]).getByRole("status").textContent).toContain("正在加载");
  expect(within(regions[1]).getByRole("button", { name: "会话 b" })).toBeTruthy();
  await act(async () => { a.resolve(response({ groups: [group("p1", ["a", "a2"], "A-next")], next_group_cursor: null })); });
  expect(within(regions[0]).getAllByRole("button", { name: "会话 a" })).toHaveLength(1);
  expect(within(regions[0]).getByRole("button", { name: "会话 a2" })).toBeTruthy();
  expect(workspaceStore.getSnapshot().nextGroupCursor).toBe("ROOT");
  expect(workspaceStore.getSnapshot().groupPages.p2.nextSessionCursor).toBe("B");
  fireEvent.click(within(regions[1]).getByRole("button", { name: "重试加载会话" }));
  await within(regions[1]).findByRole("button", { name: "会话 b2" });
  fireEvent.click(screen.getByRole("button", { name: "加载更多主题" }));
  await waitFor(() => expect(workspaceStore.getSnapshot().groups).toHaveLength(3));
  const pageQueries = fetcher.mock.calls.map(([url]) => new URL(String(url), "https://test").searchParams);
  expect(pageQueries.some(query => query.get("group_key") === "p1" && query.get("session_cursor") === "A" && !query.has("cursor"))).toBe(true);
  expect(pageQueries.some(query => query.get("cursor") === "ROOT" && !query.has("session_cursor") && !query.has("group_key"))).toBe(true);
});
it("distinguishes loading, root failure, retry and confirmed empty data", async () => {
  const first = deferred<Response>(); vi.stubGlobal("fetch", vi.fn().mockReturnValueOnce(first.promise).mockResolvedValue(response({ groups: [], next_group_cursor: null })));
  mount(); expect(await screen.findByRole("status")).toBeTruthy();
  expect(screen.queryByText("还没有学习主题")).toBeNull();
  await act(async () => { first.resolve(response({ detail: "主题加载失败" }, 500)); });
  expect(await screen.findByRole("alert")).toBeTruthy(); expect(screen.queryByText("还没有学习主题")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "重试加载主题" }));
  await screen.findByText("还没有学习主题");
});
it("shows honest empty and unassigned groups and supports accessible expand/collapse", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ groups: [group("p1", [], null), { group_key: "unassigned", profile: null, summary: null, sessions: [{ ...session("old"), profile_id: null }], next_session_cursor: null }], next_group_cursor: null })));
  mount(); await screen.findByText("这个主题还没有会话");
  const toggle = screen.getByRole("button", { name: "切换主题：同名主题" }); expect(toggle.getAttribute("aria-expanded")).toBe("true");
  fireEvent.click(toggle); expect(toggle.getAttribute("aria-expanded")).toBe("false");
  expect(screen.queryByText("这个主题还没有会话")).toBeNull();
  expect(screen.getByRole("button", { name: "切换主题：历史待整理" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "会话 old" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "会话 old" }).getAttribute("aria-current")).toBe("true"));
});
