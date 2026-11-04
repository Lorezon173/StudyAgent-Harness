import { ReactNode, useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from "react";
import { NavLink, useLocation, useMatch, useNavigate } from "react-router-dom";
import { ApiError } from "../../api/client";
import { listGroupedSessions, listGroupSessions } from "../../api/sessions";
import { useAuth } from "../../store/auth";
import { BackupItem, workspaceStore } from "../../store/workspace";
import SessionSidebar from "./SessionSidebar";
import NewSessionDialog from "./NewSessionDialog";
import { workspaceController } from "../../store/workspaceController";

export default function WorkspaceLayout({ children }: { children: ReactNode }) {
  const state = useSyncExternalStore(workspaceStore.subscribe, workspaceStore.getSnapshot, workspaceStore.getServerSnapshot);
  const { username, userId, logout } = useAuth(); const navigate = useNavigate(); const location = useLocation(); const selected = useMatch("/chat/:sessionId");
  const [mobile, setMobile] = useState(() => window.matchMedia("(max-width:480px)").matches);
  const [newOpen, setNewOpen] = useState(false); const newButton = useRef<HTMLButtonElement>(null); const openButton = useRef<HTMLButtonElement>(null);
  const [exitError, setExitError] = useState(false); const [backupError, setBackupError] = useState(false);
  const [failedItems, setFailedItems] = useState<BackupItem[]>([]);
  const currentLocation = useRef(location.key); currentLocation.current = location.key;
  const visible = mobile ? state.sidebar.mobileOpen : !state.sidebar.collapsed;

  async function loadGroups(cursor: string | null = null) {
    const ticket = workspaceStore.beginGroups(cursor); if (!ticket) return;
    try { workspaceStore.appendGroups(ticket, await listGroupedSessions({ cursor })); }
    catch (error) { workspaceStore.failGroups(ticket, error instanceof ApiError ? error.message : "加载主题失败"); }
  }
  async function loadGroup(key: string) {
    const cursor = workspaceStore.getSnapshot().groupPages[key]?.nextSessionCursor;
    if (cursor == null) return;
    const ticket = workspaceStore.beginGroupPage(key, cursor); if (!ticket) return;
    try { workspaceStore.appendGroupSessions(ticket, await listGroupSessions({ groupKey: key, sessionCursor: cursor })); }
    catch (error) { workspaceStore.failGroupPage(ticket, error instanceof ApiError ? error.message : "加载会话失败"); }
  }
  useLayoutEffect(() => {
    const previous = workspaceStore.getSnapshot().activeSessionId;
    const next = selected?.params.sessionId ?? null;
    if (previous && previous !== next) { workspaceStore.prepareAccountTransition(workspaceStore.captureTicket()); void workspaceController.flush(previous); }
    if (location.pathname === "/chat" || location.pathname === "/chat/") workspaceStore.syncRouteSelection(null);
    else if (next) { workspaceStore.syncRouteSelection(next); if (!(location.state as { localOnly?: boolean } | null)?.localOnly) workspaceController.selectSession(next); }
    else workspaceStore.syncRouteSelection(null);
  }, [location.pathname, location.state, selected?.params.sessionId]);
  useEffect(() => {
    const backup = () => { workspaceStore.prepareAccountTransition(workspaceStore.captureTicket()); };
    window.addEventListener("pagehide", backup); window.addEventListener("beforeunload", backup);
    return () => { window.removeEventListener("pagehide", backup); window.removeEventListener("beforeunload", backup); };
  }, []);
  useEffect(() => { if (workspaceStore.getSnapshot().groupsLoad.status === "idle") void loadGroups(); }, [state.account.generation]);
  useEffect(() => {
    const media = window.matchMedia("(max-width:480px)"); const change = (event: MediaQueryListEvent) => setMobile(event.matches);
    media.addEventListener("change", change); return () => media.removeEventListener("change", change);
  }, []);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && mobile && state.sidebar.mobileOpen && !document.querySelector("dialog[open]")) { workspaceStore.setMobileOpen(false); openButton.current?.focus(); }
    };
    window.addEventListener("keydown", escape); return () => window.removeEventListener("keydown", escape);
  }, [mobile, state.sidebar.mobileOpen]);
  function closeSidebar() {
    if (mobile) workspaceStore.setMobileOpen(false); else workspaceStore.collapseSidebar();
    queueMicrotask(() => openButton.current?.focus());
  }
  async function requestLogout() {
    const ticket = workspaceStore.captureTicket(); workspaceStore.setExitPending(true); setExitError(false); setBackupError(false);
    const saved = await workspaceController.flushAll(ticket);
    if (!workspaceStore.isCurrent(ticket)) return;
    setFailedItems(saved.items.filter(item => !item.ok));
    if (saved.ok) {
      const report = workspaceStore.prepareAccountTransition(ticket);
      if (!workspaceStore.isCurrent(ticket)) return;
      if (report.ok) { logout(); return; }
      setFailedItems(report.items.filter(item => !item.ok));
      setBackupError(true);
    }
    setExitError(true);
  }
  function logoutWithBackup() {
    const ticket = workspaceStore.captureTicket(); const report = workspaceStore.prepareAccountTransition(ticket);
    if (!report.ok || !workspaceStore.isCurrent(ticket)) { setFailedItems(report.items.filter(item => !item.ok)); setBackupError(true); return; }
    logout();
  }
  async function retryWorkspace() {
    const routeKey = location.key; const path = location.pathname; const localOnly = (location.state as { localOnly?: boolean } | null)?.localOnly;
    const result = await workspaceController.retryWorkspace();
    if (result.kind !== "read" || !result.id || localOnly || (path !== "/chat" && path !== "/chat/") || currentLocation.current !== routeKey || !workspaceStore.isCurrent(result.ticket)) return;
    const latest = workspaceStore.getSnapshot().workspace;
    if (latest.sequence !== result.sequence || latest.dirty || latest.conflict) return;
    navigate(`/chat/${encodeURIComponent(result.id)}`, { replace: true });
  }
  const selectedId = selected?.params.sessionId;
  const selectedBucket = selectedId ? state.buckets[selectedId] : null;
  const selectedSession = selectedBucket?.session;
  const selectedProfile = selectedBucket?.profile;
  const validProfileTarget = selectedId && selectedSession?.session_id === selectedId && selectedSession.user_id === state.account.userId && selectedSession.profile_id && selectedProfile?.id === selectedSession.profile_id && selectedProfile.user_id === state.account.userId;
  const profileTarget = validProfileTarget ? `/profile?${new URLSearchParams({ profile_id: selectedProfile!.id, session_id: selectedId })}` : location.pathname === "/profile" ? `/profile${location.search}` : "/profile";
  const group = state.groups.find(item => item.sessions.some(session => session.session_id === state.activeSessionId));
  const breadcrumb = location.pathname === "/knowledge" ? "知识库" : location.pathname === "/profile" ? "学习画像" : group?.profile?.name || (state.activeSessionId ? "学习会话" : "开始学习");
  return <div className="workspace-shell">
    {mobile && visible && <button type="button" className="sidebar-backdrop" aria-label="关闭会话导航遮罩" onClick={closeSidebar} />}
    <aside id="session-sidebar" className="workspace-sidebar" aria-label="会话导航" hidden={!visible} data-mode={mobile ? "mobile" : "desktop"}>
      <SessionSidebar state={state} username={username} userId={userId} mobile={mobile} newButtonRef={newButton} onNew={() => setNewOpen(true)} onSelectSession={id => navigate(`/chat/${encodeURIComponent(id)}`)} onCollapse={closeSidebar} onPin={workspaceStore.toggleSidebarPin} onToggleGroup={workspaceStore.toggleGroup} onLoadMoreGroups={() => void loadGroups(state.nextGroupCursor)} onRetryGroups={() => void loadGroups(state.groupsLoad.requestedCursor)} onLoadMoreSessions={key => void loadGroup(key)} onLogout={() => void requestLogout()} />
    </aside>
    <main className="workspace-main"><header className="workspace-topbar">
      {(mobile || state.sidebar.collapsed) && <button type="button" className="sidebar-open" ref={openButton} aria-controls="session-sidebar" aria-expanded={visible} aria-label={mobile ? "打开会话导航" : "展开会话导航"} onClick={() => mobile ? workspaceStore.setMobileOpen(true) : workspaceStore.expandSidebar()}>☰<span>会话</span></button>}
      <div className="workspace-breadcrumb">我的书房 <span aria-hidden="true">/</span> <b>{breadcrumb}</b></div>
      <nav className="workspace-actions" aria-label="工作区导航"><NavLink to="/knowledge">知识库</NavLink><NavLink to={profileTarget}>学习画像</NavLink></nav>
    </header>{state.workspace.recoveryError && <p role="alert">{state.workspace.recoveryError}</p>}
    {state.workspace.error && !state.workspace.conflict && <section role="alert"><p>{state.workspace.errorSource === "load" ? "最近会话加载失败" : "最近会话未保存"}：{state.workspace.error}</p><button type="button" onClick={() => void retryWorkspace()}>{state.workspace.errorSource === "load" ? "重试加载最近会话" : "重试保存最近会话"}</button></section>}
    {state.workspace.conflict && <section role="alert"><p>服务器最近会话：{state.workspace.lastSessionId ?? "无"}；本机最近会话：{state.workspace.desiredSessionId ?? "无"}</p><button type="button" onClick={workspaceController.useServerWorkspace}>使用服务器最近会话</button><button type="button" onClick={workspaceController.saveLocalWorkspace}>保存本机最近会话</button></section>}
    {state.workspace.candidates.map(candidate => (typeof candidate.lastSessionId === "string" || candidate.lastSessionId === null) ? <section key={candidate.writeId}><p>服务器最近会话：{state.workspace.lastSessionId ?? "无"}；本机会话：{candidate.lastSessionId ?? "无"}</p><button type="button" onClick={() => { const key = location.key; void workspaceController.validateWorkspaceCandidate(candidate).then(result => { if (result && currentLocation.current === key) navigate(result.id === null ? "/chat" : `/chat/${encodeURIComponent(result.id)}`, { state: { localOnly: true } }); }); }}>仅打开本机会话 {candidate.lastSessionId ?? "无"}</button><button type="button" onClick={() => { const key = location.key; void workspaceController.validateWorkspaceCandidate(candidate).then(result => { if (result && currentLocation.current === key) { workspaceController.selectSession(result.id); navigate(result.id === null ? "/chat" : `/chat/${encodeURIComponent(result.id)}`, { state: result.id === null ? { localOnly: true } : undefined }); } }); }}>设为最近会话 {candidate.lastSessionId ?? "无"}</button></section> : null)}
    <div className="workspace-content">{children}</div></main>
    <NewSessionDialog open={newOpen} onClose={() => setNewOpen(false)} onCreated={session => navigate(`/chat/${encodeURIComponent(session.session_id)}`)} returnFocus={newButton} />
    {exitError && <div role="dialog" aria-label="退出登录"><p>部分内容未保存到服务器</p>{failedItems.map((item, index) => <p key={index}>{item.kind === "workspace" ? "最近会话未保存" : `会话 ${item.sessionId} 的${item.kind === "draft" ? "草稿" : item.kind === "prepared" ? "待发送内容" : "请求"}未保存`}{item.itemId ? ` / ${item.itemId}` : ""}</p>)}{backupError && <p role="alert">本机备份失败，请重试或留在页面</p>}<button type="button" onClick={() => void requestLogout()}>重试保存</button><button type="button" onClick={logoutWithBackup}>退出并保留本机草稿</button><button type="button" onClick={() => { setExitError(false); workspaceStore.setExitPending(false); }}>留在页面</button></div>}
  </div>;
}

