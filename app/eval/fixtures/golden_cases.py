"""部件级黄金测试用例（§5.1.1 / §5.2），供 ComponentBench 加载。"""

from app.eval.kernel import TestCase

GOLDEN_CASES: dict[str, list[TestCase]] = {
    "tutor": [
        TestCase(name="解释完整性_base",
                 component="tutor",
                 input={"topic": "RAG", "action": "tutor_explain"},
                 expected={"explanation_completeness": 0.7},
                 meta={"source": "golden_v1", "rubric": "基础概念覆盖"}),
    ],
    "retriever": [
        TestCase(name="RAG检索_准确率",
                 component="retriever",
                 input={"query": "什么是RAG", "top_k": 5,
                        "golden_chunks": ["RAG = Retrieval Augmented Generation"],
                        "golden_answer": "RAG是检索增强生成技术"},
                 expected={"recall_at_k": 0.8, "faithfulness": 0.7,
                          "answer_relevancy": 0.6, "context_precision": 0.6},
                 meta={"source": "golden_v1"}),
    ],
    "critic": [
        TestCase(name="掌握度判定_准确",
                 component="critic",
                 input={"user_text": "RAG是检索增强生成",
                        "topic": "RAG"},
                 expected={"mastery_level": "partial"},
                 meta={"source": "golden_v1"}),
    ],
    "curator": [
        TestCase(name="图谱覆盖率",
                 component="curator",
                 input={"graph_nodes": {"RAG": 0.0, "retrieval": 0.0,
                                        "generation": 0.0}},
                 expected={"coverage": 1.0},
                 meta={"source": "golden_v1"}),
    ],
    "conductor": [
        TestCase(name="观察不足_请求补观察",
                 component="conductor",
                 input={"observations": [],
                        "current_mode": "Socratic"},
                 expected={"action": "request_observation",
                          "observation_enough": False},
                 meta={"source": "golden_v1"}),
    ],
}
