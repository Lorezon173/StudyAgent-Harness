from app_old.harness.intent_router import IntentRouter
from app.harness.enums import Intent


def test_teach_loop_default():
    router = IntentRouter()
    result = router.route("我想学二分查找", None, [])
    assert result["intent"] == Intent.TEACH_LOOP
    assert result["intent_source"] == "fallback"


def test_qa_direct_rule():
    router = IntentRouter()
    result = router.route("二分查找是什么", None, [])
    assert result["intent"] == Intent.QA_DIRECT
    assert result["intent_source"] == "rule"
    assert result["intent_confidence"] >= 0.9


def test_review_rule():
    router = IntentRouter()
    result = router.route("帮我复习二分查找", None, [])
    assert result["intent"] == Intent.REVIEW


def test_replan_rule():
    router = IntentRouter()
    result = router.route("换个话题吧", None, [])
    assert result["intent"] == Intent.REPLAN
