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


def test_socratic_prereq_observed_goes_regress():
    p = TeachingPolicy()
    target, action = p.next(_obs(prereq_weak=True, prereq_basis="observed"))
    assert target == TeachingMode.REGRESS
    assert action == ActionKind.REGRESS_TO_PREREQ


def test_socratic_prereq_historical_stays_socratic_with_probe():
    p = TeachingPolicy()
    target, action = p.next(_obs(prereq_weak=True, prereq_basis="historical"))
    assert target == TeachingMode.SOCRATIC
    assert action == ActionKind.TUTOR_PROBE_PREREQ


def test_feynman_mastered_returns_to_socratic():
    p = TeachingPolicy(initial=TeachingMode.FEYNMAN)
    target, action = p.next(_obs(mastery=MasteryLevel.MASTERED))
    assert target == TeachingMode.SOCRATIC


def test_feynman_confusion_goes_analogy():
    p = TeachingPolicy(initial=TeachingMode.FEYNMAN)
    target, action = p.next(_obs(confusion=True))
    assert target == TeachingMode.ANALOGY
    assert action == ActionKind.TUTOR_OFFER_ANALOGY


def test_feynman_prereq_observed_goes_regress():
    p = TeachingPolicy(initial=TeachingMode.FEYNMAN)
    target, action = p.next(_obs(prereq_weak=True, prereq_basis="observed"))
    assert target == TeachingMode.REGRESS


def test_feynman_weak_no_confusion_no_prereq_back_to_socratic():
    p = TeachingPolicy(initial=TeachingMode.FEYNMAN)
    target, action = p.next(_obs(mastery=MasteryLevel.WEAK))
    assert target == TeachingMode.SOCRATIC
    assert action == ActionKind.TUTOR_RE_EXPLAIN


def test_analogy_understood_returns_to_socratic():
    p = TeachingPolicy(initial=TeachingMode.ANALOGY)
    target, action = p.next(_obs(mastery=MasteryLevel.PARTIAL))
    assert target == TeachingMode.SOCRATIC


def test_analogy_still_weak_goes_regress():
    p = TeachingPolicy(initial=TeachingMode.ANALOGY)
    target, action = p.next(_obs(mastery=MasteryLevel.WEAK))
    assert target == TeachingMode.REGRESS


def test_regress_prereq_mastered_back_to_socratic():
    p = TeachingPolicy(initial=TeachingMode.REGRESS)
    target, action = p.next(_obs(mastery=MasteryLevel.MASTERED))
    assert target == TeachingMode.SOCRATIC


def test_regress_prereq_still_weak_self_loop():
    p = TeachingPolicy(initial=TeachingMode.REGRESS)
    target, action = p.next(_obs(prereq_weak=True, prereq_basis="observed"))
    assert target == TeachingMode.REGRESS


def test_turn_over_limit_triggers_loop_exit_in_any_mode():
    for m in TeachingMode:
        p = TeachingPolicy(initial=m)
        _, action = p.next(_obs(turn_over_limit=True))
        assert action == ActionKind.LOOP_EXIT, f"mode={m} 应触发 LoopExit"


def test_contradiction_triggers_tutor_correct_in_socratic():
    p = TeachingPolicy()
    _, action = p.next(_obs(contradiction=True))
    assert action == ActionKind.TUTOR_CORRECT


def test_priority_prereq_over_confusion_socratic():
    # §2.4 优先级裁决：前置缺失 (100) > 混淆 (80)
    p = TeachingPolicy()
    target, action = p.next(_obs(confusion=True, prereq_weak=True,
                                 prereq_basis="observed"))
    assert target == TeachingMode.REGRESS
    assert action == ActionKind.REGRESS_TO_PREREQ
