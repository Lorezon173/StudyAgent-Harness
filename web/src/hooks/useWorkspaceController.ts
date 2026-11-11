import { useEffect, useRef, useSyncExternalStore } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { workspaceStore } from "../store/workspace";
import { workspaceController } from "../store/workspaceController";

export function useWorkspaceController() {
  const state = useSyncExternalStore(workspaceStore.subscribe, workspaceStore.getSnapshot, workspaceStore.getServerSnapshot);
  const { sessionId } = useParams(); const location = useLocation(); const navigate = useNavigate();
  const currentPath = useRef(location.pathname); currentPath.current = location.pathname;
  useEffect(() => {
    if (sessionId) { void workspaceController.loadSession(sessionId); return; }
    if (location.pathname !== "/chat" && location.pathname !== "/chat/") return;
    if ((location.state as { localOnly?: boolean } | null)?.localOnly) return;
    let active = true; const ticket = workspaceStore.captureTicket(); const path = location.pathname;
    void workspaceController.lastSession(ticket).then(id => {
      if (active && id && currentPath.current === path && workspaceStore.isCurrent(ticket)) navigate(`/chat/${encodeURIComponent(id)}`, { replace: true });
    }).catch(() => {});
    return () => { active = false; };
  }, [state.account.generation, sessionId, location.pathname, location.state, navigate]);
  return { state, sessionId, bucket: sessionId ? state.buckets[sessionId] : undefined };
}
