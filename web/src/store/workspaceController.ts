import { apiPost, ApiError } from "../api/client";
import { getRequest, loadMessages, loadSnapshot, patchViewState, retryRequest } from "../api/sessions";
import { getWorkspaceState, patchWorkspaceState } from "../api/workspace";
import { AuthTicket, BackupItem, RequestTurnBaseline, SessionClientState, WorkspacePreferences, hasBlockingRecovery, isMatchedLinked, isMatchedLocalCopy, snapshotIdentityValid, sortHistoryMessages, workspaceStore } from "./workspace";
import { getLocalRecovery, RecoveryCandidate } from "./localRecovery";
import { ChatResponse, ReadingAnchor, SessionSnapshot, WorkspaceMessage, WorkspaceState, WorkspacePatch } from "../types";

function preferencesFromServer(result: WorkspaceState): WorkspacePreferences {
  return { pinned: typeof result.sidebar_pinned === "boolean" ? result.sidebar_pinned : true, collapsed: typeof result.sidebar_collapsed === "boolean" ? result.sidebar_collapsed : false, progressYRatio: typeof result.progress_y_ratio === "number" && Number.isFinite(result.progress_y_ratio) ? Math.max(0, Math.min(1, result.progress_y_ratio)) : 0.5 };
}

function current(ticket: AuthTicket) {
  return workspaceStore.isCurrent(ticket) && localStorage.getItem("studyagent_token") === ticket.token && localStorage.getItem("studyagent_user_id") === String(ticket.userId);
}
function message(error: unknown) { return error instanceof ApiError ? error.message : "加载失败，请重试"; }
function preserveUnreadableCandidates(existing: RecoveryCandidate[], incoming: RecoveryCandidate[], complete: boolean) {
  return complete ? incoming : [...existing, ...incoming.filter(item => !existing.some(old => old.writeId === item.writeId))];
}
class AssociationMismatch extends Error {}
class StaleObservation extends Error {}
class HistorySyncFailure extends Error {}
const timers = new Map<string, ReturnType<typeof setTimeout>>();
const anchorTimers = new Map<string, ReturnType<typeof setTimeout>>();
const lastAnchorWrites = new Map<string, number>();
const inFlight = new Map<string, Promise<boolean>>();
const drafts = new Map<string, RecoveryCandidate>();
const pollTimers = new Map<string, ReturnType<typeof setTimeout>>();
const workspaceLoads = new Map<number, Promise<boolean>>();
const workspaceSaves = new Map<number, Promise<boolean>>();
const workspaceCopies = new Map<number, RecoveryCandidate>();
const messagePages = new Map<string, Promise<boolean>>();
const retries = new Set<string>();
const requestReads = new Map<string, ReturnType<typeof getRequest>>();
const associationRuns = new Map<string, { latest: number; active: number; conflict: number }>();
const key = (ticket: AuthTicket, id: string) => `${ticket.generation}:${id}`;
let observedGeneration = workspaceStore.getSnapshot().account.generation;
workspaceStore.subscribe(() => {
  const generation = workspaceStore.getSnapshot().account.generation;
  if (generation === observedGeneration) return;
  observedGeneration = generation;
  for (const map of [timers, anchorTimers, pollTimers]) { for (const timer of map.values()) clearTimeout(timer); map.clear(); }
  lastAnchorWrites.clear(); drafts.clear(); requestReads.clear(); retries.clear(); associationRuns.clear();
  inFlight.clear(); workspaceLoads.clear(); workspaceSaves.clear(); workspaceCopies.clear(); messagePages.clear();
});
function preparationsUnchanged(ticket: AuthTicket, id: string, allowOwnUnavailable?: string) {
  const bucket = workspaceStore.getSnapshot().buckets[id];
  if (!bucket || ticket.userId === null) return false;
  const read = getLocalRecovery().listResult(ticket.userId, id, "prepared");
  const ownUnavailable = (candidate: RecoveryCandidate) => Boolean(allowOwnUnavailable && candidate.itemId === allowOwnUnavailable && candidate.writerId === getLocalRecovery().writerId);
  if (!read.ok && !bucket.preparedCandidates.length && !read.candidates.length) {
    workspaceStore.patchBucket(ticket, id, value => ({ ...value, recoveryError: "本机恢复副本不可用，关闭页面或账号失效后未确认内容可能丢失" }));
    return true;
  }
  if (!read.ok && allowOwnUnavailable && bucket.acknowledgedPreparations.length === 0 && bucket.preparedCandidates.every(ownUnavailable) && read.candidates.every(ownUnavailable)) return true;
  const acceptedUncertain = (candidate: RecoveryCandidate) => isMatchedLocalCopy(bucket, candidate, getLocalRecovery().writerId) && bucket.acknowledgedPreparations.includes(candidate.writeId);
  if (!read.ok && bucket.preparedCandidates.length > 0 && bucket.preparedCandidates.every(item => ownUnavailable(item) || acceptedUncertain(item)) && read.candidates.every(item => ownUnavailable(item) || acceptedUncertain(item))) return true;
  const expected = bucket.preparedCandidates.filter(candidate => !ownUnavailable(candidate));
  const observed = read.candidates.filter(candidate => !ownUnavailable(candidate));
  const unchanged = read.ok && expected.every(candidate => observed.some(item => JSON.stringify(item) === JSON.stringify(candidate))) && observed.length === expected.length;
  if (!unchanged) workspaceStore.patchBucket(ticket, id, value => ({ ...value, preparedCandidates: preserveUnreadableCandidates(value.preparedCandidates, read.candidates, read.ok), acknowledgedPreparations: [], cancelledPreparations: [], recoveryError: "本机内容已变化或无法读取，请重新检查" }));
  return unchanged;
}
function linkedAcknowledgementsCurrent(ticket: AuthTicket, id: string, allowRequestId?: string) {
  const bucket = workspaceStore.getSnapshot().buckets[id];
  if (!bucket || ticket.userId === null) return false;
  const acknowledged = bucket.preparedCandidates.filter(item => bucket.acknowledgedPreparations.includes(item.writeId) && (item.phase === "linked" || isMatchedLocalCopy(bucket, item, getLocalRecovery().writerId)));
  if (!acknowledged.length) return true;
  const prepared = getLocalRecovery().listResult(ticket.userId, id, "prepared");
  const requests = getLocalRecovery().listResult(ticket.userId, id, "request");
  const ownWriter = getLocalRecovery().writerId;
  if ((!prepared.ok || !requests.ok) && acknowledged.every(item => isMatchedLocalCopy(bucket, item, ownWriter)) && bucket.preparedCandidates.every(item => acknowledged.some(known => known.writeId === item.writeId) || (item.writerId === ownWriter && item.requestId === allowRequestId)) && bucket.requestCandidates.every(item => isMatchedLocalCopy(bucket, item, ownWriter) || item.itemId === allowRequestId && (item.writerId === ownWriter || item.writerId === "")) && prepared.candidates.every(item => acknowledged.some(known => JSON.stringify(known) === JSON.stringify(item)) || (item.writerId === ownWriter && item.requestId === allowRequestId)) && requests.candidates.every(item => isMatchedLocalCopy(bucket, item, ownWriter) || item.itemId === allowRequestId && item.writerId === ownWriter)) return true;
  const expectedRequests = bucket.requestCandidates.filter(item => item.writerId !== "");
  const local = allowRequestId ? bucket.localRequests[allowRequestId] : undefined;
  const observedRequests = requests.candidates.filter(item => !(allowRequestId && item.itemId === allowRequestId && item.writerId === ownWriter && !expectedRequests.some(known => known.writerId === item.writerId && known.itemId === item.itemId) && local && JSON.stringify(item.payload) === JSON.stringify(local.payload) && JSON.stringify(item.baseline) === JSON.stringify(local.baseline)));
  const unchanged = prepared.ok && requests.ok && acknowledged.every(item => (isMatchedLinked(bucket, item) || isMatchedLocalCopy(bucket, item, ownWriter)) && prepared.candidates.some(currentItem => JSON.stringify(item) === JSON.stringify(currentItem))) && observedRequests.length === expectedRequests.length && observedRequests.every(item => expectedRequests.some(known => JSON.stringify(item) === JSON.stringify(known)));
  if (!unchanged) workspaceStore.patchBucket(ticket, id, value => ({ ...value, preparedCandidates: preserveUnreadableCandidates(value.preparedCandidates, prepared.candidates, prepared.ok), requestCandidates: preserveUnreadableCandidates(value.requestCandidates, requests.candidates, requests.ok), acknowledgedPreparations: value.acknowledgedPreparations.filter(writeId => !acknowledged.some(item => item.writeId === writeId)), recoveryError: "其他本机请求或副本已变化或无法读取，请重新检查" }));
  return unchanged;
}
function requestRecoveriesUnchanged(ticket: AuthTicket, id: string, allowRequestId?: string) {
  const bucket = workspaceStore.getSnapshot().buckets[id]; if (!bucket || ticket.userId === null) return false;
  const recovery = getLocalRecovery(); const read = recovery.listResult(ticket.userId, id, "request");
  const safeKnown = (item: RecoveryCandidate) => isMatchedLocalCopy(bucket, item, recovery.writerId) || Boolean(allowRequestId && item.itemId === allowRequestId && (item.writerId === recovery.writerId || item.writerId === ""));
  if (!read.ok && bucket.requestCandidates.every(safeKnown) && read.candidates.every(safeKnown)) {
    workspaceStore.patchBucket(ticket, id, value => ({ ...value, recoveryError: value.recoveryError || "本机恢复副本不可用，关闭页面或账号失效后未确认内容可能丢失" })); return true;
  }
  const expected = bucket.requestCandidates.filter(item => item.writerId !== "");
  const local = allowRequestId ? bucket.localRequests[allowRequestId] : undefined;
  const observed = read.candidates.filter(item => !(allowRequestId && item.itemId === allowRequestId && item.writerId === recovery.writerId && !expected.some(known => known.writerId === item.writerId && known.itemId === item.itemId) && local && JSON.stringify(item.payload) === JSON.stringify(local.payload) && JSON.stringify(item.baseline) === JSON.stringify(local.baseline)));
  if (read.ok && observed.length === expected.length && observed.every(item => expected.some(known => JSON.stringify(known) === JSON.stringify(item)))) return true;
  workspaceStore.patchBucket(ticket, id, value => ({ ...value, requestCandidates: preserveUnreadableCandidates(value.requestCandidates, read.candidates, false), acknowledgedPreparations: value.acknowledgedPreparations.filter(writeId => !value.preparedCandidates.some(item => item.writeId === writeId && (item.phase === "linked" || isMatchedLocalCopy(value, item, recovery.writerId)))), recoveryError: "其他本机请求已变化或无法读取，请重新检查" })); return false;
}
function recoveryCandidateUnchanged(ticket: AuthTicket, id: string, candidate: RecoveryCandidate) {
  if (ticket.userId === null) return false;
  if (candidate.writerId === "") return true; // in-memory fallback when storage is unavailable
  const kind = candidate.kind === "prepared" && candidate.phase === "linked" ? "prepared" : "request";
  const read = getLocalRecovery().listResult(ticket.userId, id, kind);
  const exact = read.ok && read.candidates.some(item => JSON.stringify(item) === JSON.stringify(candidate));
  if (!exact) workspaceStore.patchBucket(ticket, id, value => ({ ...value, ...(read.ok ? kind === "prepared" ? { preparedCandidates: read.candidates, acknowledgedPreparations: [] } : { requestCandidates: read.candidates } : {}), recoveryError: "本机内容已变化或无法读取，请重新检查" }));
  return exact;
}
function canRetryOriginal(ticket: AuthTicket, id: string, requestId: string, candidate: RecoveryCandidate) {
  const bucket = workspaceStore.getSnapshot().buckets[id];
  if (!bucket || ticket.userId === null || bucket.activityGate !== "clear" || bucket.session?.active_request_id || bucket.pendingRequests.some(item => item.request_id !== requestId && item.status === "running")) return false;
  const recovery = getLocalRecovery(); const prepared = recovery.listResult(ticket.userId, id, "prepared"); const requests = recovery.listResult(ticket.userId, id, "request");
  if (!prepared.ok || !requests.ok) {
    workspaceStore.patchBucket(ticket, id, value => ({ ...value, preparedCandidates: preserveUnreadableCandidates(value.preparedCandidates, prepared.candidates, prepared.ok), requestCandidates: preserveUnreadableCandidates(value.requestCandidates, requests.candidates, requests.ok), recoveryError: `${value.recoveryError ? `${value.recoveryError}；` : ""}其他本机请求暂时无法读取，不能确认是否还有未决请求` }));
    return false;
  }
  const sameOwnLinked = (item: RecoveryCandidate) => item.phase === "linked" && item.requestId === requestId && (item.writerId === candidate.writerId || candidate.writerId === "" && item.writerId === recovery.writerId && Boolean(bucket.localRequests[requestId])) && JSON.stringify(item.payload) === JSON.stringify(candidate.payload) && JSON.stringify(item.baseline) === JSON.stringify(candidate.baseline);
  const otherPrepared = prepared.candidates.some(item => JSON.stringify(item) !== JSON.stringify(candidate) && !sameOwnLinked(item) && !bucket.cancelledPreparations.includes(item.writeId) && !bucket.acknowledgedPreparations.includes(item.writeId));
  const sameIdConflict = requests.candidates.some(item => item.itemId === requestId && (JSON.stringify(item.payload) !== JSON.stringify(candidate.payload) || JSON.stringify(item.baseline) !== JSON.stringify(candidate.baseline)));
  const otherRequests = requests.candidates.filter(item => item.itemId !== requestId);
  if (otherPrepared || sameIdConflict || hasBlockingRecovery({ ...bucket, requestCandidates: otherRequests })) {
    workspaceStore.patchBucket(ticket, id, value => ({ ...value, preparedCandidates: prepared.candidates, requestCandidates: requests.candidates, recoveryError: `${value.recoveryError ? `${value.recoveryError}；` : ""}存在其他待确认内容，请先检查` })); return false;
  }
  return true;
}
function cleanupMatchedRequest(ticket: AuthTicket, id: string, requestId: string) {
  if (!current(ticket) || ticket.userId === null) return;
  const bucket = workspaceStore.getSnapshot().buckets[id]; const record = bucket?.requests[requestId]; const local = bucket?.localRequests[requestId];
  if (!bucket || !record || record.association !== "matched" || record.snapshot.status !== "completed" || !record.baseline || !local || JSON.stringify(local.baseline) !== JSON.stringify(record.baseline)) return;
  const payload = local.payload; const server = record.snapshot;
  if (payload.request_id !== requestId || payload.session_id !== id || payload.profile_id !== server.profile_id || payload.expected_state_version !== server.base_state_version || payload.message !== server.request_payload.message || server.user_id !== ticket.userId) return;
  const recovery = getLocalRecovery();
  const prepared = recovery.listResult(ticket.userId, id, "prepared"); const requests = recovery.listResult(ticket.userId, id, "request");
  const ownPrepared = Object.entries(bucket.prepared).filter(([, value]) => value.phase === "linked" && value.requestId === requestId && JSON.stringify(value.payload) === JSON.stringify(payload) && JSON.stringify(value.baseline) === JSON.stringify(record.baseline));
  if (!prepared.ok || !requests.ok) {
    workspaceStore.patchBucket(ticket, id, value => {
      const remaining = { ...value.prepared }; for (const [prepareId] of ownPrepared) delete remaining[prepareId];
      const pending = { ...value.localRequests }; delete pending[requestId];
      const uncertainPrepared = { ...value.uncertainPrepared };
      for (const [prepareId, item] of ownPrepared) { const candidate = value.preparedCandidates.find(copy => copy.writerId === recovery.writerId && copy.itemId === prepareId && copy.phase === "prepared" && copy.text === item.text && copy.sequence === item.sequence); if (candidate) uncertainPrepared[candidate.writeId] = { requestId, text: item.text, sequence: item.sequence, payload, baseline: record.baseline! }; }
      return { ...value, prepared: remaining, localRequests: pending, requestCandidates: value.requestCandidates.filter(item => !(item.writerId === "" && item.itemId === requestId && JSON.stringify(item.payload) === JSON.stringify(payload) && JSON.stringify(item.baseline) === JSON.stringify(record.baseline))), uncertainMatched: [...new Set([...value.uncertainMatched, requestId])], uncertainPrepared, recoveryError: "本轮回复已保存，但本机副本状态无法确认，重新登录后可能再次出现；可重新检查" };
    });
    return;
  }
  workspaceStore.patchBucket(ticket, id, value => ({ ...value, preparedCandidates: preserveUnreadableCandidates(value.preparedCandidates, prepared.candidates, false), requestCandidates: preserveUnreadableCandidates(value.requestCandidates, requests.candidates, false) }));
  for (const [prepareId, value] of ownPrepared) {
    const known = bucket.preparedCandidates.find(item => item.writerId === recovery.writerId && item.itemId === prepareId && item.requestId === requestId && JSON.stringify(item.payload) === JSON.stringify(payload) && JSON.stringify(item.baseline) === JSON.stringify(record.baseline));
    const stored = prepared.candidates.find(item => item.writerId === recovery.writerId && item.itemId === prepareId);
    const knownPure = stored && bucket.preparedCandidates.find(item => item.writerId === recovery.writerId && item.itemId === prepareId && item.phase === "prepared" && item.text === value.text && item.sequence === value.sequence && JSON.stringify(item) === JSON.stringify(stored));
    if (knownPure) {
      workspaceStore.patchBucket(ticket, id, currentValue => { const remaining = { ...currentValue.prepared }; delete remaining[prepareId]; return { ...currentValue, prepared: remaining, uncertainMatched: [...new Set([...currentValue.uncertainMatched, requestId])], uncertainPrepared: { ...currentValue.uncertainPrepared, [knownPure.writeId]: { requestId, text: value.text, sequence: value.sequence, payload, baseline: record.baseline! } }, recoveryError: "本轮回复已保存，但本机副本状态无法确认，重新登录后可能再次出现；可重新检查" }; });
      continue;
    }
    const priorLinked = bucket.preparedCandidates.some(item => item.writerId === recovery.writerId && item.itemId === prepareId && item.phase === "linked");
    if (stored && !known && !priorLinked && stored.phase === "linked" && stored.requestId === requestId && stored.text === value.text && stored.sequence === value.sequence && JSON.stringify(stored.payload) === JSON.stringify(payload) && JSON.stringify(stored.baseline) === JSON.stringify(record.baseline)) {
      workspaceStore.patchBucket(ticket, id, currentValue => { const remaining = { ...currentValue.prepared }; delete remaining[prepareId]; return { ...currentValue, prepared: remaining, preparedCandidates: prepared.candidates, uncertainMatched: [...new Set([...currentValue.uncertainMatched, requestId])], recoveryError: "本轮回复已保存，但本机副本状态无法确认，重新登录后可能再次出现；可重新检查" }; });
      continue;
    }
    if (stored && (!known || JSON.stringify(stored) !== JSON.stringify(known) || !recovery.remove(stored))) { workspaceStore.patchBucket(ticket, id, currentValue => ({ ...currentValue, recoveryError: "本机副本已变化或无法清理，请重新检查" })); continue; }
    workspaceStore.patchBucket(ticket, id, currentValue => { const remaining = { ...currentValue.prepared }; delete remaining[prepareId]; return { ...currentValue, prepared: remaining, preparedCandidates: currentValue.preparedCandidates.filter(item => item.writeId !== known?.writeId) }; });
    const latest = workspaceStore.getSnapshot().buckets[id];
    if (latest && latest.draftRevision === value.sequence && latest.draft === value.text) workspaceController.setDraft(id, "");
  }
  const sameKey = requests.candidates.filter(item => item.writerId === recovery.writerId && item.itemId === requestId);
  const ownRequests = sameKey.filter(item => JSON.stringify(item.payload) === JSON.stringify(payload) && JSON.stringify(item.baseline) === JSON.stringify(record.baseline));
  const realKnown = bucket.requestCandidates.some(item => item.writerId === recovery.writerId && item.itemId === requestId);
  const memoryFallback = bucket.requestCandidates.some(item => item.writerId === "" && item.itemId === requestId && JSON.stringify(item.payload) === JSON.stringify(payload) && JSON.stringify(item.baseline) === JSON.stringify(record.baseline));
  if (ownRequests.length === sameKey.length && ownRequests.length > 0 && !realKnown && memoryFallback) {
    workspaceStore.patchBucket(ticket, id, value => { const pending = { ...value.localRequests }; delete pending[requestId]; return { ...value, localRequests: pending, requestCandidates: [...value.requestCandidates.filter(item => !(item.writerId === "" && item.itemId === requestId)), ...ownRequests], uncertainMatched: [...new Set([...value.uncertainMatched, requestId])], recoveryError: "本轮回复已保存，但本机副本状态无法确认，重新登录后可能再次出现；可重新检查" }; });
    return;
  }
  if (sameKey.length !== ownRequests.length || ownRequests.some(item => !bucket.requestCandidates.some(known => JSON.stringify(known) === JSON.stringify(item)))) { workspaceStore.patchBucket(ticket, id, value => ({ ...value, requestCandidates: preserveUnreadableCandidates(value.requestCandidates, requests.candidates, false), recoveryError: "本机副本已变化或无法清理，请重新检查" })); return; }
  if (ownRequests.every(item => recovery.remove(item))) workspaceStore.patchBucket(ticket, id, value => { const pending = { ...value.localRequests }; delete pending[requestId]; return { ...value, localRequests: pending, requestCandidates: value.requestCandidates.filter(item => !ownRequests.some(copy => copy.writeId === item.writeId) && !(item.writerId === "" && item.itemId === requestId && JSON.stringify(item.payload) === JSON.stringify(payload) && JSON.stringify(item.baseline) === JSON.stringify(record.baseline))) }; });
}
function readRequest(ticket: AuthTicket, id: string, requestId: string) {
  const k = `${key(ticket, id)}:${requestId}`; const existing = requestReads.get(k);
  if (existing) return existing;
  if (!current(ticket)) return Promise.reject(new Error("stale account"));
  const bucket = workspaceStore.getSnapshot().buckets[id]; if (!bucket) return Promise.reject(new StaleObservation());
  const epoch = bucket.activityEpoch; const sequence = bucket.activityObservationSequence + 1;
  workspaceStore.patchBucket(ticket, id, value => ({ ...value, activityObservationSequence: sequence }));
  const valid = () => { const value = workspaceStore.getSnapshot().buckets[id]; return current(ticket) && value?.activityEpoch === epoch && value.activityObservationSequence === sequence; };
  const result = getRequest(id, requestId).then(value => { if (!valid()) throw new StaleObservation(); return value; }, error => { if (!valid()) throw new StaleObservation(); throw error; }); requestReads.set(k, result);
  const clear = () => { if (requestReads.get(k) === result) requestReads.delete(k); };
  void result.then(clear, clear); return result;
}
async function connectSnapshotHistory(ticket: AuthTicket, id: string, snapshot: SessionSnapshot, stillCurrent: () => boolean) {
  if (!current(ticket) || !stillCurrent()) throw new StaleObservation();
  if (snapshot.session.user_id !== ticket.userId || snapshot.session.session_id !== id || snapshot.session.profile_id !== (snapshot.profile?.id ?? null) || (snapshot.profile && snapshot.profile.user_id !== ticket.userId)) throw new Error("身份不匹配");
  if (!snapshot.messages || !(snapshot.messages.next_cursor === null || typeof snapshot.messages.next_cursor === "string")) throw new HistorySyncFailure("历史分页无效，请重新同步");
  const gathered = new Map<number, WorkspaceMessage>(); const visited = new Set<string>();
  const collect = (items: WorkspaceMessage[]) => {
    if (!Array.isArray(items)) throw new HistorySyncFailure("历史页无效");
    const bucket = workspaceStore.getSnapshot().buckets[id]; if (!bucket) throw new StaleObservation();
    const existing = new Map(bucket.messages.map(item => [item.id, item]));
    for (const item of items) {
      const prior = gathered.get(item.id) ?? existing.get(item.id);
      if (prior && JSON.stringify(prior) !== JSON.stringify(item)) throw new HistorySyncFailure("历史消息内容不一致");
      gathered.set(item.id, item);
    }
  };
  collect(snapshot.messages.items);
  let cursor = snapshot.messages.next_cursor;
  for (;;) {
    if (!current(ticket) || !stillCurrent()) throw new StaleObservation();
    const bucket = workspaceStore.getSnapshot().buckets[id]; if (!bucket) throw new StaleObservation();
    if (!bucket.historyLoaded || !bucket.historyIds.length || bucket.historyIds.some(item => gathered.has(item))) break;
    if (typeof cursor !== "string" || visited.has(cursor)) throw new HistorySyncFailure("历史消息无法连续同步");
    visited.add(cursor);
    let page: Awaited<ReturnType<typeof loadMessages>>;
    try { page = await loadMessages(id, { cursor }); }
    catch { if (!current(ticket) || !stillCurrent()) throw new StaleObservation(); throw new HistorySyncFailure("历史消息同步失败，请重试"); }
    if (!current(ticket) || !stillCurrent()) throw new StaleObservation();
    if (!(page.next_cursor === null || typeof page.next_cursor === "string") || page.next_cursor === cursor || (page.next_cursor !== null && visited.has(page.next_cursor))) throw new HistorySyncFailure("历史分页无效");
    collect(page.items); cursor = page.next_cursor;
  }
  return { ...snapshot, messages: { ...snapshot.messages, items: [...gathered.values()] } };
}
async function recoverSupersededSend(ticket: AuthTicket, id: string, requestId: string, sequence: number) {
  const before = workspaceStore.getSnapshot().buckets[id];
  const local = before?.localRequests[requestId];
  if (!current(ticket) || !local || !local.baseline || typeof local.baseline !== "object" || before?.load.status === "loading" || before?.request.id !== requestId || before.request.sequence !== sequence || before.requests[requestId]) return;
  const baseline = local.baseline; const revision = Object.values(before.prepared).find(item => item.phase === "linked" && item.requestId === requestId)?.sequence; const text = String(local.payload.message);
  try {
    const server = await readRequest(ticket, id, requestId);
    const latest = workspaceStore.getSnapshot().buckets[id];
    if (!current(ticket) || !latest || latest.request.id !== requestId || latest.request.sequence !== sequence || latest.requests[requestId]) return;
    if (server.user_id !== ticket.userId || server.session_id !== id || server.request_id !== requestId || server.profile_id !== baseline.profile_id || server.active_node_id !== baseline.active_node_id || server.base_state_version !== baseline.base_state_version || server.request_payload.message !== local.payload.message || server.request_payload.profile_id !== baseline.profile_id || server.request_payload.active_node_id !== baseline.active_node_id || server.request_payload.base_state_version !== baseline.base_state_version || !workspaceStore.mergeRequest(ticket, server)) throw new Error("request mismatch");
    workspaceStore.patchBucket(ticket, id, value => value.request.id === requestId && value.request.sequence === sequence ? { ...value, requests: { ...value.requests, [requestId]: { ...value.requests[requestId], baseline } }, request: { ...value.request, status: server.status === "completed" ? "pending_messages" : server.status, attempt: server.attempt, error: server.error_code } } : value);
    const checked = workspaceStore.getSnapshot().buckets[id];
    if (checked && checked.draftRevision === revision && checked.draft === text) workspaceController.setDraft(id, "");
    if (server.status === "completed") await workspaceController.confirmCompleted(id, requestId, ticket);
    else if (server.status === "running") workspaceController.schedulePoll(id, requestId, ticket);
  } catch {
    if (current(ticket)) workspaceStore.patchBucket(ticket, id, value => value.request.id === requestId && value.request.sequence === sequence && !value.requests[requestId] ? { ...value, request: { ...value.request, status: "unknown", error: "原请求尚未确认，请重新查询" } } : value);
  }
}
async function loadWorkspace(ticket: AuthTicket, forceFresh = false) {
  void forceFresh;
  if (!current(ticket)) return false;
  const existing = workspaceLoads.get(ticket.generation); if (existing) return existing;
  const readSequence = workspaceStore.getSnapshot().workspace.readSequence + 1;
  workspaceStore.patchWorkspace(ticket, value => ({ ...value, readSequence }));
  const work = (async () => {
    const start = workspaceStore.getSnapshot().workspace;
    try {
      if (!current(ticket)) return false;
      const result = await getWorkspaceState(); if (!current(ticket)) return false;
      if (!Number.isSafeInteger(result.version) || result.version < 0 || !(typeof result.last_session_id === "string" || result.last_session_id === null)) throw new Error("invalid workspace state");
      const latest = workspaceStore.getSnapshot().workspace;
      if (latest.readSequence !== readSequence || latest.version !== start.version || (latest.sequence !== start.sequence && !latest.dirty)) return false;
      let candidates: RecoveryCandidate[] = []; let recoveryError: string | null = null;
      if (ticket.userId !== null && !workspaceStore.getSnapshot().workspace.candidatesLoaded) {
        try { const recovered = getLocalRecovery().listResult(ticket.userId, "workspace", "workspace"); candidates = recovered.candidates; if (!recovered.ok) recoveryError = "本机最近会话读取失败或包含损坏记录"; }
        catch { recoveryError = "本机最近会话读取失败或包含损坏记录"; }
      }
      workspaceStore.patchWorkspace(ticket, value => ({ ...value, version: result.version, lastSessionId: result.last_session_id, desiredSessionId: value.dirty ? value.desiredSessionId : result.last_session_id, error: value.sequence === start.sequence ? null : value.error, errorSource: value.sequence === start.sequence ? null : value.errorSource, candidates: value.candidatesLoaded ? value.candidates : candidates, candidatesLoaded: true, recoveryError }));
      workspaceStore.applyWorkspacePreferences(ticket, preferencesFromServer(result)); return true;
    } catch (error) { if (current(ticket)) workspaceStore.patchWorkspace(ticket, value => value.readSequence === readSequence && value.sequence === start.sequence && value.version === start.version ? { ...value, error: message(error), errorSource: "load", prefs: { ...value.prefs, error: value.prefs.loaded ? value.prefs.error : message(error) } } : value); return false; }
  })();
  workspaceLoads.set(ticket.generation, work); const ok = await work; if (workspaceLoads.get(ticket.generation) === work) workspaceLoads.delete(ticket.generation); return ok;
}
async function flushWorkspace(ticket: AuthTicket): Promise<boolean> {
  if (!current(ticket)) return false;
  const existing = workspaceSaves.get(ticket.generation); if (existing) return existing;
  const work = (async () => {
    while (current(ticket)) {
      let ws = workspaceStore.getSnapshot().workspace;
      if (ws.conflict) return false;
      if (!ws.dirty && !ws.prefs.dirtyFields.length) return !ws.error && !ws.prefs.error;
      if (ws.version === null) {
        const observedRead = ws.readSequence; const reusedRead = workspaceLoads.has(ticket.generation);
        if (!await loadWorkspace(ticket) || !current(ticket)) {
          const latest = workspaceStore.getSnapshot().workspace;
          if (current(ticket) && (latest.version !== null || latest.readSequence > observedRead + (reusedRead ? 0 : 1))) continue;
          return false;
        }
        ws = workspaceStore.getSnapshot().workspace;
      }
      if (ws.version === null) return false;
      const version = ws.version; const sequence = ws.sequence; const target = ws.desiredSessionId; const copy = workspaceCopies.get(ticket.generation);
      const recentDirty = ws.dirty; const captured = ws.prefs; const fields = captured.dirtyFields;
      const patch: WorkspacePatch = { expected_version: version };
      if (recentDirty) patch.last_session_id = target;
      if (fields.includes("pinned")) patch.sidebar_pinned = captured.localValues.pinned;
      if (fields.includes("collapsed")) patch.sidebar_collapsed = captured.localValues.collapsed;
      if (fields.includes("progressYRatio")) patch.progress_y_ratio = captured.localValues.progressYRatio;
      workspaceStore.patchWorkspace(ticket, value => ({ ...value, saving: true, error: null, errorSource: null, prefs: { ...value.prefs, saving: fields.length > 0, error: null } }));
      try {
        if (!current(ticket)) return false;
        const result = await patchWorkspaceState(patch);
        if (!current(ticket)) return false;
        if (result.version !== version + 1 || (recentDirty && result.last_session_id !== target) || (patch.sidebar_pinned !== undefined && result.sidebar_pinned !== patch.sidebar_pinned) || (patch.sidebar_collapsed !== undefined && result.sidebar_collapsed !== patch.sidebar_collapsed) || (patch.progress_y_ratio !== undefined && result.progress_y_ratio !== patch.progress_y_ratio)) throw new Error("invalid workspace response");
        const latest = workspaceStore.getSnapshot().workspace; const unchanged = recentDirty && latest.sequence === sequence && latest.desiredSessionId === target;
        workspaceStore.patchWorkspace(ticket, value => ({ ...value, version: result.version, lastSessionId: recentDirty ? result.last_session_id : value.lastSessionId, dirty: recentDirty ? !unchanged : value.dirty, saving: false, error: null, errorSource: null, prefs: { ...value.prefs, serverValues: preferencesFromServer(result), dirtyFields: value.prefs.dirtyFields.filter(field => !fields.includes(field) || value.prefs.localValues[field] !== captured.localValues[field]), saving: false, error: null } }));
        if (unchanged && copy && getLocalRecovery().remove(copy)) {
          workspaceStore.patchWorkspace(ticket, value => ({ ...value, candidates: value.candidates.filter(item => item.writeId !== copy.writeId) }));
          workspaceCopies.delete(ticket.generation);
        }
      } catch (error) {
        if (error instanceof ApiError && error.status === 409 && current(ticket)) {
          try {
            const latest = await getWorkspaceState(); if (!current(ticket)) return false;
            if (!Number.isSafeInteger(latest.version) || latest.version < 0 || !(typeof latest.last_session_id === "string" || latest.last_session_id === null)) throw new Error("invalid workspace state");
            workspaceStore.patchWorkspace(ticket, value => ({ ...value, version: latest.version, lastSessionId: latest.last_session_id, conflict: value.dirty, saving: false, error: value.dirty ? "最近会话与其他设备冲突，请选择" : null, errorSource: value.dirty ? "save" : null, prefs: { ...value.prefs, saving: false, error: fields.length ? "界面偏好与其他设备冲突，请重试" : value.prefs.error } }));
            return false;
          } catch { /* retain the unsaved candidate and report the original conflict */ }
        }
        if (current(ticket)) workspaceStore.patchWorkspace(ticket, value => ({ ...value, saving: false, error: value.dirty ? message(error) : value.error, errorSource: value.dirty ? "save" : value.errorSource, conflict: value.dirty && error instanceof ApiError && error.status === 409, prefs: { ...value.prefs, saving: false, error: fields.length ? message(error) : value.prefs.error } })); return false;
      }
    }
    return false;
  })();
  workspaceSaves.set(ticket.generation, work); const ok = await work; if (workspaceSaves.get(ticket.generation) === work) workspaceSaves.delete(ticket.generation);
  return ok;
}
async function flushView(id: string, ticket: AuthTicket, forceAnchor = false): Promise<boolean> {
  if (!current(ticket)) return false;
  const k = key(ticket, id); const timer = timers.get(k); if (timer) { clearTimeout(timer); timers.delete(k); }
  const anchorTimer = anchorTimers.get(k); if (anchorTimer) { clearTimeout(anchorTimer); anchorTimers.delete(k); }
  const existing = inFlight.get(k);
  if (existing) {
    const result = await existing;
    if (!result || !forceAnchor || !current(ticket)) return result;
    if (inFlight.get(k) === existing) inFlight.delete(k);
    return flushView(id, ticket, true);
  }
  const work = (async () => {
    while (current(ticket)) {
      const bucket = workspaceStore.getSnapshot().buckets[id];
      if (!bucket || bucket.save.status === "idle" || bucket.save.status === "saved") return true;
      if (bucket.save.viewVersion === null || bucket.save.status === "conflict") return false;
      const version = bucket.save.viewVersion; const revision = bucket.draftRevision; const text = bucket.draft; const anchor = bucket.readingAnchor; const candidate = drafts.get(k);
      const lastAnchor = lastAnchorWrites.get(k);
      const includeAnchor = forceAnchor || lastAnchor === undefined || Date.now() - lastAnchor >= 1000;
      workspaceStore.patchBucket(ticket, id, value => ({ ...value, save: { ...value.save, status: "saving", error: null } }));
      try {
        if (!current(ticket)) return false;
        if (includeAnchor) lastAnchorWrites.set(k, Date.now());
        const saved = await patchViewState(id, { expected_version: version, draft: text, ...(includeAnchor ? { reading_anchor: anchor } : {}) });
        if (!current(ticket)) return false;
        if (saved.version !== version + 1 || saved.draft !== text || (includeAnchor && JSON.stringify(saved.reading_anchor) !== JSON.stringify(anchor))) throw new Error("invalid view response");
        const latest = workspaceStore.getSnapshot().buckets[id]; if (!latest) return false;
        const unchanged = latest.draftRevision === revision && latest.draft === text && JSON.stringify(latest.readingAnchor) === JSON.stringify(anchor);
        const anchorPending = JSON.stringify(latest.readingAnchor) !== JSON.stringify(saved.reading_anchor);
        const fullySaved = unchanged && !anchorPending;
        workspaceStore.patchBucket(ticket, id, value => ({ ...value, save: { status: fullySaved ? "saved" : "dirty", error: null, viewVersion: saved.version } }));
        if (fullySaved && candidate && getLocalRecovery().remove(candidate)) {
          workspaceStore.patchBucket(ticket, id, value => ({ ...value, recoveryCandidates: value.recoveryCandidates.filter(item => item.writeId !== candidate.writeId) }));
          drafts.delete(k);
        }
        if (anchorPending && latest.draft === text && !includeAnchor) {
          const delay = Math.max(0, 1000 - (Date.now() - (lastAnchorWrites.get(k) ?? 0)));
          if (!anchorTimers.has(k)) anchorTimers.set(k, setTimeout(() => { anchorTimers.delete(k); void flushView(id, ticket); }, delay));
          return true;
        }
      } catch (error) {
        if (error instanceof ApiError && error.status === 409 && current(ticket)) {
          try {
            const latest = await loadSnapshot(id); if (!current(ticket)) return false;
            if (!snapshotIdentityValid(latest, ticket.userId, id, workspaceStore.getSnapshot().buckets[id]?.session ?? null)) {
              workspaceStore.patchBucket(ticket, id, value => value.draftRevision === revision && value.save.viewVersion === version ? { ...value, activityGate: "uncertain", activityError: "会话画像信息不一致，请重新查询", save: { ...value.save, status: "error", error: "无法核对服务器草稿，请重新查询" } } : value); return false;
            }
            if (!Number.isSafeInteger(latest.view_state.version) || latest.view_state.version < 0 || typeof latest.view_state.draft !== "string") throw new Error("invalid view");
            workspaceStore.patchBucket(ticket, id, value => ({ ...value, conflictView: latest.view_state, save: { ...value.save, status: "conflict", error: "草稿与其他设备冲突，请选择" } }));
            return false;
          } catch { /* preserve the local copy and expose the conflict */ }
        }
        if (current(ticket)) workspaceStore.patchBucket(ticket, id, value => ({ ...value, save: { ...value.save, status: error instanceof ApiError && error.status === 409 ? "conflict" : "error", error: message(error) } }));
        return false;
      }
    }
    return false;
  })();
  inFlight.set(k, work); const ok = await work; if (inFlight.get(k) === work) inFlight.delete(k);
  return ok;
}

export const workspaceController = {
  async loadSession(id: string) {
    workspaceStore.ensureSessionBucket(id);
    const ticket = workspaceStore.beginSessionLoad(id);
    try {
      if (!current(ticket)) return;
      const rawSnapshot = await loadSnapshot(id);
      if (!current(ticket)) return;
      const initialBucket = workspaceStore.getSnapshot().buckets[id];
      if (!initialBucket || initialBucket.load.sequence !== ticket.sequence) return;
      if (!snapshotIdentityValid(rawSnapshot, ticket.userId, id, initialBucket.session)) {
        const activityCurrent = initialBucket.activityEpoch === ticket.activityEpoch && initialBucket.activityObservationSequence === ticket.activityObservationSequence;
        workspaceStore.applySessionResult(ticket, { activityGate: "uncertain", ...(activityCurrent ? { activityError: "会话画像信息不一致，请重新查询" } : {}), load: { ...initialBucket.load, status: initialBucket.session ? "ready" : "error", error: initialBucket.session ? null : "会话画像信息不一致，请重新查询" } }); return;
      }
      const currentVersion = workspaceStore.getSnapshot().buckets[id]?.teachingStateVersion;
      let snapshot = rawSnapshot;
      try {
        if (currentVersion === null || currentVersion === undefined || rawSnapshot.session.state_version >= currentVersion) snapshot = await connectSnapshotHistory(ticket, id, rawSnapshot, () => workspaceStore.getSnapshot().buckets[id]?.load.sequence === ticket.sequence);
      } catch (error) {
        if (!(error instanceof HistorySyncFailure) || !current(ticket)) throw error;
        if (!workspaceStore.applySnapshot(ticket, rawSnapshot, error.message)) return;
        for (const request of workspaceStore.getSnapshot().buckets[id]?.pendingRequests ?? []) if (request.status === "running") workspaceController.schedulePoll(id, request.request_id, ticket);
        return;
      }
      if (!current(ticket)) return;
      if (!workspaceStore.applySnapshot(ticket, snapshot)) throw new Error("invalid snapshot");
      for (const request of workspaceStore.getSnapshot().buckets[id]?.pendingRequests ?? []) if (request.status === "running") workspaceController.schedulePoll(id, request.request_id, ticket);
      const anchor = workspaceStore.getSnapshot().buckets[id]?.readingAnchor;
      if (anchor) {
        while (current(ticket)) {
          const bucket = workspaceStore.getSnapshot().buckets[id];
          if (!bucket || bucket.load.sequence !== ticket.sequence || JSON.stringify(bucket.readingAnchor) !== JSON.stringify(anchor) || bucket.messages.some(item => item.id === anchor.message_id)) break;
          if (bucket.nextMessageCursor === null) { workspaceStore.patchBucket(ticket, id, value => ({ ...value, recoveryError: "无法在会话历史中找到保存的阅读位置" })); break; }
          if (!await workspaceController.loadOlder(id)) break;
        }
      }
    } catch (error) {
      if (error instanceof StaleObservation) return;
      if (error instanceof HistorySyncFailure && current(ticket)) { const hasSession = Boolean(workspaceStore.getSnapshot().buckets[id]?.session); workspaceStore.applySessionResult(ticket, hasSession ? { historySyncError: error.message, load: { status: "ready", error: null, sequence: ticket.sequence } } : { load: { status: "error", error: error.message, sequence: ticket.sequence } }); return; }
      if (current(ticket)) workspaceStore.applySessionResult(ticket, { load: { status: "error", error: message(error), sequence: ticket.sequence } });
    } finally {
      const bucket = workspaceStore.getSnapshot().buckets[id];
      if (current(ticket) && bucket?.load.sequence === ticket.sequence && bucket.load.status !== "loading" && bucket.request.id && bucket.request.status === "unknown" && bucket.request.error === "原请求待确认，正在重新查询") void recoverSupersededSend(ticket, id, bucket.request.id, bucket.request.sequence);
    }
  },
  async lastSession(ticket: AuthTicket) {
    const initial = workspaceStore.getSnapshot().workspace;
    if (!await loadWorkspace(ticket, true) || !current(ticket)) return null;
    const latest = workspaceStore.getSnapshot().workspace;
    if (initial.conflict || latest.conflict || latest.sequence !== initial.sequence || (latest.dirty && latest.desiredSessionId !== latest.lastSessionId)) return null;
    return latest.lastSessionId;
  },
  async ensureWorkspacePreferences(ticket: AuthTicket) {
    if (!current(ticket) || ticket.userId === null || !ticket.token) return false;
    if (workspaceStore.getSnapshot().workspace.prefs.loaded) return true;
    return loadWorkspace(ticket);
  },
  async savePreference(ratio: number) {
    const ticket = workspaceStore.captureTicket();
    if (!workspaceStore.setWorkspacePreferences(ticket, { progressYRatio: ratio })) return false;
    return flushWorkspace(ticket);
  },
  async retryPreferences() {
    const ticket = workspaceStore.captureTicket();
    if (!current(ticket) || workspaceStore.getSnapshot().workspace.conflict) return false;
    if (!workspaceStore.getSnapshot().workspace.prefs.loaded && !await loadWorkspace(ticket)) return false;
    return flushWorkspace(ticket);
  },
  async validateWorkspaceCandidate(candidate: RecoveryCandidate) {
    const ticket = workspaceStore.captureTicket(); const id = candidate.lastSessionId;
    if (!current(ticket) || candidate.kind !== "workspace" || candidate.userId !== ticket.userId || !(typeof id === "string" || id === null) || !workspaceStore.getSnapshot().workspace.candidates.some(item => item.writeId === candidate.writeId)) return null;
    if (id === null) return { id: null };
    const initial = workspaceStore.getSnapshot().buckets[id];
    try {
      const snapshot = await loadSnapshot(id); if (!current(ticket)) return null;
      const latest = workspaceStore.getSnapshot().buckets[id];
      if (!snapshotIdentityValid(snapshot, ticket.userId, id, latest?.session ?? null)) {
        if (initial) workspaceStore.patchBucket(ticket, id, value => value.load.sequence === initial.load.sequence && value.activityEpoch === initial.activityEpoch && value.activityObservationSequence === initial.activityObservationSequence ? { ...value, activityGate: "uncertain", activityError: "会话画像信息不一致，请重新查询" } : value);
        throw new Error("owner mismatch");
      }
      return { id };
    } catch { if (current(ticket)) workspaceStore.patchWorkspace(ticket, value => ({ ...value, recoveryError: "本机会话不可恢复，请检查访问权限" })); return null; }
  },
  async loadOlder(id: string) {
    const ticket = workspaceStore.captureTicket(); const bucket = workspaceStore.getSnapshot().buckets[id];
    if (!current(ticket) || !bucket || bucket.load.status !== "ready" || bucket.nextMessageCursor === null) return false;
    const k = key(ticket, id); const existing = messagePages.get(k); if (existing) return existing;
    const cursor = bucket.nextMessageCursor;
    const work = (async () => {
      try {
        const page = await loadMessages(id, { cursor });
        if (!current(ticket)) return false;
        const latest = workspaceStore.getSnapshot().buckets[id];
        if (!latest || latest.nextMessageCursor !== cursor) return false;
        if (!Array.isArray(page.items) || !(page.next_cursor === null || typeof page.next_cursor === "string") || page.next_cursor === cursor || (page.next_cursor !== null && latest.visitedMessageCursors.includes(page.next_cursor))) throw new Error("invalid cursor");
        const items = new Map(latest.messages.map(item => [item.id, item]));
        for (const item of page.items) { const existingItem = items.get(item.id); if (existingItem && JSON.stringify(existingItem) !== JSON.stringify(item)) throw new Error("conflicting message id"); if (!existingItem) items.set(item.id, item); }
        workspaceStore.patchBucket(ticket, id, value => ({ ...value, messages: sortHistoryMessages([...items.values()]), historyLoaded: true, historyIds: [...new Set([...value.historyIds, ...page.items.map(item => item.id)])], nextMessageCursor: page.next_cursor, messagePageError: null, visitedMessageCursors: [...value.visitedMessageCursors, cursor] }));
        return true;
      } catch { if (current(ticket)) workspaceStore.patchBucket(ticket, id, value => value.nextMessageCursor === cursor ? { ...value, messagePageError: "更早消息加载失败，请重试" } : value); return false; }
    })();
    messagePages.set(k, work); const result = await work; if (messagePages.get(k) === work) messagePages.delete(k); return result;
  },
  selectSession(id: string | null) {
    const ticket = workspaceStore.captureTicket(); if (!current(ticket) || ticket.userId === null) return;
    const previous = workspaceStore.getSnapshot().workspace;
    if ((previous.dirty && previous.desiredSessionId === id) || (!previous.dirty && previous.version !== null && previous.lastSessionId === id)) return;
    const sequence = previous.sequence + 1;
    workspaceStore.patchWorkspace(ticket, value => ({ ...value, desiredSessionId: id, dirty: true, sequence, error: null, errorSource: null }));
    const copy = getLocalRecovery().writeWorkspace(ticket.userId, { lastSessionId: id, baseVersion: previous.version, sequence });
    if (copy.ok) workspaceCopies.set(ticket.generation, copy.candidate);
    else workspaceStore.patchWorkspace(ticket, value => ({ ...value, error: "本机最近会话备份不可用", errorSource: "save" }));
    void flushWorkspace(ticket);
  },
  useServerWorkspace() {
    const ticket = workspaceStore.captureTicket(); if (!current(ticket)) return;
    workspaceStore.patchWorkspace(ticket, value => ({ ...value, desiredSessionId: value.lastSessionId, dirty: false, conflict: false, error: null, errorSource: null }));
  },
  saveLocalWorkspace() {
    const ticket = workspaceStore.captureTicket(); if (!current(ticket)) return;
    workspaceStore.patchWorkspace(ticket, value => ({ ...value, conflict: false, error: null, errorSource: null })); void flushWorkspace(ticket);
  },
  async retryWorkspace() {
    const ticket = workspaceStore.captureTicket(); if (!current(ticket)) return { kind: "stale" as const };
    const initial = workspaceStore.getSnapshot().workspace;
    if (initial.errorSource !== "load") return { kind: "write" as const, ok: await flushWorkspace(ticket) };
    if (!await loadWorkspace(ticket) || !current(ticket)) return { kind: "failed" as const };
    const latest = workspaceStore.getSnapshot().workspace;
    if (latest.sequence !== initial.sequence || latest.dirty || latest.conflict) return { kind: "stale" as const };
    return { kind: "read" as const, id: latest.lastSessionId, sequence: initial.sequence, ticket };
  },
  setDraft(id: string, text: string) {
    const ticket = workspaceStore.captureTicket(); if (!current(ticket) || ticket.userId === null) return;
    const bucket = workspaceStore.getSnapshot().buckets[id]; if (!bucket) return;
    const revision = bucket.draftRevision + 1;
    workspaceStore.patchBucket(ticket, id, value => ({ ...value, draft: text, draftRevision: revision, save: { ...value.save, status: value.save.status === "conflict" ? "conflict" : "dirty", error: value.save.status === "conflict" ? value.save.error : null } }));
    const result = getLocalRecovery().writeDraft(ticket.userId, id, { draft: text, reading_anchor: bucket.readingAnchor, baseVersion: bucket.save.viewVersion ?? 0, sequence: revision });
    if (result.ok) drafts.set(key(ticket, id), result.candidate);
    else workspaceStore.patchBucket(ticket, id, value => ({ ...value, save: { ...value.save, error: "本机草稿备份不可用" } }));
    if (bucket.save.status === "conflict") return;
    const k = key(ticket, id); const previous = timers.get(k); if (previous) clearTimeout(previous);
    timers.set(k, setTimeout(() => { timers.delete(k); void flushView(id, ticket); }, 500));
  },
  setAnchor(id: string, anchor: ReadingAnchor | null) {
    const ticket = workspaceStore.captureTicket();
    if (!current(ticket) || ticket.userId === null || (anchor && (!Number.isFinite(anchor.offset_ratio) || anchor.offset_ratio < 0 || anchor.offset_ratio > 1))) return;
    const bucket = workspaceStore.getSnapshot().buckets[id];
    if (!bucket || (anchor && !bucket.messages.some(item => item.id === anchor.message_id)) || JSON.stringify(bucket.readingAnchor) === JSON.stringify(anchor)) return;
    const revision = bucket.draftRevision + 1;
    workspaceStore.patchBucket(ticket, id, value => ({ ...value, readingAnchor: anchor, draftRevision: revision, save: { ...value.save, status: value.save.status === "conflict" ? "conflict" : "dirty", error: value.save.status === "conflict" ? value.save.error : null } }));
    const result = getLocalRecovery().writeDraft(ticket.userId, id, { draft: bucket.draft, reading_anchor: anchor, baseVersion: bucket.save.viewVersion ?? 0, sequence: revision });
    const k = key(ticket, id);
    if (result.ok) drafts.set(k, result.candidate);
    else workspaceStore.patchBucket(ticket, id, value => ({ ...value, save: { ...value.save, error: "本机阅读位置备份不可用" } }));
    if (bucket.save.status !== "conflict" && !anchorTimers.has(k)) anchorTimers.set(k, setTimeout(() => { anchorTimers.delete(k); void flushView(id, ticket); }, 1000));
  },
  flush(id: string) { return flushView(id, workspaceStore.captureTicket(), true); },
  useServerView(id: string) {
    const ticket = workspaceStore.captureTicket(); const bucket = workspaceStore.getSnapshot().buckets[id]; const view = bucket?.conflictView;
    if (!current(ticket) || !view) return;
    workspaceStore.patchBucket(ticket, id, value => ({ ...value, draft: view.draft, readingAnchor: view.reading_anchor, draftRevision: value.draftRevision + 1, conflictView: null, save: { status: "saved", error: null, viewVersion: view.version } }));
  },
  saveLocalView(id: string) {
    const ticket = workspaceStore.captureTicket(); const bucket = workspaceStore.getSnapshot().buckets[id]; const view = bucket?.conflictView;
    if (!current(ticket) || !view) return;
    workspaceStore.patchBucket(ticket, id, value => ({ ...value, conflictView: null, save: { status: "dirty", error: null, viewVersion: view.version } })); void flushView(id, ticket);
  },
  recoverDraft(id: string, candidate: RecoveryCandidate) {
    const ticket = workspaceStore.captureTicket(); const bucket = workspaceStore.getSnapshot().buckets[id];
    if (!current(ticket) || !bucket?.session || candidate.userId !== ticket.userId || candidate.sessionId !== id || candidate.kind !== "draft" || typeof candidate.draft !== "string" || bucket.draftRevision > 0) return;
    workspaceController.setDraft(id, candidate.draft);
    const revision = workspaceStore.getSnapshot().buckets[id]?.draftRevision;
    const applyAnchor = () => {
      const currentBucket = workspaceStore.getSnapshot().buckets[id];
      if (!current(ticket) || !currentBucket || currentBucket.draftRevision !== revision) return false;
      if (candidate.reading_anchor && !currentBucket.messages.some(item => item.id === candidate.reading_anchor!.message_id)) return false;
      workspaceController.setAnchor(id, candidate.reading_anchor ?? null);
      workspaceStore.patchBucket(ticket, id, value => ({ ...value, anchorRestoreSequence: value.anchorRestoreSequence + 1 }));
      return true;
    };
    if (!applyAnchor() && candidate.reading_anchor) void (async () => {
      while (current(ticket)) {
        const currentBucket = workspaceStore.getSnapshot().buckets[id];
        if (!currentBucket || currentBucket.draftRevision !== revision || currentBucket.nextMessageCursor === null || !await workspaceController.loadOlder(id)) break;
        if (applyAnchor()) return;
      }
      if (current(ticket)) workspaceStore.patchBucket(ticket, id, value => ({ ...value, recoveryError: "本机阅读位置尚未恢复，请检查历史消息" }));
    })();
    workspaceStore.patchBucket(ticket, id, value => ({ ...value, recoveryCandidates: value.recoveryCandidates.filter(item => item.writeId !== candidate.writeId) }));
  },
  acknowledgePreparedRisk(id: string, candidate: RecoveryCandidate) {
    const ticket = workspaceStore.captureTicket(); const bucket = workspaceStore.getSnapshot().buckets[id];
    if (!current(ticket) || !bucket || bucket.draft !== "" || candidate.userId !== ticket.userId || candidate.sessionId !== id || candidate.kind !== "prepared" || (candidate.schema === 1 || candidate.phase === "linked") || typeof candidate.text !== "string") return;
    const read = getLocalRecovery().listResult(ticket.userId!, id, "prepared");
    const exact = read.ok && read.candidates.some(item => JSON.stringify(item) === JSON.stringify(candidate));
    if (!exact) {
      workspaceStore.patchBucket(ticket, id, value => ({ ...value, preparedCandidates: preserveUnreadableCandidates(value.preparedCandidates, read.candidates, read.ok), acknowledgedPreparations: value.acknowledgedPreparations.filter(item => item !== candidate.writeId), recoveryError: "本机内容已变化或无法读取，请重新检查" })); return;
    }
    workspaceController.setDraft(id, candidate.text);
    workspaceStore.patchBucket(ticket, id, value => ({ ...value, acknowledgedPreparations: [...value.acknowledgedPreparations, candidate.writeId] }));
  },
  acknowledgeMatchedLinked(id: string, candidate: RecoveryCandidate) {
    const ticket = workspaceStore.captureTicket(); const bucket = workspaceStore.getSnapshot().buckets[id];
    if (!current(ticket) || ticket.userId === null || !bucket || candidate.userId !== ticket.userId || candidate.sessionId !== id || !isMatchedLinked(bucket, candidate)) return;
    const prepared = getLocalRecovery().listResult(ticket.userId, id, "prepared"); const requests = getLocalRecovery().listResult(ticket.userId, id, "request");
    if (!prepared.ok || !requests.ok || !prepared.candidates.some(item => JSON.stringify(item) === JSON.stringify(candidate))) {
      workspaceStore.patchBucket(ticket, id, value => ({ ...value, preparedCandidates: preserveUnreadableCandidates(value.preparedCandidates, prepared.candidates, prepared.ok), requestCandidates: preserveUnreadableCandidates(value.requestCandidates, requests.candidates, requests.ok), acknowledgedPreparations: value.acknowledgedPreparations.filter(item => item !== candidate.writeId), recoveryError: "其他本机请求或副本已变化或无法读取，请重新检查" })); return;
    }
    workspaceStore.patchBucket(ticket, id, value => ({ ...value, preparedCandidates: prepared.candidates, requestCandidates: requests.candidates, acknowledgedPreparations: [...new Set([...value.acknowledgedPreparations, candidate.writeId])] }));
  },
  acknowledgeUncertainMatched(id: string, candidate: RecoveryCandidate) {
    const ticket = workspaceStore.captureTicket(); const bucket = workspaceStore.getSnapshot().buckets[id];
    if (!current(ticket) || !bucket || candidate.userId !== ticket.userId || candidate.sessionId !== id || !isMatchedLocalCopy(bucket, candidate, getLocalRecovery().writerId)) return;
    workspaceStore.patchBucket(ticket, id, value => ({ ...value, acknowledgedPreparations: [...new Set([...value.acknowledgedPreparations, candidate.writeId])] }));
  },
  recoverPrepared(id: string, candidate: RecoveryCandidate) {
    const ticket = workspaceStore.captureTicket(); const bucket = workspaceStore.getSnapshot().buckets[id];
    if (!current(ticket) || !bucket?.session || bucket.draft !== "" || candidate.userId !== ticket.userId || candidate.sessionId !== id || candidate.kind !== "prepared" || typeof candidate.text !== "string") return;
    workspaceController.setDraft(id, candidate.text);
    const draftCopy = drafts.get(key(ticket, id));
    const localPrepared = bucket.prepared[candidate.itemId];
    if (localPrepared && candidate.writerId === getLocalRecovery().writerId && draftCopy?.draft === candidate.text && getLocalRecovery().remove(candidate)) {
      workspaceStore.patchBucket(ticket, id, value => { const prepared = { ...value.prepared }; delete prepared[candidate.itemId]; return { ...value, prepared, preparedCandidates: value.preparedCandidates.filter(item => item.writeId !== candidate.writeId) }; });
    } else if (!localPrepared) workspaceStore.patchBucket(ticket, id, value => ({ ...value, preparedCandidates: value.preparedCandidates.filter(item => item.writeId !== candidate.writeId) }));
  },
  async recheckLegacyPreparation(id: string, candidate: RecoveryCandidate) {
    const ticket = workspaceStore.captureTicket();
    if (!current(ticket) || ticket.userId === null || candidate.userId !== ticket.userId || candidate.sessionId !== id || candidate.kind !== "prepared" || candidate.schema !== 1 || typeof candidate.text !== "string") return;
    const read = getLocalRecovery().listResult(ticket.userId, id, "prepared");
    if (!read.ok || !read.candidates.some(item => JSON.stringify(item) === JSON.stringify(candidate))) { workspaceStore.patchBucket(ticket, id, value => ({ ...value, preparedCandidates: preserveUnreadableCandidates(value.preparedCandidates, read.candidates, read.ok), recoveryError: "本机内容已变化或无法读取，请重新检查" })); return; }
    try {
      const server = await readRequest(ticket, id, candidate.itemId); if (!current(ticket)) return;
      const latest = getLocalRecovery().listResult(ticket.userId, id, "prepared");
      if (!latest.ok || !latest.candidates.some(item => JSON.stringify(item) === JSON.stringify(candidate))) { workspaceStore.patchBucket(ticket, id, value => ({ ...value, ...(latest.ok ? { preparedCandidates: latest.candidates } : {}), recoveryError: "本机内容已变化或无法读取，请重新检查" })); return; }
      if (server.user_id !== ticket.userId || server.session_id !== id || server.request_id !== candidate.itemId || server.request_payload.message !== candidate.text || !workspaceStore.mergeRequest(ticket, server)) throw new Error("request mismatch");
      workspaceStore.patchBucket(ticket, id, value => ({ ...value, request: { id: candidate.itemId, status: server.status === "completed" ? "pending_messages" : server.status, attempt: server.attempt, error: server.error_code, sequence: value.request.sequence + 1, text: candidate.text } }));
      if (server.status === "completed") await workspaceController.confirmCompleted(id, candidate.itemId, ticket);
      else if (server.status === "running") workspaceController.schedulePoll(id, candidate.itemId, ticket);
    } catch (error) { if (current(ticket) && !(error instanceof StaleObservation)) workspaceStore.patchBucket(ticket, id, value => ({ ...value, recoveryError: "原请求尚未确认，请重新查询" })); }
  },
  async recheckLinkedPreparation(id: string, candidate: RecoveryCandidate) {
    const ticket = workspaceStore.captureTicket();
    if (!current(ticket) || ticket.userId === null || candidate.userId !== ticket.userId || candidate.sessionId !== id || candidate.phase !== "linked" || typeof candidate.requestId !== "string") return;
    const read = getLocalRecovery().listResult(ticket.userId, id, "prepared");
    if (!read.ok || !read.candidates.some(item => JSON.stringify(item) === JSON.stringify(candidate))) {
      workspaceStore.patchBucket(ticket, id, value => ({ ...value, preparedCandidates: preserveUnreadableCandidates(value.preparedCandidates, read.candidates, read.ok), acknowledgedPreparations: [], recoveryError: "本机内容已变化或无法读取，请重新检查" })); return;
    }
    const requests = getLocalRecovery().listResult(ticket.userId, id, "request");
    if (!requests.ok) workspaceStore.patchBucket(ticket, id, value => ({ ...value, requestCandidates: preserveUnreadableCandidates(value.requestCandidates, requests.candidates, false), recoveryError: "其他本机请求暂时无法读取，不能确认是否还有未决请求" }));
    await workspaceController.recheckCandidate(id, candidate);
  },
  async resendLinkedPreparation(id: string, candidate: RecoveryCandidate) {
    const ticket = workspaceStore.captureTicket();
    if (!current(ticket) || ticket.userId === null || candidate.userId !== ticket.userId || candidate.sessionId !== id || candidate.phase !== "linked" || typeof candidate.requestId !== "string") return;
    const read = getLocalRecovery().listResult(ticket.userId, id, "prepared");
    if (!read.ok || !read.candidates.some(item => JSON.stringify(item) === JSON.stringify(candidate))) {
      workspaceStore.patchBucket(ticket, id, value => ({ ...value, preparedCandidates: preserveUnreadableCandidates(value.preparedCandidates, read.candidates, read.ok), acknowledgedPreparations: [], recoveryError: "本机内容已变化或无法读取，请重新检查" })); return;
    }
    await workspaceController.resendCandidate(id, candidate);
  },
  async recheckCandidate(id: string, candidate: RecoveryCandidate) {
    const ticket = workspaceStore.captureTicket(); const payload = candidate.payload as Record<string, unknown> | undefined;
    const requestId = candidate.kind === "prepared" && candidate.phase === "linked" && typeof candidate.requestId === "string" ? candidate.requestId : candidate.kind === "request" ? candidate.itemId : null;
    if (!current(ticket) || candidate.userId !== ticket.userId || candidate.sessionId !== id || !requestId || !payload || !recoveryCandidateUnchanged(ticket, id, candidate)) return;
    try {
      const server = await readRequest(ticket, id, requestId); if (!current(ticket)) return;
      if (!recoveryCandidateUnchanged(ticket, id, candidate)) return;
      if (server.user_id !== ticket.userId || server.session_id !== id || server.request_id !== requestId || server.profile_id !== payload.profile_id || server.base_state_version !== payload.expected_state_version || server.request_payload.message !== payload.message || server.request_payload.profile_id !== payload.profile_id || server.request_payload.base_state_version !== payload.expected_state_version) throw new Error("request mismatch");
      const baseline = typeof candidate.baseline === "object" && candidate.baseline !== null ? candidate.baseline as RequestTurnBaseline : null;
      if (baseline && (baseline.owner_user_id !== ticket.userId || baseline.session_id !== id || baseline.request_id !== requestId || baseline.profile_id !== server.profile_id || baseline.active_node_id !== server.active_node_id || baseline.base_state_version !== server.base_state_version || server.request_payload.active_node_id !== baseline.active_node_id)) throw new Error("baseline mismatch");
      if (!workspaceStore.mergeRequest(ticket, server)) return;
      const existing = workspaceStore.getSnapshot().buckets[id]?.requests[requestId];
      if (existing?.association === "matched") {
        if (!baseline || JSON.stringify(existing.baseline) !== JSON.stringify(baseline)) throw new Error("baseline mismatch");
        cleanupMatchedRequest(ticket, id, requestId); return;
      }
      if (existing?.association === "inconsistent") throw new Error("request inconsistent");
      workspaceStore.patchBucket(ticket, id, value => ({ ...value, requests: { ...value.requests, [requestId]: { ...value.requests[requestId], baseline } }, request: { id: requestId, status: server.status === "completed" ? "pending_messages" : server.status, attempt: server.attempt, error: server.error_code, sequence: value.request.sequence + 1, text: String(payload.message) } }));
      if (server.status === "completed") await workspaceController.confirmCompleted(id, requestId, ticket, candidate);
      else if (server.status === "running") workspaceController.schedulePoll(id, requestId, ticket);
    } catch (error) {
      if (error instanceof StaleObservation) return;
      if (current(ticket) && !recoveryCandidateUnchanged(ticket, id, candidate)) return;
      const canRetry = current(ticket) && error instanceof ApiError && error.status === 404 && canRetryOriginal(ticket, id, requestId, candidate);
      if (current(ticket)) workspaceStore.patchBucket(ticket, id, value => ({ ...value, resendableRequests: canRetry && !value.conflictedRequests.includes(requestId) ? [...new Set([...value.resendableRequests, requestId])] : value.resendableRequests.filter(item => item !== requestId), recoveryError: `${value.recoveryError ? `${value.recoveryError}；` : ""}上次请求尚未确认：${message(error)}` }));
    }
  },
  async resendCandidate(id: string, candidate: RecoveryCandidate) {
    const ticket = workspaceStore.captureTicket(); const bucket = workspaceStore.getSnapshot().buckets[id];
    const requestId = candidate.kind === "prepared" && candidate.phase === "linked" && typeof candidate.requestId === "string" ? candidate.requestId : candidate.kind === "request" ? candidate.itemId : null;
    const payload = candidate.payload as Record<string, unknown> | undefined; const k = `${key(ticket, id)}:${requestId}`;
    if (!current(ticket) || !requestId || !bucket?.resendableRequests.includes(requestId) || candidate.userId !== ticket.userId || candidate.sessionId !== id || !payload || retries.has(k) || !recoveryCandidateUnchanged(ticket, id, candidate) || !canRetryOriginal(ticket, id, requestId, candidate)) return;
    retries.add(k);
    try {
      try { await readRequest(ticket, id, requestId); if (current(ticket)) await workspaceController.recheckCandidate(id, candidate); return; }
      catch (error) { if (!(error instanceof ApiError) || error.status !== 404 || !current(ticket)) throw error; }
      const beforeSnapshot = workspaceStore.getSnapshot(); const beforeBucket = beforeSnapshot.buckets[id];
      if (!beforeBucket) return;
      const activityEpoch = beforeBucket.activityEpoch; const observation = beforeBucket.activityObservationSequence + 1; const activeSessionEpoch = beforeSnapshot.activeSessionEpoch;
      workspaceStore.patchBucket(ticket, id, value => ({ ...value, activityObservationSequence: observation }));
      const snapshot = await loadSnapshot(id); if (!current(ticket)) return;
      const latest = workspaceStore.getSnapshot(); const latestBucket = latest.buckets[id];
      if (!latestBucket || latest.activeSessionId !== id || latest.activeSessionEpoch !== activeSessionEpoch || latestBucket.activityEpoch !== activityEpoch || latestBucket.activityObservationSequence !== observation) return;
      if (!snapshotIdentityValid(snapshot, ticket.userId, id, latestBucket.session)) {
        workspaceStore.patchBucket(ticket, id, value => value.activityEpoch === activityEpoch && value.activityObservationSequence === observation ? { ...value, activityGate: "uncertain", activityError: "会话画像信息不一致，请重新查询" } : value); return;
      }
      if (snapshot.session.user_id !== ticket.userId || snapshot.session.session_id !== id || snapshot.session.profile_id !== payload.profile_id || !snapshot.profile || snapshot.profile.id !== payload.profile_id || snapshot.profile.user_id !== ticket.userId || snapshot.session.state_version !== payload.expected_state_version || snapshot.session.active_request_id !== null) throw new Error("请求上下文已变化，请重新查询");
      if (!recoveryCandidateUnchanged(ticket, id, candidate) || !canRetryOriginal(ticket, id, requestId, candidate)) return;
      const result = await apiPost<ChatResponse>("/api/chat", payload); if (!current(ticket)) return;
      if (result.session_id !== id || result.request_id !== requestId) throw new Error("request mismatch");
      workspaceStore.patchBucket(ticket, id, value => ({ ...value, resendableRequests: value.resendableRequests.filter(item => item !== requestId) }));
      await workspaceController.recheckCandidate(id, candidate);
    } catch (error) {
      if (error instanceof StaleObservation) return;
      if (current(ticket)) {
        const code = error instanceof ApiError ? error.code : null;
        workspaceStore.patchBucket(ticket, id, value => ({ ...value, resendableRequests: ["payload_conflict", "session_busy", "stale_context"].includes(code ?? "") ? value.resendableRequests.filter(item => item !== requestId) : value.resendableRequests, conflictedRequests: code === "payload_conflict" ? [...new Set([...value.conflictedRequests, requestId])] : value.conflictedRequests, recoveryError: code === "payload_conflict" ? "请求编号对应内容不一致，原文已保留，请检查" : code === "session_busy" ? "会话已有正在处理的请求，正在刷新状态" : code === "stale_context" ? "会话内容已变化，原文已保留" : `原请求仍未确认：${message(error)}` }));
        if (code === "session_busy" && current(ticket)) await workspaceController.loadSession(id);
      }
    }
    finally { retries.delete(k); }
  },
  async flushAll(ticket: AuthTicket) {
    const items: BackupItem[] = [];
    if (!current(ticket)) return { ok: false, stale: true, items };
    const ids = Object.keys(workspaceStore.getSnapshot().buckets);
    const results = await Promise.all([...ids.map(id => flushView(id, ticket, true)), flushWorkspace(ticket)]);
    ids.forEach((id, index) => items.push({ kind: "draft", sessionId: id, ok: results[index] }));
    const ws = workspaceStore.getSnapshot().workspace;
    items.push({ kind: "workspace", sessionId: null, ok: results[ids.length] || (!ws.dirty && !ws.conflict && !ws.error) });
    items.push({ kind: "preferences", sessionId: null, ok: results[ids.length] || (!ws.prefs.dirtyFields.length && !ws.prefs.error) });
    if (!current(ticket)) return { ok: false, stale: true, items };
    for (const [id, bucket] of Object.entries(workspaceStore.getSnapshot().buckets)) {
      const unresolved = new Set([...Object.keys(bucket.prepared), ...Object.keys(bucket.localRequests), ...bucket.requestCandidates.filter(item => !isMatchedLocalCopy(bucket, item, getLocalRecovery().writerId)).map(item => item.itemId), ...bucket.pendingRequests.filter(item => item.status === "running").map(item => item.request_id)]);
      if (["preparing", "unknown", "running", "pending_messages"].includes(bucket.request.status || "") && bucket.request.id) unresolved.add(bucket.request.id);
      unresolved.forEach(itemId => items.push({ kind: bucket.prepared[itemId] ? "prepared" : "request", sessionId: id, itemId, ok: false }));
    }
    return { ok: items.every(item => item.ok), stale: false, items };
  },
  async send(id: string) {
    const ticket = workspaceStore.captureTicket(); const bucket = workspaceStore.getSnapshot().buckets[id];
    if (!current(ticket) || ticket.userId === null || !bucket || !bucket.session || hasBlockingRecovery(bucket) || Boolean(bucket.session.active_request_id) || bucket.activityGate !== "clear" || bucket.preparedCandidates.some(item => !bucket.cancelledPreparations.includes(item.writeId) && !bucket.acknowledgedPreparations.includes(item.writeId)) || ["running", "preparing", "unknown", "pending_messages", "unassociated", "inconsistent"].includes(bucket.request.status || "") || bucket.pendingRequests.some(request => request.status === "running") || !bucket.draft.trim() || bucket.draft.length > 4000) return;
    if (!preparationsUnchanged(ticket, id) || !requestRecoveriesUnchanged(ticket, id) || !linkedAcknowledgementsCurrent(ticket, id)) return;
    const text = bucket.draft; const revision = bucket.draftRevision; const sequence = bucket.request.sequence + 1; const activeSessionEpoch = workspaceStore.getSnapshot().activeSessionEpoch; const activityEpoch = bucket.activityEpoch; const activitySequence = bucket.activityObservationSequence + 1; const prepareId = crypto.randomUUID();
    const prepared = { text, sequence: revision, phase: "prepared" as const };
    workspaceStore.patchBucket(ticket, id, value => ({ ...value, activityObservationSequence: activitySequence, prepared: { ...value.prepared, [prepareId]: prepared }, request: { id: prepareId, status: "preparing", attempt: null, error: null, sequence, text } }));
    const preparedCopy = getLocalRecovery().writePrepared(ticket.userId, id, prepareId, prepared);
    if (preparedCopy.ok) workspaceStore.patchBucket(ticket, id, value => ({ ...value, preparedCandidates: [...value.preparedCandidates, preparedCopy.candidate] }));
    else workspaceStore.patchBucket(ticket, id, value => ({ ...value, recoveryError: "本机恢复副本不可用，关闭页面或账号失效后未确认内容可能丢失", request: { ...value.request, error: "本机待发送内容备份不可用" } }));
    let requestId = prepareId;
    let postAccepted = false;
    try {
      if (!current(ticket)) return;
      const snap = await loadSnapshot(id);
      if (!current(ticket)) return;
      const now = workspaceStore.getSnapshot();
      const compatible = snapshotIdentityValid(snap, ticket.userId, id, now.buckets[id]?.session ?? null);
      if (now.activeSessionId !== id || now.activeSessionEpoch !== activeSessionEpoch || now.buckets[id]?.request.id !== prepareId || now.buckets[id]?.request.sequence !== sequence || now.buckets[id]?.activityEpoch !== activityEpoch || now.buckets[id]?.activityObservationSequence !== activitySequence || now.buckets[id]?.pendingRequests.some(item => item.status === "running") || !compatible || snap.session.active_request_id || snap.session.profile_id === null || !Number.isSafeInteger(snap.session.state_version) || snap.session.state_version < 0 || !Number.isSafeInteger(snap.session.next_turn_index) || snap.session.next_turn_index < 0) {
        const candidate = now.buckets[id]?.preparedCandidates.find(item => item.itemId === prepareId && item.writerId === getLocalRecovery().writerId && item.schema === 2 && item.phase === "prepared" && item.text === text && item.sequence === revision);
        const stored = getLocalRecovery().listResult(ticket.userId, id, "prepared");
        const verified = candidate && stored.ok && stored.candidates.some(item => JSON.stringify(item) === JSON.stringify(candidate));
        workspaceStore.patchBucket(ticket, id, value => value.request.id === prepareId && value.request.sequence === sequence ? { ...value, cancelledPreparations: verified ? [...value.cancelledPreparations, candidate.writeId] : value.cancelledPreparations, activityGate: !compatible || value.session?.active_request_id || value.pendingRequests.some(item => item.status === "running") || (value.load.status === "loading" && value.activityObservationSequence !== activitySequence) ? "uncertain" : value.activityGate, ...(!compatible && value.activityEpoch === activityEpoch && value.activityObservationSequence === activitySequence ? { activityError: "会话画像信息不一致，请重新查询" } : {}), request: { ...value.request, status: "unsent", error: "未发送，可重试" } } : value); return;
      }
      workspaceStore.patchBucket(ticket, id, value => ({ ...value, activityEpoch: value.activityEpoch + 1 }));
      requestId = crypto.randomUUID();
      const payload = { message: text, session_id: id, profile_id: snap.session.profile_id, request_id: requestId, expected_state_version: snap.session.state_version };
      const baseline = { owner_user_id: ticket.userId, session_id: id, request_id: requestId, profile_id: snap.session.profile_id, active_node_id: snap.session.active_node_id, base_state_version: snap.session.state_version, expected_turn_index: snap.session.next_turn_index, provenance: "before_submit" as const, snapshot_sequence: bucket.load.sequence };
      const local = { payload, baseline };
      const linked = getLocalRecovery().writePrepared(ticket.userId, id, prepareId, { ...prepared, phase: "linked", requestId, payload, baseline });
      workspaceStore.patchBucket(ticket, id, value => ({ ...value, prepared: { ...value.prepared, [prepareId]: { ...prepared, phase: "linked", requestId, payload, baseline } }, preparedCandidates: linked.ok ? value.preparedCandidates.filter(item => item.itemId !== prepareId || item.writerId !== linked.candidate.writerId).concat(linked.candidate) : value.preparedCandidates, request: { ...value.request, id: requestId }, recoveryError: linked.ok ? value.recoveryError : "本机恢复副本不可用，关闭页面或账号失效后未确认内容可能丢失", localRequests: { ...value.localRequests, [requestId]: local } }));
      const requestCopy = getLocalRecovery().writeRequest(ticket.userId, id, requestId, local);
      if (requestCopy.ok) workspaceStore.patchBucket(ticket, id, value => ({ ...value, requestCandidates: [...value.requestCandidates, requestCopy.candidate] }));
      else workspaceStore.patchBucket(ticket, id, value => ({ ...value, recoveryError: "本机请求恢复副本不可用，关闭页面或账号失效后未确认内容可能丢失", requestCandidates: [...value.requestCandidates, { schema: 1, kind: "request", userId: ticket.userId!, sessionId: id, writerId: "", writeId: "", itemId: requestId, savedAt: Date.now(), ...local }], request: { ...value.request, error: "本机请求恢复副本不可用" } }));
      if (!current(ticket)) return;
      const finalState = workspaceStore.getSnapshot(); const finalBucket = finalState.buckets[id];
      if (finalState.activeSessionId !== id || finalState.activeSessionEpoch !== activeSessionEpoch || !finalBucket || finalBucket.request.id !== requestId || finalBucket.request.sequence !== sequence || finalBucket.activityEpoch !== activityEpoch + 1 || finalBucket.activityObservationSequence !== activitySequence || finalBucket.pendingRequests.some(item => item.status === "running") || finalBucket.activityGate !== "clear" || !preparationsUnchanged(ticket, id, !linked.ok || !requestCopy.ok ? prepareId : undefined) || !requestRecoveriesUnchanged(ticket, id, requestId) || !linkedAcknowledgementsCurrent(ticket, id, requestId)) {
        workspaceStore.patchBucket(ticket, id, value => value.request.id === requestId && value.request.sequence === sequence ? { ...value, request: { ...value.request, status: "unknown", error: "原请求待确认，请查询或按原请求重试" } } : value); return;
      }
      const result = await apiPost<ChatResponse>("/api/chat", payload);
      if (!current(ticket)) return;
      if (result.session_id !== id || result.request_id !== requestId) throw new Error("request mismatch");
      postAccepted = true;
      const accepted = workspaceStore.getSnapshot().buckets[id]?.requests[requestId]?.snapshot;
      if (accepted && Number.isSafeInteger(result.attempt) && (accepted.attempt > Number(result.attempt) || (accepted.attempt === result.attempt && accepted.status === "completed"))) return;
      const server = await readRequest(ticket, id, requestId);
      if (!current(ticket)) return;
      if (server.user_id !== ticket.userId || server.session_id !== id || server.request_id !== requestId || server.profile_id !== snap.session.profile_id || server.active_node_id !== snap.session.active_node_id || server.request_payload.message !== text || server.request_payload.profile_id !== snap.session.profile_id || server.request_payload.active_node_id !== snap.session.active_node_id || server.request_payload.base_state_version !== snap.session.state_version || server.base_state_version !== snap.session.state_version) throw new Error("request mismatch");
      if (!workspaceStore.mergeRequest(ticket, server)) throw new Error("request mismatch");
      workspaceStore.patchBucket(ticket, id, value => ({ ...value, requests: { ...value.requests, [requestId]: { ...value.requests[requestId], baseline } }, request: { ...value.request, status: server.status === "completed" ? "pending_messages" : server.status, attempt: server.attempt, error: server.error_code } }));
      const latest = workspaceStore.getSnapshot().buckets[id];
      if (latest && latest.draftRevision === revision && latest.draft === text) workspaceController.setDraft(id, "");
      if (server.status === "completed") await workspaceController.confirmCompleted(id, requestId, ticket);
      else if (server.status === "running") workspaceController.schedulePoll(id, requestId, ticket);
    } catch (error) {
      if (error instanceof StaleObservation) {
        const before = workspaceStore.getSnapshot().buckets[id];
        const local = before?.localRequests[requestId];
        if (!postAccepted || !current(ticket) || !local || !local.baseline || typeof local.baseline !== "object" || before?.request.id !== requestId || before.request.sequence !== sequence || before.requests[requestId]) return;
        workspaceStore.patchBucket(ticket, id, value => value.request.id === requestId && value.request.sequence === sequence ? { ...value, request: { ...value.request, status: "unknown", error: "原请求待确认，正在重新查询" } } : value);
        await recoverSupersededSend(ticket, id, requestId, sequence);
        return;
      }
      if (current(ticket) && error instanceof ApiError && ["payload_conflict", "session_busy", "stale_context"].includes(error.code ?? "")) {
        workspaceStore.patchBucket(ticket, id, value => {
          if (value.request.id !== requestId || value.request.sequence !== sequence) return value;
          const code = error.code;
          return { ...value, activityGate: code === "session_busy" ? "uncertain" : value.activityGate, conflictedRequests: code === "payload_conflict" ? [...new Set([...value.conflictedRequests, requestId])] : value.conflictedRequests, recoveryError: code === "payload_conflict" ? "请求编号对应内容不一致，原文已保留，请检查" : code === "session_busy" ? "会话已有正在处理的请求，正在刷新状态" : "会话内容已变化，原文已保留", request: { ...value.request, status: code === "payload_conflict" ? "inconsistent" : code === "session_busy" ? "unknown" : "unsent", error: message(error) } };
        });
        if (error.code === "session_busy" && current(ticket)) await workspaceController.loadSession(id);
        return;
      }
      if (current(ticket)) workspaceStore.patchBucket(ticket, id, value => {
        const authoritative = value.requests[requestId]?.snapshot;
        if (value.request.id !== requestId || value.request.sequence !== sequence || (authoritative && authoritative.status !== "running")) return value;
        return { ...value, request: { ...value.request, status: "unknown", error: message(error) } };
      });
      if (current(ticket)) {
        const bucket = workspaceStore.getSnapshot().buckets[id];
        const pending = bucket?.localRequests[requestId];
        const candidate = bucket?.requestCandidates.find(item => item.itemId === requestId) ?? (pending && ticket.userId !== null ? { schema: 1 as const, kind: "request" as const, userId: ticket.userId, sessionId: id, writerId: "", writeId: "", itemId: requestId, savedAt: Date.now(), ...pending } : undefined);
        if (candidate && bucket.request.id === requestId && bucket.request.status === "unknown") await workspaceController.recheckCandidate(id, candidate);
      }
    }
  },
  schedulePoll(id: string, requestId: string, ticket: AuthTicket) {
    const k = `${key(ticket, id)}:${requestId}`; if (pollTimers.has(k)) return;
    pollTimers.set(k, setTimeout(() => { pollTimers.delete(k); if (current(ticket)) void workspaceController.reconcile(id, requestId, ticket); }, 3000));
  },
  async reconcile(id: string, requestId: string, ticket: AuthTicket = workspaceStore.captureTicket(), revalidateInconsistent = false) {
    const initial = workspaceStore.getSnapshot().buckets[id]; const sequence = initial?.request.sequence; const attempt = initial?.requests[requestId]?.snapshot.attempt;
    try {
      if (!current(ticket)) return;
      const server = await readRequest(ticket, id, requestId); if (!current(ticket)) return;
      if (server.session_id !== id || server.user_id !== ticket.userId || server.request_id !== requestId) throw new Error("request mismatch");
      const accepted = workspaceStore.mergeRequest(ticket, server);
      if (!accepted) return;
      const record = workspaceStore.getSnapshot().buckets[id]?.requests[requestId];
      if (record?.association === "matched") return;
      if (record?.association === "inconsistent") {
        if (revalidateInconsistent && server.status === "completed") { await workspaceController.confirmCompleted(id, requestId, ticket); return; }
        workspaceStore.patchBucket(ticket, id, value => value.request.id === requestId ? { ...value, request: { ...value.request, status: "inconsistent", error: "请求状态不一致，请重新查询" } } : value);
        return;
      }
      if (record?.association === "unassociated" && valueRequestCompleted(id, requestId)) return;
      workspaceStore.patchBucket(ticket, id, value => value.request.id === requestId ? { ...value, request: { ...value.request, status: server.status === "completed" ? "pending_messages" : server.status, attempt: server.attempt, error: server.error_code } } : value);
      if (server.status === "running") workspaceController.schedulePoll(id, requestId, ticket);
      if (server.status === "completed") await workspaceController.confirmCompleted(id, requestId, ticket);
    } catch (error) {
      if (error instanceof StaleObservation) return;
      if (current(ticket)) workspaceStore.patchBucket(ticket, id, value => {
        const latest = value.requests[requestId]?.snapshot;
        if (value.request.id !== requestId || value.request.sequence !== sequence || (latest && (latest.status !== "running" || (attempt !== undefined && latest.attempt > attempt)))) return value;
        return { ...value, request: { ...value.request, status: "unknown", error: message(error) } };
      });
    }
  },
  async confirmCompleted(id: string, requestId: string, ticket: AuthTicket = workspaceStore.captureTicket(), source?: RecoveryCandidate) {
    const initialBucket = workspaceStore.getSnapshot().buckets[id]; const initial = initialBucket?.requests[requestId]; const activityEpoch = initialBucket?.activityEpoch;
    const sourceCurrent = () => !source || recoveryCandidateUnchanged(ticket, id, source);
    if (!current(ticket) || !initial || initial.snapshot.status !== "completed" || !sourceCurrent()) return;
    const requestSequence = initialBucket?.request.id === requestId ? initialBucket.request.sequence : null;
    const associationCurrent = (value: SessionClientState) => {
      const record = value.requests[requestId];
      return Boolean(record && record.snapshot.status === "completed" && record.snapshot.attempt === initial.snapshot.attempt && record.snapshot.user_id === initial.snapshot.user_id && record.snapshot.session_id === initial.snapshot.session_id && record.snapshot.request_id === initial.snapshot.request_id && record.snapshot.profile_id === initial.snapshot.profile_id && record.snapshot.active_node_id === initial.snapshot.active_node_id && record.snapshot.base_state_version === initial.snapshot.base_state_version && JSON.stringify(record.snapshot.request_payload) === JSON.stringify(initial.snapshot.request_payload) && JSON.stringify(record.snapshot.response_json) === JSON.stringify(initial.snapshot.response_json) && JSON.stringify(record.baseline) === JSON.stringify(initial.baseline) && !(value.request.id === requestId && requestSequence !== null && value.request.sequence !== requestSequence) && !(record.association === "matched" && initial.association !== "matched") && !(record.association === "inconsistent" && initial.association !== "inconsistent"));
    };
    const uiCurrent = (value: SessionClientState) => requestSequence !== null && value.request.id === requestId && value.request.sequence === requestSequence;
    const response = initial.snapshot.response_json; const baseline = initial.baseline;
    if (!response || response.persisted !== true || response.state_version !== initial.snapshot.base_state_version + 1) return;
    if (baseline === null) {
      workspaceStore.patchBucket(ticket, id, value => ({ ...value, requests: { ...value.requests, [requestId]: { ...value.requests[requestId], association: "unassociated" } }, request: value.request.id === requestId ? { ...value.request, status: "unassociated", error: "请求已完成，无法确定对应历史消息" } : value.request })); return;
    }
    if (baseline.owner_user_id !== ticket.userId || baseline.session_id !== id || baseline.request_id !== requestId || baseline.profile_id !== initial.snapshot.profile_id || baseline.active_node_id !== initial.snapshot.active_node_id || baseline.base_state_version !== initial.snapshot.base_state_version || !Number.isSafeInteger(baseline.expected_turn_index) || baseline.expected_turn_index < 0) {
      workspaceStore.patchBucket(ticket, id, value => ({ ...value, requests: { ...value.requests, [requestId]: { ...value.requests[requestId], association: "inconsistent" } }, request: value.request.id === requestId ? { ...value.request, status: "inconsistent", error: "已保存的消息与请求不一致，请检查" } : value.request })); return;
    }
    const associationKey = JSON.stringify([ticket.generation, ticket.userId, id, requestId, initial.snapshot.attempt, initial.snapshot.user_id, initial.snapshot.session_id, initial.snapshot.request_id, initial.snapshot.profile_id, initial.snapshot.active_node_id, initial.snapshot.base_state_version, initial.snapshot.request_payload, initial.snapshot.response_json, initial.baseline]);
    const run = associationRuns.get(associationKey) ?? { latest: 0, active: 0, conflict: 0 };
    run.latest++; run.active++; associationRuns.set(associationKey, run); const runSequence = run.latest;
    const latestRun = () => associationRuns.get(associationKey) === run && run.latest === runSequence;
    const turn = baseline.expected_turn_index;
    const activitySequence = (initialBucket?.activityObservationSequence ?? 0) + 1;
    workspaceStore.patchBucket(ticket, id, value => ({ ...value, activityObservationSequence: activitySequence }));
    try {
      if (!current(ticket)) return;
      const latest = await loadSnapshot(id); if (!current(ticket) || !sourceCurrent()) return;
      const observed = workspaceStore.getSnapshot().buckets[id];
      if (!snapshotIdentityValid(latest, ticket.userId, id, observed?.session ?? null)) {
        workspaceStore.patchBucket(ticket, id, value => value.activityEpoch === activityEpoch && value.activityObservationSequence === activitySequence && value.requests[requestId]?.snapshot.attempt === initial.snapshot.attempt ? { ...value, activityGate: "uncertain", activityError: "会话画像信息不一致，请重新查询" } : value); return;
      }
      if (latest.session.state_version < Number(response.state_version)) throw new Error("snapshot mismatch");
      let page = latest.messages; const found = [...page.items]; const visited = new Set<string>();
      while (!(found.some(m => m.turn_index === turn && m.role === "user") && found.some(m => m.turn_index === turn && m.role === "assistant")) && page.next_cursor !== null && !found.some(m => m.turn_index < turn)) {
        const cursor = page.next_cursor; if (visited.has(cursor)) throw new Error("cursor loop"); visited.add(cursor);
        if (!current(ticket)) return;
        page = await loadMessages(id, { cursor }); if (!current(ticket) || !sourceCurrent()) return;
        found.push(...page.items);
      }
      const unique = new Map<number, typeof found[number]>();
      for (const item of found) {
        const previous = unique.get(item.id);
        if (previous && JSON.stringify(previous) !== JSON.stringify(item)) throw new AssociationMismatch("conflicting message id");
        unique.set(item.id, item);
      }
      const users = [...unique.values()].filter(m => m.turn_index === turn && m.role === "user");
      const answers = [...unique.values()].filter(m => m.turn_index === turn && m.role === "assistant");
      if (users.length !== 1 || answers.length !== 1 || users[0].content !== initial.snapshot.request_payload.message || answers[0].content !== response.reply) throw new AssociationMismatch("message mismatch");
      if (!current(ticket) || !sourceCurrent()) return;
      const currentRecord = workspaceStore.getSnapshot().buckets[id]?.requests[requestId];
      if (!currentRecord || !associationCurrent(workspaceStore.getSnapshot().buckets[id])) return;
      let matched = false;
      workspaceStore.patchBucket(ticket, id, value => {
        const record = value.requests[requestId];
        if (!record || !associationCurrent(value) || associationRuns.get(associationKey) !== run || run.conflict > runSequence) return value;
        const byId = new Map(value.messages.map(m => [m.id, m]));
        if (found.some(item => byId.has(item.id) && JSON.stringify(byId.get(item.id)) !== JSON.stringify(item))) {
          if (!latestRun()) return value;
          run.conflict = runSequence;
          return { ...value, requests: { ...value.requests, [requestId]: { ...record, association: "inconsistent" } }, request: uiCurrent(value) ? { ...value.request, status: "inconsistent", error: "已保存的消息与请求不一致，请检查" } : value.request };
        }
        for (const item of found) byId.set(item.id, item);
        const incomingRevision = latest.profile_summary?.profile_revision ?? latest.profile?.revision ?? null;
        const profileConflict = value.profileRevision !== null && incomingRevision === value.profileRevision && (JSON.stringify(value.profile) !== JSON.stringify(latest.profile) || JSON.stringify(value.profileSummary) !== JSON.stringify(latest.profile_summary));
        const activityCurrent = value.activityEpoch === activityEpoch && value.activityObservationSequence === activitySequence;
        const validTeaching = Number.isSafeInteger(latest.session.state_version) && latest.session.state_version >= 0 && Number.isSafeInteger(latest.session.next_turn_index) && latest.session.next_turn_index >= 0;
        const teachingConflict = value.session !== null && value.teachingStateVersion === latest.session.state_version && (value.session.active_node_id !== latest.session.active_node_id || value.session.next_turn_index !== latest.session.next_turn_index || JSON.stringify(value.teachingState) !== JSON.stringify(latest.teaching_state) || value.teachingStateSource !== latest.teaching_state_source);
        const teachingSession = activityCurrent ? latest.session : value.session && value.session.user_id === latest.session.user_id && value.session.session_id === latest.session.session_id && value.session.profile_id === latest.session.profile_id ? { ...value.session, active_node_id: latest.session.active_node_id, state_version: latest.session.state_version, next_turn_index: latest.session.next_turn_index } : null;
        const useTeaching = validTeaching && !teachingConflict && teachingSession && (value.teachingStateVersion === null || latest.session.state_version >= value.teachingStateVersion);
        matched = true;
        return { ...value, ...(profileConflict ? { recoveryError: "画像版本相同但内容不一致，请重新查询" } : {}), ...(!activityCurrent || !validTeaching || teachingConflict || !teachingSession ? { activityGate: "uncertain" as const } : { activityEpoch: value.activityEpoch + 1 }), ...(!validTeaching || teachingConflict || !teachingSession ? { activityError: "教学状态不一致，请重新查询" } : {}), ...(useTeaching ? { session: teachingSession, teachingState: latest.teaching_state, teachingStateSource: latest.teaching_state_source, teachingStateVersion: latest.session.state_version } : {}), ...((latest.profile_summary?.profile_revision ?? latest.profile?.revision ?? null) !== null && (value.profileRevision === null || (latest.profile_summary?.profile_revision ?? latest.profile?.revision ?? -1) > value.profileRevision) ? { profile: latest.profile, profileSummary: latest.profile_summary, profileRevision: latest.profile_summary?.profile_revision ?? latest.profile?.revision ?? null } : {}), messages: sortHistoryMessages([...byId.values()]), requests: { ...value.requests, [requestId]: { ...value.requests[requestId], association: "matched" } }, request: uiCurrent(value) ? { ...value.request, status: "completed", error: null } : value.request };
      });
      if (matched) cleanupMatchedRequest(ticket, id, requestId);
    } catch (error) {
      if (current(ticket) && sourceCurrent() && latestRun()) workspaceStore.patchBucket(ticket, id, value => {
        const record = value.requests[requestId]; if (!record || !associationCurrent(value)) return value;
        const inconsistent = error instanceof AssociationMismatch;
        if (!inconsistent && record.association === "inconsistent") return uiCurrent(value) ? { ...value, request: { ...value.request, status: "inconsistent", error: "回复复核失败，请重新查询" } } : value;
        if (!inconsistent && record.association === "matched") return value.activityEpoch === activityEpoch && value.activityObservationSequence === activitySequence ? { ...value, activityGate: "uncertain", activityError: value.activityError ?? "已保存消息复核失败，请重新查询" } : value;
        if (inconsistent) run.conflict = runSequence;
        return { ...value, requests: inconsistent ? { ...value.requests, [requestId]: { ...record, association: "inconsistent" } } : value.requests, request: uiCurrent(value) ? { ...value.request, status: inconsistent ? "inconsistent" : "pending_messages", error: inconsistent ? "已保存的消息与请求不一致，请检查" : "回复已保存，消息尚未确认，请重试" } : value.request };
      });
    } finally {
      if (associationRuns.get(associationKey) === run) { run.active--; if (run.active === 0) associationRuns.delete(associationKey); }
    }
  },
  async recheckSessionActivity(id: string) {
    const ticket = workspaceStore.captureTicket(); const bucket = workspaceStore.getSnapshot().buckets[id];
    if (!current(ticket) || !bucket || bucket.activityGate === "checking") return;
    if (bucket.activityError === "教学状态不一致，请重新查询") { await workspaceController.loadSession(id); return; }
    const epoch = bucket.activityEpoch; const sequence = bucket.activityObservationSequence + 1;
    workspaceStore.patchBucket(ticket, id, value => ({ ...value, activityGate: "checking", activityError: null, activityObservationSequence: sequence }));
    try {
      const snapshot = await loadSnapshot(id);
      if (!current(ticket)) return;
      if (!snapshotIdentityValid(snapshot, ticket.userId, id, workspaceStore.getSnapshot().buckets[id]?.session ?? null)) {
        workspaceStore.patchBucket(ticket, id, value => value.activityObservationSequence === sequence && value.activityEpoch === epoch ? { ...value, activityGate: "uncertain", activityError: "会话画像信息不一致，请重新查询" } : value); return;
      }
      if (snapshot.session.active_request_id !== null) {
        const currentBucket = workspaceStore.getSnapshot().buckets[id];
        if (!currentBucket || currentBucket.activityObservationSequence !== sequence || currentBucket.activityEpoch !== epoch) return;
        workspaceStore.patchBucket(ticket, id, value => ({ ...value, activityGate: "uncertain" }));
        try {
          const server = await readRequest(ticket, id, snapshot.session.active_request_id);
          if (!current(ticket) || server.user_id !== ticket.userId || server.session_id !== id || server.request_id !== snapshot.session.active_request_id || server.profile_id !== snapshot.session.profile_id || !workspaceStore.mergeRequest(ticket, server)) throw new Error("request mismatch");
          if (server.status === "completed") await workspaceController.confirmCompleted(id, server.request_id, ticket);
          else if (server.status === "running") workspaceController.schedulePoll(id, server.request_id, ticket);
        } catch (error) {
          if (current(ticket) && !(error instanceof StaleObservation)) workspaceStore.patchBucket(ticket, id, value => ({ ...value, activityGate: "uncertain", activityError: "查询失败，请重试" }));
        }
        return;
      }
      workspaceStore.patchBucket(ticket, id, value => {
        if (value.activityObservationSequence !== sequence) return value;
        if (value.activityEpoch !== epoch || snapshot.session.active_request_id !== null) return { ...value, activityGate: "uncertain" };
        return { ...value, activityEpoch: value.activityEpoch + 1, session: value.session ? { ...value.session, active_request_id: null } : value.session, activityGate: "clear", activityError: null };
      });
    } catch {
      if (current(ticket)) workspaceStore.patchBucket(ticket, id, value => value.activityObservationSequence === sequence ? { ...value, activityGate: "uncertain", activityError: "查询失败，请重试" } : value);
    }
  },
  async continueUnassociated(id: string, requestId: string) {
    const ticket = workspaceStore.captureTicket(); const initialBucket = workspaceStore.getSnapshot().buckets[id]; const initial = initialBucket?.requests[requestId]; const activityEpoch = initialBucket?.activityEpoch;
    if (!current(ticket) || !initial || initial.association !== "unassociated" || initial.snapshot.status !== "completed") return;
    const activitySequence = (initialBucket?.activityObservationSequence ?? 0) + 1;
    workspaceStore.patchBucket(ticket, id, value => ({ ...value, activityObservationSequence: activitySequence }));
    const historyTicket = { ...workspaceStore.captureTicket(id, undefined, "load"), activityEpoch, activityObservationSequence: activitySequence };
    try {
      const rawSnapshot = await loadSnapshot(id); if (!current(ticket)) return;
      const observed = workspaceStore.getSnapshot().buckets[id];
      if (!snapshotIdentityValid(rawSnapshot, ticket.userId, id, observed?.session ?? null)) {
        workspaceStore.patchBucket(ticket, id, value => value.load.sequence === historyTicket.sequence && value.activityEpoch === activityEpoch && value.activityObservationSequence === activitySequence && value.request.id === requestId && value.request.sequence === initialBucket?.request.sequence && value.requests[requestId]?.snapshot.attempt === initial.snapshot.attempt ? { ...value, activityGate: "uncertain", activityError: "会话画像信息不一致，请重新查询" } : value); return;
      }
      const currentVersion = workspaceStore.getSnapshot().buckets[id]?.teachingStateVersion;
      let snapshot = rawSnapshot;
      try {
        if (currentVersion === null || currentVersion === undefined || rawSnapshot.session.state_version >= currentVersion) snapshot = await connectSnapshotHistory(ticket, id, rawSnapshot, () => { const value = workspaceStore.getSnapshot().buckets[id]; return Boolean(value && value.request.id === requestId && value.request.sequence === initialBucket?.request.sequence && value.requests[requestId]?.snapshot.attempt === initial.snapshot.attempt && value.requests[requestId]?.association === "unassociated"); });
      } catch (error) {
        const value = workspaceStore.getSnapshot().buckets[id];
        if (error instanceof HistorySyncFailure) {
          if (current(ticket) && value?.request.id === requestId && value.request.sequence === initialBucket?.request.sequence && value.requests[requestId]?.snapshot.attempt === initial.snapshot.attempt && value.requests[requestId]?.association === "unassociated" && workspaceStore.applySnapshot(historyTicket, rawSnapshot, error.message, true)) {
            if (value.activityEpoch === activityEpoch && value.activityObservationSequence === activitySequence) workspaceStore.patchBucket(ticket, id, currentValue => currentValue.request.id === requestId && currentValue.request.sequence === initialBucket?.request.sequence ? { ...currentValue, request: { ...currentValue.request, error: error.message } } : currentValue);
            for (const request of workspaceStore.getSnapshot().buckets[id]?.pendingRequests ?? []) if (request.status === "running") workspaceController.schedulePoll(id, request.request_id, ticket);
          }
          return;
        }
        throw error;
      }
      const record = workspaceStore.getSnapshot().buckets[id]?.requests[requestId];
      if (!record || record.association !== "unassociated" || record.snapshot.status !== "completed" || record.snapshot.attempt !== initial.snapshot.attempt || snapshot.session.user_id !== ticket.userId || snapshot.session.session_id !== id || snapshot.session.profile_id !== (snapshot.profile?.id ?? null) || (snapshot.profile && snapshot.profile.user_id !== ticket.userId) || snapshot.session.active_request_id !== null || snapshot.session.state_version < Number(initial.snapshot.response_json?.state_version)) throw new Error("session mismatch");
      workspaceStore.patchBucket(ticket, id, value => {
        const currentRecord = value.requests[requestId];
        if (!currentRecord || currentRecord.association !== "unassociated" || currentRecord.snapshot.status !== "completed" || currentRecord.snapshot.attempt !== initial.snapshot.attempt || value.request.id !== requestId || value.request.sequence !== initialBucket?.request.sequence) return value;
        const existingMessages = new Map(value.messages.map(item => [item.id, item]));
        if (snapshot.messages.items.some(item => existingMessages.has(item.id) && JSON.stringify(existingMessages.get(item.id)) !== JSON.stringify(item))) return { ...value, request: { ...value.request, error: "消息内容不一致，请重新查询" } };
        const incomingRevision = snapshot.profile_summary?.profile_revision ?? snapshot.profile?.revision ?? null;
        const profileConflict = value.profileRevision !== null && incomingRevision === value.profileRevision && (JSON.stringify(value.profile) !== JSON.stringify(snapshot.profile) || JSON.stringify(value.profileSummary) !== JSON.stringify(snapshot.profile_summary));
        const profileNewer = value.profileRevision === null || (incomingRevision !== null && incomingRevision > value.profileRevision);
        const profilePatch = profileConflict ? { recoveryError: "画像版本相同但内容不一致，请重新查询" } : profileNewer ? { profile: snapshot.profile, profileSummary: snapshot.profile_summary, profileRevision: incomingRevision } : {};
        const invalidTeaching = !Number.isSafeInteger(snapshot.session.state_version) || snapshot.session.state_version < 0 || !Number.isSafeInteger(snapshot.session.next_turn_index) || snapshot.session.next_turn_index < 0;
        const teachingConflict = value.session !== null && value.teachingStateVersion === snapshot.session.state_version && (value.session.active_node_id !== snapshot.session.active_node_id || value.session.next_turn_index !== snapshot.session.next_turn_index || JSON.stringify(value.teachingState) !== JSON.stringify(snapshot.teaching_state) || value.teachingStateSource !== snapshot.teaching_state_source);
        if (invalidTeaching || teachingConflict || (value.session && value.session.profile_id !== snapshot.session.profile_id)) return { ...value, ...profilePatch, activityGate: "uncertain", activityError: "教学状态不一致，请重新查询" };
        if (value.activityEpoch !== activityEpoch || value.activityObservationSequence !== activitySequence || value.session?.active_request_id || value.pendingRequests.some(item => item.request_id !== requestId && item.status === "running")) return { ...value, ...profilePatch, activityGate: "uncertain" };
        const useHistory = value.teachingStateVersion === null || snapshot.session.state_version >= value.teachingStateVersion;
        if (useHistory) for (const item of snapshot.messages.items) existingMessages.set(item.id, item);
        const retainFrontier = value.historyLoaded && value.historyIds.length > 0;
        return { ...value, ...(useHistory ? { session: snapshot.session, teachingState: snapshot.teaching_state, teachingStateSource: snapshot.teaching_state_source, teachingStateVersion: snapshot.session.state_version } : {}), ...profilePatch, ...(useHistory ? { messages: sortHistoryMessages([...existingMessages.values()]), historyLoaded: true, historyIds: [...new Set([...value.historyIds, ...snapshot.messages.items.map(item => item.id)])], historySyncError: null, ...(retainFrontier || messagePages.has(key(ticket, id)) ? {} : { nextMessageCursor: snapshot.messages.next_cursor, visitedMessageCursors: [] }) } : {}), continuedUnassociated: { ...value.continuedUnassociated, [requestId]: initial.snapshot.attempt }, request: { ...value.request, status: "completed", error: null } };
      });
    } catch (error) { if (error instanceof StaleObservation) return; if (current(ticket)) workspaceStore.patchBucket(ticket, id, value => value.load.sequence === historyTicket.sequence && value.activityEpoch === activityEpoch && value.activityObservationSequence === activitySequence && value.request.id === requestId && value.request.sequence === initialBucket?.request.sequence && value.requests[requestId]?.snapshot.attempt === initial.snapshot.attempt && value.requests[requestId]?.association === "unassociated" ? { ...value, ...(error instanceof HistorySyncFailure ? { historySyncError: error.message } : {}), request: { ...value.request, error: error instanceof HistorySyncFailure ? error.message : "尚无法继续，请重新查询" } } : value); }
  },
  async retry(id: string, requestId: string) {
    const ticket = workspaceStore.captureTicket();
    const draftRevision = workspaceStore.getSnapshot().buckets[id]?.draftRevision ?? null;
    const retryKey = `${key(ticket, id)}:${requestId}`;
    if (retries.has(retryKey)) return;
    retries.add(retryKey);
    try {
      if (!current(ticket)) return;
      const request = await readRequest(ticket, id, requestId);
      if (!current(ticket)) return;
      if (request.user_id !== ticket.userId || request.session_id !== id || request.request_id !== requestId || !["failed", "interrupted"].includes(request.status)) throw new Error("request not retryable");
      if (!workspaceStore.mergeRequest(ticket, request) || workspaceStore.getSnapshot().buckets[id]?.requests[requestId]?.association === "inconsistent") throw new Error("request mismatch");
      workspaceStore.patchBucket(ticket, id, value => ({ ...value, request: { id: requestId, status: "running", attempt: request.attempt, error: null, sequence: value.request.sequence + 1, text: String(request.request_payload.message ?? "") } }));
      const beforeSnapshot = workspaceStore.getSnapshot(); const beforeBucket = beforeSnapshot.buckets[id];
      if (!beforeBucket) return;
      const activityEpoch = beforeBucket.activityEpoch; const observation = beforeBucket.activityObservationSequence + 1; const activeSessionEpoch = beforeSnapshot.activeSessionEpoch; const requestSequence = beforeBucket.request.sequence;
      workspaceStore.patchBucket(ticket, id, value => ({ ...value, activityObservationSequence: observation }));
      const snap = await loadSnapshot(id);
      if (!current(ticket)) return;
      const latest = workspaceStore.getSnapshot(); const latestBucket = latest.buckets[id];
      if (!latestBucket || latest.activeSessionId !== id || latest.activeSessionEpoch !== activeSessionEpoch || latestBucket.activityEpoch !== activityEpoch || latestBucket.activityObservationSequence !== observation || latestBucket.request.id !== requestId || latestBucket.request.sequence !== requestSequence) {
        workspaceStore.patchBucket(ticket, id, value => value.request.id === requestId && value.request.sequence === requestSequence && value.request.status === "running" ? { ...value, request: { ...value.request, status: "failed", error: "状态已变化，请重新查询" } } : value);
        return;
      }
      if (!snapshotIdentityValid(snap, ticket.userId, id, latestBucket.session)) {
        workspaceStore.patchBucket(ticket, id, value => value.request.id === requestId && value.request.sequence === requestSequence && value.activityEpoch === activityEpoch && value.activityObservationSequence === observation ? { ...value, activityGate: "uncertain", activityError: "会话画像信息不一致，请重新查询", request: { ...value.request, status: "failed", error: "会话信息待确认，请重新查询" } } : value); return;
      }
      if (snap.session.session_id !== id || snap.session.user_id !== ticket.userId || snap.session.profile_id !== request.profile_id || snap.profile?.id !== request.profile_id || snap.profile.user_id !== ticket.userId || snap.session.active_node_id !== request.active_node_id || snap.session.state_version !== request.base_state_version) throw new ApiError(409, "会话内容已变化，请复制原文后重新提问", "stale_context");
      if (snap.session.active_request_id !== null) {
        workspaceStore.patchBucket(ticket, id, value => ({ ...value, activityGate: "uncertain", request: { ...value.request, status: "failed", error: "会话已有正在处理的请求，请重新查询" } }));
        return;
      }
      if (!current(ticket)) return;
      const result = await retryRequest(id, requestId, { expected_attempt: request.attempt, expected_state_version: snap.session.state_version });
      if (!current(ticket)) return;
      if (result.session_id !== id || result.request_id !== requestId) throw new Error("request mismatch");
      await workspaceController.reconcile(id, requestId, ticket);
    } catch (error) {
      if (error instanceof StaleObservation) return;
      if (current(ticket)) workspaceStore.patchBucket(ticket, id, value => ({ ...value, staleRequestId: error instanceof ApiError && error.code === "stale_context" ? requestId : value.staleRequestId, staleDraftRevision: error instanceof ApiError && error.code === "stale_context" ? draftRevision : value.staleDraftRevision, request: value.request.id === requestId ? { ...value.request, status: error instanceof ApiError && error.code === "stale_context" ? "failed" : "unknown", error: message(error) } : value.request }));
    } finally { retries.delete(retryKey); }
  },
};

function valueRequestCompleted(id: string, requestId: string) {
  const request = workspaceStore.getSnapshot().buckets[id]?.request;
  return request?.id === requestId && request.status === "completed";
}
