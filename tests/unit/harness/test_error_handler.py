from app.harness.error_handler import ErrorHandler, get_error_handler
from app.harness.enums import ErrorKind, RecoveryAction
from app.harness.state import LearningState


def test_rag_timeout():
    handler = ErrorHandler()
    state: LearningState = {"user_input": "", "meta": {"session_id": "t", "stage": "init", "branch_trace": []}}
    result = handler.handle(TimeoutError("RAG query timed out after 30s"), state)
    assert result["meta"]["error_kind"] == ErrorKind.RAG_TIMEOUT
    assert result["meta"]["recovery_action"] == RecoveryAction.RETRY


def test_rag_no_result():
    handler = ErrorHandler()
    state: LearningState = {"user_input": "", "meta": {"session_id": "t", "stage": "init", "branch_trace": []}}
    result = handler.handle(ValueError("no result found"), state)
    assert result["meta"]["error_kind"] == ErrorKind.RAG_NO_RESULT


def test_llm_rate_limit():
    handler = ErrorHandler()
    state: LearningState = {"user_input": "", "meta": {"session_id": "t", "stage": "init", "branch_trace": []}}
    result = handler.handle(Exception("429 rate limit exceeded"), state)
    assert result["meta"]["error_kind"] == ErrorKind.LLM_ERROR


def test_fatal():
    handler = ErrorHandler()
    state: LearningState = {"user_input": "", "meta": {"session_id": "t", "stage": "init", "branch_trace": []}}
    result = handler.handle(RuntimeError("unknown crash"), state)
    assert result["meta"]["error_kind"] == ErrorKind.FATAL
    assert result["meta"]["recovery_action"] == RecoveryAction.ABORT


def test_get_error_handler_singleton():
    h1 = get_error_handler()
    h2 = get_error_handler()
    assert h1 is h2
