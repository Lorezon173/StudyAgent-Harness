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
    """记忆作用域 — 5级"""
    WORKING = "working"
    EPISODE = "episode"
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


class EventType(StrEnum):
    """事件类型（§3.2）— 值即 §3.2 白名单中的事件名"""
    # 用户输入类
    USER_MESSAGE = "UserMessage"
    USER_UPLOADED = "UserUploaded"
    # Tutor 产出类
    TUTOR_ASKED = "TutorAsked"
    TUTOR_EXPLAINED = "TutorExplained"
    TUTOR_REQUESTED_RECAP = "TutorRequestedRecap"
    TUTOR_OFFERED_ANALOGY = "TutorOfferedAnalogy"
    # Retriever 产出类
    RETRIEVED_EVIDENCE = "RetrievedEvidence"
    RETRIEVAL_FAILED = "RetrievalFailed"
    # Critic 产出类
    MASTERY_ASSESSED = "MasteryAssessed"
    CONFUSION_DETECTED = "ConfusionDetected"
    CONTRADICTION_DETECTED = "ContradictionDetected"
    LOW_CONFIDENCE_DETECTED = "LowConfidenceDetected"
    RAG_QUALITY_ASSESSED = "RAGQualityAssessed"
    # Curator 产出类
    PROFILE_UPDATED = "ProfileUpdated"
    GRAPH_NODE_STRENGTHENED = "GraphNodeStrengthened"
    GRAPH_PREREQ_WEAK_DETECTED = "GraphPrereqWeakDetected"
    # 控制类
    TOPIC_ENTERED = "TopicEntered"
    LOOP_EXIT = "LoopExit"
    POLICY_TRANSITION = "PolicyTransition"
    ACTION_REQUESTED = "ActionRequested"
    CONDUCTOR_REQUESTED = "ConductorRequested"
    CONDUCTOR_DECIDED = "ConductorDecided"
    ORCHESTRATOR_TICK = "OrchestratorTick"


class EventSource(StrEnum):
    """事件来源身份（§3.1 source）— 七角色"""
    USER = "user"
    TUTOR = "tutor"
    RETRIEVER = "retriever"
    CRITIC = "critic"
    CURATOR = "curator"
    CONDUCTOR = "conductor"
    ORCHESTRATOR = "orchestrator"


class TeachingMode(StrEnum):
    """融合式教学四模式（§4.1）"""
    SOCRATIC = "Socratic"
    FEYNMAN = "Feynman"
    ANALOGY = "Analogy"
    REGRESS = "Regress"


class ActionKind(StrEnum):
    """Orchestrator 可下达的动作（§3.4）"""
    RETRIEVER_SEARCH = "retriever_search"
    RETRIEVER_EXPAND_QUERY = "retriever_expand_query"
    TUTOR_ASK = "tutor_ask"
    TUTOR_EXPLAIN = "tutor_explain"
    TUTOR_RE_EXPLAIN = "tutor_re_explain"
    TUTOR_REQUEST_RECAP = "tutor_request_recap"
    TUTOR_OFFER_ANALOGY = "tutor_offer_analogy"
    TUTOR_CORRECT = "tutor_correct"
    TUTOR_PROBE_PREREQ = "tutor_probe_prereq"
    REGRESS_TO_PREREQ = "regress_to_prereq"
    CONDUCTOR_DECIDE = "conductor_decide"
    REQUEST_OBSERVATION = "request_observation"
    LOOP_EXIT = "loop_exit"
