import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { listProfiles, getProfile, getProfileSummary } from "../api/profiles";
import { loadSnapshot } from "../api/sessions";
import { getWorkspaceState } from "../api/workspace";
import { workspaceStore } from "../store/workspace";
import { ProfileDetail as ProfileDetailDTO, ProfileItem, ProfileSummary, WorkspaceSession } from "../types";
import ProfileDetail from "../components/profile/ProfileDetail";
import ProfileNodeControls from "../components/profile/ProfileNodeControls";
import ProfileSummaryCard from "../components/profile/ProfileSummaryCard";

type Pair = { profile: ProfileItem; summary: ProfileSummary; activeNodeId: string | null; sessionId: string | null; generation: number; detail: ProfileDetailDTO; session: WorkspaceSession | null; seq: number; query: string };

export default function Profile() {
  const [params, setParams] = useSearchParams();
  const account = useSyncExternalStore(workspaceStore.subscribe, workspaceStore.getSnapshot, workspaceStore.getServerSnapshot).account;
  const [options, setOptions] = useState<ProfileItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [pair, setPair] = useState<Pair | null>(null);
  const [target, setTarget] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [listLoading, setListLoading] = useState(false);
  const [retry, setRetry] = useState(0);
  const operation = useRef(0);
  const listOperation = useRef(0);
  const query = params.toString();

  useEffect(() => {
    setPair(null); setTarget(null); setError(null); setOptions([]); setCursor(null); setListError(null);
    return () => { operation.current++; listOperation.current++; };
  }, [account.generation]);

  useEffect(() => {
    const ticket = workspaceStore.captureTicket();
    const seq = ++operation.current;
    listOperation.current++;
    let mounted = true;
    const valid = () => mounted && operation.current === seq && workspaceStore.isCurrent(ticket);
    if (ticket.userId === null) return () => { mounted = false; };
    const run = async () => {
      setLoading(true); setListLoading(false); setError(null);
      let requested = params.get("profile_id");
      let sessionId = params.get("session_id");
      let activeNodeId: string | null = null;
      let verifiedSession: WorkspaceSession | null = null;
      try {
        const page = await listProfiles({ limit: 50 });
        if (!valid()) return;
        setOptions(page.items); setCursor(page.next_cursor); setListError(null);
        if (!requested && !sessionId) {
          const workspace = await getWorkspaceState();
          if (!valid()) return;
          sessionId = workspace.last_session_id;
        }
        if (sessionId) {
          const snapshot = await loadSnapshot(sessionId);
          if (!valid()) return;
          if (snapshot.session.session_id !== sessionId || snapshot.session.user_id !== ticket.userId || snapshot.profile?.user_id !== ticket.userId || snapshot.session.profile_id !== snapshot.profile?.id || (requested && snapshot.session.profile_id !== requested)) throw new Error("会话与画像链接不一致或不可访问");
          requested = snapshot.session.profile_id;
          activeNodeId = snapshot.session.active_node_id;
          verifiedSession = snapshot.session;
        }
        requested = requested || page.items[0]?.id || null;
        setTarget(requested);
        if (!requested) { setPair(null); return; }
        for (let attempt = 0; attempt < 2; attempt++) {
          const [detail, summary]: [ProfileDetailDTO, ProfileSummary] = await Promise.all([getProfile(requested), getProfileSummary(requested)]);
          if (!valid()) return;
          if (detail.profile.id !== requested || detail.profile.user_id !== ticket.userId) throw new Error("画像不可访问或身份不匹配");
          if (detail.profile.revision === detail.profile_revision && detail.profile_revision === summary.profile_revision) {
            setPair({ profile: detail.profile, summary, activeNodeId, sessionId, generation: ticket.generation, detail, session: verifiedSession, seq, query }); return;
          }
        }
        throw new Error("画像已更新，请重试");
      } catch (err) {
        if (valid()) { setTarget(requested); setError(err instanceof Error ? err.message : "读取画像失败"); }
      } finally { if (valid()) setLoading(false); }
    };
    void run();
    return () => { mounted = false; };
  }, [account.generation, query, retry]);

  async function more() {
    if (!cursor || listLoading) return;
    const ticket = workspaceStore.captureTicket(); const seq = ++listOperation.current;
    setListLoading(true); setListError(null);
    try {
      const page = await listProfiles({ limit: 50, cursor });
      if (!workspaceStore.isCurrent(ticket) || seq !== listOperation.current) return;
      setOptions(old => [...old, ...page.items.filter(item => !old.some(existing => existing.id === item.id))]);
      setCursor(page.next_cursor);
    } catch (err) { if (workspaceStore.isCurrent(ticket) && seq === listOperation.current) setListError(err instanceof Error ? err.message : "读取主题失败"); }
    finally { if (workspaceStore.isCurrent(ticket) && seq === listOperation.current) setListLoading(false); }
  }
  const shown = pair && pair.generation === account.generation && pair.profile.id === target && pair.query === query ? pair : null;
  return <main className="profile-page">
    <header className="profile-header"><p>STUDY PROFILE</p><h1>学习画像</h1><p>从真实学习记录中，查看主题、知识关系与来源。</p></header>
    <div className="profile-toolbar"><label htmlFor="profile-select">查看主题</label><select id="profile-select" value={target ?? ""} onChange={event => { setTarget(event.target.value); setParams({ profile_id: event.target.value }); }} disabled={!options.length && !shown}><option value="">选择主题</option>{shown && !options.some(item => item.id === shown.profile.id) && <option value={shown.profile.id}>{shown.profile.name}</option>}{options.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select>{cursor && <button type="button" onClick={more} disabled={listLoading}>加载更多主题</button>}</div>
    {listError && <p role="alert">{listError} <button type="button" onClick={more}>重试加载主题</button></p>}
    {loading && <p role="status">正在读取画像…</p>}
    {error && <p role="alert">{error} {shown && "（仍显示上次版本）"} <button type="button" onClick={() => setRetry(value => value + 1)}>重试</button></p>}
    {!loading && !error && !target && <p className="profile-notice">暂无主题，请先<Link to="/chat">新建学习会话</Link>。</p>}
    {shown && <ProfileNodeControls key={`${account.generation}:${query}:${shown.profile.id}`} pair={shown} explicitSessionId={params.get("session_id")} loading={loading} readError={error} refresh={() => { setLoading(true); setRetry(value => value + 1); }} />}
    {shown && <div className="profile-grid"><ProfileDetail profile={shown.profile} summary={shown.summary} activeNodeId={shown.activeNodeId} sourceSessionId={shown.sessionId} /><ProfileSummaryCard profile={shown.profile} summary={shown.summary} activeNodeId={shown.activeNodeId} /></div>}
  </main>;
}

