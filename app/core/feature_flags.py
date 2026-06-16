"""Feature flags（运行时环境变量驱动，支持灰度热切换）。

Plan D：用 FEATURE_USE_NEW_AGENT_GRAPH 控制 /chat 与 /chat/stream 走
新栈（事件驱动 5 Agent 协作环）还是老栈（app_old LangGraph 图）。
在请求处理函数内实时读取（不在模块加载期固化），故无需重启即可切换、
一键回退。
"""
import os

_TRUE_VALUES = {"true", "1", "yes", "on"}


def use_new_agent_graph() -> bool:
    """是否启用新栈。true/1/yes/on（大小写与首尾空白不敏感）→ True；
    其余值或未设置 → False（默认回退老栈）。
    """
    return os.getenv("FEATURE_USE_NEW_AGENT_GRAPH", "").strip().lower() in _TRUE_VALUES
