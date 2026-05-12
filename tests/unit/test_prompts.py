from app.core.prompts import DIAGNOSE_USER, EXPLAIN_USER, INTENT_CLASSIFY_USER


def test_user_prompts_have_placeholders():
    assert "{topic}" in EXPLAIN_USER
    assert "{user_input}" in INTENT_CLASSIFY_USER


def test_diagnose_user_template():
    assert "{topic}" in DIAGNOSE_USER
    assert "{user_input}" in DIAGNOSE_USER
