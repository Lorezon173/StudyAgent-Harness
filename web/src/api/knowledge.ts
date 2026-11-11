import { apiDelete, apiGet, apiPatch, apiPost } from "./client";
import { KnowledgeResponse, LibraryCreate, LibraryPatch } from "../types";
export function listKnowledge(params: { q?: string; profile_id?: string; limit?: number; before_id?: number } = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => { if (value !== undefined) query.set(key, String(value)); });
  return apiGet<KnowledgeResponse[]>(`/api/private-library${query.size ? `?${query}` : ""}`);
}
export const getKnowledge = (id: number) => apiGet<KnowledgeResponse>(`/api/private-library/${id}`);
export const createKnowledge = (input: LibraryCreate) => apiPost<KnowledgeResponse>("/api/private-library", input);
export const patchKnowledge = (id: number, input: LibraryPatch) => apiPatch<KnowledgeResponse>(`/api/private-library/${id}`, input);
export const deleteKnowledge = (id: number) => apiDelete<{ status: string }>(`/api/private-library/${id}`);
