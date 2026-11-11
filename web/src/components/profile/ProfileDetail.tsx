import { Link } from "react-router-dom";
import { ProfileItem, ProfileSummary } from "../../types";

export default function ProfileDetail({ profile, summary, activeNodeId, sourceSessionId }: { profile: ProfileItem; summary: ProfileSummary; activeNodeId: string | null; sourceSessionId: string | null }) {
  const active = summary.nodes.find(node => node.id === activeNodeId);
  return <div className="profile-panel">
    <header><p>主题画像 · REV {summary.profile_revision}</p><h2>{profile.name}</h2><p>{profile.scope_description}</p></header>
    <p>已评估知识点平均掌握度：{summary.mastery_score === null ? "待评估" : `${summary.mastery_score}%`}；{summary.total_count === 0 ? "暂无知识点" : `评估覆盖 ${summary.assessed_count} / ${summary.total_count}`}</p>
    {sourceSessionId && <p>当前知识点：{active?.title ?? "未选择或已归档"}</p>}
    <section><h3>知识点</h3>{summary.nodes.length === 0 ? <p>暂无知识点</p> : <ul className="profile-node-list">{summary.nodes.map(node => <li className="profile-node" key={node.id}><h4>{node.title}</h4><p>{node.description}</p><p>掌握度：{node.mastery === null ? "待评估" : `${node.mastery}%`} · 练习 {node.practice_count} 次</p>{node.rationale && <p>{node.rationale}</p>}</li>)}</ul>}</section>
    <section><h3>知识关系</h3>{summary.edges.length === 0 ? <p>暂无已记录关系</p> : <ul className="profile-edge-list">{summary.edges.map((edge, i) => <li key={`${edge.from_node_id}-${edge.to_node_id}-${edge.type}-${i}`}>{edge.from_node_id} → {edge.to_node_id} · {edge.type}</li>)}</ul>}</section>
    <section><h3>最近来源</h3>{summary.recent_evidence.length === 0 ? <p>暂无已记录来源</p> : <ul className="profile-evidence-list">{summary.recent_evidence.map(item => <li key={item.id}><p>{summary.nodes.find(node => node.id === item.node_id)?.title ?? `已归档知识点（${item.node_id}）`}</p><p>{item.rationale}</p><p>{item.created_at} · 消息 {item.message_id} · 请求 {item.request_id}</p><Link to={`/chat/${encodeURIComponent(item.session_id)}`}>查看来源会话</Link></li>)}</ul>}</section>
  </div>;
}
