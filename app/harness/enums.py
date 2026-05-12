from enum import StrEnum


class Stage(StrEnum):
    """节点执行阶段"""
    INIT = "init"
    ROUTING = "routing"
    HISTORY_CHECK = "history_check"
    KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"
    RETRIEVING = "retrieving"
    DIAGNOSING = "diagnosing"
    EXPLAINING = "explaining"
    RESTATE_CHECK = "restate_check"
    FOLLOWUP = "followup"
    EVALUATE = "evaluate"
    SUMMARIZE = "summarize"
    RECOVERING = "recovering"
    COMPLETE = "complete"


class Intent(StrEnum):
    """用户意图分类"""
    TEACH_LOOP = "teach_loop"
    QA_DIRECT = "qa_direct"
    REVIEW = "review"
    REPLAN = "replan"


class GateStatus(StrEnum):
    """证据守门状态"""
    PASS = "pass"
    SUPPLEMENT = "supplement"
    REJECT = "reject"


class MasteryLevel(StrEnum):
    """掌握度等级"""
    WEAK = "weak"
    PARTIAL = "partial"
    MASTERED = "mastered"


class ErrorKind(StrEnum):
    """错误分类"""
    RAG_TIMEOUT = "rag_timeout"
    RAG_NO_RESULT = "rag_no_result"
    LLM_ERROR = "llm_error"
    TOOL_ERROR = "tool_error"
    INPUT_INVALID = "input_invalid"
    FATAL = "fatal"


class RecoveryAction(StrEnum):
    """恢复策略"""
    RETRY = "retry"
    FALLBACK_LLM = "fallback_llm"
    SKIP_RETRIEVAL = "skip_retrieval"
    ABORT = "abort"


class RetrievalMode(StrEnum):
    """检索模式"""
    FACT = "fact"
    FRESHNESS = "freshness"
    COMPARISON = "comparison"


class MemoryScope(StrEnum):
    """记忆作用域"""
    WORKING = "working"
    SESSION = "session"
    USER = "user"
    GLOBAL = "global"


class AgentRole(StrEnum):
    """Multi-Agent 角色标识"""
    TEACHING = "teaching"
    EVAL = "eval"
    RETRIEVAL = "retrieval"
    ORCHESTRATOR = "orchestrator"


class EvalMetric(StrEnum):
    """ragas 评估指标"""
    FAITHFULNESS = "faithfulness"
    RELEVANCY = "relevancy"
    CONTEXT_PRECISION = "context_precision"
    CONTEXT_RECALL = "context_recall"
