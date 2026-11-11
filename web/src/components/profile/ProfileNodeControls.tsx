import { FormEvent, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../../api/client";
import { createProfileNode } from "../../api/profiles";
import { patchActiveNode } from "../../api/sessions";
import { workspaceStore } from "../../store/workspace";
import { ProfileDetail, WorkspaceSession } from "../../types";

type Pair = { detail: ProfileDetail; session: WorkspaceSession | null; seq: number };
type Pending = { kind: "create"; id: string; revision: number; seq: number } | { kind: "select"; id: string; version: number; seq: number } | { kind: "unknown"; seq: number };

export default function ProfileNodeControls({ pair, explicitSessionId, loading, readError, refresh }: { pair: Pair; explicitSessionId: string | null; loading: boolean; readError: string | null; refresh: () => void }) {
  const [title, setTitle] = useState(""); const [description, setDescription] = useState("");
  const [selected, setSelected] = useState(""); const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null); const [pending, setPending] = useState<Pending | null>(null);
  const mounted = useRef(true); const write = useRef(0); const lock = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; write.current++; }; }, []);
  const session = explicitSessionId && pair.session?.session_id === explicitSessionId ? pair.session : null;
  const nodes = pair.detail.nodes.filter(node => !node.archived && node.profile_id === pair.detail.profile.id);
  useEffect(() => { setSelected(session?.active_node_id ?? ""); }, [session?.session_id, session?.active_node_id, pair.seq]);
  useEffect(() => {
    if (!pending || loading || readError || pair.seq <= pending.seq) return;
    if (pending.kind === "create") {
      if (pair.detail.profile_revision >= pending.revision && pair.detail.nodes.some(node => node.id === pending.id && node.profile_id === pair.detail.profile.id && !node.archived)) { setMessage("知识点已创建"); setTitle(""); setDescription(""); }
      else setMessage("读取结果未确认知识点，请核对后重试");
    } else if (pending.kind === "select") {
      setMessage(session?.active_node_id === pending.id && session.state_version >= pending.version ? "当前知识点已保存" : "会话状态已变化，请核对当前知识点");
    } else setMessage(previous => `${previous ?? "提交结果未知"}；已重新读取，请核对服务器记录后决定是否重试`);
    setPending(null);
  }, [pair, pending, loading, readError, session]);
  const disabled = loading || !!readError || busy || !!pending;
  const begin = () => { if (lock.current || disabled) return null; lock.current = true; setBusy(true); setMessage(null); const seq = ++write.current; const ticket = workspaceStore.captureTicket(); return () => mounted.current && write.current === seq && workspaceStore.isCurrent(ticket); };
  const finish = (valid: () => boolean) => { if (valid()) { lock.current = false; setBusy(false); } };
  const reload = (result: Pending, text?: string) => { setPending(result); if (text) setMessage(text); refresh(); };
  async function create(event: FormEvent) {
    event.preventDefault(); const name = title.trim(); if (!name || name.length > 512) return;
    const valid = begin(); if (!valid) return; const revision = pair.detail.profile_revision;
    try {
      const result = await createProfileNode(pair.detail.profile.id, { expected_revision: revision, title: name, description });
      if (!valid()) return;
      if (!result.node?.id || result.node.profile_id !== pair.detail.profile.id || result.node.archived || result.profile_revision !== revision + 1) { reload({ kind: "unknown", seq: pair.seq }, "提交结果无法确认，可能已保存，请重新读取"); return; }
      reload({ kind: "create", id: result.node.id, revision: result.profile_revision, seq: pair.seq });
    } catch (err) {
      if (!valid()) return;
      if (err instanceof ApiError && err.status === 409) reload({ kind: "unknown", seq: pair.seq }, "画像已更新，请核对后重试");
      else if (err instanceof ApiError && err.status >= 400 && err.status < 500 && err.status !== 408) reload({ kind: "unknown", seq: pair.seq }, `创建请求已被拒绝（${err.status}），请核对后重试`);
      else reload({ kind: "unknown", seq: pair.seq }, "提交结果可能已保存，请重新读取后核对");
    } finally { finish(valid); }
  }
  async function select() {
    if (!session || session.active_request_id || !nodes.some(node => node.id === selected) || selected === session.active_node_id) return;
    const valid = begin(); if (!valid) return; const id = selected;
    try {
      const result = await patchActiveNode(session.session_id, { expected_state_version: session.state_version, node_id: id });
      if (!valid()) return;
      if (result.session_id !== session.session_id || result.user_id !== session.user_id || result.profile_id !== session.profile_id || result.active_node_id !== id || result.state_version !== session.state_version + 1) { reload({ kind: "unknown", seq: pair.seq }, "保存结果无法确认，请重新读取"); return; }
      reload({ kind: "select", id, version: result.state_version, seq: pair.seq });
    } catch (err) {
      if (!valid()) return;
      let text = "保存结果无法确认，请重新读取并核对";
      if (err instanceof ApiError && err.status === 409 && err.code === "session_busy") text = "保存请求已被拒绝：会话正在生成，完成后可更换知识点";
      else if (err instanceof ApiError && err.status === 409 && err.code === "state_version_conflict") text = "保存请求已被拒绝：会话状态已更新，请核对后重试";
      else if (err instanceof ApiError && err.status === 404) text = "知识点不存在或已归档，保存请求已被拒绝";
      else if (err instanceof ApiError && err.status >= 400 && err.status < 500 && err.status !== 408) text = `保存请求已被拒绝（${err.status}），请核对后重试`;
      reload({ kind: "unknown", seq: pair.seq }, text);
    } finally { finish(valid); }
  }
  return <section aria-label="知识点管理">
    <form aria-label="新建知识点" onSubmit={create}>
      <label>知识点名称<input value={title} disabled={busy || !!pending} maxLength={512} onChange={event => setTitle(event.target.value)} /></label>
      <label>知识点说明<textarea value={description} disabled={busy || !!pending} onChange={event => setDescription(event.target.value)} /></label>
      <button type="submit" disabled={disabled || !title.trim()}>新建知识点</button>
    </form>
    {session && <div><p>当前会话：{session.title}</p><p>已保存知识点：{nodes.find(node => node.id === session.active_node_id)?.title ?? "未选择"}</p>
      <label>当前知识点<select value={selected} onChange={event => setSelected(event.target.value)} disabled={disabled || !!session.active_request_id}><option value="">选择知识点</option>{nodes.map(node => <option value={node.id} key={node.id}>{node.title}{nodes.filter(other => other.title === node.title).length > 1 ? `（${node.id}）` : ""}</option>)}</select></label>
      <button type="button" onClick={select} disabled={disabled || !!session.active_request_id || !nodes.some(node => node.id === selected) || selected === session.active_node_id}>保存当前知识点</button>
      {session.active_request_id && <p>会话正在生成，完成后可更换知识点</p>}
      <Link to={`/chat/${encodeURIComponent(session.session_id)}`}>返回当前会话</Link>
    </div>}
    {message && <p role="status">{message}</p>}
    {(readError || session?.active_request_id) && <button type="button" onClick={refresh} disabled={loading || busy}>重新读取</button>}
  </section>;
}
