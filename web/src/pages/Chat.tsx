import { useState, FormEvent } from "react";
import { Link } from "react-router-dom";
import { apiPost, ApiError } from "../api/client";
import { useAuth } from "../store/auth";
import { ChatMessage, ChatResponse } from "../types";
import MessageBubble from "../components/MessageBubble";
import TeachingStatus from "../components/TeachingStatus";

function newSessionId(): string {
  return "s-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
}

export default function Chat() {
  const { userId, username, logout } = useAuth();
  const [sessionId, setSessionId] = useState(newSessionId());
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [lastResp, setLastResp] = useState<ChatResponse | null>(null);

  async function send(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: text }]);
    setBusy(true);
    try {
      const resp = await apiPost<ChatResponse>("/api/chat", {
        message: text, session_id: sessionId, user_id: userId,
      });
      setLastResp(resp);
      setMessages((m) => [...m, { role: "assistant", content: resp.reply }]);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "请求失败";
      setMessages((m) => [...m, { role: "error", content: msg }]);
    } finally {
      setBusy(false);
    }
  }

  function resetSession() {
    setSessionId(newSessionId());
    setMessages([]);
    setLastResp(null);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <nav style={{ display: "flex", gap: 12, padding: "8px 12px",
        background: "#fff", borderBottom: "1px solid #e3e6ea", alignItems: "center" }}>
        <strong>聊天</strong>
        <Link to="/knowledge">知识库</Link>
        <Link to="/profile">画像</Link>
        <button onClick={resetSession}>新建会话</button>
        <span style={{ marginLeft: "auto" }}>{username}</span>
        <button onClick={logout}>退出</button>
      </nav>
      <TeachingStatus last={lastResp} />
      <div style={{ flex: 1, overflowY: "auto", padding: "12px 16px" }}>
        {messages.length === 0 && (
          <p style={{ color: "#888" }}>输入一个学习问题开始（如「我想学二分查找」）。</p>
        )}
        {messages.map((m, i) => <MessageBubble key={i} msg={m} />)}
        {busy && <p style={{ color: "#888", margin: "8px 0" }}>AI 思考中…（协作环可能 10-40s）</p>}
      </div>
      <form onSubmit={send} style={{ display: "flex", gap: 8, padding: 12,
        background: "#fff", borderTop: "1px solid #e3e6ea" }}>
        <input style={{ flex: 1, padding: "8px 12px" }} value={input}
          placeholder="输入学习问题…" onChange={(e) => setInput(e.target.value)} />
        <button type="submit" disabled={busy}>发送</button>
      </form>
    </div>
  );
}
