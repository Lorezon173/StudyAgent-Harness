import { afterEach, beforeEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import { workspaceStore } from "../store/workspace";
import { ProfileItem, WorkspaceSession } from "../types";
export function deferred<T>() { let resolve!: (value: T) => void; let reject!: (reason: unknown) => void; const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
export const response = (body: unknown, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => body }) as Response;
export const profile = (id = "p1", name = "概率论"): ProfileItem => ({ id, name, user_id: 1, scope_description: "学习范围", kind: "manual", revision: 0, created_at: "2026-10-27T00:00:00Z", updated_at: "2026-10-27T00:00:00Z" });
export const session = (id = "s1", pid = "p1"): WorkspaceSession => ({ session_id: id, title: `会话 ${id}`, user_id: 1, profile_id: pid, active_node_id: null, state_version: 0, next_turn_index: 0, active_request_id: null, created_at: null, updated_at: null });
export function storeIdentity(id = 1, token = "A") { localStorage.setItem("studyagent_user_id", String(id)); localStorage.setItem("studyagent_username", `用户${id}`); localStorage.setItem("studyagent_token", token); }
export function mockViewport(width: number) {
  Object.defineProperty(window, "innerWidth", { configurable: true, value: width });
  Object.defineProperty(window, "matchMedia", { configurable: true, value: vi.fn((query: string) => ({ matches: query.includes("480") && width <= 480, media: query, onchange: null, addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn() })) });
}
beforeEach(() => {
  vi.restoreAllMocks(); localStorage.clear(); workspaceStore.clearAccount(); window.history.replaceState(null, "", "/login"); mockViewport(1200);
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); this.dispatchEvent(new Event("close")); };
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
