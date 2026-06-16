from app.harness.enums import AgentRole, Intent
from app_old.agent.multi_agent.state import MultiAgentState


def route_to_agent(state: MultiAgentState) -> str:
    intent = state.get("routing", {}).get("intent", Intent.TEACH_LOOP)
    return {
        Intent.TEACH_LOOP: AgentRole.TEACHING,
        Intent.REVIEW: AgentRole.EVAL,
    }.get(intent, AgentRole.TEACHING)
