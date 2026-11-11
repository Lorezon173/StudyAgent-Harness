import { hasBlockingRecovery, isMatchedLinked, isMatchedLocalCopy } from "../store/workspace";
import { getLocalRecovery } from "../store/localRecovery";
import { useWorkspaceController } from "../hooks/useWorkspaceController";
import { workspaceController } from "../store/workspaceController";
import MessageBubble from "../components/MessageBubble";
import { useLayoutEffect, useRef, useState } from "react";
import { useDraftPersistence } from "../hooks/useDraftPersistence";
import ChatComposer from "../components/workspace/ChatComposer";
import FloatingProfile from "../components/profile/FloatingProfile";

export default function Chat() {
  const { sessionId, bucket, state } = useWorkspaceController();
  const persistence = useDraftPersistence(sessionId);
  const scrollRef = useRef<HTMLDivElement>(null);
  const hostRef = useRef<HTMLDivElement>(null); const composerRef = useRef<HTMLDivElement>(null); const topbarRef = useRef<HTMLElement | null>(null);
  const [topbarReady, setTopbarReady] = useState(false);
  useLayoutEffect(() => { topbarRef.current = document.querySelector<HTMLElement>("[data-workspace-topbar]"); setTopbarReady(Boolean(topbarRef.current)); }, []);
  const preserved = useRef<{ id: string; height: number; top: number } | null>(null);
  const restored = useRef<string | null>(null);
  useLayoutEffect(() => {
    const node = scrollRef.current; if (!node || !sessionId || !bucket || bucket.load.status !== "ready") return;
    if (preserved.current?.id === sessionId) { node.scrollTop = preserved.current.top + node.scrollHeight - preserved.current.height; preserved.current = null; return; }
    const restoreKey = `${sessionId}:${bucket.load.sequence}:${bucket.anchorRestoreSequence}`;
    if (restored.current === restoreKey) return;
    const anchor = bucket.readingAnchor;
    const target = anchor && node.querySelector<HTMLElement>(`[data-message-id="${anchor.message_id}"]`);
    if (anchor && !target) return;
    restored.current = restoreKey;
    if (anchor && target) node.scrollTop = target.offsetTop - node.offsetTop + target.offsetHeight * anchor.offset_ratio;
  }, [sessionId, bucket?.load.status, bucket?.load.sequence, bucket?.anchorRestoreSequence, bucket?.messages]);
  if (!sessionId) return <section className="selected-session"><h1>开始学习</h1><p>从左侧开启一段新的探索。</p></section>;
  if (!bucket || bucket.load.status === "loading" || bucket.load.status === "idle") return <section className="selected-session" role="status">正在加载会话…</section>;
  if (bucket.load.status === "error") return <section className="selected-session"><p role="alert">{bucket.load.error}</p><button type="button" onClick={() => void workspaceController.loadSession(sessionId)}>重新加载</button></section>;
  const validOwner = bucket.session?.session_id === sessionId && bucket.session.user_id === state.account.userId && bucket.session.profile_id === bucket.profile?.id && bucket.profile?.user_id === state.account.userId;
  return <div ref={hostRef} className="legacy-chat" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
    <h1 className="chat-session-title" tabIndex={0}>{bucket.session?.title || "学习会话"}</h1>
    {bucket.activityGate !== "clear" && <section role="alert"><p>会话状态待确认</p>{bucket.activityError && <p>{bucket.activityError}</p>}<button type="button" disabled={bucket.activityGate === "checking"} onClick={() => void workspaceController.recheckSessionActivity(sessionId)}>重新查询会话状态</button></section>}
    {bucket.recoveryError && <p role="alert">{bucket.recoveryError}</p>}
    {bucket.conflictView && <section role="alert"><p>服务器草稿：{bucket.conflictView.draft}</p><p>本机草稿：{bucket.draft}</p><button type="button" onClick={() => workspaceController.useServerView(sessionId)}>使用服务器草稿</button><button type="button" onClick={() => workspaceController.saveLocalView(sessionId)}>保存本机草稿</button></section>}
    {bucket.recoveryCandidates.map(candidate => <section key={candidate.writeId}><p>发现本机草稿：{String(candidate.draft ?? "")}</p><button type="button" onClick={() => workspaceController.recoverDraft(sessionId, candidate)}>恢复本机草稿</button></section>)}
    {bucket.preparedCandidates.filter(candidate => candidate.phase === "prepared" && isMatchedLocalCopy(bucket, candidate, getLocalRecovery().writerId) && !bucket.acknowledgedPreparations.includes(candidate.writeId)).map(candidate => <section key={`uncertain-${candidate.writeId}`} role="alert"><p>当前页面已核对的请求已保存，但本机副本此刻无法确认，其他页面可能改变或新增副本；本操作不删除副本。</p><button type="button" onClick={() => workspaceController.acknowledgeUncertainMatched(sessionId, candidate)}>知悉本机状态不确定，继续本页</button></section>)}
    {bucket.preparedCandidates.map(candidate => <section key={candidate.writeId}><p>{String(candidate.text ?? "")}</p>{bucket.cancelledPreparations.includes(candidate.writeId) ? <button type="button" disabled={bucket.draft !== ""} onClick={() => workspaceController.recoverPrepared(sessionId, candidate)}>恢复待发送原文</button> : <><p>另一页面可能已经发送，重新提问可能产生重复回复；系统无法确认是否已发送。</p>{candidate.schema === 1 && <button type="button" onClick={() => void workspaceController.recheckLegacyPreparation(sessionId, candidate)}>查询原请求</button>}{candidate.phase === "linked" && <><button type="button" onClick={() => void workspaceController.recheckLinkedPreparation(sessionId, candidate)}>查询原请求</button>{typeof candidate.requestId === "string" && bucket.resendableRequests.includes(candidate.requestId) && <button type="button" onClick={() => void workspaceController.resendLinkedPreparation(sessionId, candidate)}>按原请求重试</button>}{isMatchedLinked(bucket, candidate) && !bucket.acknowledgedPreparations.includes(candidate.writeId) && (isMatchedLocalCopy(bucket, candidate, getLocalRecovery().writerId) ? <><p>当前页面已核对的请求已保存，但本机副本此刻无法确认，其他页面可能改变或新增副本。</p><button type="button" onClick={() => workspaceController.acknowledgeUncertainMatched(sessionId, candidate)}>知悉本机状态不确定，继续本页</button></> : <><p>此请求和历史已核对；本机副本可能仍由另一页面使用，本操作只让当前页面继续，不会删除副本；重新登录需再次确认。</p><button type="button" onClick={() => workspaceController.acknowledgeMatchedLinked(sessionId, candidate)}>确认此请求已完成并继续</button></>)}</>}<button type="button" disabled={bucket.draft !== "" || candidate.schema === 1 || candidate.phase === "linked"} onClick={() => workspaceController.acknowledgePreparedRisk(sessionId, candidate)}>复制原文并自行决定是否重新提问</button></>}{bucket.draft !== "" && <small>请先处理当前草稿，原文会保留。</small>}</section>)}
    {bucket.requestCandidates.filter(candidate => candidate.itemId !== bucket.request.id || bucket.request.status === "unknown" || candidate.writerId !== getLocalRecovery().writerId && hasBlockingRecovery({ ...bucket, requestCandidates: [candidate] })).map(candidate => <section key={candidate.writeId}><p>{String((candidate.payload as Record<string, unknown>)?.message ?? "")}</p><p>上次请求结果待确认</p><button type="button" onClick={() => void workspaceController.recheckCandidate(sessionId, candidate)}>查询上次请求</button>{bucket.resendableRequests.includes(candidate.itemId) && <button type="button" onClick={() => void workspaceController.resendCandidate(sessionId, candidate)}>按原请求重发</button>}</section>)}
    <div ref={scrollRef} className="chat-messages" style={{ flex: 1, overflowY: "auto", padding: "12px 16px" }} onScroll={event => {
      const node = event.currentTarget; const top = node.getBoundingClientRect().top;
      const visible = [...node.querySelectorAll<HTMLElement>("[data-message-id]")].find(item => item.getBoundingClientRect().bottom > top);
      if (!visible) return;
      const rect = visible.getBoundingClientRect(); const ratio = rect.height > 0 ? Math.max(0, Math.min(1, (top - rect.top) / rect.height)) : 0;
      persistence.setReadingAnchor({ message_id: Number(visible.dataset.messageId), offset_ratio: ratio });
    }}>
      {bucket.historySyncError && <section role="alert"><p>{bucket.historySyncError}</p><button type="button" onClick={() => void workspaceController.loadSession(sessionId)}>重新同步历史</button></section>}
      {bucket.messagePageError && <p role="alert">{bucket.messagePageError}</p>}
      {bucket.nextMessageCursor !== null && <button type="button" onClick={() => { const node = scrollRef.current; if (node) preserved.current = { id: sessionId, height: node.scrollHeight, top: node.scrollTop }; void workspaceController.loadOlder(sessionId).then(ok => { if (!ok && preserved.current?.id === sessionId) preserved.current = null; }); }}>{bucket.messagePageError ? "重试加载更早消息" : "加载更早消息"}</button>}
      {bucket.messages.map(item => <div key={item.id} data-message-id={item.id}><MessageBubble msg={{ role: item.role === "user" ? "user" : "assistant", content: item.content }} /></div>)}
    </div>
    {bucket.pendingRequests.map(item => <section key={item.request_id}><p>{String(item.request_payload.message ?? "")}</p><p>{bucket.requests[item.request_id]?.association === "inconsistent" ? "请求状态不一致，请重新查询" : item.status === "failed" ? "请求失败，可重试" : item.status === "interrupted" ? "请求已中断，可重试" : "请求处理中"}</p>{bucket.requests[item.request_id]?.association === "inconsistent" ? <button type="button" onClick={() => void workspaceController.reconcile(sessionId, item.request_id)}>重新查询状态</button> : ["failed", "interrupted"].includes(item.status) && <button type="button" onClick={() => void workspaceController.retry(sessionId, item.request_id)}>重试请求</button>}{bucket.staleRequestId === item.request_id && <button type="button" disabled={bucket.staleDraftRevision !== bucket.draftRevision} onClick={() => persistence.setDraft(String(item.request_payload.message ?? ""))}>复制原文到输入框</button>}</section>)}
    {bucket.request.id && !bucket.pendingRequests.some(item => item.request_id === bucket.request.id) && ["preparing", "unknown", "pending_messages", "unassociated", "inconsistent"].includes(bucket.request.status || "") && <section><p>{bucket.request.text}</p><p>{bucket.request.status === "preparing" ? "正在准备…" : bucket.request.status === "unknown" ? "结果待确认" : bucket.request.status === "inconsistent" ? "消息存在冲突，请重新查询" : bucket.request.status === "unassociated" ? "请求已完成，无法确定其对应历史消息；历史按服务器内容显示" : "回复已保存，正在同步"}</p>{bucket.request.status === "unassociated" ? <button type="button" onClick={() => void workspaceController.continueUnassociated(sessionId, bucket.request.id!)}>保留未关联记录并继续</button> : <button type="button" onClick={() => void workspaceController.reconcile(sessionId, bucket.request.id!, undefined, bucket.request.status === "inconsistent")}>重新查询</button>}</section>}
    {bucket.save.status !== "idle" && <p role="status">{bucket.save.status === "saved" ? "草稿已保存" : bucket.save.status === "saving" ? "正在保存草稿…" : bucket.save.status === "conflict" ? "草稿有冲突，请处理" : "草稿未保存"}{bucket.save.error && `：${bucket.save.error}`}</p>}
    {bucket.save.status === "error" && <button type="button" onClick={() => void persistence.retry()}>重试保存草稿</button>}
    {bucket.request.error && <p role="alert">{bucket.request.error}</p>}
    <div ref={composerRef} className="chat-composer-area"><ChatComposer draft={persistence.draft} disabled={state.exitPending || hasBlockingRecovery(bucket) || bucket.activityGate !== "clear" || Boolean(bucket.session?.active_request_id) || bucket.pendingRequests.some(item => item.status === "running")} busy={bucket.preparedCandidates.some(item => !bucket.cancelledPreparations.includes(item.writeId) && !bucket.acknowledgedPreparations.includes(item.writeId)) || ["running", "preparing", "unknown", "pending_messages", "unassociated", "inconsistent"].includes(bucket.request.status || "")} onDraftChange={persistence.setDraft} onSend={() => void workspaceController.send(sessionId)} /></div>
    {validOwner && topbarReady && <FloatingProfile profile={bucket.profile} summary={bucket.profileSummary} activeNodeId={bucket.session?.active_node_id ?? null} sessionId={sessionId} generation={state.account.generation} hostRef={hostRef} topbarRef={topbarRef} composerRef={composerRef} ratio={state.workspace.prefs.localValues.progressYRatio} savePreference={workspaceController.savePreference} />}
  </div>;
}
