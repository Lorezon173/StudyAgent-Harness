import { RefObject, useState } from "react";
import { WorkspaceClientState } from "../../store/workspace";

interface Props {
  state: WorkspaceClientState;
  username: string | null;
  userId: number | null;
  mobile: boolean;
  newButtonRef: RefObject<HTMLButtonElement>;
  onNew: () => void;
  onSelectSession: (id: string) => void;
  onCollapse: () => void;
  onPin: () => void;
  onToggleGroup: (key: string) => void;
  onLoadMoreGroups: () => void;
  onRetryGroups: () => void;
  onLoadMoreSessions: (key: string) => void;
  onLogout: () => void;
}
function dateLabel(value: string | null) {
  if (value === null) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric" }).format(date);
}
export default function SessionSidebar(props: Props) {
  const { state } = props; const [accountOpen, setAccountOpen] = useState(false);
  const name = props.username || (props.userId === null ? "未登录" : `账号 ${props.userId}`);
  return <>
    <div className="sidebar-top-controls" tabIndex={0} role="region" aria-label="会话导航操作">
    <div className="study-brand"><span className="brand-mark" aria-hidden="true">学</span><div><span className="brand-name">StudyAgent</span><small>慢慢理解，自有回响</small></div></div>
    <div className="sidebar-controls"><button type="button" onClick={props.onPin} aria-controls="session-sidebar" aria-pressed={state.sidebar.pinned} aria-label={state.sidebar.pinned ? "取消固定侧栏，保持当前展示" : "固定侧栏，保持展开"}>{state.sidebar.pinned ? "已固定" : "固定侧栏"}</button><button type="button" onClick={props.onCollapse} aria-controls="session-sidebar" aria-expanded="true" aria-label={props.mobile ? "关闭会话导航" : "收起会话导航"}>收起 ‹</button></div>
    <button type="button" className="new-session" ref={props.newButtonRef} onClick={props.onNew} aria-label="开启一段新的探索">开启一段新的探索 <span aria-hidden="true">＋</span></button>
    <div className="sidebar-label">我的学习主题 / TOPICS</div>
    </div>
    <div className="sidebar-groups">
      {(state.groupsLoad.status === "idle" || state.groupsLoad.status === "loading") && <p className="sidebar-note" role="status">正在加载学习主题…</p>}
      {state.groupsLoad.status === "error" && <div className="sidebar-error"><p role="alert">{state.groupsLoad.error}</p><button type="button" onClick={props.onRetryGroups}>重试加载主题</button></div>}
      {state.groupsLoad.status === "ready" && state.groups.length === 0 && <p className="sidebar-note">还没有学习主题</p>}
      {state.groups.map(group => {
        const groupName = group.profile?.name || "历史待整理";
        const expanded = state.sidebar.expandedGroups.has(group.group_key);
        const page = state.groupPages[group.group_key];
        const cursor = page ? page.nextSessionCursor : group.next_session_cursor;
        const id = `session-group-${encodeURIComponent(group.group_key)}`;
        return <section className="session-group" key={group.group_key} data-group-key={group.group_key} aria-label={`主题：${groupName}`}>
          <button type="button" className="group-toggle" onClick={() => props.onToggleGroup(group.group_key)} aria-label={`切换主题：${groupName}`} aria-expanded={expanded} aria-controls={id}><span aria-hidden="true">{expanded ? "⌄" : "›"}</span><span>{groupName}</span><small>已加载 {group.sessions.length}</small></button>
          {expanded && <div id={id}>
            {group.sessions.map(session => <button type="button" key={session.session_id} className={`session-button${state.activeSessionId === session.session_id ? " active" : ""}`} onClick={() => props.onSelectSession(session.session_id)} aria-current={state.activeSessionId === session.session_id ? "true" : undefined} aria-label={session.title || "未命名会话"}><span>{session.title || "未命名会话"}</span>{session.updated_at !== null && <small>{dateLabel(session.updated_at)}</small>}</button>)}
            {group.sessions.length === 0 && page?.status === "ready" && cursor === null && <p className="sidebar-note">这个主题还没有会话</p>}
            {page?.status === "loading" && <p className="sidebar-note" role="status">正在加载会话…</p>}
            {page?.status === "error" && <div className="sidebar-error"><p role="alert">{page.error}</p><button type="button" onClick={() => props.onLoadMoreSessions(group.group_key)}>重试加载会话</button></div>}
            {cursor !== null && page?.status !== "error" && <button type="button" className="load-more" disabled={page?.status === "loading"} onClick={() => props.onLoadMoreSessions(group.group_key)}>加载更多会话</button>}
          </div>}
        </section>;
      })}
      {state.nextGroupCursor !== null && state.groupsLoad.status !== "error" && <button type="button" className="load-more" disabled={state.groupsLoad.status === "loading"} onClick={props.onLoadMoreGroups}>加载更多主题</button>}
    </div>
    <footer className="sidebar-account"><button type="button" className="account-button" aria-label={`账号：${name}`} aria-expanded={accountOpen} aria-controls="account-actions" onClick={() => setAccountOpen(open => !open)}><span className="account-avatar" aria-hidden="true">{name.slice(0, 1)}</span><span>{name}<small>我的学习书房</small></span><span className="account-dots" aria-hidden="true">···</span></button>{accountOpen && <div id="account-actions" className="account-actions" role="group" aria-label="账号操作"><p>{name}</p><button type="button" onClick={props.onLogout}>退出登录</button></div>}</footer>
  </>;
}
