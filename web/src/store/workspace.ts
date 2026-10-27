import { GroupedSessions, ProfileItem, SessionGroup, WorkspaceMessage, WorkspaceSession } from "../types";

export interface AccountIdentity { userId: number | null; token: string | null; generation: number }
export interface AuthTicket extends AccountIdentity {}
type Status = "idle" | "loading" | "ready" | "error";
type TicketKind = "account" | "load" | "request" | "groups" | "group";
export interface AsyncTicket extends AuthTicket { kind: TicketKind; sessionId?: string; requestId?: string | null; groupKey?: string; sequence: number; requestCursor: string | null }
interface PageLoad { status: Status; error: string | null; sequence: number; requestedCursor: string | null }
export interface GroupPageState extends PageLoad { nextSessionCursor: string | null }
export interface SessionClientState {
  messages: WorkspaceMessage[];
  draft: string;
  request: { id: string | null; status: string | null; attempt: number | null; error: string | null; sequence: number };
  save: { status: "idle" | "saving" | "saved" | "error"; error: string | null; viewVersion: number | null };
  load: { status: Status; error: string | null; sequence: number };
  teachingStateVersion: number | null;
  profileRevision: number | null;
  nextMessageCursor: string | null;
}
export interface WorkspaceClientState {
  account: AccountIdentity;
  activeSessionId: string | null;
  groups: SessionGroup[];
  nextGroupCursor: string | null;
  groupsLoad: PageLoad;
  groupPages: Record<string, GroupPageState>;
  buckets: Record<string, SessionClientState>;
  sidebar: { pinned: boolean; collapsed: boolean; mobileOpen: boolean; expandedGroups: Set<string> };
}
const idlePage = (): PageLoad => ({ status: "idle", error: null, sequence: 0, requestedCursor: null });
function emptyState(account: AccountIdentity): WorkspaceClientState {
  return { account, activeSessionId: null, groups: [], nextGroupCursor: null, groupsLoad: idlePage(), groupPages: {}, buckets: {}, sidebar: { pinned: true, collapsed: false, mobileOpen: false, expandedGroups: new Set() } };
}
const emptyBucket = (): SessionClientState => ({ messages: [], draft: "", request: { id: null, status: null, attempt: null, error: null, sequence: 0 }, save: { status: "idle", error: null, viewVersion: null }, load: { status: "idle", error: null, sequence: 0 }, teachingStateVersion: null, profileRevision: null, nextMessageCursor: null });
function mergeSessions(existing: WorkspaceSession[], incoming: WorkspaceSession[]) {
  const seen = new Set(existing.map(session => session.session_id));
  return [...existing, ...incoming.filter(session => { if (seen.has(session.session_id)) return false; seen.add(session.session_id); return true; })];
}

export function createWorkspaceStore() {
  let initialized = false;
  let state = emptyState({ userId: null, token: null, generation: 0 });
  const listeners = new Set<() => void>();
  const publish = (next: WorkspaceClientState) => { state = next; listeners.forEach(listener => listener()); };
  const isCurrent = (ticket: AuthTicket) => ticket.generation === state.account.generation && ticket.userId === state.account.userId && ticket.token === state.account.token;
  function startAccount(userId: number | null, token: string | null) {
    initialized = true;
    publish(emptyState({ userId, token, generation: state.account.generation + 1 }));
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
    if (state.activeSessionId !== id) publish({ ...state, activeSessionId: id });
  }
  function beginSessionLoad(id: string) {
    const bucket = bucketFor(id);
    if (!bucket) throw new Error("会话尚未建立");
    updateBucket(id, { ...bucket, load: { status: "loading", error: null, sequence: bucket.load.sequence + 1 } });
    return captureTicket(id, undefined, "load");
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
  return {
    getSnapshot: () => state,
    getServerSnapshot: () => state,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    startAccount, clearAccount: () => startAccount(null, null),
    bootstrapAccount(userId: number | null, token: string | null) { if (!initialized || userId !== state.account.userId || token !== state.account.token) startAccount(userId, token); },
    captureTicket, isCurrent, ensureSessionBucket, setActiveSession, syncRouteSelection: setActiveSession, beginSessionLoad, beginSessionRequest, applySessionResult,
    beginGroups, appendGroups, setGroups: appendGroups, failGroups, beginGroupPage, appendGroupSessions, failGroupPage, upsertSession,
    collapseSidebar: () => sidebarPatch({ pinned: false, collapsed: true }),
    expandSidebar: () => sidebarPatch({ collapsed: false }),
    pinSidebar: () => sidebarPatch({ pinned: true, collapsed: false }),
    toggleSidebarPin: () => sidebarPatch(state.sidebar.pinned ? { pinned: false } : { pinned: true, collapsed: false }),
    setMobileOpen: (mobileOpen: boolean) => sidebarPatch({ mobileOpen }),
    toggleGroup(key: string) { const expandedGroups = new Set(state.sidebar.expandedGroups); if (expandedGroups.has(key)) expandedGroups.delete(key); else expandedGroups.add(key); sidebarPatch({ expandedGroups }); },
  };
}
export const workspaceStore = createWorkspaceStore();
