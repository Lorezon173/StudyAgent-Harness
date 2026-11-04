// @vitest-environment jsdom
import { beforeEach, expect, it } from "vitest";
import { createLocalRecovery } from "./localRecovery";

beforeEach(() => localStorage.clear());
it("keeps separate writers' drafts and only removes the exact confirmed write", () => {
  const a = createLocalRecovery(localStorage, "writer-a");
  const b = createLocalRecovery(localStorage, "writer-b");
  const first = a.writeDraft(1, "session", { draft: "A", reading_anchor: null, baseVersion: 0, sequence: 1 });
  const second = b.writeDraft(1, "session", { draft: "B", reading_anchor: null, baseVersion: 0, sequence: 1 });
  expect(first.ok && second.ok).toBe(true);
  if (!first.ok) throw Error("write failed");
  expect(a.remove(first.candidate)).toBe(true);
  expect(a.list(1, "session", "draft").map(value => value.draft)).toEqual(["B"]);
  expect(a.list(2, "session", "draft")).toEqual([]);
});
it("retains a newer edit when an earlier save is acknowledged", () => {
  const recovery = createLocalRecovery(localStorage, "writer-a");
  const old = recovery.writeDraft(1, "session", { draft: "old", reading_anchor: null, baseVersion: 0, sequence: 1 });
  recovery.writeDraft(1, "session", { draft: "new", reading_anchor: null, baseVersion: 0, sequence: 2 });
  if (!old.ok) throw Error("write failed");
  expect(recovery.remove(old.candidate)).toBe(false);
  expect(recovery.list(1, "session", "draft")[0].draft).toBe("new");
});
it("keeps a prepared original independently of the edited draft", () => {
  const recovery = createLocalRecovery(localStorage, "writer-a");
  recovery.writePrepared(1, "session", "prepare-1", { text: "original", sequence: 1 });
  recovery.writeDraft(1, "session", { draft: "new edit", reading_anchor: null, baseVersion: 0, sequence: 2 });
  expect(recovery.list(1, "session", "prepared")[0].text).toBe("original");
  expect(recovery.list(1, "session", "draft")[0].draft).toBe("new edit");
});

it("rejects malformed fields and credentials without replacing the valid draft", () => {
  const recovery = createLocalRecovery(localStorage, "writer-a");
  recovery.writeDraft(1, "session", { draft: "safe", reading_anchor: null, baseVersion: 0, sequence: 1 });
  expect(recovery.writeDraft(1, "session", { draft: "x".repeat(4001), reading_anchor: null, baseVersion: 0, sequence: 2 }).ok).toBe(false);
  expect(recovery.writePrepared(1, "session", "p", { text: "x", sequence: -1 }).ok).toBe(false);
  expect(recovery.writeWorkspace(1, { lastSessionId: "session", baseVersion: 0, sequence: 1, token: "secret" }).ok).toBe(false);
  expect(recovery.list(1, "session", "draft")[0].draft).toBe("safe");
});
it("reports a damaged candidate while retaining valid candidates and storage", () => {
  const recovery = createLocalRecovery(localStorage, "writer-a");
  recovery.writeDraft(1, "session", { draft: "safe", reading_anchor: null, baseVersion: 0, sequence: 1 });
  localStorage.setItem("studyagent:recovery:v1:draft:1:session:broken:", "{broken");
  const result = recovery.listResult(1, "session", "draft");
  expect(result.ok).toBe(false); expect(result.candidates).toHaveLength(1);
  expect(result.issues).toEqual(["invalid_candidate"]); expect(localStorage.length).toBe(2);
});
it("reports storage failures distinctly from an empty account", () => {
  const blocked = { get length() { throw Error("blocked"); } } as unknown as Storage;
  const recovery = createLocalRecovery(blocked, "writer-a");
  expect(recovery.listResult(1, "session", "draft")).toEqual({ ok: false, candidates: [], issues: ["storage_unavailable"] });
});
it("preserves unknown request baselines as null and rejects mismatched request identity", () => {
  const recovery = createLocalRecovery(localStorage, "writer-a");
  const payload = { session_id: "session", request_id: "r", profile_id: "p", message: "original", expected_state_version: 7 };
  const result = recovery.writeRequest(1, "session", "r", { payload, baseline: null });
  expect(result.ok).toBe(true);
  if (!result.ok) throw Error("write failed");
  expect(result.candidate.baseline).toBeNull();
  expect(recovery.writeRequest(1, "session", "other", { payload, baseline: 42 }).ok).toBe(false);
});
it("requires exact writer/write/content identity and verifies deletion", () => {
  const a = createLocalRecovery(localStorage, "writer-a"); const b = createLocalRecovery(localStorage, "writer-b");
  const result = a.writePrepared(1, "session", "p", { text: "original", sequence: 1 });
  if (!result.ok) throw Error("write failed");
  expect(b.remove(result.candidate)).toBe(false);
  expect(a.remove({ ...result.candidate, text: "different" })).toBe(false);
  const blocked = new Proxy(localStorage, { get(target, prop) { if (prop === "removeItem") return () => { throw Error("blocked"); }; const value = Reflect.get(target, prop, target); return typeof value === "function" ? value.bind(target) : value; } });
  expect(createLocalRecovery(blocked, "writer-a").remove(result.candidate)).toBe(false);
  expect(a.list(1, "session", "prepared")).toHaveLength(1);
});
it("accepts only a fully bound trusted baseline and preserves legacy unknown provenance", () => {
  const recovery = createLocalRecovery(localStorage, "writer-a");
  const payload = { session_id: "session", request_id: "r", profile_id: "p", message: "original", expected_state_version: 7 };
  const baseline = { owner_user_id: 1, session_id: "session", request_id: "r", profile_id: "p", active_node_id: null, base_state_version: 7, expected_turn_index: 42, provenance: "before_submit", snapshot_sequence: 1 };
  expect(recovery.writeRequest(1, "session", "r", { payload, baseline }).ok).toBe(true);
  expect(recovery.writeRequest(1, "session", "r", { payload, baseline: { ...baseline, owner_user_id: 2 } }).ok).toBe(false);
  expect(recovery.writeRequest(1, "session", "r", { payload, baseline: { ...baseline, base_state_version: 8 } }).ok).toBe(false);
  expect(recovery.writeRequest(1, "session", "r", { payload, baseline: { ...baseline, expected_turn_index: -1 } }).ok).toBe(false);
  const legacy = recovery.writeRequest(1, "session", "r", { payload, baseline: 42 });
  expect(legacy.ok && legacy.candidate.baseline).toBe(42);
});
it("rejects corrupt typed fields on read without deleting them or exposing another account", () => {
  const recovery = createLocalRecovery(localStorage, "writer-a");
  const valid = recovery.writeDraft(1, "session", { draft: "safe", reading_anchor: null, baseVersion: null, sequence: 1 });
  if (!valid.ok) throw Error("write failed");
  const key = localStorage.key(0)!;
  localStorage.setItem(key, JSON.stringify({ ...valid.candidate, reading_anchor: { message_id: 1, offset_ratio: 2 } }));
  expect(recovery.listResult(1, "session", "draft").issues).toEqual(["invalid_candidate"]);
  expect(recovery.listResult(2, "session", "draft")).toEqual({ ok: true, candidates: [], issues: [] });
  expect(localStorage.getItem(key)).not.toBeNull();
});
it("reports quota, readback failure and individual unreadable entries", () => {
  const recovery = createLocalRecovery(localStorage, "writer-a");
  const value = { draft: "safe", reading_anchor: null, baseVersion: 0, sequence: 1 };
  recovery.writeDraft(1, "session", value);
  const blocked = (property: string) => new Proxy(localStorage, { get(target, prop) { if (prop === property) return () => { throw Error("blocked"); }; const value = Reflect.get(target, prop, target); return typeof value === "function" ? value.bind(target) : value; } });
  expect(createLocalRecovery(blocked("setItem"), "writer-a").writeDraft(1, "session", value).ok).toBe(false);
  const reader = createLocalRecovery(blocked("getItem"), "writer-a");
  expect(reader.writeDraft(1, "session", value).ok).toBe(false);
  expect(reader.listResult(1, "session", "draft").issues).toEqual(["storage_unavailable"]);
});
it("uses unique prepared writes and detached snapshots across multiple operations", () => {
  const recovery = createLocalRecovery(localStorage, "writer-a");
  const first = recovery.writePrepared(1, "session", "p1", { text: "X", sequence: 1 });
  const second = recovery.writePrepared(1, "session", "p2", { text: "X", sequence: 1 });
  if (!first.ok || !second.ok) throw Error("write failed");
  expect(first.candidate.writeId).not.toBe(second.candidate.writeId);
  expect(recovery.remove(first.candidate)).toBe(true);
  expect(recovery.list(1, "session", "prepared")).toEqual([second.candidate]);
  const anchor = { message_id: 1, offset_ratio: 0.5 };
  const draft = recovery.writeDraft(1, "session", { draft: "Y", reading_anchor: anchor, baseVersion: 1, sequence: 2 });
  anchor.offset_ratio = 0.9;
  if (!draft.ok) throw Error("write failed");
  expect(draft.candidate.reading_anchor?.offset_ratio).toBe(0.5);
  expect(recovery.remove(draft.candidate)).toBe(true);
});

it("stores versioned prepared and linked copies with a separate request identity", () => {
  const recovery = createLocalRecovery(localStorage, "writer-a");
  const pure = recovery.writePrepared(1, "session", "prepare-1", { text: "original", sequence: 1, phase: "prepared" } as never);
  expect(pure.ok).toBe(true);
  if (!pure.ok) throw Error("write failed");
  expect(pure.candidate.schema).toBe(2);
  const payload = { session_id: "session", request_id: "request-1", profile_id: "p", message: "original", expected_state_version: 7 };
  const baseline = { owner_user_id: 1, session_id: "session", request_id: "request-1", profile_id: "p", active_node_id: null, base_state_version: 7, expected_turn_index: 2, provenance: "before_submit", snapshot_sequence: 1 };
  const linked = recovery.writePrepared(1, "session", "prepare-1", { text: "original", sequence: 1, phase: "linked", requestId: "request-1", payload, baseline } as never);
  expect(linked.ok).toBe(true);
  expect(recovery.remove(pure.candidate)).toBe(false);
  expect(recovery.list(1, "session", "prepared")[0]).toMatchObject({ schema: 2, phase: "linked", requestId: "request-1", payload, baseline });
  expect(recovery.list(2, "session", "prepared")).toEqual([]);
});
