from app.harness.enums import (
    Stage, Intent, GateStatus, MasteryLevel,
    ErrorKind, RecoveryAction, RetrievalMode,
    MemoryScope, AgentRole, EvalMetric,
)


def test_stage_values():
    assert Stage.INIT == "init"
    assert Stage.ROUTING == "routing"
    assert Stage.COMPLETE == "complete"


def test_intent_values():
    assert Intent.TEACH_LOOP == "teach_loop"
    assert Intent.QA_DIRECT == "qa_direct"
    assert Intent.REVIEW == "review"
    assert Intent.REPLAN == "replan"


def test_enum_is_string():
    assert isinstance(Stage.INIT, str)
    assert isinstance(Intent.TEACH_LOOP, str)


def test_agent_role_values():
    assert AgentRole.TEACHING == "teaching"
    assert AgentRole.EVAL == "eval"


def test_eval_metric_values():
    assert EvalMetric.FAITHFULNESS == "faithfulness"
    assert EvalMetric.RELEVANCY == "relevancy"
