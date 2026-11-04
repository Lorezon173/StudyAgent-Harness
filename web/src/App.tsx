import { Routes, Route, Navigate, Outlet } from "react-router-dom";
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

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<RequireAuth><ProtectedWorkspace /></RequireAuth>}>
        <Route path="/chat" element={<Chat />} />
        <Route path="/chat/:sessionId" element={<Chat />} />
        <Route path="/knowledge" element={<Knowledge />} />
        <Route path="/profile" element={<Profile />} />
      </Route>
      <Route path="*" element={<Navigate to="/chat" replace />} />
    </Routes>
  );
}
