"""Judge 适配层 —— 为评估框架提供 judge LLM（§5.1.1 不同族校验）

职责：
  - 构造 judge（llm + embeddings）用于 RAGAS/DeepEval
  - 校验 judge 与被评 Agent 不同族（anthropic ≠ openai）
  - 复用 OpenAI 配置（app/core/config.py:9-11）

设计要点：
  - 最简实现（Karpathy 准则）：直接返回 dict，不过度抽象
  - RAGAS 需要 llm + embeddings 两个对象
  - 同族返回 None（硬约束），失败返回 None（降级）
"""

from app.core.config import settings


def infer_family(model_name: str) -> str:
    """从模型名推断所属族。

    Args:
        model_name: 模型名称（如 "gpt-4o-mini", "claude-3-sonnet"）

    Returns:
        "openai" | "anthropic" | "unknown"
    """
    model_lower = model_name.lower()
    # 用词边界/前缀匹配，避免子串误判（如 "sol-v1" 含 "o1" 但非 OpenAI）
    # 特殊处理裸 "o1"（OpenAI 推理模型基础名）
    if model_lower == "o1" or any(model_lower.startswith(p) for p in ["gpt-", "o1-", "text-"]):
        return "openai"
    if "claude" in model_lower or "sonnet" in model_lower or "opus" in model_lower:
        return "anthropic"
    return "unknown"


def build_judge(target_agent_family: str) -> dict | None:
    """构造 judge 并校验不同族约束。

    Args:
        target_agent_family: 被评 Agent 的族（"openai" | "anthropic"）

    Returns:
        成功返回 {"llm": ..., "embeddings": ..., "family": "openai"}
        失败返回 None（同族 / 无 key / unknown 族）
    """
    # 1. 检查 OpenAI 配置是否可用
    if not settings.openai_api_key:
        return None

    # 2. 推断 judge 族（当前只有 OpenAI 配置）
    judge_family = infer_family(settings.openai_model)

    # 3. 不同族校验（§5.1.1 硬约束）
    if judge_family == target_agent_family:
        return None  # 同族，返回 None 触发降级
    if judge_family == "unknown":
        return None  # 保守策略：未知族不作为 judge

    # 4. 构造 llm + embeddings
    try:
        from langchain_openai import ChatOpenAI
        from app.infrastructure.rag.embedding import EmbeddingService

        llm = ChatOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or None,
            model=settings.openai_model,
            temperature=0.0,  # judge 需要稳定输出
            timeout=30,  # 避免 API 故障时无限挂起
        )

        embeddings = EmbeddingService().client

        return {
            "llm": llm,
            "embeddings": embeddings,
            "family": judge_family,
        }

    except Exception:
        return None  # 构造失败，降级
