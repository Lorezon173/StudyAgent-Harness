import { FormEvent, RefObject, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { ApiError } from "../../api/client";
import { createProfile, listProfiles } from "../../api/profiles";
import { createSession } from "../../api/sessions";
import { workspaceStore } from "../../store/workspace";
import { ProfileItem, WorkspaceSession } from "../../types";

interface Props { open: boolean; onClose: () => void; onCreated: (session: WorkspaceSession) => void; returnFocus?: RefObject<HTMLButtonElement> }
interface CreatedProfileBinding { profileId: string; name: string; scopeDescription: string; userId: number | null; accountGeneration: number; profile: ProfileItem }
export default function NewSessionDialog(props: Props) {
  const state = useSyncExternalStore(workspaceStore.subscribe, workspaceStore.getSnapshot, workspaceStore.getServerSnapshot);
  return props.open ? <DialogForm key={state.account.generation} {...props} /> : null;
}
function DialogForm({ onClose, onCreated, returnFocus }: Props) {
  const dialog = useRef<HTMLDialogElement>(null); const epoch = useRef(0); const submitSequence = useRef(0); const profileSequence = useRef(0); const busyRef = useRef(false); const profileBusyRef = useRef(false);
  const [title, setTitle] = useState(""); const [selection, setSelection] = useState(""); const [name, setName] = useState(""); const [scope, setScope] = useState("");
  const [profiles, setProfiles] = useState<ProfileItem[]>([]); const [nextCursor, setNextCursor] = useState<string | null>(null); const [profilesLoading, setProfilesLoading] = useState(false); const [profileError, setProfileError] = useState("");
  const [binding, setBinding] = useState<CreatedProfileBinding | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  async function loadProfiles(cursor: string | null, mount = epoch.current) {
    if (profileBusyRef.current) return;
    profileBusyRef.current = true; const sequence = ++profileSequence.current; const ticket = workspaceStore.captureTicket();
    const current = () => epoch.current === mount && profileSequence.current === sequence && workspaceStore.isCurrent(ticket);
    setProfilesLoading(true); setProfileError("");
    try {
      const page = await listProfiles({ cursor }); if (!current()) return;
      setProfiles(previous => { const items = cursor === null ? [] : previous; const known = new Set(items.map(item => item.id)); return [...items, ...page.items.filter(item => { if (known.has(item.id)) return false; known.add(item.id); return true; })]; });
      setNextCursor(page.next_cursor);
    } catch (failure) { if (current()) setProfileError(failure instanceof ApiError ? failure.message : "加载主题选项失败"); }
    finally { if (current()) { profileBusyRef.current = false; setProfilesLoading(false); } }
  }
  useEffect(() => {
    const mount = ++epoch.current; void loadProfiles(null, mount);
    return () => { epoch.current++; profileSequence.current++; submitSequence.current++; profileBusyRef.current = false; busyRef.current = false; };
  }, []);
  useEffect(() => {
    const element = dialog.current; element?.showModal();
    return () => { if (element?.open) element.close(); returnFocus?.current?.focus(); };
  }, [returnFocus]);
  async function submit(event: FormEvent) {
    event.preventDefault(); if (busyRef.current || profileBusyRef.current) return;
    busyRef.current = true; setBusy(true); setError("");
    const ticket = workspaceStore.captureTicket(); const mount = epoch.current; const sequence = ++submitSequence.current;
    const current = () => epoch.current === mount && submitSequence.current === sequence && workspaceStore.isCurrent(ticket);
    try {
      if (!current()) return;
      let chosen: ProfileItem | undefined;
      if (selection === "__new") {
        if (binding) {
          if (binding.accountGeneration !== ticket.generation || binding.userId !== ticket.userId) return;
          chosen = binding.profile;
        } else {
          if (!name.trim()) throw new ApiError(0, "请填写新主题名称");
          const detail = await createProfile({ name: name.trim(), scope_description: scope });
          // 两次 POST 之间必须重新核身份；不能把旧画像 id 带到新 JWT。
          if (!current()) return;
          chosen = detail.profile;
          setBinding({ profileId: chosen.id, name: chosen.name, scopeDescription: chosen.scope_description, userId: ticket.userId, accountGeneration: ticket.generation, profile: chosen });
          setName(chosen.name); setScope(chosen.scope_description);
          setProfiles(previous => previous.some(item => item.id === chosen!.id) ? previous : [...previous, chosen!]);
        }
      } else {
        chosen = profiles.find(item => item.id === selection);
        if (!chosen) throw new ApiError(0, "请选择本人主题");
      }
      if (!current()) return;
      const created = await createSession({ profile_id: chosen.id, title: title.trim() || "新会话", active_node_id: null });
      if (!current()) return;
      if (!workspaceStore.upsertSession(ticket, created, chosen)) throw new ApiError(200, "会话主题与选择不符", "invalid_session_profile");
      busyRef.current = false; setBusy(false); setError(""); onCreated(created); onClose();
    } catch (failure) { if (current()) setError(failure instanceof ApiError ? failure.message : "创建失败，请重试"); }
    finally { if (current()) { busyRef.current = false; setBusy(false); } }
  }
  return <dialog className="session-dialog" ref={dialog} aria-labelledby="new-session-heading" onCancel={event => { event.preventDefault(); onClose(); }}>
    <button className="dialog-close" type="button" aria-label="关闭" onClick={onClose}>×</button><div className="eyebrow">开启新的探索</div><h2 id="new-session-heading">从一个好问题开始</h2><p className="form-intro">同一主题的会话，共用一份学习画像。</p>
    <form aria-label="新建会话" onSubmit={submit}>
      <label htmlFor="session-title">会话标题</label><input id="session-title" value={title} maxLength={128} placeholder="新会话" disabled={busy} onChange={event => setTitle(event.target.value)} />
      <label htmlFor="session-profile">所属主题画像</label><select id="session-profile" value={selection} disabled={busy || !!binding} onChange={event => { if (!busyRef.current && !binding) { setSelection(event.target.value); setError(""); } }}><option value="">请选择主题</option>{profiles.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}<option value="__new">创建新主题</option></select>
      {profilesLoading && <p className="form-note" role="status">正在加载主题选项…</p>}{profileError && <div><p role="alert" className="form-error">{profileError}</p><button type="button" disabled={profilesLoading} onClick={() => void loadProfiles(nextCursor)}>重试加载主题选项</button></div>}
      {nextCursor !== null && <button type="button" className="load-more" disabled={profilesLoading || busy} onClick={() => void loadProfiles(nextCursor)}>加载更多主题选项</button>}
      {selection === "__new" && <div className="new-profile-fields"><label htmlFor="new-profile-name">新主题名称</label><input id="new-profile-name" value={name} maxLength={128} disabled={busy || !!binding} onChange={event => { if (!busyRef.current && !binding) setName(event.target.value); }} /><label htmlFor="new-profile-scope">学习范围</label><textarea id="new-profile-scope" rows={3} value={scope} disabled={busy || !!binding} onChange={event => { if (!busyRef.current && !binding) setScope(event.target.value); }} /></div>}
      {binding && <div className="profile-binding"><p className="form-note">主题已创建，可重试创建会话。</p><button type="button" disabled={busy} onClick={() => { if (!busyRef.current) { setBinding(null); setError(""); } }}>重新选择主题</button></div>}
      {error && <p role="alert" className="form-error">{error}</p>}
      <div className="dialog-actions"><button type="button" onClick={onClose}>暂时取消</button><button className="primary-button" type="submit" disabled={busy || profilesLoading}>{busy ? "创建中…" : "进入书房 →"}</button></div>
    </form>
  </dialog>;
}
