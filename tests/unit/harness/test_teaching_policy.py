from app.harness.teaching_policy import TeachingPolicy, ObservationSet
from app.harness.enums import TeachingMode, ActionKind, MasteryLevel


def _obs(**kw) -> ObservationSet:
    return ObservationSet(**kw)


def test_policy_starts_in_socratic():
    p = TeachingPolicy()
    assert p.current_mode == TeachingMode.SOCRATIC
    assert p.history == [TeachingMode.SOCRATIC]


def test_socratic_mastered_topic_complete_exits():
    p = TeachingPolicy()
    target, action = p.next(_obs(mastery=MasteryLevel.MASTERED, topic_complete=True))
    assert action == ActionKind.LOOP_EXIT


def test_socratic_partial_transitions_to_feynman():
    p = TeachingPolicy()
    target, action = p.next(_obs(mastery=MasteryLevel.PARTIAL))
    assert target == TeachingMode.FEYNMAN
    assert action == ActionKind.TUTOR_REQUEST_RECAP


def test_socratic_weak_self_loop_within_repeat_limit():
    p = TeachingPolicy()
    target, action = p.next(_obs(mastery=MasteryLevel.WEAK, repeat_count=0))
    assert target == TeachingMode.SOCRATIC      # 自环
    assert action == ActionKind.TUTOR_RE_EXPLAIN


def test_socratic_confusion_transitions_to_analogy():
    p = TeachingPolicy()
    target, action = p.next(_obs(confusion=True))
    assert target == TeachingMode.ANALOGY
    assert action == ActionKind.TUTOR_OFFER_ANALOGY


def test_history_records_each_transition():
    p = TeachingPolicy()
    p.next(_obs(mastery=MasteryLevel.PARTIAL))   # → Feynman
    assert p.current_mode == TeachingMode.FEYNMAN
    assert p.history == [TeachingMode.SOCRATIC, TeachingMode.FEYNMAN]
