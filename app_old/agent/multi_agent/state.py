from typing import TypedDict
from app_old.harness.state import LearningState


class MultiAgentState(LearningState, total=False):
    agent_messages: list[dict]
    current_agent: str
    agent_trace: list[dict]
