import { useState, FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { apiPost, ApiError } from "../api/client";
import { useAuth } from "../store/auth";
import { AuthResponse } from "../types";

export default function Login() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const path = mode === "login" ? "/api/auth/login" : "/api/auth/register";
      const resp = await apiPost<AuthResponse>(path, { username, password });
      login(resp.user_id, resp.username);
      navigate("/chat");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "请求失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="container" style={{ maxWidth: 360, marginTop: 80 }}>
      <h1>StudyAgent</h1>
      <div style={{ margin: "16px 0" }}>
        <button onClick={() => setMode("login")} disabled={mode === "login"}>登录</button>
        <button onClick={() => setMode("register")} disabled={mode === "register"}>注册</button>
      </div>
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <input placeholder="用户名" value={username}
          onChange={(e) => setUsername(e.target.value)} required />
        <input placeholder="密码" type="password" value={password}
          onChange={(e) => setPassword(e.target.value)} required />
        <button type="submit" disabled={busy}>
          {busy ? "提交中…" : mode === "login" ? "登录" : "注册"}
        </button>
      </form>
      {error && <p style={{ color: "#c0392b", marginTop: 8 }}>{error}</p>}
    </div>
  );
}
