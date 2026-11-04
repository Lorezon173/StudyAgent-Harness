// @vitest-environment jsdom
import { StrictMode, useEffect } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "./auth";
import { workspaceStore } from "./workspace";
import { apiGet } from "../api/client";
import { deferred, response, storeIdentity } from "../test/setup";
import { getLocalRecovery } from "./localRecovery";
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
it.each(["登录A", "登录B"])("backs up unsaved content before %s clears the old account", action => {
  storeIdentity(); render(<AuthProvider><Probe /></AuthProvider>);
  workspaceStore.ensureSessionBucket("old"); const ticket = workspaceStore.captureTicket();
  workspaceStore.patchBucket(ticket, "old", value => ({ ...value, draft: "尚未保存", draftRevision: 1, save: { ...value.save, status: "dirty", viewVersion: 0 } }));
  fireEvent.click(screen.getByText(action));
  expect(getLocalRecovery().list(1, "old", "draft").some(candidate => candidate.draft === "尚未保存")).toBe(true);
  expect(getLocalRecovery().list(2, "old", "draft")).toEqual([]);
});
it("backs up a dirty draft before the current protected request invalidates authentication", async () => {
  storeIdentity(); render(<AuthProvider><Probe /></AuthProvider>);
  workspaceStore.ensureSessionBucket("old"); const ticket = workspaceStore.captureTicket();
  workspaceStore.patchBucket(ticket, "old", value => ({ ...value, draft: "401前的草稿", draftRevision: 1, save: { ...value.save, status: "dirty", viewVersion: 0 } }));
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ detail: "expired" }, 401)));
  await act(async () => { await apiGet("/api/sessions").catch(() => {}); });
  expect(screen.getByText("anonymous:none")).toBeTruthy();
  expect(getLocalRecovery().list(1, "old", "draft").some(candidate => candidate.draft === "401前的草稿")).toBe(true);
});
it("clears invalid credentials even when saving a recovery copy fails", async () => {
  storeIdentity(); render(<AuthProvider><Probe /></AuthProvider>);
  workspaceStore.ensureSessionBucket("old"); const ticket = workspaceStore.captureTicket();
  workspaceStore.patchBucket(ticket, "old", value => ({ ...value, draft: "未确认", draftRevision: 1, save: { ...value.save, status: "dirty", viewVersion: 0 } }));
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new DOMException("disabled", "SecurityError"); });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ detail: "expired" }, 401)));
  await act(async () => { await apiGet("/api/sessions").catch(() => {}); });
  expect(screen.getByText("anonymous:none")).toBeTruthy();
  expect(localStorage.getItem("studyagent_token")).toBeNull();
  expect(workspaceStore.recoveryWarning()).toBe(true);
});
it("backs up both the original prepared question and an unresolved request before changing account", () => {
  storeIdentity(); render(<AuthProvider><Probe /></AuthProvider>);
  workspaceStore.ensureSessionBucket("old"); const ticket = workspaceStore.captureTicket();
  workspaceStore.patchBucket(ticket, "old", value => ({ ...value, prepared: { p1: { text: "最初的问题", sequence: 1 } }, localRequests: { r1: { payload: { message: "未确认问题", session_id: "old", profile_id: "p1", request_id: "r1", expected_state_version: 0 }, baseline: 3 } }, draft: "后续编辑", draftRevision: 2, save: { ...value.save, status: "dirty", viewVersion: 0 } }));
  fireEvent.click(screen.getByText("登录B"));
  const recovery = getLocalRecovery();
  expect(recovery.list(1, "old", "prepared").some(candidate => candidate.text === "最初的问题")).toBe(true);
  expect(recovery.list(1, "old", "request").some(candidate => (candidate.payload as {message?: string})?.message === "未确认问题")).toBe(true);
  expect(recovery.list(1, "old", "draft").some(candidate => candidate.draft === "后续编辑")).toBe(true);
  expect(recovery.list(2, "old", "prepared")).toEqual([]);
});
it("refuses to claim existing recovery candidates are safe when they cannot be read back", () => {
  storeIdentity(); render(<AuthProvider><Probe /></AuthProvider>);
  workspaceStore.ensureSessionBucket("old"); const ticket = workspaceStore.captureTicket();
  const written = getLocalRecovery().writePrepared(1, "old", "p1", { text: "待保留", sequence: 1 }); expect(written.ok).toBe(true);
  if (!written.ok) return;
  workspaceStore.patchBucket(ticket, "old", value => ({ ...value, preparedCandidates: [written.candidate] }));
  const original = Storage.prototype.getItem;
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (this: Storage, key: string) { if (key.startsWith("studyagent:recovery:")) throw new Error("unavailable"); return original.call(this, key); });
  const report = workspaceStore.prepareAccountTransition(ticket);
  expect(report.ok).toBe(false);
  expect(report.items).toEqual(expect.arrayContaining([expect.objectContaining({ kind: "prepared", sessionId: "old", ok: false })]));
});
