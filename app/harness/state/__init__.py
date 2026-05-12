from typing import TypedDict
from .routing import RoutingState
from .teaching import TeachingState
from .retrieval import RetrievalState
from .evaluation import EvalState
from .memory import MemoryState
from .meta import MetaState


class LearningState(TypedDict, total=False):
    """学习 Agent 总状态 — 所有图节点共享"""
    user_input: str

    routing: RoutingState
    teaching: TeachingState
    retrieval: RetrievalState
    evaluation: EvalState
    memory: MemoryState
    meta: MetaState
