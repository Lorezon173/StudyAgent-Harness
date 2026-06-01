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


from app.harness.enums import EventType, EventSource, TeachingMode, ActionKind


def test_event_type_covers_whitelist():
    # §3.2 五类产出 + 控制类，逐一存在
    assert EventType.USER_MESSAGE == "UserMessage"
    assert EventType.TUTOR_ASKED == "TutorAsked"
    assert EventType.RETRIEVED_EVIDENCE == "RetrievedEvidence"
    assert EventType.MASTERY_ASSESSED == "MasteryAssessed"
    assert EventType.GRAPH_PREREQ_WEAK_DETECTED == "GraphPrereqWeakDetected"
    assert EventType.TOPIC_ENTERED == "TopicEntered"
    assert EventType.ORCHESTRATOR_TICK == "OrchestratorTick"
    assert EventType.CONDUCTOR_DECIDED == "ConductorDecided"


def test_event_source_seven_roles():
    # §3.1 source 七角色（含 orchestrator）
    roles = {s.value for s in EventSource}
    assert roles == {"user", "tutor", "retriever", "critic",
                     "curator", "conductor", "orchestrator"}


def test_teaching_mode_four():
    assert {m.value for m in TeachingMode} == {"Socratic", "Feynman", "Analogy", "Regress"}


def test_action_kind_has_probe_prereq():
    # §3.4 新增动作
    assert ActionKind.TUTOR_PROBE_PREREQ == "tutor_probe_prereq"
    assert ActionKind.REGRESS_TO_PREREQ == "regress_to_prereq"
    assert ActionKind.REQUEST_OBSERVATION == "request_observation"
