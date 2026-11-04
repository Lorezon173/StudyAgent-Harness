import { ReadingAnchor } from "../types";

type RecoveryKind = "draft" | "prepared" | "request" | "workspace";
export interface RecoveryCandidate {
  schema: 1 | 2;
  kind: RecoveryKind;
  userId: number;
  sessionId: string;
  writerId: string;
  writeId: string;
  itemId: string;
  savedAt: number;
  draft?: string;
  reading_anchor?: ReadingAnchor | null;
  baseVersion?: number | null;
  sequence?: number;
  text?: string;
  [key: string]: unknown;
}
export type RecoveryIssue = "invalid_candidate" | "storage_unavailable" | "invalid_identity";
export interface RecoveryListResult { ok: boolean; candidates: RecoveryCandidate[]; issues: RecoveryIssue[] }
type Result = { ok: true; candidate: RecoveryCandidate } | { ok: false };
const prefix = "studyagent:recovery:v1:";
const randomId = () => globalThis.crypto.randomUUID();
const integer = (value: unknown): value is number => Number.isSafeInteger(value) && (value as number) >= 0;
const id = (value: unknown): value is string => typeof value === "string" && value.length > 0 && value.length <= 256;
const text = (value: unknown): value is string => typeof value === "string" && value.length <= 4000;
const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === "object" && !Array.isArray(value);
const only = (value: Record<string, unknown>, keys: string[]) => Object.keys(value).every(key => keys.includes(key));
function keyFor(kind: RecoveryKind, userId: number, sessionId: string, writerId: string, itemId = "") {
  return prefix + [kind, userId, sessionId, writerId, itemId].map(value => encodeURIComponent(String(value))).join(":");
}
function validFields(kind: RecoveryKind, userId: number, sessionId: string, itemId: string, fields: Record<string, unknown>) {
  if (kind === "draft") {
    const anchor = fields.reading_anchor;
    return itemId === "" && only(fields, ["draft", "reading_anchor", "baseVersion", "sequence"]) && text(fields.draft) && integer(fields.sequence) && (fields.baseVersion === null || integer(fields.baseVersion)) &&
      (anchor === null || (object(anchor) && only(anchor, ["message_id", "offset_ratio"]) && integer(anchor.message_id) && anchor.message_id > 0 && typeof anchor.offset_ratio === "number" && Number.isFinite(anchor.offset_ratio) && anchor.offset_ratio >= 0 && anchor.offset_ratio <= 1));
  }
  if (kind === "prepared") {
    if (!id(itemId) || !text(fields.text) || !fields.text.length || !integer(fields.sequence)) return false;
    if (fields.phase === undefined) return only(fields, ["text", "sequence"]);
    if (fields.phase === "prepared") return only(fields, ["text", "sequence", "phase"]);
    if (fields.phase !== "linked" || !only(fields, ["text", "sequence", "phase", "requestId", "payload", "baseline"]) || !id(fields.requestId) || !object(fields.payload) || fields.payload.message !== fields.text) return false;
    return validFields("request", userId, sessionId, fields.requestId, { payload: fields.payload, baseline: fields.baseline });
  }
  if (kind === "workspace") return sessionId === "workspace" && itemId === "" && only(fields, ["lastSessionId", "baseVersion", "sequence"]) && (fields.lastSessionId === null || id(fields.lastSessionId)) && (fields.baseVersion === null || integer(fields.baseVersion)) && integer(fields.sequence);
  if (kind !== "request" || !id(itemId) || !only(fields, ["payload", "baseline", "baselineReason"]) || (fields.baselineReason !== undefined && (!id(fields.baselineReason)))) return false;
  const payload = fields.payload;
  if (!object(payload) || !only(payload, ["message", "session_id", "profile_id", "request_id", "expected_state_version"]) || !text(payload.message) || !payload.message.trim() || payload.session_id !== sessionId || payload.request_id !== itemId || !id(payload.profile_id) || !integer(payload.expected_state_version)) return false;
  const baseline = fields.baseline;
  // Legacy scalar baselines remain candidates, never upgraded into a trusted identity.
  if (baseline === null || integer(baseline)) return true;
  return object(baseline) && only(baseline, ["owner_user_id", "session_id", "request_id", "profile_id", "active_node_id", "base_state_version", "expected_turn_index", "provenance", "snapshot_sequence"]) &&
    baseline.owner_user_id === userId && baseline.session_id === sessionId && baseline.request_id === itemId && baseline.profile_id === payload.profile_id &&
    (baseline.active_node_id === null || id(baseline.active_node_id)) && baseline.base_state_version === payload.expected_state_version && integer(baseline.expected_turn_index) &&
    ["before_submit", "observed_running_snapshot"].includes(String(baseline.provenance)) && integer(baseline.snapshot_sequence);
}
function validCandidate(value: unknown): value is RecoveryCandidate {
  if (!object(value) || ![1, 2].includes(Number(value.schema)) || (value.schema === 2 && (value.kind !== "prepared" || !["prepared", "linked"].includes(String(value.phase)))) || (value.schema === 1 && value.phase !== undefined) || !["draft", "prepared", "request", "workspace"].includes(String(value.kind)) || !integer(value.userId) || value.userId <= 0 || !id(value.sessionId) || !id(value.writerId) || !id(value.writeId) || typeof value.itemId !== "string" || !integer(value.savedAt)) return false;
  const { schema, kind, userId, sessionId, writerId, writeId, itemId, savedAt, ...fields } = value;
  return validFields(kind as RecoveryKind, userId as number, sessionId as string, itemId as string, fields);
}
export function createLocalRecovery(storage: Storage, writerId: string = randomId()) {
  function write(kind: RecoveryKind, userId: number, sessionId: string, itemId: string, fields: Record<string, unknown>): Result {
    try {
      if (!integer(userId) || userId <= 0 || !id(sessionId) || !id(writerId) || !validFields(kind, userId, sessionId, itemId, fields)) return { ok: false };
      const candidate: RecoveryCandidate = { ...fields, schema: kind === "prepared" && fields.phase !== undefined ? 2 : 1, kind, userId, sessionId, writerId, itemId, writeId: randomId(), savedAt: Date.now() };
      const key = keyFor(kind, userId, sessionId, writerId, itemId);
      const value = JSON.stringify(candidate); storage.setItem(key, value);
      // Return a detached snapshot: callers cannot mutate nested input after persistence.
      return storage.getItem(key) === value ? { ok: true, candidate: JSON.parse(value) as RecoveryCandidate } : { ok: false };
    } catch { return { ok: false }; }
  }
  function listResult(userId: number, sessionId: string, kind: RecoveryKind): RecoveryListResult {
    const candidates: RecoveryCandidate[] = []; const issues: RecoveryIssue[] = [];
    if (!integer(userId) || userId <= 0 || !id(sessionId) || !["draft", "prepared", "request", "workspace"].includes(kind)) return { ok: false, candidates, issues: ["invalid_identity"] };
    try {
      const namespace = prefix + [kind, userId, sessionId].map(value => encodeURIComponent(String(value))).join(":") + ":";
      for (let index = 0; index < storage.length; index++) {
        const key = storage.key(index); if (!key?.startsWith(namespace)) continue;
        let raw: string | null;
        try { raw = storage.getItem(key); } catch { issues.push("storage_unavailable"); continue; }
        try {
          const item: unknown = JSON.parse(raw || "null");
          if (!validCandidate(item) || item.kind !== kind || item.userId !== userId || item.sessionId !== sessionId || key !== keyFor(kind, userId, sessionId, item.writerId, item.itemId)) { issues.push("invalid_candidate"); continue; }
          candidates.push(item);
        } catch { issues.push("invalid_candidate"); }
      }
    } catch { issues.push("storage_unavailable"); }
    return { ok: issues.length === 0, candidates, issues };
  }
  function list(userId: number, sessionId: string, kind: RecoveryKind): RecoveryCandidate[] { return listResult(userId, sessionId, kind).candidates; }
  function remove(candidate: RecoveryCandidate) {
    try {
      if (!validCandidate(candidate) || candidate.writerId !== writerId) return false;
      const key = keyFor(candidate.kind, candidate.userId, candidate.sessionId, writerId, candidate.itemId);
      const current = storage.getItem(key); if (!current || current !== JSON.stringify(candidate)) return false;
      storage.removeItem(key); return storage.getItem(key) === null;
    } catch { return false; }
  }
  return {
    writerId, list, listResult, remove,
    writeDraft: (userId: number, sessionId: string, value: { draft: string; reading_anchor: ReadingAnchor | null; baseVersion: number | null; sequence: number }) => write("draft", userId, sessionId, "", value),
    writePrepared: (userId: number, sessionId: string, id: string, value: { text: string; sequence: number; phase?: "prepared" | "linked"; requestId?: string; payload?: Record<string, unknown>; baseline?: unknown }) => write("prepared", userId, sessionId, id, value),
    writeRequest: (userId: number, sessionId: string, id: string, value: Record<string, unknown>) => write("request", userId, sessionId, id, value),
    writeWorkspace: (userId: number, value: Record<string, unknown>) => write("workspace", userId, "workspace", "", value),
  };
}
let recovery: ReturnType<typeof createLocalRecovery> | null = null;
export function getLocalRecovery() {
  if (!recovery) recovery = createLocalRecovery(localStorage);
  return recovery;
}

