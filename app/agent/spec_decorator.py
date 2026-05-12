"""@with_spec 装饰器：声明节点的规范来源，自动注入 system_prompt"""

from functools import wraps
from app.agent.spec_loader import SpecLoader
from app.harness.state import LearningState


_default_loader: SpecLoader | None = None


def get_spec_loader() -> SpecLoader:
    global _default_loader
    if _default_loader is None:
        _default_loader = SpecLoader.default()
    return _default_loader


def set_spec_loader(loader: SpecLoader):
    """依赖注入入口：替换全局 SpecLoader 实例（主要用于测试）"""
    global _default_loader
    _default_loader = loader


def with_spec(intent: str, node: str):
    """声明节点的规范来源，自动从意图地图加载并注入 system_prompt

    用法：
        @with_spec(intent="teach_loop", node="diagnose")
        def diagnose_node(state: LearningState) -> dict:
            system_prompt = state["_system_prompt"]
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(state: LearningState) -> dict:
            loader = get_spec_loader()
            current_intent = state.get("routing", {}).get("intent", intent)
            system_prompt = loader.compose(current_intent, node)
            enriched_state = {**state, "_system_prompt": system_prompt}
            return func(enriched_state)
        wrapper._spec_intent = intent
        wrapper._spec_node = node
        return wrapper
    return decorator
