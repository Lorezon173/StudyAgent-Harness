import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { listKnowledge } from "../api/knowledge";
import KnowledgeLibrary from "../components/knowledge/KnowledgeLibrary";
import ResourceDialog from "../components/knowledge/ResourceDialog";
import { workspaceStore } from "../store/workspace";
import { KnowledgeResponse } from "../types";

export default function Knowledge() {
  const state = useSyncExternalStore(workspaceStore.subscribe, workspaceStore.getSnapshot, workspaceStore.getServerSnapshot);
  return <KnowledgePage key={state.account.generation} />;
}

function KnowledgePage() {
  const [items, setItems] = useState<KnowledgeResponse[]>([]);
  const [query, setQuery] = useState("");
  const [applied, setApplied] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [stale, setStale] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [dialog, setDialog] = useState<{ target: number | null; focus: HTMLButtonElement; epoch: number } | null>(null);
  const sequence = useRef(0);
  const epoch = useRef(0);
  const mounted = useRef(false);
  const requested = useRef("");

  async function load(q: string, before?: number, confirmed?: "已保存" | "已删除") {
    const ticket = workspaceStore.captureTicket();
    const n = ++sequence.current;
    requested.current = q;
    setLoading(true);
    setError("");
    if (before === undefined && q !== applied) setStale(true);
    const current = () => mounted.current && workspaceStore.isCurrent(ticket) && sequence.current === n;
    try {
      const page = await listKnowledge({ q: q || undefined, limit: 50, before_id: before });
      if (!current()) return;
      setItems(old => {
        const result = before === undefined ? [] : [...old];
        const seen = new Set(result.map(x => x.id));
        for (const item of page) {
          if (!seen.has(item.id)) {
            seen.add(item.id);
            result.push(item);
          }
        }
        return result;
      });
      setApplied(q);
      setStale(false);
      setHasMore(page.length === 50);
    } catch (e) {
      if (current()) setError(`${confirmed ? `${confirmed}，列表刷新失败：` : ""}${e instanceof Error ? e.message : "加载失败"}`);
    } finally {
      if (current()) setLoading(false);
    }
  }

  useEffect(() => {
    mounted.current = true;
    void load("");
    return () => { mounted.current = false; sequence.current++; };
  }, []);

  function search() {
    const q = query.trim();
    if (q.length > 256) { setError("搜索词最多256字"); return; }
    void load(q);
  }
  function changed(deletedId?: number) {
    if (deletedId !== undefined) setItems(old => old.filter(x => x.id !== deletedId));
    void load(requested.current, undefined, deletedId === undefined ? "已保存" : "已删除");
  }

  return <>
    <KnowledgeLibrary
      items={items} query={query} onQuery={setQuery} onSearch={search}
      onOpen={(target, focus) => setDialog({ target, focus, epoch: ++epoch.current })}
      onCreate={focus => setDialog({ target: null, focus, epoch: ++epoch.current })}
      onMore={() => {
        if (!stale && requested.current === applied && items.length) {
          void load(applied, Math.min(...items.map(x => x.id)));
        }
      }}
      onRetry={() => void load(requested.current)}
      loading={loading} error={error} hasMore={hasMore} stale={stale}
    />
    {dialog && <ResourceDialog key={dialog.epoch} target={dialog.target} returnFocus={dialog.focus} onClose={() => setDialog(null)} onChanged={changed} />}
  </>;
}
