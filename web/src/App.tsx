import { Routes, Route, Navigate, Outlet, Link, useParams } from "react-router-dom";
import { useAuth } from "./store/auth";
import { ReactNode, useSyncExternalStore } from "react";
import Login from "./pages/Login";
import Chat from "./pages/Chat";
import Knowledge from "./pages/Knowledge";
import Profile from "./pages/Profile";
import WorkspaceLayout from "./components/workspace/WorkspaceLayout";
import { workspaceStore } from "./store/workspace";

function RequireAuth({ children }: { children: ReactNode }) {
  const { userId, token } = useAuth();
  return userId === null || !token ? <Navigate to="/login" replace /> : <>{children}</>;
}

function ProtectedWorkspace() {
  const state = useSyncExternalStore(workspaceStore.subscribe, workspaceStore.getSnapshot, workspaceStore.getServerSnapshot);
  return <WorkspaceLayout key={state.account.generation}><Outlet /></WorkspaceLayout>;
}

function SelectedSession() {
  const { sessionId } = useParams();
  const state = useSyncExternalStore(workspaceStore.subscribe, workspaceStore.getSnapshot, workspaceStore.getServerSnapshot);
  const session = state.groups.flatMap(group => group.sessions).find(item => item.session_id === sessionId);
  return <section className="selected-session"><div className="eyebrow">我的学习会话</div><h1>{session?.title || "学习会话"}</h1><div className="unavailable-card"><h2>此会话的内容暂不可用</h2><p>你可以返回学习，或从左侧选择其他会话。</p><Link to="/chat">返回学习 →</Link></div></section>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<RequireAuth><ProtectedWorkspace /></RequireAuth>}>
        <Route path="/chat" element={<Chat />} />
        <Route path="/chat/:sessionId" element={<SelectedSession />} />
        <Route path="/knowledge" element={<Knowledge />} />
        <Route path="/profile" element={<Profile />} />
      </Route>
      <Route path="*" element={<Navigate to="/chat" replace />} />
    </Routes>
  );
}
