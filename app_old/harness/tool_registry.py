from dataclasses import dataclass, field
from typing import Any, Callable

from app.harness.state import LearningState


@dataclass
class ToolSchema:
    name: str
    description: str
    parameters: dict
    returns: dict
    timeout: float = 30.0
    risky: bool = False


@dataclass
class ToolResult:
    success: bool
    output: Any
    error: str | None = None
    metadata: dict | None = None


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, tuple[ToolSchema, Callable]] = {}

    def register(self, schema: ToolSchema, executor: Callable):
        self._tools[schema.name] = (schema, executor)

    def select(self, user_input: str, state: LearningState) -> list[str]:
        intent = state.get("routing", {}).get("intent", "")
        selected = []
        for name, (schema, _) in self._tools.items():
            keywords = schema.description.split()
            if any(k in user_input for k in keywords) or intent in ("teach_loop", "qa_direct"):
                selected.append(name)
        return selected[:3]

    def execute(self, tool_name: str, params: dict) -> ToolResult:
        if tool_name not in self._tools:
            return ToolResult(success=False, output=None, error=f"工具未注册: {tool_name}")
        schema, executor = self._tools[tool_name]
        try:
            result = executor(params)
            return ToolResult(success=True, output=result)
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())
