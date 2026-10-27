import { apiGet, apiPost, apiPatch } from "./client";
import { ProfileCreate, ProfileDetail, ProfilePage, ProfilePatch, ProfileSummary } from "../types";
export function listProfiles(params: { limit?: number; cursor?: string | null } = {}) {
  const query = new URLSearchParams();
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.cursor != null) query.set("cursor", params.cursor);
  return apiGet<ProfilePage>(`/api/topic-profiles${query.size ? `?${query}` : ""}`);
}
export const createProfile = (input: ProfileCreate) => apiPost<ProfileDetail>("/api/topic-profiles", input);
export const getProfile = (id: string) => apiGet<ProfileDetail>(`/api/topic-profiles/${encodeURIComponent(id)}`);
export const getProfileSummary = (id: string) => apiGet<ProfileSummary>(`/api/topic-profiles/${encodeURIComponent(id)}/summary`);
export const patchProfile = (id: string, input: ProfilePatch) => apiPatch<ProfileDetail>(`/api/topic-profiles/${encodeURIComponent(id)}`, input);
