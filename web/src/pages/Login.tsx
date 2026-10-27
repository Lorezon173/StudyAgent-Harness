import { useState, useRef, useLayoutEffect, FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { apiPost, ApiError } from "../api/client";
import { useAuth } from "../store/auth";
import { AuthResponse } from "../types";
import { workspaceStore } from "../store/workspace";

export default function Login() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();
  const alive = useRef(false); const mountEpoch = useRef(0); const submitSequence = useRef(0); const busyRef = useRef(false);
  useLayoutEffect(() => {
    const mount = ++mountEpoch.current; alive.current = true;
    let observedGeneration = workspaceStore.getSnapshot().account.generation;
    const unsubscribe = workspaceStore.subscribe(() => {
      const generation = workspaceStore.getSnapshot().account.generation;
      if (generation === observedGeneration) return;
      observedGeneration = generation;
      if (!alive.current || mountEpoch.current !== mount) return;
      submitSequence.current++; busyRef.current = false; setBusy(false); setError("");
    });
    return () => { unsubscribe(); if (mountEpoch.current === mount) { alive.current = false; mountEpoch.current++; submitSequence.current++; busyRef.current = false; } };
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busyRef.current) return;
    busyRef.current = true;
    setError("");
    setBusy(true);
    const ticket = { mount: mountEpoch.current, sequence: ++submitSequence.current, generation: workspaceStore.getSnapshot().account.generation };
    const current = () => alive.current && mountEpoch.current === ticket.mount && submitSequence.current === ticket.sequence && workspaceStore.getSnapshot().account.generation === ticket.generation;
    try {
      const path = mode === "login" ? "/api/auth/login" : "/api/auth/register";
      const resp = await apiPost<AuthResponse>(path, { username, password });
      if (!current()) return;
      // 自有 login 会换代；先结束本次忙状态，再同步 login → navigate。
      setError(""); busyRef.current = false; setBusy(false);
      login(resp.user_id, resp.username, resp.token ?? undefined);
      navigate("/chat");
    } catch (err) {
      if (current()) setError(err instanceof ApiError ? err.message : "请求失败");
    } finally {
      if (current()) { busyRef.current = false; setBusy(false); }
    }
  }

  return (
    <main className="login-page"><section className="login-card">
      <div className="study-brand"><span className="brand-mark" aria-hidden="true">学</span><h1>StudyAgent</h1></div><p className="form-intro">登录你的学习书房</p>
      <div className="login-modes">
        <button type="button" onClick={() => { setMode("login"); setError(""); }} disabled={busy || mode === "login"}>登录</button>
        <button type="button" onClick={() => { setMode("register"); setError(""); }} disabled={busy || mode === "register"}>注册</button>
      </div>
      <form onSubmit={submit}>
        <label htmlFor="login-username">用户名</label><input id="login-username" name="username" autoComplete="username" placeholder="用户名" value={username}
          onChange={(e) => setUsername(e.target.value)} disabled={busy} required />
        <label htmlFor="login-password">密码</label><input id="login-password" name="password" autoComplete={mode === "login" ? "current-password" : "new-password"} placeholder="密码" type="password" value={password}
          onChange={(e) => setPassword(e.target.value)} disabled={busy} required />
        <button className="primary-button" type="submit" disabled={busy}>
          {busy ? "提交中…" : mode === "login" ? "登录" : "注册"}
        </button>
      </form>
      {error && <p role="alert" className="form-error">{error}</p>}
    </section></main>
  );
}
