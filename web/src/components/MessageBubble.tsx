import ReactMarkdown from "react-markdown";
import { ChatMessage } from "../types";

export default function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  const isError = msg.role === "error";
  const align = isUser ? "flex-end" : "flex-start";
  const bg = isError ? "#fdecea" : isUser ? "#dcf0ff" : "#ffffff";
  const color = isError ? "#c0392b" : "#1a1a1a";
  return (
    <div style={{ display: "flex", justifyContent: align, margin: "8px 0" }}>
      <div
        style={{
          maxWidth: "75%",
          background: bg,
          color,
          padding: "10px 14px",
          borderRadius: 12,
          border: "1px solid #e3e6ea",
        }}
      >
        {isUser ? msg.content : <ReactMarkdown>{msg.content}</ReactMarkdown>}
      </div>
    </div>
  );
}
