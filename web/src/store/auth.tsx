import { createContext, useContext, useState, ReactNode } from "react";

interface AuthState {
  userId: number | null;
  username: string | null;
  login: (userId: number, username: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

const KEY_ID = "studyagent_user_id";
const KEY_NAME = "studyagent_username";

function readStoredId(): number | null {
  const raw = localStorage.getItem(KEY_ID);   // localStorage 只存字符串
  if (raw === null) return null;
  const n = Number(raw);                       // 转回 number（spec §2.3）
  return Number.isFinite(n) ? n : null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [userId, setUserId] = useState<number | null>(readStoredId());
  const [username, setUsername] = useState<string | null>(
    localStorage.getItem(KEY_NAME),
  );

  function login(id: number, name: string) {
    localStorage.setItem(KEY_ID, String(id));  // number → string
    localStorage.setItem(KEY_NAME, name);
    setUserId(id);
    setUsername(name);
  }

  function logout() {
    localStorage.removeItem(KEY_ID);
    localStorage.removeItem(KEY_NAME);
    setUserId(null);
    setUsername(null);
  }

  return (
    <AuthContext.Provider value={{ userId, username, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth 必须在 AuthProvider 内使用");
  return ctx;
}
