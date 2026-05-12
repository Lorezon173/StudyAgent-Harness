from app.harness.enums import EvalMetric


class TeachingEval:
    """教学评估：计算教学质量的各项指标"""

    def evaluate_teaching(self, state: dict) -> dict:
        mastery_score = state.get("evaluation", {}).get("mastery_score", 0)
        explanation = state.get("teaching", {}).get("explanation", "")
        return {
            "explanation_length": len(explanation),
            "mastery_score": mastery_score,
            "teaching_quality": "high" if mastery_score >= 70 else "medium" if mastery_score >= 40 else "low",
        }
