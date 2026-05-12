import copy
import uuid
from app.harness.state import LearningState


class StateManager:
    def __init__(self):
        self._snapshots: dict[str, LearningState] = {}

    def transition(self, state: LearningState, updates: dict) -> LearningState:
        result = copy.deepcopy(state)
        for key, value in updates.items():
            if key in ("user_input",):
                result[key] = value
            elif isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key].update(value)
            else:
                result[key] = value

        if "meta" in updates and "stage" in updates.get("meta", {}):
            old_stage = state.get("meta", {}).get("stage", "")
            new_stage = updates["meta"]["stage"]
            if old_stage != new_stage:
                trace = result.get("meta", {}).get("branch_trace", [])
                trace.append({"from": old_stage, "to": new_stage})
                result["meta"]["branch_trace"] = trace
        return result

    def snapshot(self, state: LearningState) -> str:
        sid = str(uuid.uuid4())
        self._snapshots[sid] = copy.deepcopy(state)
        return sid

    def restore(self, snapshot_id: str) -> LearningState:
        return copy.deepcopy(self._snapshots[snapshot_id])
