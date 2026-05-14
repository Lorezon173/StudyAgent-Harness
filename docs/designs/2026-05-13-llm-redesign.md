# LLM 调用层重写 — 三层设计文档

> 日期：2026-05-13
> 方案：方案B — 核心一次性重写（Observability + Memory + LLM 联动）
> 优先级：第三阶段（可观测 + 记忆之后）
> 设计来源：brainstorming 产出的完整规划，后续 spec 编写以此为据

---

## 第一层：总览

```
目标：将 LLMService 从每次新建实例 + 无重试 + 无流式，
      升级为连接池复用 + 流式支持 + 重试/回退 + token 预算。

改动范围：
  - 重写 app/infrastructure/llm.py
  - 修改 app/agent/nodes/*.py（7个节点，统一传入 session_id/node/intent）
  - 新增 tests/unit/infrastructure/test_llm.py（重写）

联动：
  - 可观测系统：LLMService.invoke 自动写入 llm_span
  - 记忆系统：LLMService.summarize_memories 供 LongTermStore 调用

不动：
  - FakeLLM 保持接口兼容，内部实现增强
  - specs/ 规范文件
```

## 第二层：概述

```
┌───────────────────────────────────────────────┐
│              LLMService (门面)                 │
│  invoke() / invoke_json() / stream()          │
│  自动：重试 → 回退 → token 计数 → llm_span    │
├───────────────────────────────────────────────┤
│  LLMConfig                                    │
│  ┌─────────────────────────────────────────┐  │
│  │ primary_model: str      主模型          │  │
│  │ fallback_model: str     回退模型        │  │
│  │ max_retries: int        最大重试次数    │  │
│  │ retry_delay: float      重试间隔(秒)    │  │
│  │ token_budget: int       单次 token 上限 │  │
│  │ temperature: float      温度            │  │
│  └─────────────────────────────────────────┘  │
├───────────────────────────────────────────────┤
│  FakeLLM (测试)                               │
│  - 可配置响应映射                              │
│  - 记录调用历史供断言                          │
│  - 模拟 token 用量                             │
└───────────────────────────────────────────────┘
```

| 组件 | 职责 | 输入 | 输出 |
|------|------|------|------|
| `LLMConfig` | 封装所有 LLM 配置 | 环境变量 / 构造参数 | 配置对象 |
| `LLMService` | 门面：调用+重试+回退+追踪 | prompt + 上下文 | response + span |
| `FakeLLM` | 测试替身 | 可配置响应 | 预设回复 + 调用记录 |
| `TokenBudgetExceeded` | 预算超限异常 | — | — |

## 第三层：详细实施计划

### 3.1 LLMConfig 数据类

```python
# app/infrastructure/llm.py

from dataclasses import dataclass

@dataclass
class LLMConfig:
    """LLM 调用配置"""
    primary_model: str = "gpt-4o-mini"
    fallback_model: str = "gpt-4o-mini"
    api_key: str = ""
    base_url: str = ""
    max_retries: int = 2
    retry_delay: float = 1.0                # 首次重试间隔，指数退避
    token_budget: int = 4096                # 单次调用 token 上限
    temperature: float = 0.7
    timeout: float = 30.0                   # 单次请求超时(秒)
```

### 3.2 TokenBudgetExceeded 异常

```python
class TokenBudgetExceeded(Exception):
    """Token 预算超限 — 当前作为软警告使用（仅 log.warning），
    不中断调用。如需硬限制，在 _call_with_span 中改为 raise 此异常。"""
    def __init__(self, budget: int, requested: int):
        self.budget = budget
        self.requested = requested
        super().__init__(
            f"Token 预算超限: 预算={budget}, 请求={requested}"
        )
```

### 3.3 LLMService 重写

```python
import json
import time
import logging
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.harness.observability import get_observability, LLMSpan

logger = logging.getLogger("learning_agent")

class LLMService:
    """LLM 调用服务 — 连接复用 + 重试回退 + 可观测"""

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig()
        self._llm: ChatOpenAI | None = None
        self._fallback_llm: ChatOpenAI | None = None

    # ── 连接复用 ──

    @property
    def llm(self) -> ChatOpenAI:
        """懒初始化 + 缓存 ChatOpenAI 实例"""
        if self._llm is None:
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
    def fallback_llm(self) -> ChatOpenAI:
        if self._fallback_llm is None:
            self._fallback_llm = ChatOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url or None,
                model=self.config.fallback_model,
                temperature=self.config.temperature,
                max_tokens=self.config.token_budget,
                timeout=self.config.timeout,
            )
        return self._fallback_llm

    # ── 核心调用 ──

    def invoke(self, system_prompt: str, user_prompt: str,
               session_id: str = "", node: str = "", intent: str = "",
               **kwargs) -> str:
        """带重试+回退+追踪的 LLM 调用"""
        last_error = None
        # 主模型重试
        for attempt in range(self.config.max_retries + 1):
            try:
                return self._call_with_span(
                    self.llm, system_prompt, user_prompt,
                    session_id, node, intent,
                )
            except Exception as e:
                last_error = e
                logger.warning(
                    f"LLM 调用失败(尝试{attempt+1}/{self.config.max_retries+1}): {e}"
                )
                if attempt < self.config.max_retries:
                    delay = self.config.retry_delay * (2 ** attempt)
                    time.sleep(delay)

        # 回退模型
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
        """调用 LLM 并解析 JSON 响应"""
        text = self.invoke(system_prompt, user_prompt,
                           session_id, node, intent, **kwargs)
        # 清理 markdown 代码块包裹
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()
        return json.loads(cleaned)

    def stream(self, system_prompt: str, user_prompt: str,
               session_id: str = "", node: str = "", intent: str = "",
               **kwargs):
        """流式调用 — 返回生成器。
        限制：stream 仅使用主模型，无重试/回退机制。
        如需高可靠性流式，需在外部自行处理重试。
        """
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
            full_response = "".join(collected)
            estimated_tokens = len(full_response) // 4
            obs.llm_span(LLMSpan(
                model=self.config.primary_model,
                completion_tokens=estimated_tokens,
                latency_ms=latency_ms,
                node=node,
                intent=intent,
                session_id=session_id,
                metadata={"streaming": True},
            ))

    def summarize_memories(self, memories: list[str]) -> str:
        """压缩多条记忆为摘要"""
        combined = "\n".join(f"- {m}" for m in memories)
        return self.invoke(
            "你是一个学习记忆整理助手。请将以下学习记录压缩为简洁摘要，"
            "保留关键知识点和掌握程度。",
            combined,
        )

    # ── 内部 ──

    def _call_with_span(self, llm: ChatOpenAI, system_prompt: str,
                         user_prompt: str, session_id: str, node: str,
                         intent: str) -> str:
        """单次调用 + 可观测追踪"""
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
            logger.warning(
                f"Token 预算超限: {total_tokens} > {self.config.token_budget}"
            )

        cost = self._calc_cost(llm.model_name, prompt_tokens, completion_tokens)

        obs.llm_span(LLMSpan(
            model=llm.model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            cost_usd=cost,
            node=node,
            intent=intent,
            session_id=session_id,
        ))

        return response.content

    @staticmethod
    def _calc_cost(model: str, prompt_tokens: int,
                   completion_tokens: int) -> float:
        PRICING = {
            "gpt-4o-mini": (0.15 / 1e6, 0.60 / 1e6),
            "gpt-4o":      (2.50 / 1e6, 10.00 / 1e6),
            "gpt-4-turbo": (10.00 / 1e6, 30.00 / 1e6),
        }
        input_price, output_price = PRICING.get(model, (0.0, 0.0))
        return prompt_tokens * input_price + completion_tokens * output_price
```

### 3.4 FakeLLM 重写

```python
class FakeLLM:
    """测试替身 — 可配置响应 + 调用记录 + 模拟 token"""

    RESPONSES = {
        "掌握度评估": '{"mastery_score": 65, "mastery_level": "partial", "mastery_rationale": "基本概念掌握，细节不足"}',
        "意图分类": '{"intent": "teach_loop", "confidence": 0.9}',
        "学习总结": "本次学习了二分查找的核心概念，掌握程度为中等。",
        "诊断": "用户对主题有基础了解，需要补充细节",
        "讲解": "知识点讲解内容...",
        "追问": "能否解释一下时间复杂度为什么是O(log n)？",
        "评估": "用户理解较为准确",
    }

    def __init__(self, responses: dict | None = None,
                 token_per_char: float = 0.25):
        self._responses = responses or self.RESPONSES.copy()
        self._token_per_char = token_per_char
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

    def estimate_tokens(self, text: str) -> int:
        return int(len(text) * self._token_per_char)

    def assert_called_with(self, keyword: str):
        """断言包含某关键词的调用发生过"""
        for call in self.call_history:
            if keyword in call.get("user_prompt", ""):
                return
        raise AssertionError(f"未找到包含 '{keyword}' 的 LLM 调用")

    @property
    def call_count(self) -> int:
        return len(self.call_history)
```

### 3.5 节点改造要点

7 个节点文件的改造模式一致：调用时传入 `session_id` / `node` / `intent`。

改造前（以 diagnose.py 为例）：
```python
_llm = FakeLLM()

@with_spec(intent="teach_loop", node="diagnose")
def diagnose_node(state: LearningState) -> dict:
    result = _llm.invoke(system_prompt, f"主题：{topic}\n用户：{user_input}")
    return {"teaching": {"diagnosis": result}}
```

改造后：
```python
_llm = FakeLLM()  # 默认测试用，生产环境由 DI 替换

@with_spec(intent="teach_loop", node="diagnose")
def diagnose_node(state: LearningState) -> dict:
    system_prompt = state["_system_prompt"]
    topic = state.get("memory", {}).get("topic", "")
    user_input = state["user_input"]
    session_id = state.get("meta", {}).get("session_id", "")
    result = _llm.invoke(
        system_prompt,
        f"主题：{topic}\n用户：{user_input}",
        session_id=session_id,
        node="diagnose",
        intent="teach_loop",
    )
    return {"teaching": {"diagnosis": result}}
```

需要改造的 7 个节点：diagnose / explain / followup / restate_check / evaluate / summarize / answer_policy

### 3.6 测试计划

| 测试文件 | 覆盖内容 | 用例数 |
|----------|----------|--------|
| `test_llm.py` | LLMConfig 默认值 | 2 |
| `test_llm.py` | LLMService 连接复用（懒初始化） | 2 |
| `test_llm.py` | LLMService 重试机制（模拟失败） | 3 |
| `test_llm.py` | LLMService 回退模型切换 | 2 |
| `test_llm.py` | LLMService invoke_json 清理 markdown | 2 |
| `test_llm.py` | LLMService stream 生成器 | 2 |
| `test_llm.py` | _calc_cost 各模型定价 | 3 |
| `test_llm.py` | FakeLLM 调用记录 + 断言 | 3 |
| `test_llm.py` | FakeLLM stream | 1 |
| `test_llm.py` | TokenBudgetExceeded 异常 | 1 |

合计：21 个测试用例
