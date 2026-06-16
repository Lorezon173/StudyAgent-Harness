"""渐进式 Prompt 加载器（§10 / agent-root.md 渐进式加载体系）。

compose(agent, intent) → 拼接：
  层级0 _root.prompt.md（全局规则）
  层级1 agents/<agent>.prompt.md（角色定义，含全部 intent 段落）
  层级2 该 agent spec 内 intent 对应的子段落（精确指令，追加到末尾高亮）

intent 段落以 `### <intent>` 标题分段；支持合并标题 `### a / b / c`
（多个相近 intent 共享一段），按 `/` 拆分逐一匹配。
"""

from functools import lru_cache
from pathlib import Path

_SPECS_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=32)
def _read_file(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


class SpecLoader:
    def __init__(self, specs_dir: Path | None = None):
        self._dir = specs_dir or _SPECS_DIR

    def compose(self, agent: str, intent: str) -> str:
        root = _read_file(self._dir / "_root.prompt.md")
        agent_spec = _read_file(self._dir / "agents" / f"{agent}.prompt.md")
        parts = [root]
        if agent_spec:
            parts.append(agent_spec)
        section = self._extract_section(agent_spec, intent)
        if section:
            parts.append(f"## 当前任务: {intent}\n\n{section}")
        return "\n\n---\n\n".join(p for p in parts if p.strip())

    @staticmethod
    def _extract_section(text: str, intent: str) -> str:
        """提取 `### <intent>` 段落；支持合并标题 `### a / b / c`。"""
        if not text or not intent:
            return ""
        lines = text.splitlines(keepends=True)
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped.startswith("### "):
                continue
            heading = stripped[len("### "):]
            tokens = [t.strip() for t in heading.split("/")]
            if intent not in tokens:
                continue
            body: list[str] = []
            for nxt in lines[i + 1 :]:
                if nxt.strip().startswith("### "):
                    break
                body.append(nxt)
            return "".join(body).strip()
        return ""
