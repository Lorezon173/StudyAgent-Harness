from dataclasses import dataclass, field
from typing import Any


@dataclass
class TestCase:
    """部件级评估的单个测试用例（§5.2）。

    name:       测试用例名称
    component:  被测部件标识（tutor|retriever|critic|curator|conductor）
    input:      输入参数（传给 Agent.evaluate()）
    expected:   期望的指标值
    meta:       元信息（来源、版本、标注者等）
    """
    name: str
    component: str
    input: dict = field(default_factory=dict)
    expected: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)


@dataclass
class EvalResult:
    """单个测试用例的评估结果。"""
    test_name: str
    component: str
    passed: bool
    metrics: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


@dataclass
class ScenarioDefinition:
    """系统级场景定义（§5.3）。

    script:    模拟用户的多轮回复
    expected:  结果断言 + 过程断言（§5.3 格式 + §5.4 轨迹偏离）
    meta:      场景元信息
    """
    name: str
    user_profile: dict = field(default_factory=dict)
    topic: str = ""
    script: list[dict] = field(default_factory=list)
    expected: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)
