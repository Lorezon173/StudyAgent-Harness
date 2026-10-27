import { apiGet, apiPost, apiPatch, ApiError } from "./client";
import { ActiveNodePatch, ChatResponse, GroupedSessions, MessagePage, RequestSnapshot, RetryRequest, SessionCreate, SessionGroup, SessionSnapshot, ViewPatch, ViewState, WorkspaceSession } from "../types";
export function listGroupedSessions(params: { limit?: number; groupLimit?: number; cursor?: string | null } = {}): Promise<GroupedSessions> {
  const query = new URLSearchParams({ group_by: "profile" });
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.groupLimit !== undefined) query.set("group_limit", String(params.groupLimit));
  if (params.cursor != null) query.set("cursor", params.cursor);
  return apiGet(`/api/sessions?${query}`);
}
export async function listGroupSessions(params: { groupKey: string; sessionCursor?: string | null; limit?: number }): Promise<SessionGroup> {
  const query = new URLSearchParams({ group_by: "profile", group_key: params.groupKey });
  if (params.sessionCursor != null) query.set("session_cursor", params.sessionCursor);
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  const page = await apiGet<GroupedSessions>(`/api/sessions?${query}`);
  const group = page?.groups?.[0];
  if (!Array.isArray(page?.groups) || page.groups.length !== 1 || !group || group.group_key !== params.groupKey || (params.groupKey === "unassigned" ? group.profile !== null : group.profile?.id !== params.groupKey)) throw new ApiError(200, "会话分组数据不匹配", "invalid_group_page");
  return group;
}
const path = (id: string) => `/api/sessions/${encodeURIComponent(id)}`;
export const createSession = (input: SessionCreate) => apiPost<WorkspaceSession>("/api/sessions", input);
export const loadSnapshot = (id: string, messageLimit = 50) => apiGet<SessionSnapshot>(`${path(id)}/snapshot?message_limit=${messageLimit}`);
export function loadMessages(id: string, params: { cursor?: string | null; limit?: number } = {}) {
  const query = new URLSearchParams({ limit: String(params.limit ?? 50) });
  if (params.cursor != null) query.set("cursor", params.cursor);
  return apiGet<MessagePage>(`${path(id)}/messages?${query}`);
}
export const getRequest = (id: string, requestId: string) => apiGet<RequestSnapshot>(`${path(id)}/requests/${encodeURIComponent(requestId)}`);
export const retryRequest = (id: string, requestId: string, input: RetryRequest) => apiPost<ChatResponse>(`${path(id)}/requests/${encodeURIComponent(requestId)}/retry`, input);
export const patchViewState = (id: string, input: ViewPatch) => apiPatch<ViewState>(`${path(id)}/view-state`, input);
export const patchActiveNode = (id: string, input: ActiveNodePatch) => apiPatch<WorkspaceSession>(`${path(id)}/active-node`, input);
