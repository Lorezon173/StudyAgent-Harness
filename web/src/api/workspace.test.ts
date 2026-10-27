/// <reference types="vite/client" />
import { beforeEach, expect, it, vi } from "vitest";

const modules = import.meta.glob("./{sessions,profiles,workspace,knowledge}.ts");
const ownedProfile = { id: "p1", user_id: 1, name: "主题", scope_description: "范围", kind: "manual", revision: 0, created_at: "2026-10-27T00:00:00Z", updated_at: "2026-10-27T00:00:00Z" };
beforeEach(() => {
  vi.stubGlobal("localStorage", { getItem: () => null, removeItem: () => {} });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ groups: [], next_group_cursor: null }) }));
});
it("provides real workspace endpoint modules", () => {
  expect(Object.keys(modules).sort()).toEqual(["./knowledge.ts", "./profiles.ts", "./sessions.ts", "./workspace.ts"]);
});
it("keeps group cursor separate from the selected group's session cursor", async () => {
  expect(modules["./sessions.ts"]).toBeTypeOf("function");
  const api = await modules["./sessions.ts"]() as typeof import("./sessions");
  await api.listGroupedSessions({ cursor: "a+/=", groupLimit: 2, limit: 3 });
  const first = new URL(vi.mocked(fetch).mock.calls[0][0] as string, "https://test");
  expect(Object.fromEntries(first.searchParams)).toEqual({ group_by: "profile", cursor: "a+/=", group_limit: "2", limit: "3" });
  vi.mocked(fetch).mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ groups: [{ group_key: "p1", profile: ownedProfile, sessions: [], summary: null, next_session_cursor: null }], next_group_cursor: null }) } as Response);
  await api.listGroupSessions({ groupKey: "p1", sessionCursor: "b+/=" });
  const second = new URL(vi.mocked(fetch).mock.calls[1][0] as string, "https://test");
  expect(Object.fromEntries(second.searchParams)).toEqual({ group_by: "profile", group_key: "p1", session_cursor: "b+/=" });
  vi.mocked(fetch).mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ groups: [], next_group_cursor: null }) } as Response);
  await expect(api.listGroupSessions({ groupKey: "p1" })).rejects.toMatchObject({ code: "invalid_group_page" });
});
it.each([null, { groups: null, next_group_cursor: null }, { groups: [{ group_key: "p1", profile: { ...ownedProfile, id: "other" }, sessions: [], summary: null, next_session_cursor: null }], next_group_cursor: null }])("rejects a malformed or mismatched group page as a readable ApiError", async body => {
  const api = await modules["./sessions.ts"]() as typeof import("./sessions");
  vi.mocked(fetch).mockResolvedValueOnce({ ok: true, status: 200, json: async () => body } as Response);
  await expect(api.listGroupSessions({ groupKey: "p1" })).rejects.toMatchObject({ status: 200, code: "invalid_group_page", message: "会话分组数据不匹配" });
});
it("encodes path IDs and preserves the real create/patch request bodies", async () => {
  const ownedSession = { session_id: "a/b", user_id: 1, title: "新会话", profile_id: "p1", active_node_id: null, state_version: 0, next_turn_index: 0, active_request_id: null, created_at: null, updated_at: null };
  const view = { draft: "草稿", reading_anchor: null, version: 1, updated_at: null };
  const summary = { profile_revision: 0, nodes: [], edges: [], recent_evidence: [], assessed_count: 0, total_count: 0, mastery_score: null, metric_kind: "assessed_mean", assessment_coverage: null };
  const detail = { profile: ownedProfile, profile_revision: 0, nodes: [], edges: [] };
  vi.mocked(fetch).mockImplementation(async (url, init) => {
    const path = String(url);
    let body: unknown = [];
    if (path === "/api/sessions") body = ownedSession;
    else if (path.includes("/snapshot")) body = { session: ownedSession, teaching_state: null, teaching_state_source: "legacy", legacy_state: null, messages: { items: [], next_cursor: null }, profile: ownedProfile, profile_summary: summary, view_state: view, pending_requests: [] };
    else if (path.includes("/messages")) body = { items: [], next_cursor: null };
    else if (path.includes("/retry")) body = { reply: "真实协议测试回复", session_id: "a/b", persisted: true };
    else if (path.includes("/requests/")) body = { user_id: 1, session_id: "a/b", request_id: "r/x", profile_id: "p1", active_node_id: null, request_payload: {}, base_state_version: 0, attempt: 1, status: "failed", lease_until: null, lease_expired: true, error_code: "test", response_json: null, created_at: "2026-10-27T00:00:00Z", updated_at: "2026-10-27T00:00:00Z" };
    else if (path.includes("/view-state")) body = view;
    else if (path.startsWith("/api/topic-profiles?")) body = { items: [ownedProfile], next_cursor: null };
    else if (path.endsWith("/summary")) body = summary;
    else if (path.startsWith("/api/topic-profiles")) body = detail;
    else if (path === "/api/workspace-state") body = { last_session_id: null, sidebar_pinned: true, sidebar_collapsed: false, progress_y_ratio: .5, version: 1, updated_at: null };
    expect(init?.method).toBeTruthy();
    return { ok: true, status: 200, json: async () => body } as Response;
  });
  const sessions = await modules["./sessions.ts"]() as typeof import("./sessions");
  const profiles = await modules["./profiles.ts"]() as typeof import("./profiles");
  const workspace = await modules["./workspace.ts"]() as typeof import("./workspace");
  const knowledge = await modules["./knowledge.ts"]() as typeof import("./knowledge");
  await sessions.createSession({ profile_id: "p1", title: "新会话", active_node_id: null });
  await sessions.loadSnapshot("a/b", 20);
  await sessions.loadMessages("a/b", { cursor: "c+/=", limit: 10 });
  await sessions.getRequest("a/b", "r/x");
  await sessions.retryRequest("a/b", "r/x", { expected_attempt: 1, expected_state_version: 2 });
  await sessions.patchViewState("a/b", { expected_version: 0, reading_anchor: null, draft: "草稿" });
  await profiles.listProfiles({ cursor: "p+/=", limit: 30 });
  await profiles.createProfile({ name: "主题", scope_description: "范围" });
  await profiles.getProfile("a/b"); await profiles.getProfileSummary("a/b");
  await workspace.patchWorkspaceState({ expected_version: 0, last_session_id: null });
  await knowledge.listKnowledge({ q: "a & b", profile_id: "p1", before_id: 4 });
  const calls = vi.mocked(fetch).mock.calls;
  expect(calls[0][0]).toBe("/api/sessions");
  expect(JSON.parse(calls[0][1]!.body as string)).toEqual({ profile_id: "p1", title: "新会话", active_node_id: null });
  expect(calls[1][0]).toBe("/api/sessions/a%2Fb/snapshot?message_limit=20");
  expect(calls[2][0]).toBe("/api/sessions/a%2Fb/messages?limit=10&cursor=c%2B%2F%3D");
  expect(calls[3][0]).toBe("/api/sessions/a%2Fb/requests/r%2Fx");
  expect(calls[4][0]).toBe("/api/sessions/a%2Fb/requests/r%2Fx/retry");
  expect(JSON.parse(calls[4][1]!.body as string)).toEqual({ expected_attempt: 1, expected_state_version: 2 });
  expect(calls[5][1]!.method).toBe("PATCH");
  expect(JSON.parse(calls[5][1]!.body as string)).toEqual({ expected_version: 0, reading_anchor: null, draft: "草稿" });
  expect(calls[6][0]).toBe("/api/topic-profiles?limit=30&cursor=p%2B%2F%3D");
  expect(JSON.parse(calls[7][1]!.body as string)).toEqual({ name: "主题", scope_description: "范围" });
  expect(calls[8][0]).toBe("/api/topic-profiles/a%2Fb");
  expect(calls[9][0]).toBe("/api/topic-profiles/a%2Fb/summary");
  expect(calls[10][0]).toBe("/api/workspace-state");
  expect(calls[11][0]).toBe("/api/knowledge?q=a+%26+b&profile_id=p1&before_id=4");
});
