import { ReactNode, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { NavLink, useLocation, useMatch, useNavigate } from "react-router-dom";
import { ApiError } from "../../api/client";
import { listGroupedSessions, listGroupSessions } from "../../api/sessions";
import { useAuth } from "../../store/auth";
import { workspaceStore } from "../../store/workspace";
import SessionSidebar from "./SessionSidebar";
import NewSessionDialog from "./NewSessionDialog";

export default function WorkspaceLayout({ children }: { children: ReactNode }) {
  const state = useSyncExternalStore(workspaceStore.subscribe, workspaceStore.getSnapshot, workspaceStore.getServerSnapshot);
  const { username, userId, logout } = useAuth(); const navigate = useNavigate(); const location = useLocation(); const selected = useMatch("/chat/:sessionId");
  const [mobile, setMobile] = useState(() => window.matchMedia("(max-width:480px)").matches);
  const [newOpen, setNewOpen] = useState(false); const newButton = useRef<HTMLButtonElement>(null); const openButton = useRef<HTMLButtonElement>(null);
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
  useEffect(() => {
    if (location.pathname === "/chat" || location.pathname === "/chat/") workspaceStore.syncRouteSelection(null);
    else if (selected?.params.sessionId) workspaceStore.syncRouteSelection(selected.params.sessionId);
  }, [location.pathname, selected?.params.sessionId]);
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
  const group = state.groups.find(item => item.sessions.some(session => session.session_id === state.activeSessionId));
  const breadcrumb = location.pathname === "/knowledge" ? "知识库" : location.pathname === "/profile" ? "学习画像" : group?.profile?.name || (state.activeSessionId ? "学习会话" : "开始学习");
  return <div className="workspace-shell">
    {mobile && visible && <button type="button" className="sidebar-backdrop" aria-label="关闭会话导航遮罩" onClick={closeSidebar} />}
    <aside id="session-sidebar" className="workspace-sidebar" aria-label="会话导航" hidden={!visible} data-mode={mobile ? "mobile" : "desktop"}>
      <SessionSidebar state={state} username={username} userId={userId} mobile={mobile} newButtonRef={newButton} onNew={() => setNewOpen(true)} onSelectSession={id => navigate(`/chat/${encodeURIComponent(id)}`)} onCollapse={closeSidebar} onPin={workspaceStore.toggleSidebarPin} onToggleGroup={workspaceStore.toggleGroup} onLoadMoreGroups={() => void loadGroups(state.nextGroupCursor)} onRetryGroups={() => void loadGroups(state.groupsLoad.requestedCursor)} onLoadMoreSessions={key => void loadGroup(key)} onLogout={logout} />
    </aside>
    <main className="workspace-main"><header className="workspace-topbar">
      {(mobile || state.sidebar.collapsed) && <button type="button" className="sidebar-open" ref={openButton} aria-controls="session-sidebar" aria-expanded={visible} aria-label={mobile ? "打开会话导航" : "展开会话导航"} onClick={() => mobile ? workspaceStore.setMobileOpen(true) : workspaceStore.expandSidebar()}>☰<span>会话</span></button>}
      <div className="workspace-breadcrumb">我的书房 <span aria-hidden="true">/</span> <b>{breadcrumb}</b></div>
      <nav className="workspace-actions" aria-label="工作区导航"><NavLink to="/knowledge">知识库</NavLink><NavLink to="/profile">学习画像</NavLink></nav>
    </header><div className="workspace-content">{children}</div></main>
    <NewSessionDialog open={newOpen} onClose={() => setNewOpen(false)} onCreated={session => navigate(`/chat/${encodeURIComponent(session.session_id)}`)} returnFocus={newButton} />
  </div>;
}
