import { describe, expect, it } from "vitest";
import { createWorkspaceStore } from "./workspace";
import { ProfileItem, RequestSnapshot, SessionGroup, WorkspaceSession } from "../types";
const profile = (id: string): ProfileItem => ({ id, user_id: 1, name: "同名主题", scope_description: "", kind: "manual", revision: 0, created_at: "2026-10-27T00:00:00Z", updated_at: "2026-10-27T00:00:00Z" });
const session = (id: string, pid = "p1"): WorkspaceSession => ({ session_id: id, user_id: 1, title: id, profile_id: pid, active_node_id: null, state_version: 0, next_turn_index: 0, active_request_id: null, created_at: null, updated_at: null });
const group = (id: string, ids: string[], cursor: string | null = null): SessionGroup => ({ group_key: id, profile: profile(id), summary: null, sessions: ids.map(id2 => session(id2, id)), next_session_cursor: cursor });

describe("workspace account and session isolation", () => {
  it("never lets an old running request overwrite a completed attempt or a newer retry", () => {
    const store = createWorkspaceStore(); store.startAccount(1, "A"); store.ensureSessionBucket("s"); const ticket = store.captureTicket();
    const base: RequestSnapshot = { user_id: 1, session_id: "s", request_id: "r", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "running", lease_until: null, lease_expired: false, error_code: null, response_json: null, created_at: "", updated_at: "" };
    expect(store.mergeRequest(ticket, base)).toBe(true);
    expect(store.mergeRequest(ticket, { ...base, status: "completed", response_json: { session_id: "s", request_id: "r", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" } })).toBe(true);
    expect(store.mergeRequest(ticket, base)).toBe(false);
    expect(store.getSnapshot().buckets.s.requests.r.snapshot.status).toBe("completed");
    const next = { ...base, request_id: "r2", status: "failed", attempt: 2 };
    expect(store.mergeRequest(ticket, next)).toBe(true);
    expect(store.mergeRequest(ticket, { ...next, status: "running", attempt: 3 })).toBe(true);
    expect(store.mergeRequest(ticket, next)).toBe(false);
    expect(store.getSnapshot().buckets.s.requests.r2.snapshot.attempt).toBe(3);
  });
  it("accepts an identical completed observation without undoing its association", () => {
    const store = createWorkspaceStore(); store.startAccount(1, "A"); store.ensureSessionBucket("s"); const ticket = store.captureTicket();
    const completed: RequestSnapshot = { user_id: 1, session_id: "s", request_id: "r", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "p1", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "completed", lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: "s", request_id: "r", status: "completed", attempt: 1, persisted: true, state_version: 1, reply: "答案" }, created_at: "", updated_at: "" };
    expect(store.mergeRequest(ticket, completed)).toBe(true);
    store.patchBucket(ticket, "s", value => ({ ...value, requests: { ...value.requests, r: { ...value.requests.r, association: "matched" } } }));
    expect(store.mergeRequest(ticket, completed)).toBe(true);
    expect(store.getSnapshot().buckets.s.requests.r.association).toBe("matched");
  });
  it("rejects a request whose payload identity disagrees with its authoritative fields", () => {
    const store = createWorkspaceStore(); store.startAccount(1, "A"); store.ensureSessionBucket("s"); const ticket = store.captureTicket();
    const invalid: RequestSnapshot = { user_id: 1, session_id: "s", request_id: "r", profile_id: "p1", active_node_id: null, request_payload: { message: "问题", profile_id: "other", active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: "running", lease_until: null, lease_expired: false, error_code: null, response_json: null, created_at: "", updated_at: "" };
    expect(store.mergeRequest(ticket, invalid)).toBe(false);
    expect(store.getSnapshot().buckets.s.requests.r).toBeUndefined();
  });
  it("bootstraps idempotently but every explicit login/logout advances generation", () => {
    const store = createWorkspaceStore(); store.bootstrapAccount(1, "A");
    const first = store.captureTicket(); store.bootstrapAccount(1, "A");
    expect(store.getSnapshot().account.generation).toBe(first.generation);
    store.startAccount(1, "A"); expect(store.getSnapshot().account.generation).toBe(first.generation + 1);
    expect(store.isCurrent(first)).toBe(false);
    store.clearAccount(); expect(store.getSnapshot().account.generation).toBe(first.generation + 2);
  });
  it("keeps A and B buckets, drafts and late responses independent of the active session", () => {
    const store = createWorkspaceStore(); store.startAccount(1, "A");
    expect(store).toHaveProperty("ensureSessionBucket", expect.any(Function));
    store.ensureSessionBucket("A"); store.ensureSessionBucket("B");
    store.syncRouteSelection("A"); const ticket = store.beginSessionLoad("A");
    store.applySessionResult(store.captureTicket("A"), { draft: "A草稿" });
    store.syncRouteSelection("B");
    expect(store.applySessionResult(ticket, { messages: [{ id: 1, role: "assistant", content: "A回复", turn_index: 0, created_at: null }] })).toBe(true);
    expect(store.getSnapshot().buckets.B.messages).toEqual([]);
    expect(store.getSnapshot().buckets.A.draft).toBe("A草稿");
    expect(store.getSnapshot().buckets.A.messages[0].content).toBe("A回复");
    store.syncRouteSelection(null); expect(store.getSnapshot().activeSessionId).toBeNull();
    expect(store.getSnapshot().buckets.A.draft).toBe("A草稿");
  });
  it("rejects older loads, requests, absent buckets and previous accounts", () => {
    const store = createWorkspaceStore(); store.startAccount(1, "A");
    expect(store).toHaveProperty("beginSessionLoad", expect.any(Function));
    store.ensureSessionBucket("s"); const old = store.beginSessionLoad("s"); const newer = store.beginSessionLoad("s");
    expect(store.applySessionResult(old, { draft: "old" })).toBe(false);
    expect(store.applySessionResult(newer, { draft: "new" })).toBe(true);
    const firstRequest = store.beginSessionRequest("s", "r1"); store.beginSessionRequest("s", "r2");
    expect(store.applySessionResult(firstRequest, { draft: "old request" })).toBe(false);
    expect(store.applySessionResult(store.captureTicket("absent"), { draft: "invented" })).toBe(false);
    const beforeLogin = store.captureTicket("s"); store.startAccount(1, "A");
    expect(store.getSnapshot().buckets).toEqual({});
    expect(store.applySessionResult(beforeLogin, { draft: "old account" })).toBe(false);
  });
});
describe("independent root and group pagination", () => {
  it("preserves an exhausted group's null cursor when a root page repeats the group", () => {
    const store = createWorkspaceStore(); store.startAccount(1, "A");
    store.appendGroups(store.beginGroups(null)!, { groups: [group("p1", ["a"], "next")], next_group_cursor: "root" });
    store.appendGroupSessions(store.beginGroupPage("p1", "next")!, group("p1", ["a2"], null));
    store.appendGroups(store.beginGroups("root")!, { groups: [group("p1", ["a"], "stale")], next_group_cursor: null });
    expect(store.getSnapshot().groups[0].next_session_cursor).toBeNull();
    expect(store.getSnapshot().groupPages.p1.nextSessionCursor).toBeNull();
  });
  it("treats every URL session id as a dictionary key rather than an inherited property", () => {
    const store = createWorkspaceStore(); store.startAccount(1, "A");
    store.syncRouteSelection("constructor");
    expect(store.getSnapshot().buckets["constructor" as string].messages).toEqual([]);
    store.syncRouteSelection("__proto__");
    expect(store.getSnapshot().buckets["__proto__"].load.status).toBe("idle");
  });
  it("separates same-name profiles and concurrent group pages, preserving cursors and order", () => {
    const store = createWorkspaceStore(); store.startAccount(1, "A");
    expect(store).toHaveProperty("beginGroups", expect.any(Function));
    const root = store.beginGroups(null)!;
    store.appendGroups(root, { groups: [group("p1", ["a"], "A-page"), group("p2", ["b"], "B-page")], next_group_cursor: "ROOT-page" });
    expect(store.getSnapshot().groups).toHaveLength(2);
    expect(store.beginGroupPage("p1", "ROOT-page")).toBeNull();
    const a = store.beginGroupPage("p1", "A-page")!; const b = store.beginGroupPage("p2", "B-page")!;
    expect(store.beginGroupPage("p1", "A-page")).toBeNull();
    store.failGroupPage(b, "B加载失败");
    store.appendGroupSessions(a, group("p1", ["a", "a2"], "A-next"));
    expect(store.getSnapshot().groups[0].sessions.map(s => s.session_id)).toEqual(["a", "a2"]);
    expect(store.getSnapshot().groupPages.p2.error).toBe("B加载失败");
    expect(store.getSnapshot().groupPages.p2.nextSessionCursor).toBe("B-page");
    expect(store.getSnapshot().nextGroupCursor).toBe("ROOT-page");
    expect(store.getSnapshot().groupPages.p1.nextSessionCursor).toBe("A-next");
    const retry = store.beginGroupPage("p2", "B-page")!;
    expect(store.appendGroupSessions(b, group("p2", ["obsolete"], "bad"))).toBe(false);
    expect(store.appendGroupSessions(retry, group("p2", ["b", "b2"], null))).toBe(true);
    const nextRoot = store.beginGroups("ROOT-page")!;
    store.appendGroups(nextRoot, { groups: [group("p1", ["a"], "stale"), group("p3", [], null)], next_group_cursor: null });
    expect(store.getSnapshot().groups[0].sessions.map(s => s.session_id)).toEqual(["a", "a2"]);
    expect(store.getSnapshot().groupPages.p1.nextSessionCursor).toBe("A-next");
  });
  it("rejects late root and group results after another login", () => {
    const store = createWorkspaceStore(); store.startAccount(1, "A");
    expect(store).toHaveProperty("beginGroups", expect.any(Function));
    const ticket = store.beginGroups(null)!; store.startAccount(2, "B");
    expect(store.appendGroups(ticket, { groups: [group("p1", ["a"])], next_group_cursor: null })).toBe(false);
    expect(store.getSnapshot().groups).toEqual([]);
  });
});

it("keeps profile revision independent of teaching state and preserves its source", () => {
  const store = createWorkspaceStore(); store.startAccount(1, "A"); store.ensureSessionBucket("s");
  const snap = (revision: number, version: number, source: "stored" | "legacy") => ({ session: { ...session("s"), state_version: version }, profile: { ...profile("p1"), revision }, profile_summary: null, teaching_state: { version }, teaching_state_source: source, messages: { items: [], next_cursor: null }, view_state: { draft: "", reading_anchor: null, version: 0, updated_at: null }, pending_requests: [] });
  store.applySnapshot(store.beginSessionLoad("s"), snap(5, 2, "stored"));
  store.applySnapshot(store.beginSessionLoad("s"), snap(3, 3, "legacy"));
  expect(store.getSnapshot().buckets.s.profile?.revision).toBe(5);
  expect(store.getSnapshot().buckets.s.teachingStateSource).toBe("legacy");
  store.applySnapshot(store.beginSessionLoad("s"), snap(6, 1, "stored"));
  expect(store.getSnapshot().buckets.s.profileRevision).toBe(6);
  expect(store.getSnapshot().buckets.s.teachingStateSource).toBe("legacy");
  expect(store.getSnapshot().buckets.s.teachingStateVersion).toBe(3);
});
