import { createContext, useContext, useState, ReactNode } from "react";

interface AuthState {
  userId: number | null;
  username: string | null;
  token: string | null;
  login: (userId: number, username: string, token?: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

const KEY_ID = "studyagent_user_id";
const KEY_NAME = "studyagent_username";
const KEY_TOKEN = "studyagent_token";

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
  const [token, setToken] = useState<string | null>(
    localStorage.getItem(KEY_TOKEN),
  );

  function login(id: number, name: string, tok?: string) {
    localStorage.setItem(KEY_ID, String(id));  // number → string
    localStorage.setItem(KEY_NAME, name);
    localStorage.setItem(KEY_TOKEN, tok || "");
    setUserId(id);
    setUsername(name);
    setToken(tok || null);
  }

  function logout() {
    localStorage.removeItem(KEY_ID);
    localStorage.removeItem(KEY_NAME);
    localStorage.removeItem(KEY_TOKEN);
    setUserId(null);
    setUsername(null);
    setToken(null);
  }

  return (
    <AuthContext.Provider value={{ userId, username, token, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth 必须在 AuthProvider 内使用");
  return ctx;
}

export function getToken(): string | null {
  const raw = localStorage.getItem(KEY_TOKEN);
  return raw || null;
}
