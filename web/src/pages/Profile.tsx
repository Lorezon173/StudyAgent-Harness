import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { apiGet } from "../api/client";
import { useAuth } from "../store/auth";

interface ProfileResp {
  user_id: number;
  stats: { sessions: number; avg_mastery: number };
}

export default function Profile() {
  const { userId } = useAuth();
  const [stats, setStats] = useState<ProfileResp["stats"] | null>(null);

  useEffect(() => {
    if (userId === null) return;
    apiGet<ProfileResp>(`/api/profile/${userId}`)
      .then((r) => setStats(r.stats))
      .catch(() => setStats(null));
  }, [userId]);

  const placeholder = { color: "#aaa", fontStyle: "italic" as const };
  return (
    <div className="container">
      <nav style={{ display: "flex", gap: 12, marginBottom: 16 }}>
        <Link to="/chat">聊天</Link><Link to="/knowledge">知识库</Link><strong>画像</strong>
      </nav>
      <section style={{ background: "#fff", padding: 16, borderRadius: 8, marginBottom: 12 }}>
        <h3>学习进度</h3>
        <p>会话数：{stats?.sessions ?? 0} ｜ 平均掌握度：{stats?.avg_mastery ?? 0}</p>
      </section>
      <section style={{ background: "#fff", padding: 16, borderRadius: 8, marginBottom: 12 }}>
        <h3>掌握点图谱</h3>
        <p style={placeholder}>待后端持久化后填充（新栈当前用内存 EventStore，不写画像）</p>
      </section>
      <section style={{ background: "#fff", padding: 16, borderRadius: 8 }}>
        <h3>学习偏好</h3>
        <p style={placeholder}>待后端持久化后填充</p>
      </section>
    </div>
  );
}
