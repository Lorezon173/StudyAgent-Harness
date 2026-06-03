import pytest
from pathlib import Path
from app_old.agent.spec_loader import SpecLoader
from app_old.agent.spec_decorator import with_spec, set_spec_loader, get_spec_loader
from app_old.harness.state import LearningState


SPEC_DIR = Path(__file__).parent.parent.parent.parent / "app_old" / "agent" / "specs"


class TestWithSpecDecorator:
    def setup_method(self):
        self.loader = SpecLoader(SPEC_DIR)
        set_spec_loader(self.loader)

    def teardown_method(self):
        set_spec_loader(None)

    def test_decorator_injects_system_prompt(self):
        @with_spec(intent="teach_loop", node="diagnose")
        def test_node(state: LearningState) -> dict:
            return {"prompt": state.get("_system_prompt", "")}

        state = {"user_input": "test", "routing": {"intent": "teach_loop"}}
        result = test_node(state)
        assert "<root_rules>" in result["prompt"]
        assert "<agent_role>" in result["prompt"]
        assert "<node_instruction>" in result["prompt"]

    def test_decorator_uses_state_intent(self):
        @with_spec(intent="teach_loop", node="diagnose")
        def test_node(state: LearningState) -> dict:
            return {"prompt": state.get("_system_prompt", "")}

        state = {"user_input": "test", "routing": {"intent": "qa_direct"}}
        result = test_node(state)
        # qa_direct 的 agent 是 retrieval，不是 teaching
        assert "检索" in result["prompt"]

    def test_decorator_preserves_function_name(self):
        @with_spec(intent="teach_loop", node="diagnose")
        def my_node(state: LearningState) -> dict:
            return {}

        assert my_node.__name__ == "my_node"

    def test_decorator_sets_spec_metadata(self):
        @with_spec(intent="teach_loop", node="diagnose")
        def test_node(state: LearningState) -> dict:
            return {}

        assert test_node._spec_intent == "teach_loop"
        assert test_node._spec_node == "diagnose"

    def test_set_spec_loader_overrides_default(self, tmp_path):
        custom = tmp_path / "specs"
        custom.mkdir()
        (custom / "_root.prompt.md").write_text("CUSTOM_ROOT", encoding="utf-8")
        (custom / "agents").mkdir()
        (custom / "agents" / "teaching.prompt.md").write_text("", encoding="utf-8")
        (custom / "prompts").mkdir()
        (custom / "prompts" / "diagnose.prompt.md").write_text("", encoding="utf-8")
        (custom / "intent_map.yaml").write_text(
            "teach_loop:\n  agent: teaching\n  flow:\n    diagnose:\n      needs: [prompts/diagnose]\n",
            encoding="utf-8",
        )

        custom_loader = SpecLoader(custom)
        set_spec_loader(custom_loader)

        @with_spec(intent="teach_loop", node="diagnose")
        def test_node(state: LearningState) -> dict:
            return {"prompt": state.get("_system_prompt", "")}

        result = test_node({"user_input": "test", "routing": {}})
        assert "CUSTOM_ROOT" in result["prompt"]
