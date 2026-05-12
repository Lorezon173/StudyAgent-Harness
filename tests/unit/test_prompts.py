from app.core.prompts import DIAGNOSE_SYSTEM, EXPLAIN_USER, INTENT_CLASSIFY_USER


def test_prompts_have_placeholders():
    assert "{topic}" in EXPLAIN_USER
    assert "{user_input}" in INTENT_CLASSIFY_USER


def test_diagnose_system_not_empty():
    assert len(DIAGNOSE_SYSTEM) > 0
