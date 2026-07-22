// 与后端 app/models/schemas.py 对应。字段精度见 spec §2.3。

export interface ChatRequest {
  message: string;
  session_id: string;
  user_id: number | null;   // 后端是 int
}

export interface ChatResponse {
  reply: string;
  session_id: string;       // 勿漏（schemas.py:14）
  mastery_score?: number | null;
  turn_count?: number | null;
  mode_path?: string[] | null;
  cost_est_usd?: number | null;
  stack?: "new" | null;
  persisted?: boolean;       // 后端已返回（持久化状态）
}

export interface AuthResponse {
  user_id: number;          // int
  username: string;
  token?: string | null;    // 后端 Task 10 已签发 JWT
}

export interface KnowledgeResponse {
  id: number;
  name: string;
  description: string;
}

export interface SessionSummary {
  session_id: string;
  title: string;
  updated_at?: string | number | null;
}

// 前端聊天消息（内存维护，非后端类型）
export interface ChatMessage {
  role: "user" | "assistant" | "error";
  content: string;
}
