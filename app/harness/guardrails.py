from dataclasses import dataclass


@dataclass
class GuardResult:
    passed: bool
    reason: str | None = None
    corrected: str | None = None


class Guardrails:
    MAX_INPUT_LENGTH = 10000
    INJECTION_PATTERNS = ("ignore previous", "disregard", "system prompt")

    def check_input(self, user_input: str) -> GuardResult:
        if len(user_input) > self.MAX_INPUT_LENGTH:
            return GuardResult(False, reason="输入超过长度上限", corrected=user_input[:self.MAX_INPUT_LENGTH])
        lower = user_input.lower()
        for pattern in self.INJECTION_PATTERNS:
            if pattern in lower:
                return GuardResult(False, reason=f"检测到潜在注入: {pattern}")
        return GuardResult(True)

    def check_tool_result(self, tool_name: str, result) -> GuardResult:
        if result is None or (hasattr(result, 'success') and not result.success):
            return GuardResult(False, reason=f"工具 {tool_name} 执行失败")
        return GuardResult(True)

    def check_output(self, reply: str, citations: list[dict]) -> GuardResult:
        if not citations and reply:
            corrected = reply + "\n\n[注：以上回答未基于检索到的引用，请谨慎参考。]"
            return GuardResult(True, corrected=corrected)
        return GuardResult(True)
