// 预留组件：会话历史侧栏。当前未集成到 Chat 页面，待后续增强时挂入。
import { useState, useEffect } from "react";
import { apiGet } from "../api/client";
import { useAuth } from "../store/auth";
import { SessionSummary } from "../types";

export default function Sidebar({ onNew }: { onNew: () => void }) {
  const { userId } = useAuth();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);

  useEffect(() => {
    if (userId === null) return;
    apiGet<SessionSummary[]>("/api/sessions")
      .then(setSessions)
      .catch(() => setSessions([]));
  }, [userId]);

  return (
    <aside style={{ width: 200, background: "#fff", borderRight: "1px solid #e3e6ea",
      padding: 12 }}>
      <button onClick={onNew} style={{ width: "100%", marginBottom: 12 }}>+ 新建会话</button>
      {sessions.length === 0 ? (
        <p style={{ color: "#aaa", fontSize: 13 }}>暂无历史会话</p>
      ) : (
        <ul style={{ listStyle: "none" }}>
          {sessions.map((s) => (
            <li key={s.session_id} style={{ padding: 6, fontSize: 13 }}>{s.title || s.session_id}</li>
          ))}
        </ul>
      )}
    </aside>
  );
}
