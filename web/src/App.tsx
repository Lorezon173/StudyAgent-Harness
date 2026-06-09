import { Routes, Route, Navigate } from "react-router-dom";
import { useAuth } from "./store/auth";
import { ReactNode } from "react";
import Login from "./pages/Login";
import Chat from "./pages/Chat";
import Knowledge from "./pages/Knowledge";
import Profile from "./pages/Profile";

function RequireAuth({ children }: { children: ReactNode }) {
  const { userId } = useAuth();
  return userId === null ? <Navigate to="/login" replace /> : <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/chat" element={<RequireAuth><Chat /></RequireAuth>} />
      <Route path="/knowledge" element={<RequireAuth><Knowledge /></RequireAuth>} />
      <Route path="/profile" element={<RequireAuth><Profile /></RequireAuth>} />
      <Route path="*" element={<Navigate to="/chat" replace />} />
    </Routes>
  );
}
