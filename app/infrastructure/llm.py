import json
import time
import logging
from dataclasses import dataclass

logger = logging.getLogger("study_agent")


@dataclass
class LLMConfig:
    """LLM 调用配置"""
    primary_model: str = "gpt-4o-mini"
    fallback_model: str = "gpt-4o-mini"
    api_key: str = ""
    base_url: str = ""
    max_retries: int = 2
    retry_delay: float = 1.0
    token_budget: int = 4096
    temperature: float = 0.7
    timeout: float = 30.0


class TokenBudgetExceeded(Exception):
    """Token 预算超限 — 当前作为软警告使用"""
    def __init__(self, budget: int, requested: int):
        self.budget = budget
        self.requested = requested
        super().__init__(f"Token 预算超限: 预算={budget}, 请求={requested}")


class FakeLLM:
    """测试替身"""

    RESPONSES = {
        "掌握度评估": '{"mastery_score": 65, "mastery_level": "partial", "mastery_rationale": "基本概念掌握，细节不足"}',
        "意图分类": '{"intent": "teach_loop", "confidence": 0.9}',
        "学习总结": "本次学习了二分查找的核心概念，掌握程度为中等。",
        "诊断": "用户对主题有基础了解，需要补充细节",
        "讲解": "知识点讲解内容...",
        "追问": "能否解释一下时间复杂度为什么是O(log n)？",
        "评估": "用户理解较为准确",
    }

    def __init__(self, responses: dict | None = None):
        self._responses = responses or self.RESPONSES.copy()
        self.call_history: list[dict] = []

    def invoke(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        for keyword, response in self._responses.items():
            if keyword in user_prompt:
                self.call_history.append({
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "response": response,
                    "kwargs": kwargs,
                })
                return response
        self.call_history.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "response": "默认测试回复",
            "kwargs": kwargs,
        })
        return "默认测试回复"

    def invoke_json(self, system_prompt: str, user_prompt: str, **kwargs) -> dict:
        return json.loads(self.invoke(system_prompt, user_prompt, **kwargs))

    def stream(self, system_prompt: str, user_prompt: str, **kwargs):
        response = self.invoke(system_prompt, user_prompt, **kwargs)
        for char in response:
            yield char

    def summarize_memories(self, memories: list[str]) -> str:
        return f"[摘要] 共{len(memories)}条记忆的压缩结果"

    def assert_called_with(self, keyword: str):
        for call in self.call_history:
            if keyword in call.get("user_prompt", ""):
                return
        raise AssertionError(f"未找到包含 '{keyword}' 的 LLM 调用")

    @property
    def call_count(self) -> int:
        return len(self.call_history)


class LLMService:
    """LLM 调用服务 — 连接复用 + 重试回退 + 可观测"""

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig()
        self._llm = None
        self._fallback_llm = None

    @property
    def llm(self):
        if self._llm is None:
            from langchain_openai import ChatOpenAI
            self._llm = ChatOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url or None,
                model=self.config.primary_model,
                temperature=self.config.temperature,
                max_tokens=self.config.token_budget,
                timeout=self.config.timeout,
            )
        return self._llm

    @property
    def fallback_llm(self):
        if self._fallback_llm is None:
            from langchain_openai import ChatOpenAI
            self._fallback_llm = ChatOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url or None,
                model=self.config.fallback_model,
                temperature=self.config.temperature,
                max_tokens=self.config.token_budget,
                timeout=self.config.timeout,
            )
        return self._fallback_llm

    def invoke(self, system_prompt: str, user_prompt: str,
               session_id: str = "", node: str = "", intent: str = "",
               **kwargs) -> str:
        last_error = None
        for attempt in range(self.config.max_retries + 1):
            try:
                return self._call_with_span(
                    self.llm, system_prompt, user_prompt,
                    session_id, node, intent,
                )
            except Exception as e:
                last_error = e
                logger.warning(f"LLM 调用失败(尝试{attempt+1}): {e}")
                if attempt < self.config.max_retries:
                    time.sleep(self.config.retry_delay * (2 ** attempt))

        if self.config.fallback_model != self.config.primary_model:
            logger.info(f"切换回退模型: {self.config.fallback_model}")
            try:
                return self._call_with_span(
                    self.fallback_llm, system_prompt, user_prompt,
                    session_id, node, intent,
                )
            except Exception as e:
                last_error = e

        raise last_error

    def invoke_json(self, system_prompt: str, user_prompt: str,
                    session_id: str = "", node: str = "", intent: str = "",
                    **kwargs) -> dict:
        text = self.invoke(system_prompt, user_prompt,
                           session_id, node, intent, **kwargs)
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()
        return json.loads(cleaned)

    def stream(self, system_prompt: str, user_prompt: str,
               session_id: str = "", node: str = "", intent: str = "",
               **kwargs):
        from langchain_core.messages import SystemMessage, HumanMessage
        from app.harness.observability import get_observability, LLMSpan
        obs = get_observability()
        start = time.monotonic()
        collected = []
        try:
            for chunk in self.llm.stream([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]):
                content = chunk.content
                collected.append(content)
                yield content
        finally:
            latency_ms = (time.monotonic() - start) * 1000
            obs.llm_span(LLMSpan(
                model=self.config.primary_model,
                completion_tokens=len("".join(collected)) // 4,
                latency_ms=latency_ms,
                node=node, intent=intent, session_id=session_id,
                metadata={"streaming": True},
            ))

    def summarize_memories(self, memories: list[str]) -> str:
        combined = "\n".join(f"- {m}" for m in memories)
        return self.invoke(
            "你是一个学习记忆整理助手。请将以下学习记录压缩为简洁摘要，保留关键知识点和掌握程度。",
            combined,
        )

    def _call_with_span(self, llm, system_prompt: str, user_prompt: str,
                         session_id: str, node: str, intent: str) -> str:
        from langchain_core.messages import SystemMessage, HumanMessage
        from app.harness.observability import get_observability, LLMSpan
        obs = get_observability()
        start = time.monotonic()
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        latency_ms = (time.monotonic() - start) * 1000
        usage = getattr(response, 'usage_metadata', None) or {}
        prompt_tokens = usage.get('input_tokens', 0)
        completion_tokens = usage.get('output_tokens', 0)
        total_tokens = prompt_tokens + completion_tokens
        if total_tokens > self.config.token_budget:
            logger.warning(f"Token 预算超限: {total_tokens} > {self.config.token_budget}")
        cost = self._calc_cost(llm.model_name, prompt_tokens, completion_tokens)
        obs.llm_span(LLMSpan(
            model=llm.model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            cost_usd=cost,
            node=node, intent=intent, session_id=session_id,
        ))
        return response.content

    @staticmethod
    def _calc_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
        PRICING = {
            "gpt-4o-mini": (0.15 / 1e6, 0.60 / 1e6),
            "gpt-4o":      (2.50 / 1e6, 10.00 / 1e6),
            "gpt-4-turbo": (10.00 / 1e6, 30.00 / 1e6),
        }
        input_price, output_price = PRICING.get(model, (0.0, 0.0))
        return prompt_tokens * input_price + completion_tokens * output_price
