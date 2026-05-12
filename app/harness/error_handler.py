from app.harness.enums import ErrorKind, RecoveryAction
from app.harness.state import LearningState


class ErrorHandler:
    def handle(self, error: Exception, state: LearningState) -> dict:
        msg = str(error).lower()
        error_kind = self._classify(msg)
        recovery = self._recovery(error_kind)
        return {
            "meta": {
                "error_kind": error_kind,
                "error_detail": str(error),
                "recovery_action": recovery,
                "fallback_used": False,
            }
        }

    def _classify(self, msg: str) -> str:
        if "timeout" in msg or "timed out" in msg:
            return ErrorKind.RAG_TIMEOUT
        if "no result" in msg or "empty" in msg:
            return ErrorKind.RAG_NO_RESULT
        if "rate" in msg or "429" in msg:
            return ErrorKind.LLM_ERROR
        if "tool" in msg:
            return ErrorKind.TOOL_ERROR
        if "input" in msg and "invalid" in msg:
            return ErrorKind.INPUT_INVALID
        return ErrorKind.FATAL

    def _recovery(self, kind: str) -> str:
        mapping = {
            ErrorKind.RAG_TIMEOUT: RecoveryAction.RETRY,
            ErrorKind.RAG_NO_RESULT: RecoveryAction.FALLBACK_LLM,
            ErrorKind.LLM_ERROR: RecoveryAction.SKIP_RETRIEVAL,
            ErrorKind.TOOL_ERROR: RecoveryAction.FALLBACK_LLM,
            ErrorKind.INPUT_INVALID: RecoveryAction.ABORT,
            ErrorKind.FATAL: RecoveryAction.ABORT,
        }
        return mapping.get(kind, RecoveryAction.ABORT)


_instance: ErrorHandler | None = None


def get_error_handler() -> ErrorHandler:
    global _instance
    if _instance is None:
        _instance = ErrorHandler()
    return _instance
