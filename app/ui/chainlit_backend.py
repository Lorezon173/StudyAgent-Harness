"""Chainlit 后端桥接（可选依赖）"""


class ChainlitBackend:
    """将 Chainlit 消息桥接到 LangGraph"""

    def __init__(self):
        self._graph = None

    async def process_message(self, user_input: str, session_id: str) -> str:
        return "Chainlit 后端暂未配置"
