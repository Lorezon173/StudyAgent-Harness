import { Routes, Route, Navigate, Link } from "react-router-dom";
import { useAuth } from "./store/auth";
import { ReactNode } from "react";

function RequireAuth({ children }: { children: ReactNode }) {
  const { userId } = useAuth();
  return userId === null ? <Navigate to="/login" replace /> : <>{children}</>;
}

function Placeholder({ name }: { name: string }) {
  const { username, logout } = useAuth();
  return (
    <div className="container">
      <nav style={{ display: "flex", gap: 12, marginBottom: 16 }}>
        <Link to="/chat">聊天</Link>
        <Link to="/knowledge">知识库</Link>
        <Link to="/profile">画像</Link>
        <span style={{ marginLeft: "auto" }}>{username}</span>
        <button onClick={logout}>退出</button>
      </nav>
      <h2>{name}（占位，Task 6-10 实装）</h2>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Placeholder name="登录" />} />
      <Route path="/chat" element={<RequireAuth><Placeholder name="聊天" /></RequireAuth>} />
      <Route path="/knowledge" element={<RequireAuth><Placeholder name="知识库" /></RequireAuth>} />
      <Route path="/profile" element={<RequireAuth><Placeholder name="画像" /></RequireAuth>} />
      <Route path="*" element={<Navigate to="/chat" replace />} />
    </Routes>
  );
}
