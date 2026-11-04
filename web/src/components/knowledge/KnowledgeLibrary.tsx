import { FormEvent } from "react";
import { KnowledgeResponse } from "../../types";

interface Props {
  items: KnowledgeResponse[];
  query: string;
  onQuery: (value: string) => void;
  onSearch: () => void;
  onOpen: (id: number, button: HTMLButtonElement) => void;
  onCreate: (button: HTMLButtonElement) => void;
  onMore: () => void;
  onRetry: () => void;
  loading: boolean;
  error: string;
  hasMore: boolean;
  stale: boolean;
}

export default function KnowledgeLibrary(p: Props) {
  function search(e: FormEvent) {
    e.preventDefault();
    p.onSearch();
  }
  return <div className="paper-page">
    <header className="paper-heading">
      <div>
        <div className="eyebrow">YOUR PERSONAL LIBRARY</div>
        <h1>把知识，留在手边。</h1>
        <p>收藏自己的文本资料，为下一次探索留下一点线索。</p>
      </div>
      <button className="paper-primary" onClick={e => p.onCreate(e.currentTarget)}>＋ 新建文本资料</button>
    </header>
    <form className="paper-search" onSubmit={search}>
      <label htmlFor="library-search">搜索资料</label>
      <input id="library-search" type="search" value={p.query} onChange={e => p.onQuery(e.target.value)} />
      <button type="submit">搜索</button>
    </form>
    {p.stale && <p>仍显示上次结果</p>}
    {p.error && <div role="alert">{p.error} <button onClick={p.onRetry}>重试加载</button></div>}
    {p.loading && <p role="status">正在加载资料…</p>}
    {!p.loading && !p.error && p.items.length === 0 && <p>暂无文本资料</p>}
    <div className="paper-cards">
      {p.items.map(item => <article className="paper-resource" key={item.id}>
        <span className="paper-resource-icon" aria-hidden="true">文</span>
        <h2>{item.name}</h2>
        <p>{item.description || "暂无说明"}</p>
        <div className="paper-card-footer">
          <span>文本资料 · {item.source_type}</span>
          <button onClick={e => p.onOpen(item.id, e.currentTarget)} aria-label={`查看 ${item.name}`}>阅读 ↗</button>
        </div>
      </article>)}
    </div>
    {p.hasMore && <button disabled={p.loading || p.stale} onClick={p.onMore}>加载更多</button>}
  </div>;
}
