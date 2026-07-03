"""黄金测试用例 v2（由 refine_testset.py 自动生成，κ = 0.14）"""

from app.eval.kernel import TestCase

RETRIEVER_CASES_V2: list[TestCase] = [
    TestCase(
        name="retriever_v2_001",
        component="retriever",
        input={"query": '什么是光合作用？'},
        expected={"faithfulness": 0.8, "answer_relevancy": 0.8},
        meta={"source": "ragas_generated", "kappa": 0.14,
               "consensus": 'relevant'},
    ),
]
