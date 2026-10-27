// @vitest-environment jsdom
import { StrictMode, useEffect } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "./auth";
import { workspaceStore } from "./workspace";
import { apiGet } from "../api/client";
import { deferred, response, storeIdentity } from "../test/setup";
function Probe({ onMount }: { onMount?: () => void }) {
  const auth = useAuth(); useEffect(() => { onMount?.(); }, []);
  return <><output>{auth.userId ?? "anonymous"}:{auth.token ?? "none"}</output><button onClick={() => auth.login(1, "用户1", "A")}>登录A</button><button onClick={() => auth.login(1, "用户1", "A2")}>换token</button><button onClick={() => auth.login(2, "用户2", "B")}>登录B</button><button onClick={auth.logout}>退出</button></>;
}
it("bootstraps synchronously before child requests and StrictMode does not advance the same fingerprint", async () => {
  storeIdentity(); const seen: { userId: number | null; generation: number; token: string | null }[] = [];
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response([])));
  render(<StrictMode><AuthProvider><Probe onMount={() => { seen.push(workspaceStore.captureTicket()); void apiGet("/api/sessions"); }} /></AuthProvider></StrictMode>);
  await waitFor(() => expect(seen.length).toBeGreaterThan(0));
  expect(seen.every(ticket => ticket.userId === 1 && ticket.token === "A")).toBe(true);
  expect(new Set(seen.map(ticket => ticket.generation)).size).toBe(1);
  expect(screen.getByText("1:A")).toBeTruthy();
});
it.each(["登录B", "换token", "登录A"])("discards delayed old 401 after %s and a new request still succeeds", async (action) => {
  storeIdentity(); render(<AuthProvider><Probe /></AuthProvider>);
  const oldGeneration = workspaceStore.getSnapshot().account.generation;
  const delayed = deferred<Response>(); vi.stubGlobal("fetch", vi.fn().mockReturnValueOnce(delayed.promise).mockResolvedValue(response({ ok: true })));
  const pending = apiGet("/api/sessions").catch(error => error);
  fireEvent.click(screen.getByText(action));
  expect(workspaceStore.getSnapshot().account.generation).toBe(oldGeneration + 1);
  const expected = action === "登录B" ? "B" : action === "换token" ? "A2" : "A";
  await act(async () => { delayed.resolve(response({ detail: "expired" }, 401)); await pending; });
  expect(localStorage.getItem("studyagent_token")).toBe(expected);
  expect(screen.getByText(`${action === "登录B" ? 2 : 1}:${expected}`)).toBeTruthy();
  await expect(apiGet("/api/sessions")).resolves.toEqual({ ok: true });
});
it("current 401 clears React auth, storage and workspace together", async () => {
  storeIdentity(); render(<AuthProvider><Probe /></AuthProvider>);
  const generation = workspaceStore.getSnapshot().account.generation;
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ detail: "expired" }, 401)));
  await act(async () => { await apiGet("/api/sessions").catch(() => {}); });
  expect(screen.getByText("anonymous:none")).toBeTruthy();
  expect(localStorage.getItem("studyagent_token")).toBeNull();
  expect(workspaceStore.getSnapshot().account.generation).toBe(generation + 1);
  fireEvent.click(screen.getByText("登录A")); const next = workspaceStore.getSnapshot().account.generation;
  fireEvent.click(screen.getByText("退出"));
  expect(workspaceStore.getSnapshot().account.generation).toBe(next + 1);
});
