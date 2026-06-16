"""黄金轨迹 —— 人工标注的参考事件序列（§5.1.1 / #21）。

每条轨迹 = (scenario, events, expected_assessments)。
events 是期望的理想事件序列，expected_assessments 是逐场景的期望评估。
冻结后只增不改，改则升版本。
"""

GOLDEN_VERSION = "v1.0"

GOLDEN_TRACE_ZERO_RAG = {
    "scenario": "零基础学习RAG",
    "user_profile": {"type": "blank"},
    "topic": "RAG",
    "expected_mode_path": ["Socratic", "Feynman", "Analogy"],
    "events": [
        {"type": "TopicEntered", "source": "orchestrator",
         "payload": {"topic": "RAG"}},
        {"type": "ActionRequested", "source": "orchestrator",
         "payload": {"action": "tutor_ask", "target": "tutor"}},
        {"type": "TutorAsked", "source": "tutor",
         "payload": {"content": "什么是RAG?"}},
        {"type": "UserMessage", "source": "user",
         "payload": {"text": "RAG是检索增强生成"}},
        {"type": "MasteryAssessed", "source": "critic",
         "payload": {"level": "partial", "score": 60}},
    ],
    "expected_assessments": {
        "mastery_reached": "mastered",
        "max_turns": 12,
        "must_contain_events": ["TutorExplained", "RetrievedEvidence"],
        "must_not_contain_events": ["ConductorRequested"],
    },
}

GOLDEN_TRACES = {
    "zero_rag": GOLDEN_TRACE_ZERO_RAG,
}
