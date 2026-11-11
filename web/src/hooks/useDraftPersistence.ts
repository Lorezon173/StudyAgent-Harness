import { useSyncExternalStore } from "react";
import { ReadingAnchor } from "../types";
import { RecoveryCandidate } from "../store/localRecovery";
import { workspaceController } from "../store/workspaceController";
import { workspaceStore } from "../store/workspace";

export function useDraftPersistence(sessionId?: string) {
  const state = useSyncExternalStore(workspaceStore.subscribe, workspaceStore.getSnapshot, workspaceStore.getServerSnapshot);
  const bucket = sessionId ? state.buckets[sessionId] : undefined;
  return {
    draft: bucket?.draft ?? "", readingAnchor: bucket?.readingAnchor ?? null,
    saveStatus: bucket?.save.status ?? "idle", error: bucket?.save.error ?? null,
    setDraft: (value: string) => { if (sessionId) workspaceController.setDraft(sessionId, value); },
    setReadingAnchor: (value: ReadingAnchor | null) => { if (sessionId) workspaceController.setAnchor(sessionId, value); },
    flush: () => sessionId ? workspaceController.flush(sessionId) : Promise.resolve(false),
    retry: () => sessionId ? workspaceController.flush(sessionId) : Promise.resolve(false),
    recoverLocalDraft: (candidate: RecoveryCandidate) => { if (sessionId) workspaceController.recoverDraft(sessionId, candidate); },
  };
}
