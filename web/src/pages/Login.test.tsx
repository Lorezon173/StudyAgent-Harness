// @vitest-environment jsdom
import { StrictMode } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import Login from "./Login";
import { AuthProvider, useAuth } from "../store/auth";
import { workspaceStore } from "../store/workspace";
import { apiGet } from "../api/client";
import { deferred, response, storeIdentity } from "../test/setup";
function Controls() { const navigate = useNavigate(); const location = useLocation(); const auth = useAuth(); return <><output data-testid="location">{location.pathname}</output><output data-testid="auth">{auth.userId}:{auth.token}</output><button onClick={() => navigate("/away")}>离开登录</button><button onClick={() => navigate("/login")}>重进登录</button></>; }
function mount() { return render(<StrictMode><AuthProvider><MemoryRouter initialEntries={["/login"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><Controls /><Routes><Route path="/login" element={<Login />} /><Route path="*" element={<p>其他页面</p>} /></Routes></MemoryRouter></AuthProvider></StrictMode>); }
function fill(name: string) { fireEvent.change(screen.getByPlaceholderText("用户名"), { target: { value: name } }); fireEvent.change(screen.getByPlaceholderText("密码"), { target: { value: "password" } }); }
function submit() { fireEvent.submit(screen.getByPlaceholderText("用户名").closest("form")!); }
it.each(["login", "register"])("preserves username/password protocol and completes normal %s exactly once", async mode => {
  const fetcher = vi.fn().mockResolvedValue(response({ user_id: 1, username: "甲", token: "TOKEN" })); vi.stubGlobal("fetch", fetcher); mount();
  if (mode === "register") fireEvent.click(screen.getByRole("button", { name: "注册" }));
  fill("甲"); const before = workspaceStore.getSnapshot().account.generation; submit();
  await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/chat"));
  expect(workspaceStore.getSnapshot().account.generation).toBe(before + 1);
  expect(localStorage.getItem("studyagent_token")).toBe("TOKEN");
  expect(fetcher.mock.calls[0][0]).toBe(`/api/auth/${mode}`);
  expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({ username: "甲", password: "password" });
});
it("rejects same-tick double submissions using a synchronous busy guard", async () => {
  const pending = deferred<Response>(); const fetcher = vi.fn(() => pending.promise); vi.stubGlobal("fetch", fetcher); mount(); fill("甲");
  act(() => { submit(); submit(); }); expect(fetcher).toHaveBeenCalledTimes(1);
  await act(async () => { pending.resolve(response({ detail: "稍后重试" }, 503)); });
  expect(await screen.findByRole("alert")).toBeTruthy(); expect(screen.queryByRole("button", { name: "提交中…" })).toBeNull();
});
it.each([["login", false], ["login", true], ["register", false], ["register", true]] as const)("shows a normal %s credential failure without changing generation (stored identity=%s)", async (mode, existing) => {
  if (existing) storeIdentity();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(response({ detail: "用户名或密码错误" }, 401)).mockResolvedValue(response({ user_id: 2, username: "乙", token: "B" })));
  mount(); if (mode === "register") fireEvent.click(screen.getByRole("button", { name: "注册" })); fill("乙"); const generation = workspaceStore.getSnapshot().account.generation; submit();
  expect((await screen.findByRole("alert")).textContent).toContain("用户名或密码错误");
  expect(screen.queryByRole("button", { name: "提交中…" })).toBeNull();
  expect(workspaceStore.getSnapshot().account.generation).toBe(generation);
  expect(workspaceStore.getSnapshot().account.userId).toBe(existing ? 1 : null);
  expect(screen.getByTestId("location").textContent).toBe("/login"); submit();
  await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/chat"));
  expect(workspaceStore.getSnapshot().account.generation).toBe(generation + 1);
});
it.each([true, false])("drops an unmounted A submission's delayed success=%s after B logs in", async success => {
  const a = deferred<Response>(); const fetcher = vi.fn().mockReturnValueOnce(a.promise).mockResolvedValue(response({ user_id: 2, username: "乙", token: "B" })); vi.stubGlobal("fetch", fetcher);
  mount(); fill("甲"); submit(); fireEvent.click(screen.getByRole("button", { name: "离开登录" })); fireEvent.click(screen.getByRole("button", { name: "重进登录" })); fill("乙"); submit();
  await waitFor(() => expect(screen.getByTestId("auth").textContent).toBe("2:B"));
  const before = workspaceStore.getSnapshot().account.generation;
  // An old continuation must not navigate back to /chat from this later location.
  fireEvent.click(screen.getByRole("button", { name: "离开登录" }));
  await act(async () => { a.resolve(success ? response({ user_id: 1, username: "甲", token: "A" }) : response({ detail: "A迟到错误" }, 401)); });
  expect(screen.getByTestId("auth").textContent).toBe("2:B"); expect(localStorage.getItem("studyagent_token")).toBe("B");
  expect(workspaceStore.getSnapshot().account.generation).toBe(before); expect(screen.getByTestId("location").textContent).toBe("/away");
});
it("does not let A's old catch/finally change the busy or error of B's new mount", async () => {
  const a = deferred<Response>(); const b = deferred<Response>(); vi.stubGlobal("fetch", vi.fn().mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise));
  mount(); fill("甲"); submit(); fireEvent.click(screen.getByRole("button", { name: "离开登录" })); fireEvent.click(screen.getByRole("button", { name: "重进登录" })); fill("乙"); submit();
  await act(async () => { a.resolve(response({ detail: "A迟到错误" }, 401)); });
  expect(screen.getByRole("button", { name: "提交中…" })).toBeTruthy(); expect(screen.queryByRole("alert")).toBeNull();
  await act(async () => { b.resolve(response({ user_id: 2, username: "乙", token: "B" })); });
  await waitFor(() => expect(screen.getByTestId("auth").textContent).toBe("2:B"));
});
it.each([true, false])("releases an invalidated mounted submission before it settles and isolates its late success=%s", async success => {
  storeIdentity(); const protectedResponse = deferred<Response>(); const oldLogin = deferred<Response>(); const newLogin = deferred<Response>();
  const fetcher = vi.fn().mockReturnValueOnce(protectedResponse.promise).mockReturnValueOnce(oldLogin.promise).mockReturnValueOnce(newLogin.promise); vi.stubGlobal("fetch", fetcher);
  mount(); const before = workspaceStore.getSnapshot().account.generation;
  const protectedCall = apiGet("/api/sessions").catch(() => undefined); fill("旧提交"); submit();
  await act(async () => { protectedResponse.resolve(response({ detail: "认证已过期" }, 401)); await protectedCall; });
  // The old login is still pending: releasing the lock must not depend on its finally.
  expect(screen.queryByRole("button", { name: "提交中…" })).toBeNull();
  expect((screen.getByPlaceholderText("用户名") as HTMLInputElement).disabled).toBe(false);
  expect(workspaceStore.getSnapshot().account.generation).toBe(before + 1);
  fill("新提交"); submit(); expect(fetcher).toHaveBeenCalledTimes(3);
  await act(async () => { oldLogin.resolve(success ? response({ user_id: 9, username: "旧提交", token: "OLD" }) : response({ detail: "旧错误" }, 401)); });
  expect(screen.getByRole("button", { name: "提交中…" })).toBeTruthy(); expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.getByTestId("auth").textContent).toBe(":"); expect(localStorage.getItem("studyagent_token")).toBeNull();
  expect(workspaceStore.getSnapshot().account.generation).toBe(before + 1); expect(screen.getByTestId("location").textContent).toBe("/login");
  await act(async () => { newLogin.resolve(response({ user_id: 2, username: "新提交", token: "NEW" })); });
  expect(screen.getByTestId("auth").textContent).toBe("2:NEW"); expect(localStorage.getItem("studyagent_token")).toBe("NEW");
  expect(workspaceStore.getSnapshot().account.generation).toBe(before + 2); expect(screen.getByTestId("location").textContent).toBe("/chat");
});
it("preserves a retry's error when an invalidated submission finishes later", async () => {
  storeIdentity(); const protectedResponse = deferred<Response>(); const oldLogin = deferred<Response>(); const retry = deferred<Response>();
  const fetcher = vi.fn().mockReturnValueOnce(protectedResponse.promise).mockReturnValueOnce(oldLogin.promise).mockReturnValueOnce(retry.promise).mockResolvedValue(response({ user_id: 2, username: "重试", token: "RETRY" })); vi.stubGlobal("fetch", fetcher);
  mount(); const protectedCall = apiGet("/api/sessions").catch(() => undefined); fill("旧提交"); submit();
  await act(async () => { protectedResponse.resolve(response({ detail: "认证已过期" }, 401)); await protectedCall; });
  expect(screen.queryByRole("button", { name: "提交中…" })).toBeNull(); fill("重试"); submit();
  await act(async () => { retry.resolve(response({ detail: "当前重试失败" }, 503)); });
  expect((await screen.findByRole("alert")).textContent).toBe("当前重试失败");
  await act(async () => { oldLogin.resolve(response({ detail: "旧提交失败" }, 401)); });
  expect(screen.getByRole("alert").textContent).toBe("当前重试失败"); expect(screen.queryByRole("button", { name: "提交中…" })).toBeNull();
  submit(); await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/chat"));
  expect(screen.getByTestId("auth").textContent).toBe("2:RETRY");
  expect(screen.getByTestId("location").textContent).toBe("/chat"); expect(fetcher).toHaveBeenCalledTimes(4);
});
it("keeps the active submission locked across same-generation workspace notifications", async () => {
  const pending = deferred<Response>(); const fetcher = vi.fn(() => pending.promise); vi.stubGlobal("fetch", fetcher); mount(); fill("甲"); submit();
  const generation = workspaceStore.getSnapshot().account.generation;
  act(() => { workspaceStore.collapseSidebar(); submit(); });
  expect(workspaceStore.getSnapshot().account.generation).toBe(generation); expect(fetcher).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("button", { name: "提交中…" })).toBeTruthy();
  await act(async () => { pending.resolve(response({ user_id: 1, username: "甲", token: "TOKEN" })); });
  expect(screen.getByTestId("auth").textContent).toBe("1:TOKEN"); expect(screen.getByTestId("location").textContent).toBe("/chat");
});
