import { apiDelete, apiGet, apiPatch, apiPost } from "./client";
import { KnowledgeResponse, LibraryCreate, LibraryPatch } from "../types";
export function listKnowledge(params: { q?: string; profile_id?: string; limit?: number; before_id?: number } = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => { if (value !== undefined) query.set(key, String(value)); });
  return apiGet<KnowledgeResponse[]>(`/api/knowledge${query.size ? `?${query}` : ""}`);
}
export const getKnowledge = (id: number) => apiGet<KnowledgeResponse>(`/api/knowledge/${id}`);
export const createKnowledge = (input: LibraryCreate) => apiPost<KnowledgeResponse>("/api/knowledge", input);
export const patchKnowledge = (id: number, input: LibraryPatch) => apiPatch<KnowledgeResponse>(`/api/knowledge/${id}`, input);
export const deleteKnowledge = (id: number) => apiDelete<{ status: string }>(`/api/knowledge/${id}`);
