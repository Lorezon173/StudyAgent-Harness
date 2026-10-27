// 与后端 app/models/schemas.py 对应。字段精度见 spec §2.3。

export interface ChatRequest {
  message: string;
  session_id?: string;
  user_id?: number | null;   // 后端是 int，缺省为 null
  request_id?: string | null;
  profile_id?: string | null;
  expected_state_version?: number | null;
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
  request_id?: string | null;
  state_version?: number | null;
  profile_revision?: number | null;
  active_node_id?: string | null;
  status?: string | null;
  attempt?: number | null;
  error_code?: string | null;
  context_reduced?: boolean | null;
  reduction_reasons?: string[] | null;
}

export interface AuthResponse {
  user_id: number;          // int
  username: string;
  token?: string | null;    // 后端签发的 JWT
}

export interface KnowledgeResponse {
  id: number;
  name: string;
  description: string;
  user_id: number;
  profile_id: string | null;
  content_text: string;
  source_type: string;
  created_at: string;
  updated_at: string;
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

// app/models/workspace_schemas.py：日期保留 ISO 字符串，未评估数值保留 null。
export interface ProfileItem { id: string; user_id: number; name: string; scope_description: string; kind: string; revision: number; created_at: string; updated_at: string }
export interface ProfileNode { id: string; profile_id: string; title: string; description: string; mastery: number | null; last_practiced_at: number; practice_count: number; rationale: string; revision: number; archived: boolean }
export interface ProfileEdge { profile_id: string; from_node_id: string; to_node_id: string; type: string; weight: number; confidence: number; source: string }
export interface ProfileDetail { profile: ProfileItem; profile_revision: number; nodes: ProfileNode[]; edges: ProfileEdge[] }
export interface ProfilePage { items: ProfileItem[]; next_cursor: string | null }
export interface ProfileEvidence { id: string; node_id: string; session_id: string; request_id: string; message_id: number; score: number; rationale: string; created_at: string }
export interface ProfileSummary { profile_revision: number; nodes: ProfileNode[]; edges: ProfileEdge[]; recent_evidence: ProfileEvidence[]; assessed_count: number; total_count: number; mastery_score: number | null; metric_kind: string; assessment_coverage: number | null }
export interface ProfileCreate { name: string; scope_description?: string }
export interface ProfilePatch { expected_revision: number; name?: string; scope_description?: string }
export interface NodeCreate { expected_revision: number; title: string; description?: string }
export interface NodePatch { expected_revision: number; title?: string; description?: string; archived?: boolean }
export interface NodeMutationResponse { node: ProfileNode; profile_revision: number }
export interface WorkspaceSession { session_id: string; user_id: number | null; title: string; profile_id: string | null; active_node_id: string | null; state_version: number; next_turn_index: number; active_request_id: string | null; created_at: string | null; updated_at: string | null }
export interface WorkspaceMessage { id: number; turn_index: number; role: string; content: string; created_at: string | null }
export interface MessagePage { items: WorkspaceMessage[]; next_cursor: string | null }
export interface ReadingAnchor { message_id: number; offset_ratio: number }
export interface ViewState { draft: string; reading_anchor: ReadingAnchor | null; version: number; updated_at: string | null }
export interface ViewPatch { expected_version: number; draft?: string; reading_anchor?: ReadingAnchor | null }
export interface WorkspaceState { last_session_id: string | null; sidebar_pinned: boolean; sidebar_collapsed: boolean; progress_y_ratio: number; version: number; updated_at: string | null }
export interface WorkspacePatch { expected_version: number; last_session_id?: string | null; sidebar_pinned?: boolean; sidebar_collapsed?: boolean; progress_y_ratio?: number }
export interface SessionCreate { profile_id: string; title?: string; active_node_id?: string | null }
export interface ActiveNodePatch { expected_state_version: number; node_id: string | null }
export interface RetryRequest { expected_attempt: number; expected_state_version: number }
export interface RequestSnapshot { user_id: number; session_id: string; request_id: string; profile_id: string; active_node_id: string | null; request_payload: Record<string, unknown>; base_state_version: number; attempt: number; status: string; lease_until: string | null; lease_expired: boolean; error_code: string | null; response_json: Record<string, unknown> | null; created_at: string; updated_at: string }
export interface SessionSnapshot { session: WorkspaceSession; teaching_state: Record<string, unknown> | null; teaching_state_source: "stored" | "legacy"; legacy_state?: Record<string, unknown> | null; messages: MessagePage; profile: ProfileItem | null; profile_summary: ProfileSummary | null; view_state: ViewState; pending_requests: RequestSnapshot[] }
export interface SessionGroup { group_key: string; profile: ProfileItem | null; summary: ProfileSummary | null; sessions: WorkspaceSession[]; next_session_cursor: string | null }
export interface GroupedSessions { groups: SessionGroup[]; next_group_cursor: string | null }
export interface LibraryCreate { name: string; description?: string; content_text?: string; profile_id?: string | null }
export type LibraryPatch = Partial<LibraryCreate>;
