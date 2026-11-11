import { apiGet, apiPatch } from "./client";
import { WorkspacePatch, WorkspaceState } from "../types";
export const getWorkspaceState = () => apiGet<WorkspaceState>("/api/workspace-state");
export const patchWorkspaceState = (input: WorkspacePatch) => apiPatch<WorkspaceState>("/api/workspace-state", input);
