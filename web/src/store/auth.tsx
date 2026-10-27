import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from "react";
import { registerAuthInvalidation } from "../api/client";
import { workspaceStore } from "./workspace";

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
  return Number.isSafeInteger(n) && n > 0 ? n : null;
}

function readStoredAuth() {
  const id = readStoredId(); const rawToken = localStorage.getItem(KEY_TOKEN);
  const valid = id !== null && !!rawToken?.trim();
  const value = { userId: valid ? id : null, username: valid ? localStorage.getItem(KEY_NAME) : null, token: valid ? rawToken : null };
  workspaceStore.bootstrapAccount(value.userId, value.token);
  return value;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [{ userId, username, token }, setAuth] = useState(readStoredAuth);

  function login(id: number, name: string, tok?: string) {
    workspaceStore.startAccount(id, tok || null);
    localStorage.setItem(KEY_ID, String(id));  // number → string
    localStorage.setItem(KEY_NAME, name);
    localStorage.setItem(KEY_TOKEN, tok || "");
    setAuth({ userId: id, username: name, token: tok || null });
  }

  const logout = useCallback(() => {
    workspaceStore.clearAccount();
    localStorage.removeItem(KEY_ID);
    localStorage.removeItem(KEY_NAME);
    localStorage.removeItem(KEY_TOKEN);
    setAuth({ userId: null, username: null, token: null });
  }, []);

  useEffect(() => registerAuthInvalidation(ticket => {
    if (workspaceStore.isCurrent(ticket)) logout();
  }), [logout]);

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
