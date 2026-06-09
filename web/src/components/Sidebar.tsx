import { useState, useEffect } from "react";
import { apiGet } from "../api/client";
import { useAuth } from "../store/auth";
import { SessionResponse } from "../types";

export default function Sidebar({ onNew }: { onNew: () => void }) {
  const { userId } = useAuth();
  const [sessions, setSessions] = useState<SessionResponse[]>([]);

  useEffect(() => {
    if (userId === null) return;
    apiGet<SessionResponse[]>(`/api/sessions?user_id=${userId}`)
      .then(setSessions)
      .catch(() => setSessions([]));
  }, [userId]);

  return (
    <aside style={{ width: 200, background: "#fff", borderRight: "1px solid #e3e6ea",
      padding: 12 }}>
      <button onClick={onNew} style={{ width: "100%", marginBottom: 12 }}>+ 新建会话</button>
      {sessions.length === 0 ? (
        <p style={{ color: "#aaa", fontSize: 13 }}>暂无历史会话（新栈未持久化）</p>
      ) : (
        <ul style={{ listStyle: "none" }}>
          {sessions.map((s) => (
            <li key={s.session_id} style={{ padding: 6, fontSize: 13 }}>{s.session_id}</li>
          ))}
        </ul>
      )}
    </aside>
  );
}
