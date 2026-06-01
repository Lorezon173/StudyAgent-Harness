from app.agents.base import AgentBase
from app.harness.events import Event
from app.harness.enums import EventType, EventSource
from app.harness.workspace_state import WorkspaceState
from app.harness.mastery_graph import MasteryGraph, EdgeType
from app.infrastructure.storage.mastery_graph_store import MasteryGraphStore


class Curator(AgentBase):
    """维护用户画像与掌握点知识图谱（§2.1 Curator 行）。

    事件契约：
    - source = curator
    - subscriptions = [MasteryAssessed, TopicEntered]
    - emittable_types = {ProfileUpdated, GraphNodeStrengthened, GraphPrereqWeakDetected}
    - 只判结构层：基于图谱 PREREQ 边 + 前置节点掌握度判"前置薄弱"
    - 绝不判文本语义（那归 Critic）

    双时机：
    - TopicEntered  → 基于历史画像发 GraphPrereqWeakDetected(basis=historical)
    - MasteryAssessed → 基于实测发 basis=observed
    - historical 分支为渐进启用：冷启动（无 PREREQ 边或前置节点缺失）时不触发
    """

    source = EventSource.CURATOR
    subscriptions = [EventType.MASTERY_ASSESSED, EventType.TOPIC_ENTERED]
    emittable_types = {
        EventType.PROFILE_UPDATED,
        EventType.GRAPH_NODE_STRENGTHENED,
        EventType.GRAPH_PREREQ_WEAK_DETECTED,
    }

    def __init__(self, graph: MasteryGraph, store: MasteryGraphStore):
        self.graph = graph
        self._store = store

    def handle(self, event: Event, ws: WorkspaceState) -> list[Event]:
        if event.type == EventType.MASTERY_ASSESSED:
            return self._on_mastery_assessed(event, ws)
        if event.type == EventType.TOPIC_ENTERED:
            return self._on_topic_entered(event, ws)
        return []

    # ---- MasteryAssessed → basis=observed ----

    def _on_mastery_assessed(self, event: Event, ws: WorkspaceState) -> list[Event]:
        """回合中：更新图谱掌握度 + 检查前置薄弱（observed）。"""
        results: list[Event] = []
        payload = event.payload
        topic_id = payload.get("topic_id") or ws.current_topic
        score = payload.get("score", 0.0)
        level = payload.get("level", "partial")

        if self.graph.get_node(topic_id) is None:
            self.graph.add_node(topic_id, topic_id, mastery=0.0)
        old_mastery = self.graph.get_node(topic_id).mastery
        self.graph.update_mastery(topic_id, score)
        node = self.graph.get_node(topic_id)

        results.append(self.emit(
            EventType.GRAPH_NODE_STRENGTHENED, ws,
            payload={
                "topic_id": topic_id,
                "mastery": score,
                "previous_mastery": old_mastery,
                "level": level,
                "practice_count": node.practice_count,
            },
            parent_id=event.id,
        ))
        results.append(self.emit(
            EventType.PROFILE_UPDATED, ws,
            payload={"action": "node_updated", "topic_id": topic_id, "mastery": score},
            parent_id=event.id,
        ))

        current_topic = ws.current_topic or topic_id
        if self.graph.has_any_prereqs(current_topic):
            for wp in self.graph.find_weak_prereqs(current_topic):
                results.append(self.emit(
                    EventType.GRAPH_PREREQ_WEAK_DETECTED, ws,
                    payload={
                        "topic_id": current_topic,
                        "prereq_topic_id": wp["prereq_topic_id"],
                        "prereq_name": wp["prereq_name"],
                        "prereq_mastery": wp["mastery"],
                        "edge_confidence": wp["edge_confidence"],
                        "adjusted_threshold": wp["adjusted_threshold"],
                        "edge_source": wp["edge_source"],
                        "basis": "observed",
                    },
                    parent_id=event.id,
                ))
        return results

    # ---- TopicEntered → basis=historical（渐进启用）----

    def _on_topic_entered(self, event: Event, ws: WorkspaceState) -> list[Event]:
        """开局/切主题：基于历史画像检查前置。

        渐进启用：无 PREREQ 边或所有前置节点缺失 → 不发。
        """
        results: list[Event] = []
        topic_id = event.payload.get("topic_id") or ws.current_topic
        if not topic_id:
            return results
        if self.graph.get_node(topic_id) is None:
            self.graph.add_node(topic_id, topic_id, mastery=0.0)
        if not self.graph.has_any_prereqs(topic_id):
            return results
        prereqs_have_mastery = any(
            self.graph.get_node(e.from_topic) is not None
            for e in self.graph.edges
            if e.to_topic == topic_id and e.type == EdgeType.PREREQ
        )
        if not prereqs_have_mastery:
            return results

        for wp in self.graph.find_weak_prereqs(topic_id):
            results.append(self.emit(
                EventType.GRAPH_PREREQ_WEAK_DETECTED, ws,
                payload={
                    "topic_id": topic_id,
                    "prereq_topic_id": wp["prereq_topic_id"],
                    "prereq_name": wp["prereq_name"],
                    "prereq_mastery": wp["mastery"],
                    "edge_confidence": wp["edge_confidence"],
                    "adjusted_threshold": wp["adjusted_threshold"],
                    "edge_source": wp["edge_source"],
                    "basis": "historical",
                },
                parent_id=event.id,
            ))
        return results

    # ---- evaluate（§5.2）----

    def evaluate(self, test_case: dict) -> dict:
        """部件级评估接口：返回图谱覆盖率等。

        test_case = {"graph_nodes": {topic_id: expected_mastery, ...}, "graph_edges": [...]}
        """
        expected_nodes = test_case.get("graph_nodes", {})
        if not expected_nodes:
            return {"coverage": 0.0, "note": "no expected nodes specified"}
        found = sum(1 for tid in expected_nodes if self.graph.get_node(tid) is not None)
        coverage = found / len(expected_nodes)
        return {
            "coverage": round(coverage, 4),
            "total_nodes_in_graph": len(self.graph.nodes),
            "total_edges_in_graph": len(self.graph.edges),
            "matched_nodes": found,
            "expected_nodes": len(expected_nodes),
        }
