from app.harness.tool_registry import ToolRegistry, ToolSchema, ToolResult
from app.harness.enums import Stage
from app.harness.state import LearningState


def test_register_and_list():
    reg = ToolRegistry()
    schema = ToolSchema(name="test_tool", description="测试工具", parameters={}, returns={})
    reg.register(schema, lambda p: "ok")
    assert "test_tool" in reg.list_tools()


def test_execute_success():
    reg = ToolRegistry()
    reg.register(ToolSchema(name="echo", description="echo", parameters={}, returns={}),
                 lambda p: p.get("msg", ""))
    result = reg.execute("echo", {"msg": "hello"})
    assert result.success
    assert result.output == "hello"


def test_execute_missing_tool():
    reg = ToolRegistry()
    result = reg.execute("nonexistent", {})
    assert not result.success
    assert "未注册" in result.error


def test_execute_exception():
    reg = ToolRegistry()
    reg.register(ToolSchema(name="bad", description="bad", parameters={}, returns={}),
                 lambda p: 1 / 0)
    result = reg.execute("bad", {})
    assert not result.success
