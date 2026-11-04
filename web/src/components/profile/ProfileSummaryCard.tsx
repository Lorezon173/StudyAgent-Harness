import { ProfileItem, ProfileSummary } from "../../types";

export interface ProfileSummaryCardProps { profile: ProfileItem; summary: ProfileSummary; activeNodeId: string | null }
export default function ProfileSummaryCard({ profile, summary, activeNodeId }: ProfileSummaryCardProps) {
  const active = summary.nodes.find(node => node.id === activeNodeId);
  return <aside className="profile-summary-card" aria-label="画像摘要">
    <p>学习画像 · REV {summary.profile_revision}</p><h2>{profile.name}</h2>
    <div className="profile-metric"><strong>{summary.mastery_score === null ? "待评估" : `${summary.mastery_score}%`}</strong><span>已评估知识点平均掌握度</span></div>
    <p>{summary.total_count === 0 ? "暂无知识点" : `评估覆盖 ${summary.assessed_count} / ${summary.total_count}（${summary.assessment_coverage === null ? "待评估" : `${summary.assessment_coverage * 100}%`}）`}</p>
    {activeNodeId !== null && <p>当前知识点：{active?.title ?? "未选择或已归档"}</p>}
  </aside>;
}
