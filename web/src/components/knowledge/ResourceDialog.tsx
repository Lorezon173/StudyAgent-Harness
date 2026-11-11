import { FormEvent, useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import { createKnowledge, deleteKnowledge, getKnowledge, patchKnowledge } from "../../api/knowledge";
import { listProfiles } from "../../api/profiles";
import { workspaceStore } from "../../store/workspace";
import { KnowledgeResponse, ProfileItem } from "../../types";
interface Props {
    target: number | null;
    returnFocus: HTMLButtonElement | null;
    onClose: () => void;
    onChanged: (deletedId?: number) => void;
}
export default function ResourceDialog({ target, returnFocus, onClose, onChanged }: Props) {
    const dialog = useRef<HTMLDialogElement>(null);
    const live = useRef(true);
    const sequence = useRef(0);
    const busyRef = useRef(false);
    const profileSequence = useRef(0);
    const [item, setItem] = useState<KnowledgeResponse | null>(null);
    const [mode, setMode] = useState<"read" | "edit" | "create">(target === null ? "create" : "read");
    const [name, setName] = useState("");
    const [description, setDescription] = useState("");
    const [content, setContent] = useState("");
    const [profileId, setProfileId] = useState("");
    const [profiles, setProfiles] = useState<ProfileItem[]>([]);
    const [cursor, setCursor] = useState<string | null>(null);
    const [profileError, setProfileError] = useState("");
    const [profileLoading, setProfileLoading] = useState(false);
    const [loading, setLoading] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [notice, setNotice] = useState("");
    const [confirm, setConfirm] = useState(false);
    const current = (ticket: ReturnType<typeof workspaceStore.captureTicket>, n: number) => live.current && sequence.current === n && workspaceStore.isCurrent(ticket);
    async function load(id: number, saved = false) {
        const ticket = workspaceStore.captureTicket();
        const n = ++sequence.current;
        setLoading(true);
        setError("");
        try {
            const value = await getKnowledge(id);
            if (current(ticket, n)) {
                setItem(value);
                setNotice(saved ? "已保存" : "");
            }
        }
        catch (e) {
            if (current(ticket, n))
                setError(`${saved ? "已保存，刷新失败：" : "加载详情失败："}${e instanceof Error ? e.message : "请重试"}`);
        }
        finally {
            if (current(ticket, n))
                setLoading(false);
        }
    }
    async function loadOptions(next: string | null) {
        const ticket = workspaceStore.captureTicket();
        const n = ++profileSequence.current;
        setProfileLoading(true);
        setProfileError("");
        try {
            const page = await listProfiles({ limit: 50, cursor: next });
            if (!live.current || n !== profileSequence.current || !workspaceStore.isCurrent(ticket))
                return;
            setProfiles(old => {
                const all = next ? [...old] : [];
                for (const p of page.items) {
                    if (!all.some(x => x.id === p.id)) all.push(p);
                }
                return all;
            });
            setCursor(page.next_cursor);
        }
        catch (e) {
            if (live.current && n === profileSequence.current && workspaceStore.isCurrent(ticket))
                setProfileError(e instanceof Error ? e.message : "加载主题失败");
        }
        finally {
            if (live.current && n === profileSequence.current && workspaceStore.isCurrent(ticket))
                setProfileLoading(false);
        }
    }
    useEffect(() => {
        live.current = true;
        dialog.current?.showModal();
        if (target !== null) void load(target);
        void loadOptions(null);
        return () => {
            live.current = false;
            sequence.current++;
            profileSequence.current++;
            if (dialog.current?.open) dialog.current.close();
            returnFocus?.focus();
        };
    }, []);
    function edit() {
        if (!item) return;
        setName(item.name);
        setDescription(item.description);
        setContent(item.content_text);
        setProfileId(item.profile_id ?? "");
        setError("");
        setMode("edit");
    }
    async function save(e: FormEvent) {
        e.preventDefault();
        if (busyRef.current)
            return;
        if (!name.trim() || name.trim().length > 128 || description.length > 2000 || content.length > 100000) {
            setError("请填写名称（最多128字），说明最多2000字，正文最多100000字");
            return;
        }
        if (profileId && !profiles.some(p => p.id === profileId) && profileId !== item?.profile_id) {
            setError("请选择本人主题");
            return;
        }
        const ticket = workspaceStore.captureTicket();
        const n = ++sequence.current;
        busyRef.current = true;
        setBusy(true);
        setError("");
        try {
            const input = { name: name.trim(), description, content_text: content, profile_id: profileId || null };
            const value = mode === "create" ? await createKnowledge(input) : await patchKnowledge(item!.id, input);
            if (!current(ticket, n))
                return;
            setItem(value);
            setMode("read");
            setNotice("已保存，正在刷新");
            onChanged();
            void load(value.id, true);
        }
        catch (e) {
            if (current(ticket, n))
                setError(e instanceof ApiError && e.code === "account_changed" ? e.message : mode === "create" && e instanceof ApiError && e.status === 0 ? "创建结果不确定，请先刷新核对；再次提交可能重复创建。" : `保存未确认：${e instanceof Error ? e.message : "请重试"}`);
        }
        finally {
            if (current(ticket, n)) {
                busyRef.current = false;
                setBusy(false);
            }
            else if (live.current && workspaceStore.isCurrent(ticket)) {
                busyRef.current = false;
                setBusy(false);
            }
        }
    }
    async function remove() {
        if (!item || busyRef.current) return;
        const ticket = workspaceStore.captureTicket();
        const n = ++sequence.current;
        busyRef.current = true;
        setBusy(true);
        setError("");
        try {
            await deleteKnowledge(item.id);
            if (!current(ticket, n)) return;
            onChanged(item.id);
            onClose();
        } catch (e) {
            if (current(ticket, n)) setError(`删除失败：${e instanceof Error ? e.message : "请重试"}`);
        } finally {
            if (current(ticket, n)) {
                busyRef.current = false;
                setBusy(false);
            }
        }
    }
    return <dialog ref={dialog} className="resource-dialog" aria-labelledby="resource-heading" onCancel={e => { e.preventDefault(); onClose(); }}>
        <button type="button" className="dialog-close" aria-label="关闭" onClick={onClose}>×</button>
        <div className="eyebrow">ON YOUR SHELF</div>
        <h2 id="resource-heading">{mode === "create" ? "新建文本资料" : mode === "edit" ? "编辑文本资料" : item?.name || "资料详情"}</h2>
        {loading && <p role="status">正在读取…</p>}
        {notice && <p role="status">{notice}</p>}
        {error && <p role="alert">{error}</p>}
        {mode === "read" && <>
            {error && <button onClick={() => void load(item?.id ?? target!, Boolean(item))}>重试读取</button>}
            {item && <>
                <p>{item.source_type} · {item.description || "暂无说明"}</p>
                <div className="resource-text">{item.content_text}</div>
                <div className="dialog-actions">
                    <button onClick={edit}>编辑</button>
                    <button onClick={() => setConfirm(true)}>删除</button>
                </div>
                {confirm && <section>
                    <p>确定删除“{item.name}”吗？</p>
                    <button disabled={busy} onClick={() => void remove()}>确认删除</button>
                    <button onClick={() => setConfirm(false)}>取消</button>
                </section>}
            </>}
        </>}
        {mode !== "read" && <form onSubmit={save} className="resource-form">
            <label>名称<input autoFocus value={name} onChange={e => setName(e.target.value)} /></label>
            <label>说明<textarea value={description} onChange={e => setDescription(e.target.value)} /></label>
            <label>正文<textarea rows={10} value={content} onChange={e => setContent(e.target.value)} /></label>
            <label>关联主题<select value={profileId} onChange={e => setProfileId(e.target.value)}>
                <option value="">未关联主题</option>
                {profileId && !profiles.some(p => p.id === profileId) && <option value={profileId}>当前关联主题</option>}
                {profiles.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select></label>
            {profileLoading && <p role="status">正在加载主题…</p>}
            {profileError && <p role="alert">{profileError} <button type="button" onClick={() => void loadOptions(cursor)}>重试主题</button></p>}
            {cursor && <button type="button" onClick={() => void loadOptions(cursor)}>加载更多主题</button>}
            <button className="paper-primary" disabled={busy} type="submit">保存</button>
            {mode === "edit" && <button type="button" onClick={() => { setMode("read"); setError(""); }}>取消编辑</button>}
        </form>}
    </dialog>;
}
