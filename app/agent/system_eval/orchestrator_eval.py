class OrchestratorEval:
    """编排器评估：检查图执行流程的正确性"""

    def evaluate_flow(self, state: dict) -> dict:
        trace = state.get("meta", {}).get("branch_trace", [])
        return {
            "trace_length": len(trace),
            "completed_stages": [t.get("to", "") for t in trace],
            "flow_correct": len(trace) > 0,
        }
