"""渐进式规范加载器：Agent 初始化 → 查意图地图 → 按需加载"""

import yaml
from pathlib import Path


class SpecLoader:
    """渐进式规范加载器

    实例化时注入 spec_dir，支持依赖注入和测试替换。
    三层加载：root(始终) → agent(路由后) → node(执行时)
    组装时用 XML 标签分隔各层级，缓存原始文件内容。
    """

    def __init__(self, spec_dir: Path | str):
        self.spec_dir = Path(spec_dir)
        self._file_cache: dict[str, str] = {}
        self._intent_map: dict | None = None

    # ── 层级0：根规范（始终加载）──

    def load_root(self) -> str:
        return self._read_prompt(self.spec_dir / "_root.prompt.md")

    # ── 层级1：Agent 规范（路由后加载）──

    def load_agent(self, agent_name: str) -> str:
        return self._read_prompt(self.spec_dir / "agents" / f"{agent_name}.prompt.md")

    # ── 层级2：节点 Prompt（执行时加载）──

    def load_node(self, prompt_name: str) -> str:
        return self._read_prompt(self.spec_dir / "prompts" / f"{prompt_name}.prompt.md")

    # ── 意图地图查询 ──

    def intent_map(self) -> dict:
        if self._intent_map is None:
            with open(self.spec_dir / "intent_map.yaml", encoding="utf-8") as f:
                self._intent_map = yaml.safe_load(f)
        return self._intent_map

    def lookup(self, intent: str, node_name: str) -> dict:
        """查询意图地图：给定意图和当前节点，返回需要加载的资源"""
        branch = self.intent_map().get(intent, {})
        flow = branch.get("flow", {})
        node_info = flow.get(node_name, {})
        return {
            "agent": branch.get("agent"),
            "needs": node_info.get("needs", []),
        }

    # ── 组装完整 system prompt（XML 标签分隔）──

    def compose(self, intent: str, node_name: str) -> str:
        """层级0 + 层级1 + 层级2 渐进组装，XML 标签分隔"""
        info = self.lookup(intent, node_name)
        parts = [self.load_root()]

        if info["agent"]:
            parts.append(self.load_agent(info["agent"]))

        for need in info["needs"]:
            # need 格式: "prompts/diagnose" → 加载 prompts/diagnose.prompt.md
            prompt_name = need.split("/")[-1]
            parts.append(self.load_node(prompt_name))

        return "\n\n".join(parts)

    # ── 内部工具 ──

    def _read_prompt(self, path: Path) -> str:
        """读取 .prompt.md 文件，带缓存"""
        key = str(path)
        if key not in self._file_cache:
            self._file_cache[key] = path.read_text(encoding="utf-8").strip()
        return self._file_cache[key]

    def clear_cache(self):
        self._file_cache.clear()
        self._intent_map = None

    @classmethod
    def default(cls) -> "SpecLoader":
        """创建默认实例，使用项目标准 spec 目录"""
        return cls(Path(__file__).parent / "specs")
