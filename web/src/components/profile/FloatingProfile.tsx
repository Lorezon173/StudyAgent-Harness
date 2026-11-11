import { useId, type RefObject } from 'react';
import { ProfileItem, ProfileSummary } from '../../types';
import { useFloatingProfile } from '../../hooks/useFloatingProfile';
import ProfileSummaryCard from './ProfileSummaryCard';
export interface FloatingProfileProps { profile: ProfileItem | null; summary: ProfileSummary | null; activeNodeId: string | null; sessionId: string; generation: number; hostRef: RefObject<HTMLElement>; topbarRef: RefObject<HTMLElement>; composerRef: RefObject<HTMLElement>; ratio: number; savePreference: (ratio: number) => Promise<boolean> | void }
export default function FloatingProfile(props: FloatingProfileProps) {
  const { profile, summary, activeNodeId, sessionId } = props;
  const valid = profile && summary && profile.revision === summary.profile_revision;
  const floating = useFloatingProfile(props); const id = useId();
  const score = valid ? summary.mastery_score : null;
  return <div ref={floating.containerRef} className={`floating-profile${floating.open ? ' is-open' : ''}${floating.dragging ? ' is-dragging' : ''}`} style={{ top: floating.top, maxHeight: floating.maxHeight }} {...floating.containerEvents}>
    <button ref={floating.triggerRef} type="button" className="floating-profile-trigger" aria-label="学习画像" aria-expanded={floating.open} aria-controls={id} onPointerDown={floating.onTriggerPointerDown} onPointerCancel={floating.onTriggerPointerCancel} onClick={floating.toggle}>
      <span className={`floating-profile-ring${score === null ? ' is-unassessed' : ''}`} style={{ '--progress': `${score ?? 0}%` } as React.CSSProperties}>{valid ? score === null ? '待评估' : `${score}%` : '画像暂不可用'}</span>
    </button>
    <button type="button" className="floating-profile-handle" aria-label="调整画像位置" {...floating.handleEvents}>⋮</button>
    {floating.open && <div id={id} className="floating-profile-content" aria-label="画像详情">
      {valid ? <><ProfileSummaryCard profile={profile} summary={summary} activeNodeId={activeNodeId} compact /><p>下一步</p><a href={`/profile?profile_id=${encodeURIComponent(profile.id)}&session_id=${encodeURIComponent(sessionId)}`}>查看完整画像</a></> : <p>画像暂不可用</p>}
    </div>}
  </div>;
}


