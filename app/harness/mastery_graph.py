import time
from dataclasses import dataclass, field
from enum import StrEnum

from app.infrastructure.storage.mastery_graph_store import MasteryGraphStore


class EdgeType(StrEnum):
    """图谱边类型（§6）。"""
    PREREQ = "PREREQ"
    RELATED = "RELATED"
    CONFLICT = "CONFLICT"


class EdgeSource(StrEnum):
    """图谱边来源（§6.1 冷启动建图）。"""
    DOC_ORDER = "DOC_ORDER"       # 教材章节顺序，confidence=0.5
    LLM_INFER = "LLM_INFER"       # LLM 推断，confidence=0.3
    INTERACTION = "INTERACTION"   # 实际交互验证，confidence=0.8


@dataclass
class MasteryNode:
    """知识点节点（§6）。"""
    topic_id: str
    topic_name: str = ""
    mastery: float = 0.0          # 0-100 掌握度（百分制）
    last_practiced_at: float = 0.0  # epoch seconds
    practice_count: int = 0
    confusion_with: list[str] = field(default_factory=list)
    rationale: str = ""           # 最近一次掌握度评分的依据（来自 Critic）


@dataclass
class MasteryEdge:
    """图谱边（§6）。"""
    from_topic: str
    to_topic: str
    type: EdgeType = EdgeType.PREREQ
    weight: float = 1.0
    confidence: float = 0.5       # 边的置信度（§6.1）
    source: EdgeSource = EdgeSource.LLM_INFER


class MasteryGraph:
    """用户级掌握点知识图谱引擎（§6）。

    核心能力：
    - add_node / add_edge：冷启动建图（DOC_ORDER / LLM_INFER）
    - update_mastery：从 Critic 的 MasteryAssessed 事件更新掌握度
    - find_weak_prereqs：基于 PREREQ 边 + 前置节点掌握度检测前置薄弱
    - load / save：与 MasteryGraphStore 交互持久化
    """

    def __init__(self, user_id: str, store):
        self.user_id = user_id
        self._store = store
        self.nodes: dict[str, MasteryNode] = {}
        self.edges: list[MasteryEdge] = []

    # ---- 图谱操作 ----

    def add_node(self, topic_id: str, topic_name: str = "",
                 mastery: float = 0.0) -> MasteryNode:
        node = MasteryNode(topic_id=topic_id, topic_name=topic_name, mastery=mastery)
        self.nodes[topic_id] = node
        return node

    def get_node(self, topic_id: str) -> MasteryNode | None:
        return self.nodes.get(topic_id)

    def add_edge(self, from_topic: str, to_topic: str,
                 edge_type: EdgeType = EdgeType.PREREQ,
                 weight: float = 1.0, confidence: float = 0.5,
                 source: EdgeSource = EdgeSource.LLM_INFER) -> MasteryEdge:
        edge = MasteryEdge(from_topic=from_topic, to_topic=to_topic,
                           type=edge_type, weight=weight,
                           confidence=confidence, source=source)
        self.edges.append(edge)
        return edge

    def update_mastery(self, topic_id: str, mastery: float,
                       rationale: str = "") -> MasteryNode | None:
        """更新掌握度（从 MasteryAssessed 触发）。自增 practice_count。"""
        node = self.nodes.get(topic_id)
        if node is None:
            return None
        node.mastery = max(0.0, min(100.0, mastery))
        if rationale:
            node.rationale = rationale
        node.last_practiced_at = time.time()
        node.practice_count += 1
        return node

    # ---- 冷启动建图（§6.1）----

    def add_doc_order_edge(self, from_topic: str, to_topic: str,
                           weight: float = 1.0) -> MasteryEdge:
        """从教材章节顺序添加 PREREQ 边（confidence=0.5）。"""
        return self.add_edge(from_topic=from_topic, to_topic=to_topic,
                             edge_type=EdgeType.PREREQ, weight=weight,
                             confidence=0.5, source=EdgeSource.DOC_ORDER)

    def add_llm_infer_edge(self, from_topic: str, to_topic: str,
                           weight: float = 1.0) -> MasteryEdge:
        """从 LLM 推断添加 PREREQ 边（confidence=0.3）。"""
        return self.add_edge(from_topic=from_topic, to_topic=to_topic,
                             edge_type=EdgeType.PREREQ, weight=weight,
                             confidence=0.3, source=EdgeSource.LLM_INFER)

    def strengthen_edge_by_interaction(self, from_topic: str,
                                        to_topic: str) -> MasteryEdge:
        """实际交互验证后强化边（升为 INTERACTION source，confidence=0.8）。

        若边不存在则新建一条高置信边。
        """
        for edge in self.edges:
            if (edge.from_topic == from_topic and edge.to_topic == to_topic
                    and edge.type == EdgeType.PREREQ):
                edge.source = EdgeSource.INTERACTION
                edge.confidence = 0.8
                return edge
        return self.add_edge(from_topic=from_topic, to_topic=to_topic,
                             edge_type=EdgeType.PREREQ,
                             confidence=0.8, source=EdgeSource.INTERACTION)

    # ---- 前置薄弱检测（§2.4）----

    def find_weak_prereqs(self, topic_id: str,
                          mastery_threshold: float = 50.0) -> list[dict]:
        """检测 topic_id 的前置薄弱节点。

        低置信边更严格：adjusted = mastery_threshold / (1 + (1-confidence)*0.5)
          confidence=0.8 → adjusted≈45.45（宽松）
          confidence=0.5 → adjusted=40（中等）
          confidence=0.3 → adjusted≈37.04（严格）
        前置节点 mastery < adjusted → 判为前置薄弱。
        """
        results = []
        for edge in self.edges:
            if edge.to_topic != topic_id or edge.type != EdgeType.PREREQ:
                continue
            prereq_node = self.nodes.get(edge.from_topic)
            if prereq_node is None:
                continue
            adjusted = mastery_threshold / (1.0 + (1.0 - edge.confidence) * 0.5)
            if prereq_node.mastery < adjusted:
                results.append({
                    "prereq_topic_id": edge.from_topic,
                    "prereq_name": prereq_node.topic_name,
                    "mastery": prereq_node.mastery,
                    "edge_confidence": edge.confidence,
                    "adjusted_threshold": round(adjusted, 4),
                    "edge_source": str(edge.source),
                })
        return results

    def has_any_prereqs(self, topic_id: str) -> bool:
        """检查 topic_id 是否在图谱中有 PREREQ 边（判断冷启动是否为空）。"""
        for edge in self.edges:
            if edge.to_topic == topic_id and edge.type == EdgeType.PREREQ:
                return True
        return False

    # ---- 持久化 ----

    async def save(self) -> None:
        nodes_data = [
            {"topic_id": n.topic_id, "topic_name": n.topic_name,
             "mastery": n.mastery, "last_practiced_at": n.last_practiced_at,
             "practice_count": n.practice_count,
             "confusion_with": n.confusion_with,
             "rationale": n.rationale}
            for n in self.nodes.values()
        ]
        await self._store.save_nodes(self.user_id, nodes_data)
        edges_data = [
            {"from_topic": e.from_topic, "to_topic": e.to_topic,
             "type": str(e.type), "weight": e.weight,
             "confidence": e.confidence, "source": str(e.source)}
            for e in self.edges
        ]
        await self._store.save_edges(self.user_id, edges_data)

    async def load(self) -> None:
        nodes_data = await self._store.load_nodes(self.user_id)
        for topic_id, n_data in nodes_data.items():
            self.nodes[topic_id] = MasteryNode(
                topic_id=n_data["topic_id"],
                topic_name=n_data["topic_name"],
                mastery=n_data["mastery"],
                last_practiced_at=n_data["last_practiced_at"],
                practice_count=n_data["practice_count"],
                confusion_with=n_data.get("confusion_with", []),
                rationale=n_data.get("rationale", ""),
            )
        edges_data = await self._store.load_edges(self.user_id)
        self.edges = [
            MasteryEdge(
                from_topic=e["from_topic"], to_topic=e["to_topic"],
                type=EdgeType(e["type"]), weight=e["weight"],
                confidence=e["confidence"], source=EdgeSource(e["source"]),
            )
            for e in edges_data
        ]
