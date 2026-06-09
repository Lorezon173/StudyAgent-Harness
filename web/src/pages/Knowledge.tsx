import { useState, useEffect, FormEvent, useCallback } from "react";
import { Link } from "react-router-dom";
import { apiGet, apiPost, apiDelete, ApiError } from "../api/client";
import { KnowledgeResponse } from "../types";

export default function Knowledge() {
  const [items, setItems] = useState<KnowledgeResponse[]>([]);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      setItems(await apiGet<KnowledgeResponse[]>("/api/knowledge"));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "加载失败");
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function create(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      await apiPost<KnowledgeResponse>("/api/knowledge", { name, description: desc });
      setName(""); setDesc("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "创建失败");
    }
  }

  async function remove(id: number) {
    try {
      await apiDelete(`/api/knowledge/${id}`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "删除失败");
    }
  }

  return (
    <div className="container">
      <nav style={{ display: "flex", gap: 12, marginBottom: 16 }}>
        <Link to="/chat">聊天</Link><strong>知识库</strong><Link to="/profile">画像</Link>
      </nav>
      <form onSubmit={create} style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <input placeholder="名称" value={name} onChange={(e) => setName(e.target.value)} />
        <input placeholder="描述" value={desc} onChange={(e) => setDesc(e.target.value)} />
        <button type="submit">创建</button>
      </form>
      {error && <p style={{ color: "#c0392b" }}>{error}</p>}
      {items.length === 0 ? <p style={{ color: "#888" }}>暂无知识库</p> : (
        <ul style={{ listStyle: "none" }}>
          {items.map((k) => (
            <li key={k.id} style={{ display: "flex", gap: 8, padding: 8,
              background: "#fff", marginBottom: 4, borderRadius: 6 }}>
              <strong>{k.name}</strong><span style={{ color: "#888" }}>{k.description}</span>
              <button style={{ marginLeft: "auto" }} onClick={() => remove(k.id)}>删除</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
