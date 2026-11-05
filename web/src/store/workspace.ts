import { GroupedSessions, ProfileItem, ProfileSummary, ReadingAnchor, RequestSnapshot, SessionGroup, SessionSnapshot, ViewState, WorkspaceMessage, WorkspaceSession } from "../types";
import { getLocalRecovery, RecoveryCandidate } from "./localRecovery";

export interface AccountIdentity { userId: number | null; token: string | null; generation: number }
export interface AuthTicket extends AccountIdentity {}
export interface BackupItem { kind: "draft" | "prepared" | "request" | "workspace" | "preferences"; sessionId: string | null; itemId?: string; ok: boolean }
type Status = "idle" | "loading" | "ready" | "error";
type TicketKind = "account" | "load" | "request" | "groups" | "group";
export interface AsyncTicket extends AuthTicket { kind: TicketKind; sessionId?: string; requestId?: string | null; groupKey?: string; sequence: number; requestCursor: string | null; activityEpoch?: number; activityObservationSequence?: number }
interface PageLoad { status: Status; error: string | null; sequence: number; requestedCursor: string | null }
export interface GroupPageState extends PageLoad { nextSessionCursor: string | null }
export interface RequestTurnBaseline { owner_user_id: number; session_id: string; request_id: string; profile_id: string | null; active_node_id: string | null; base_state_version: number; expected_turn_index: number; provenance: "before_submit" | "observed_running_snapshot"; snapshot_sequence: number }
export interface RequestRecord { snapshot: RequestSnapshot; baseline: RequestTurnBaseline | null; association: "unknown" | "pending_messages" | "matched" | "unassociated" | "inconsistent" }
export function snapshotIdentityValid(snapshot: SessionSnapshot, userId: number | null, id: string, existing: WorkspaceSession | null): boolean {
  const session = snapshot.session; const profile = snapshot.profile; const summary = snapshot.profile_summary;
  if (session.session_id !== id || session.user_id !== userId || session.profile_id !== (profile?.id ?? null) || (profile && profile.user_id !== userId) || (existing && (existing.session_id !== id || existing.user_id !== userId || existing.profile_id !== session.profile_id))) return false;
  if (summary && (!profile || !Array.isArray(summary.nodes) || !Array.isArray(summary.edges) || summary.nodes.some(item => item.profile_id !== session.profile_id) || summary.edges.some(item => item.profile_id !== session.profile_id))) return false;
  return Array.isArray(snapshot.pending_requests) && snapshot.pending_requests.every(item => item.user_id === userId && item.session_id === id && item.profile_id === session.profile_id);
}
export interface SessionClientState {
  messages: WorkspaceMessage[];
  draft: string;
  request: { id: string | null; status: string | null; attempt: number | null; error: string | null; sequence: number; text?: string };
  save: { status: "idle" | "dirty" | "saving" | "saved" | "error" | "conflict"; error: string | null; viewVersion: number | null };
  load: { status: Status; error: string | null; sequence: number };
  messageEpoch: number;
  historyLoaded: boolean;
  historyIds: number[];
  historySyncError: string | null;
  activityEpoch: number;
  activityGate: "clear" | "checking" | "uncertain";
  activityError: string | null;
  activityObservationSequence: number;
  teachingStateVersion: number | null;
  profileRevision: number | null;
  teachingStateSource: SessionSnapshot["teaching_state_source"] | null;
  nextMessageCursor: string | null;
  messagePageError: string | null;
  visitedMessageCursors: string[];
  anchorRestoreSequence: number;
  session: WorkspaceSession | null;
  profile: ProfileItem | null;
  profileSummary: ProfileSummary | null;
  teachingState: Record<string, unknown> | null;
  pendingRequests: RequestSnapshot[];
  readingAnchor: ReadingAnchor | null;
  draftRevision: number;
  recoveryCandidates: RecoveryCandidate[];
  preparedCandidates: RecoveryCandidate[];
  cancelledPreparations: string[];
  acknowledgedPreparations: string[];
  requestCandidates: RecoveryCandidate[];
  resendableRequests: string[];
  conflictedRequests: string[];
  continuedUnassociated: Record<string, number>;
  uncertainMatched: string[];
  uncertainPrepared: Record<string, { requestId: string; text: string; sequence: number; payload: Record<string, unknown>; baseline: RequestTurnBaseline }>;
  staleRequestId: string | null;
  staleDraftRevision: number | null;
  recoveryError: string | null;
  conflictView: ViewState | null;
  requests: Record<string, RequestRecord>;
  prepared: Record<string, { text: string; sequence: number; phase?: "prepared" | "linked"; requestId?: string; payload?: Record<string, unknown>; baseline?: RequestTurnBaseline | null }>;
  localRequests: Record<string, { payload: Record<string, unknown>; baseline: RequestTurnBaseline | number | null }>;
}
export function hasBlockingRecovery(bucket: SessionClientState) {
  return bucket.requestCandidates.some(candidate => {
    const record = bucket.requests[candidate.itemId]; const payload = candidate.payload as Record<string, unknown> | undefined;
    if (!record || !payload) return true;
    const request = record.snapshot;
    if (payload.request_id !== request.request_id || payload.session_id !== request.session_id || payload.profile_id !== request.profile_id || payload.message !== request.request_payload.message || payload.expected_state_version !== request.base_state_version) return true;
    const baseline = candidate.baseline;
    if (JSON.stringify(baseline) !== JSON.stringify(record.baseline)) return true;
    if (record.association === "inconsistent") return true;
    return !(record.association === "matched" || (record.association === "unassociated" && request.status === "completed" && bucket.continuedUnassociated[candidate.itemId] === request.attempt) || ["failed", "interrupted"].includes(request.status));
  });
}
export function isMatchedLinked(bucket: SessionClientState, candidate: RecoveryCandidate) {
  if (candidate.kind !== "prepared" || candidate.schema !== 2 || candidate.phase !== "linked" || typeof candidate.requestId !== "string") return false;
  const payload = candidate.payload as Record<string, unknown> | undefined; const record = bucket.requests[candidate.requestId];
  if (!payload || !record || record.association !== "matched" || record.snapshot.status !== "completed" || !record.baseline) return false;
  const request = record.snapshot;
  return payload.request_id === request.request_id && payload.session_id === request.session_id && payload.profile_id === request.profile_id && payload.message === request.request_payload.message && payload.expected_state_version === request.base_state_version && candidate.userId === request.user_id && candidate.sessionId === request.session_id && candidate.text === payload.message && JSON.stringify(candidate.baseline) === JSON.stringify(record.baseline);
}
export function isMatchedLocalCopy(bucket: SessionClientState, candidate: RecoveryCandidate, writerId: string) {
  if (candidate.writerId !== writerId) return false;
  if (candidate.kind === "prepared") {
    if (typeof candidate.requestId === "string") return bucket.uncertainMatched.includes(candidate.requestId) && isMatchedLinked(bucket, candidate);
    const proof = bucket.uncertainPrepared[candidate.writeId]; const record = proof && bucket.requests[proof.requestId];
    return Boolean(proof && candidate.phase === "prepared" && candidate.text === proof.text && candidate.sequence === proof.sequence && record && record.association === "matched" && record.snapshot.status === "completed" && record.snapshot.user_id === candidate.userId && record.snapshot.session_id === candidate.sessionId && proof.payload.request_id === record.snapshot.request_id && proof.payload.session_id === record.snapshot.session_id && proof.payload.profile_id === record.snapshot.profile_id && proof.payload.message === record.snapshot.request_payload.message && proof.payload.expected_state_version === record.snapshot.base_state_version && JSON.stringify(proof.baseline) === JSON.stringify(record.baseline));
  }
  if (candidate.kind !== "request" || !bucket.uncertainMatched.includes(candidate.itemId)) return false;
  const record = bucket.requests[candidate.itemId]; const payload = candidate.payload as Record<string, unknown> | undefined;
  return Boolean(record && record.association === "matched" && record.snapshot.status === "completed" && record.baseline && payload && candidate.userId === record.snapshot.user_id && candidate.sessionId === record.snapshot.session_id && payload.request_id === record.snapshot.request_id && payload.session_id === record.snapshot.session_id && payload.profile_id === record.snapshot.profile_id && payload.message === record.snapshot.request_payload.message && payload.expected_state_version === record.snapshot.base_state_version && JSON.stringify(candidate.baseline) === JSON.stringify(record.baseline));
}
export function sortHistoryMessages(messages: WorkspaceMessage[]) {
  const roleOrder = (role: string) => role === "user" ? 0 : role === "assistant" ? 1 : 2;
  return [...messages].sort((a, b) => a.turn_index - b.turn_index || roleOrder(a.role) - roleOrder(b.role) || a.id - b.id);
}
export interface WorkspaceClientState {
  account: AccountIdentity;
  activeSessionId: string | null;
  activeSessionEpoch: number;
  groups: SessionGroup[];
  nextGroupCursor: string | null;
  groupsLoad: PageLoad;
  groupPages: Record<string, GroupPageState>;
  buckets: Record<string, SessionClientState>;
  sidebar: { pinned: boolean; collapsed: boolean; mobileOpen: boolean; expandedGroups: Set<string> };
  exitPending: boolean;
  workspace: { version: number | null; lastSessionId: string | null; desiredSessionId: string | null; dirty: boolean; saving: boolean; conflict: boolean; error: string | null; errorSource: "load" | "save" | null; sequence: number; readSequence: number; candidates: RecoveryCandidate[]; candidatesLoaded: boolean; recoveryError: string | null; prefs: WorkspacePreferencesState };
}
export interface WorkspacePreferences { pinned: boolean; collapsed: boolean; progressYRatio: number }
export interface WorkspacePreferencesState { localValues: WorkspacePreferences; serverValues: WorkspacePreferences; dirtyFields: (keyof WorkspacePreferences)[]; sequence: number; loaded: boolean; saving: boolean; error: string | null }
const defaultPreferences = (): WorkspacePreferences => ({ pinned: true, collapsed: false, progressYRatio: 0.5 });
const idlePage = (): PageLoad => ({ status: "idle", error: null, sequence: 0, requestedCursor: null });
function emptyState(account: AccountIdentity): WorkspaceClientState {
  return { account, activeSessionId: null, activeSessionEpoch: 0, groups: [], nextGroupCursor: null, groupsLoad: idlePage(), groupPages: {}, buckets: {}, sidebar: { pinned: true, collapsed: false, mobileOpen: false, expandedGroups: new Set() }, exitPending: false, workspace: { version: null, lastSessionId: null, desiredSessionId: null, dirty: false, saving: false, conflict: false, error: null, errorSource: null, sequence: 0, readSequence: 0, candidates: [], candidatesLoaded: false, recoveryError: null, prefs: { localValues: defaultPreferences(), serverValues: defaultPreferences(), dirtyFields: [], sequence: 0, loaded: false, saving: false, error: null } } };
}
const emptyBucket = (): SessionClientState => ({ messages: [], draft: "", request: { id: null, status: null, attempt: null, error: null, sequence: 0 }, save: { status: "idle", error: null, viewVersion: null }, load: { status: "idle", error: null, sequence: 0 }, messageEpoch: 0, historyLoaded: false, historyIds: [], historySyncError: null, activityEpoch: 0, activityGate: "clear", activityError: null, activityObservationSequence: 0, teachingStateVersion: null, profileRevision: null, teachingStateSource: null, nextMessageCursor: null, messagePageError: null, visitedMessageCursors: [], anchorRestoreSequence: 0, session: null, profile: null, profileSummary: null, teachingState: null, pendingRequests: [], readingAnchor: null, draftRevision: 0, recoveryCandidates: [], preparedCandidates: [], cancelledPreparations: [], acknowledgedPreparations: [], requestCandidates: [], resendableRequests: [], conflictedRequests: [], continuedUnassociated: {}, uncertainMatched: [], uncertainPrepared: {}, staleRequestId: null, staleDraftRevision: null, recoveryError: null, conflictView: null, requests: {}, prepared: {}, localRequests: {} });
function mergeRequestValue(previous: RequestRecord | undefined, incoming: RequestSnapshot): RequestRecord | null {
  if (!Number.isSafeInteger(incoming.attempt) || incoming.attempt < 1 || !["running", "failed", "interrupted", "completed"].includes(incoming.status)) return null;
  if (typeof incoming.request_payload?.message !== "string" || incoming.request_payload.profile_id !== incoming.profile_id || incoming.request_payload.active_node_id !== incoming.active_node_id || incoming.request_payload.base_state_version !== incoming.base_state_version) return null;
  if (incoming.status === "completed") {
    const response = incoming.response_json;
    if (!response || response.persisted !== true || response.status !== "completed" || response.session_id !== incoming.session_id || response.request_id !== incoming.request_id || response.attempt !== incoming.attempt || response.state_version !== incoming.base_state_version + 1) return null;
  }
  if (previous) {
    const old = previous.snapshot;
    if (incoming.user_id !== old.user_id || incoming.session_id !== old.session_id || incoming.request_id !== old.request_id || incoming.profile_id !== old.profile_id || incoming.active_node_id !== old.active_node_id || incoming.base_state_version !== old.base_state_version || JSON.stringify(incoming.request_payload) !== JSON.stringify(old.request_payload)) return null;
    if (old.status === "completed") return incoming.attempt === old.attempt && incoming.status === "completed" && JSON.stringify(incoming.response_json) === JSON.stringify(old.response_json) ? previous : null;
    if (incoming.attempt < old.attempt) return null;
    if (incoming.attempt === old.attempt && old.status !== "running") {
      if (incoming.status === "running") return null;
      if (old.status !== incoming.status) return { ...previous, association: "inconsistent" };
    }
  }
  return { snapshot: incoming, baseline: previous?.baseline ?? null, association: incoming.status === "completed" ? "pending_messages" : previous?.association ?? "unknown" };
}
function mergeSessions(existing: WorkspaceSession[], incoming: WorkspaceSession[]) {
  const seen = new Set(existing.map(session => session.session_id));
  return [...existing, ...incoming.filter(session => { if (seen.has(session.session_id)) return false; seen.add(session.session_id); return true; })];
}

export function createWorkspaceStore() {
  let initialized = false;
  let failedRecovery = false;
  let state = emptyState({ userId: null, token: null, generation: 0 });
  const listeners = new Set<() => void>();
  const publish = (next: WorkspaceClientState) => { state = next; listeners.forEach(listener => listener()); };
  const isCurrent = (ticket: AuthTicket) => ticket.generation === state.account.generation && ticket.userId === state.account.userId && ticket.token === state.account.token;
  function prepareAccountTransition(ticket: AuthTicket) {
    const items: BackupItem[] = [];
    if (!isCurrent(ticket)) return { ok: false, stale: true, items };
    if (ticket.userId === null) return { ok: true, stale: false, items };
    let ok = true;
    const record = (item: BackupItem) => { items.push(item); if (!item.ok) ok = false; };
    for (const [id, bucket] of Object.entries(state.buckets)) {
      if (bucket.recoveryCandidates.length || bucket.preparedCandidates.length || bucket.requestCandidates.length) try {
        const recovery = getLocalRecovery();
        for (const [kind, candidates] of [["draft", bucket.recoveryCandidates], ["prepared", bucket.preparedCandidates], ["request", bucket.requestCandidates]] as const) {
          if (!candidates.length) continue;
          const found = recovery.listResult(ticket.userId, id, kind);
          if (found.ok) for (const discovered of found.candidates) if (!candidates.some(item => JSON.stringify(item) === JSON.stringify(discovered))) {
            record({ kind, sessionId: id, itemId: discovered.itemId, ok: false });
            patchBucket(ticket, id, value => kind === "prepared" ? { ...value, preparedCandidates: [...value.preparedCandidates, discovered], acknowledgedPreparations: [] } : kind === "request" ? { ...value, requestCandidates: [...value.requestCandidates, discovered] } : { ...value, recoveryCandidates: [...value.recoveryCandidates, discovered] });
          }
          for (const candidate of candidates) {
            if (isMatchedLocalCopy(bucket, candidate, recovery.writerId)) {
              const sameKey = found.candidates.find(item => item.writerId === candidate.writerId && item.itemId === candidate.itemId);
              if (!found.ok || !sameKey || JSON.stringify(sameKey) === JSON.stringify(candidate)) continue;
              patchBucket(ticket, id, value => ({ ...value, acknowledgedPreparations: value.acknowledgedPreparations.filter(item => item !== candidate.writeId), recoveryError: "本机副本已变化或无法读取，请重新检查" }));
            }
            record({ kind, sessionId: id, itemId: candidate.itemId, ok: found.ok && (candidate.writerId === "" || found.candidates.some(item => JSON.stringify(item) === JSON.stringify(candidate))) });
          }
        }
      } catch { record({ kind: "draft", sessionId: id, ok: false }); }
      if (["dirty", "saving", "error", "conflict"].includes(bucket.save.status)) {
        try {
          const result = getLocalRecovery().writeDraft(ticket.userId, id, { draft: bucket.draft, reading_anchor: bucket.readingAnchor, baseVersion: bucket.save.viewVersion ?? 0, sequence: bucket.draftRevision });
          record({ kind: "draft", sessionId: id, ok: result.ok });
          if (result.ok) patchBucket(ticket, id, value => ({ ...value, recoveryCandidates: value.recoveryCandidates.map(item => item.writerId === result.candidate.writerId ? result.candidate : item) }));
        } catch { record({ kind: "draft", sessionId: id, ok: false }); }
      }
      for (const [prepareId, prepared] of Object.entries(bucket.prepared)) {
        try { const result = getLocalRecovery().writePrepared(ticket.userId, id, prepareId, prepared); record({ kind: "prepared", sessionId: id, itemId: prepareId, ok: result.ok }); if (result.ok) patchBucket(ticket, id, value => ({ ...value, preparedCandidates: value.preparedCandidates.map(item => item.writerId === result.candidate.writerId && item.itemId === prepareId ? result.candidate : item) })); } catch { record({ kind: "prepared", sessionId: id, itemId: prepareId, ok: false }); }
      }
      for (const [requestId, local] of Object.entries(bucket.localRequests)) {
        try { const result = getLocalRecovery().writeRequest(ticket.userId, id, requestId, local); record({ kind: "request", sessionId: id, itemId: requestId, ok: result.ok }); if (result.ok) patchBucket(ticket, id, value => ({ ...value, requestCandidates: value.requestCandidates.map(item => (item.writerId === result.candidate.writerId || item.writerId === "") && item.itemId === requestId ? result.candidate : item) })); } catch { record({ kind: "request", sessionId: id, itemId: requestId, ok: false }); }
      }
    }
    if (state.workspace.candidates.length) {
      try { const found = getLocalRecovery().listResult(ticket.userId, "workspace", "workspace"); for (const candidate of state.workspace.candidates) record({ kind: "workspace", sessionId: null, ok: found.ok && found.candidates.some(item => JSON.stringify(item) === JSON.stringify(candidate)) }); }
      catch { record({ kind: "workspace", sessionId: null, ok: false }); }
    }
    if (state.workspace.dirty || state.workspace.saving) {
      try {
        const result = getLocalRecovery().writeWorkspace(ticket.userId, { lastSessionId: state.workspace.desiredSessionId, baseVersion: state.workspace.version, sequence: state.workspace.sequence });
        record({ kind: "workspace", sessionId: null, ok: result.ok });
        if (result.ok) patchWorkspace(ticket, value => ({ ...value, candidates: value.candidates.map(item => item.writerId === result.candidate.writerId ? result.candidate : item) }));
      } catch { record({ kind: "workspace", sessionId: null, ok: false }); }
    }
    return { ok, stale: false, items };
  }
  function startAccount(userId: number | null, token: string | null, force = false) {
    const backup = prepareAccountTransition(state.account);
    if (!backup.ok && !force) return false;
    if (!backup.ok && force) failedRecovery = true;
    initialized = true;
    publish(emptyState({ userId, token, generation: state.account.generation + 1 }));
    return true;
  }
  const bucketFor = (id: string) => Object.prototype.hasOwnProperty.call(state.buckets, id) ? state.buckets[id] : undefined;
  function captureTicket(sessionId?: string, requestId?: string | null, kind?: TicketKind): AsyncTicket {
    const actualKind = kind ?? (sessionId ? requestId ? "request" : "load" : "account");
    const bucket = sessionId ? bucketFor(sessionId) : undefined;
    return { ...state.account, kind: actualKind, sessionId, requestId: requestId ?? bucket?.request.id, sequence: actualKind === "request" ? bucket?.request.sequence ?? 0 : bucket?.load.sequence ?? 0, requestCursor: null };
  }
  function ensureSessionBucket(id: string) {
    if (!bucketFor(id)) publish({ ...state, buckets: { ...state.buckets, [id]: emptyBucket() } });
    return bucketFor(id)!;
  }
  function updateBucket(id: string, next: SessionClientState) { publish({ ...state, buckets: { ...state.buckets, [id]: next } }); }
  function setActiveSession(id: string | null) {
    if (id !== null) ensureSessionBucket(id);
    if (state.activeSessionId !== id) publish({ ...state, activeSessionId: id, activeSessionEpoch: state.activeSessionEpoch + 1 });
  }
  function beginSessionLoad(id: string) {
    const bucket = bucketFor(id);
    if (!bucket) throw new Error("会话尚未建立");
    const observation = bucket.activityObservationSequence + 1;
    updateBucket(id, { ...bucket, activityGate: bucket.activityGate === "checking" ? "uncertain" : bucket.activityGate, activityObservationSequence: observation, load: { status: "loading", error: null, sequence: bucket.load.sequence + 1 } });
    return { ...captureTicket(id, undefined, "load"), activityEpoch: bucket.activityEpoch, activityObservationSequence: observation };
  }
  function beginSessionRequest(id: string, requestId: string) {
    const bucket = bucketFor(id);
    if (!bucket) throw new Error("会话尚未建立");
    updateBucket(id, { ...bucket, request: { id: requestId, status: "pending", attempt: null, error: null, sequence: bucket.request.sequence + 1 } });
    return captureTicket(id, requestId, "request");
  }
  function applySessionResult(ticket: AsyncTicket, patch: Partial<SessionClientState>) {
    const id = ticket.sessionId; const bucket = id ? bucketFor(id) : undefined;
    if (!isCurrent(ticket) || !id || !bucket) return false;
    if (ticket.kind === "load" && ticket.sequence !== bucket.load.sequence) return false;
    if (ticket.kind === "request" && (ticket.sequence !== bucket.request.sequence || ticket.requestId !== bucket.request.id)) return false;
    updateBucket(id, { ...bucket, ...patch });
    return true;
  }
  function applySnapshot(ticket: AsyncTicket, snapshot: SessionSnapshot, historyError?: string, preserveLoad = false) {
    const id = ticket.sessionId; const bucket = id ? bucketFor(id) : undefined;
    if (!id || !bucket || !isCurrent(ticket) || ticket.kind !== "load" || ticket.sequence !== bucket.load.sequence || !snapshotIdentityValid(snapshot, ticket.userId, id, bucket.session)) return false;
    const activityCurrent = ticket.activityEpoch === bucket.activityEpoch && ticket.activityObservationSequence === bucket.activityObservationSequence;
    const teachingSession = activityCurrent ? snapshot.session : bucket.session && bucket.session.user_id === snapshot.session.user_id && bucket.session.session_id === snapshot.session.session_id && bucket.session.profile_id === snapshot.session.profile_id ? { ...bucket.session, active_node_id: snapshot.session.active_node_id, state_version: snapshot.session.state_version, next_turn_index: snapshot.session.next_turn_index } : null;
    const incomingProfileRevision = snapshot.profile_summary?.profile_revision ?? snapshot.profile?.revision ?? null;
    const profileConflict = bucket.profileRevision !== null && incomingProfileRevision === bucket.profileRevision && (JSON.stringify(bucket.profile) !== JSON.stringify(snapshot.profile) || JSON.stringify(bucket.profileSummary) !== JSON.stringify(snapshot.profile_summary));
    const staleProfile = profileConflict || (bucket.profileRevision !== null && (incomingProfileRevision === null || incomingProfileRevision < bucket.profileRevision));
    const profilePatch = staleProfile ? {} : { profile: snapshot.profile, profileSummary: snapshot.profile_summary, profileRevision: incomingProfileRevision };
    const staleView = bucket.save.viewVersion !== null && snapshot.view_state.version < bucket.save.viewVersion;
    const edited = bucket.draftRevision > 0 || bucket.save.status === "saving" || bucket.save.status === "error" || staleView;
    let recoveryCandidates = bucket.recoveryCandidates; let preparedCandidates = bucket.preparedCandidates; let requestCandidates = bucket.requestCandidates; let recoveryError = profileConflict ? "画像版本相同但内容不一致，请重新查询" : bucket.recoveryError;
    if (!bucket.session && ticket.userId !== null) {
      try {
        const recovery = getLocalRecovery(); const draft = recovery.listResult(ticket.userId, id, "draft"); const prepared = recovery.listResult(ticket.userId, id, "prepared"); const request = recovery.listResult(ticket.userId, id, "request");
        recoveryCandidates = draft.candidates; preparedCandidates = prepared.candidates; requestCandidates = request.candidates;
        recoveryError = draft.ok && prepared.ok && request.ok ? null : "本机恢复内容读取失败或包含损坏记录，请保留原始数据";
      } catch { recoveryError = "本机恢复内容读取失败或包含损坏记录，请保留原始数据"; }
    }
    const requests = { ...bucket.requests };
    for (const request of activityCurrent ? snapshot.pending_requests : []) {
      if (request.user_id !== ticket.userId || request.session_id !== id) continue;
      const merged = mergeRequestValue(requests[request.request_id], request);
      if (merged) {
        if (merged.baseline === null && request.status === "running" && snapshot.session.active_request_id === request.request_id && request.profile_id === snapshot.session.profile_id && request.active_node_id === snapshot.session.active_node_id && request.base_state_version === snapshot.session.state_version && Number.isSafeInteger(snapshot.session.next_turn_index) && snapshot.session.next_turn_index >= 0 && ticket.userId !== null) merged.baseline = { owner_user_id: ticket.userId, session_id: id, request_id: request.request_id, profile_id: request.profile_id, active_node_id: request.active_node_id, base_state_version: request.base_state_version, expected_turn_index: snapshot.session.next_turn_index, provenance: "observed_running_snapshot", snapshot_sequence: ticket.sequence };
        requests[request.request_id] = merged;
      }
    }
    const invalidTeaching = !Number.isSafeInteger(snapshot.session.state_version) || snapshot.session.state_version < 0 || !Number.isSafeInteger(snapshot.session.next_turn_index) || snapshot.session.next_turn_index < 0;
    const teachingConflict = bucket.session !== null && bucket.teachingStateVersion === snapshot.session.state_version && (bucket.session.active_node_id !== snapshot.session.active_node_id || bucket.session.next_turn_index !== snapshot.session.next_turn_index || JSON.stringify(bucket.teachingState) !== JSON.stringify(snapshot.teaching_state) || bucket.teachingStateSource !== snapshot.teaching_state_source);
    if (invalidTeaching || teachingConflict) {
      updateBucket(id, { ...bucket, ...profilePatch, recoveryError, session: bucket.session && activityCurrent ? { ...bucket.session, active_request_id: snapshot.session.active_request_id } : bucket.session, activityEpoch: activityCurrent ? bucket.activityEpoch + 1 : bucket.activityEpoch, activityGate: "uncertain", activityError: "教学状态不一致，请重新查询", pendingRequests: Object.values(requests).map(item => item.snapshot).filter(item => item.status !== "completed"), requests, ...(historyError ? { historySyncError: historyError } : {}), load: preserveLoad ? bucket.load : { ...bucket.load, status: bucket.session ? "ready" : "error", error: bucket.session ? null : "教学状态不一致，请重新查询" } });
      return true;
    }
    if (historyError) {
      const newerTeaching = Boolean(teachingSession) && (bucket.teachingStateVersion === null || snapshot.session.state_version >= bucket.teachingStateVersion);
      const active = activityCurrent && Boolean(snapshot.session.active_request_id || snapshot.pending_requests.some(item => item.status === "running"));
      updateBucket(id, { ...bucket, ...profilePatch, recoveryError, ...(newerTeaching ? { session: teachingSession, teachingState: snapshot.teaching_state, teachingStateSource: snapshot.teaching_state_source, teachingStateVersion: snapshot.session.state_version, ...(bucket.activityError === "教学状态不一致，请重新查询" ? { activityError: null } : {}) } : {}), activityEpoch: activityCurrent ? bucket.activityEpoch + 1 : bucket.activityEpoch, activityGate: active || !teachingSession ? "uncertain" : bucket.activityGate, pendingRequests: Object.values(requests).map(item => item.snapshot).filter(item => item.status !== "completed"), requests, historySyncError: historyError, load: preserveLoad ? bucket.load : { ...bucket.load, status: bucket.session ? "ready" : "error", error: bucket.session ? null : historyError } });
      return true;
    }
    if (bucket.teachingStateVersion !== null && snapshot.session.state_version < bucket.teachingStateVersion) {
      updateBucket(id, { ...bucket, activityEpoch: activityCurrent ? bucket.activityEpoch + 1 : bucket.activityEpoch, ...profilePatch, pendingRequests: Object.values(requests).map(item => item.snapshot).filter(item => item.status !== "completed"), requests, load: { ...bucket.load, status: "ready", error: null }, recoveryCandidates, preparedCandidates, requestCandidates, recoveryError });
      return true;
    }
    if (!teachingSession) {
      updateBucket(id, { ...bucket, ...profilePatch, recoveryError, activityGate: "uncertain", activityError: "会话状态尚未确认，请重新查询", load: { ...bucket.load, status: bucket.session ? "ready" : "error", error: bucket.session ? null : "会话状态尚未确认，请重新查询" } });
      return true;
    }
    const currentMessages = new Map(bucket.messages.map(item => [item.id, item]));
    if (snapshot.messages.items.some(item => currentMessages.has(item.id) && JSON.stringify(currentMessages.get(item.id)) !== JSON.stringify(item))) {
      updateBucket(id, { ...bucket, historySyncError: "历史消息内容不一致，请重新同步", load: { ...bucket.load, status: "ready", error: null } }); return true;
    }
    for (const item of snapshot.messages.items) currentMessages.set(item.id, item);
    const retainFrontier = bucket.historyLoaded && bucket.historyIds.length > 0;
    updateBucket(id, { ...bucket, activityEpoch: activityCurrent ? bucket.activityEpoch + 1 : bucket.activityEpoch, messageEpoch: bucket.messageEpoch + 1, session: teachingSession, ...profilePatch, teachingState: snapshot.teaching_state, teachingStateSource: snapshot.teaching_state_source, ...(bucket.activityError === "教学状态不一致，请重新查询" ? { activityError: null } : {}), messages: sortHistoryMessages([...currentMessages.values()]), historyLoaded: true, historyIds: [...new Set([...bucket.historyIds, ...snapshot.messages.items.map(item => item.id)])], historySyncError: null, nextMessageCursor: retainFrontier ? bucket.nextMessageCursor : snapshot.messages.next_cursor, messagePageError: retainFrontier ? bucket.messagePageError : null, visitedMessageCursors: retainFrontier ? bucket.visitedMessageCursors : [], pendingRequests: Object.values(requests).map(item => item.snapshot).filter(item => item.status !== "completed"), requests, teachingStateVersion: snapshot.session.state_version, draft: edited ? bucket.draft : snapshot.view_state.draft, readingAnchor: edited ? bucket.readingAnchor : snapshot.view_state.reading_anchor, save: { ...bucket.save, viewVersion: staleView ? bucket.save.viewVersion : snapshot.view_state.version }, load: { ...bucket.load, status: "ready", error: null }, recoveryCandidates, preparedCandidates, requestCandidates, recoveryError });
    return true;
  }
  function patchBucket(ticket: AuthTicket, id: string, update: (bucket: SessionClientState) => SessionClientState) {
    const bucket = bucketFor(id); if (!isCurrent(ticket) || !bucket) return false;
    const updated = update(bucket);
    const next = bucket.activityGate === "checking" && updated.activityGate === "checking" && updated.activityObservationSequence !== bucket.activityObservationSequence ? { ...updated, activityGate: "uncertain" as const } : updated;
    const changed = next.messages !== bucket.messages || next.nextMessageCursor !== bucket.nextMessageCursor || next.visitedMessageCursors !== bucket.visitedMessageCursors;
    updateBucket(id, changed ? { ...next, messageEpoch: bucket.messageEpoch + 1 } : next); return true;
  }
  function patchWorkspace(ticket: AuthTicket, update: (workspace: WorkspaceClientState["workspace"]) => WorkspaceClientState["workspace"]) {
    if (!isCurrent(ticket)) return false;
    publish({ ...state, workspace: update(state.workspace) }); return true;
  }
  function mergeRequest(ticket: AuthTicket, incoming: RequestSnapshot) {
    const id = incoming.session_id; const bucket = bucketFor(id);
    if (!isCurrent(ticket) || incoming.user_id !== ticket.userId || !bucket) return false;
    const merged = mergeRequestValue(bucket.requests[incoming.request_id], incoming); if (!merged) return false;
    const requests = { ...bucket.requests, [incoming.request_id]: merged };
    const continuedUnassociated = { ...bucket.continuedUnassociated }; if (continuedUnassociated[incoming.request_id] !== incoming.attempt) delete continuedUnassociated[incoming.request_id];
    updateBucket(id, { ...bucket, continuedUnassociated, activityEpoch: bucket.activityEpoch + 1, requests, pendingRequests: Object.values(requests).map(item => item.snapshot).filter(item => item.status !== "completed") });
    return true;
  }
  function beginGroups(cursor: string | null = null): AsyncTicket | null {
    if (state.groupsLoad.status === "loading" || (cursor !== null && cursor !== state.nextGroupCursor)) return null;
    const load: PageLoad = { status: "loading", error: null, sequence: state.groupsLoad.sequence + 1, requestedCursor: cursor };
    publish({ ...state, groupsLoad: load });
    return { ...captureTicket(), kind: "groups", sequence: load.sequence, requestCursor: cursor };
  }
  function rootMatches(ticket: AsyncTicket) {
    return isCurrent(ticket) && ticket.kind === "groups" && state.groupsLoad.status === "loading" && state.groupsLoad.sequence === ticket.sequence && state.groupsLoad.requestedCursor === ticket.requestCursor;
  }
  function appendGroups(ticket: AsyncTicket, page: GroupedSessions) {
    if (!rootMatches(ticket)) return false;
    const groups = [...state.groups]; const groupPages = { ...state.groupPages }; const expandedGroups = new Set(state.sidebar.expandedGroups);
    for (const incoming of page.groups) {
      const index = groups.findIndex(group => group.group_key === incoming.group_key);
      if (index >= 0) groups[index] = { ...incoming, sessions: mergeSessions(groups[index].sessions, incoming.sessions), next_session_cursor: groupPages[incoming.group_key] ? groupPages[incoming.group_key].nextSessionCursor : incoming.next_session_cursor };
      else { groups.push({ ...incoming, sessions: mergeSessions([], incoming.sessions) }); expandedGroups.add(incoming.group_key); }
      if (!groupPages[incoming.group_key]) groupPages[incoming.group_key] = { ...idlePage(), status: "ready", nextSessionCursor: incoming.next_session_cursor };
    }
    publish({ ...state, groups, groupPages, nextGroupCursor: page.next_group_cursor, groupsLoad: { ...state.groupsLoad, status: "ready", error: null }, sidebar: { ...state.sidebar, expandedGroups } });
    return true;
  }
  function failGroups(ticket: AsyncTicket, error: string) {
    if (!rootMatches(ticket)) return false;
    publish({ ...state, groupsLoad: { ...state.groupsLoad, status: "error", error } }); return true;
  }
  function beginGroupPage(groupKey: string, cursor: string | null): AsyncTicket | null {
    const page = state.groupPages[groupKey];
    if (!page || page.status === "loading" || page.nextSessionCursor !== cursor) return null;
    const next = { ...page, status: "loading" as const, error: null, sequence: page.sequence + 1, requestedCursor: cursor };
    publish({ ...state, groupPages: { ...state.groupPages, [groupKey]: next } });
    return { ...captureTicket(), kind: "group", groupKey, sequence: next.sequence, requestCursor: cursor };
  }
  function groupMatches(ticket: AsyncTicket) {
    const page = ticket.groupKey ? state.groupPages[ticket.groupKey] : undefined;
    return isCurrent(ticket) && ticket.kind === "group" && page?.status === "loading" && page.sequence === ticket.sequence && page.requestedCursor === ticket.requestCursor;
  }
  function appendGroupSessions(ticket: AsyncTicket, incoming: SessionGroup) {
    if (!groupMatches(ticket) || incoming.group_key !== ticket.groupKey) return false;
    const index = state.groups.findIndex(group => group.group_key === ticket.groupKey);
    if (index < 0 || state.groups[index].profile?.id !== incoming.profile?.id) return false;
    const groups = [...state.groups];
    groups[index] = { ...groups[index], sessions: mergeSessions(groups[index].sessions, incoming.sessions), next_session_cursor: incoming.next_session_cursor };
    publish({ ...state, groups, groupPages: { ...state.groupPages, [incoming.group_key]: { ...state.groupPages[incoming.group_key], status: "ready", error: null, nextSessionCursor: incoming.next_session_cursor } } });
    return true;
  }
  function failGroupPage(ticket: AsyncTicket, error: string) {
    if (!groupMatches(ticket) || !ticket.groupKey) return false;
    publish({ ...state, groupPages: { ...state.groupPages, [ticket.groupKey]: { ...state.groupPages[ticket.groupKey], status: "error", error } } }); return true;
  }
  function upsertSession(ticket: AuthTicket, session: WorkspaceSession, profile: ProfileItem | null) {
    if (!isCurrent(ticket) || session.profile_id !== (profile?.id ?? null)) return false;
    const key = profile?.id ?? "unassigned";
    const existing = state.groups.find(group => group.group_key === key);
    const next: SessionGroup = existing ? { ...existing, sessions: [session, ...existing.sessions.filter(item => item.session_id !== session.session_id)] } : { group_key: key, profile, summary: null, sessions: [session], next_session_cursor: null };
    const groups = existing ? state.groups.map(group => group.group_key === key ? next : group) : [...state.groups, next];
    const expandedGroups = new Set(state.sidebar.expandedGroups); expandedGroups.add(key);
    publish({ ...state, groups, buckets: { ...state.buckets, [session.session_id]: bucketFor(session.session_id) ?? emptyBucket() }, sidebar: { ...state.sidebar, expandedGroups } }); return true;
  }
  function sidebarPatch(patch: Partial<WorkspaceClientState["sidebar"]>) { publish({ ...state, sidebar: { ...state.sidebar, ...patch } }); }
  function setWorkspacePreferences(ticket: AuthTicket, patch: Partial<WorkspacePreferences>) {
    if (!isCurrent(ticket) || ticket.userId === null) return false;
    const valid: Partial<WorkspacePreferences> = {};
    if (typeof patch.pinned === "boolean") valid.pinned = patch.pinned;
    if (typeof patch.collapsed === "boolean") valid.collapsed = patch.collapsed;
    if (typeof patch.progressYRatio === "number") valid.progressYRatio = Number.isFinite(patch.progressYRatio) ? Math.max(0, Math.min(1, patch.progressYRatio)) : 0.5;
    if (valid.pinned === true) valid.collapsed = false;
    if (valid.collapsed === true) valid.pinned = false;
    const prefs = state.workspace.prefs; const localValues = { ...prefs.localValues, ...valid };
    const changed = (Object.keys(valid) as (keyof WorkspacePreferences)[]).filter(key => localValues[key] !== prefs.localValues[key]);
    if (!changed.length) return true;
    publish({ ...state, sidebar: { ...state.sidebar, pinned: localValues.pinned, collapsed: localValues.collapsed }, workspace: { ...state.workspace, prefs: { ...prefs, localValues, sequence: prefs.sequence + 1, dirtyFields: [...new Set([...prefs.dirtyFields, ...changed])], error: null } } });
    return true;
  }
  function applyWorkspacePreferences(ticket: AuthTicket, serverValues: WorkspacePreferences) {
    if (!isCurrent(ticket)) return false;
    const prefs = state.workspace.prefs; const localValues = { ...serverValues };
    for (const key of prefs.dirtyFields) Object.assign(localValues, { [key]: prefs.localValues[key] });
    publish({ ...state, sidebar: { ...state.sidebar, pinned: localValues.pinned, collapsed: localValues.collapsed }, workspace: { ...state.workspace, prefs: { ...prefs, localValues, serverValues, loaded: true, error: null } } });
    return true;
  }
  return {
    getSnapshot: () => state,
    getServerSnapshot: () => state,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    startAccount, clearAccount: (force = true) => startAccount(null, null, force), prepareAccountTransition, recoveryWarning: () => failedRecovery,
    bootstrapAccount(userId: number | null, token: string | null) { if (!initialized || userId !== state.account.userId || token !== state.account.token) startAccount(userId, token); },
    captureTicket, isCurrent, ensureSessionBucket, setActiveSession, syncRouteSelection: setActiveSession, beginSessionLoad, beginSessionRequest, applySessionResult, applySnapshot, patchBucket, patchWorkspace, mergeRequest, setWorkspacePreferences, applyWorkspacePreferences,
    beginGroups, appendGroups, setGroups: appendGroups, failGroups, beginGroupPage, appendGroupSessions, failGroupPage, upsertSession,
    collapseSidebar: () => setWorkspacePreferences(captureTicket(), { pinned: false, collapsed: true }),
    expandSidebar: () => setWorkspacePreferences(captureTicket(), { collapsed: false }),
    pinSidebar: () => setWorkspacePreferences(captureTicket(), { pinned: true, collapsed: false }),
    toggleSidebarPin: () => setWorkspacePreferences(captureTicket(), state.sidebar.pinned ? { pinned: false } : { pinned: true, collapsed: false }),
    setMobileOpen: (mobileOpen: boolean) => sidebarPatch({ mobileOpen }),
    setExitPending(value: boolean) { publish({ ...state, exitPending: value }); },
    toggleGroup(key: string) { const expandedGroups = new Set(state.sidebar.expandedGroups); if (expandedGroups.has(key)) expandedGroups.delete(key); else expandedGroups.add(key); sidebarPatch({ expandedGroups }); },
  };
}
export const workspaceStore = createWorkspaceStore();
