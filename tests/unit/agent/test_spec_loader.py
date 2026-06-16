import pytest
from pathlib import Path
from app_old.agent.spec_loader import SpecLoader


SPEC_DIR = Path(__file__).parent.parent.parent.parent / "app_old" / "agent" / "specs"


class TestSpecLoader:
    def setup_method(self):
        self.loader = SpecLoader(SPEC_DIR)

    def test_load_root(self):
        result = self.loader.load_root()
        assert len(result) > 0
        assert "<root_rules>" in result

    def test_load_agent(self):
        result = self.loader.load_agent("teaching")
        assert len(result) > 0
        assert "<agent_role>" in result

    def test_load_node(self):
        result = self.loader.load_node("diagnose")
        assert len(result) > 0
        assert "<node_instruction>" in result

    def test_intent_map_loaded(self):
        imap = self.loader.intent_map()
        assert "teach_loop" in imap
        assert "qa_direct" in imap
        assert imap["teach_loop"]["agent"] == "teaching"

    def test_lookup(self):
        info = self.loader.lookup("teach_loop", "diagnose")
        assert info["agent"] == "teaching"
        assert "prompts/diagnose" in info["needs"]

    def test_lookup_qa_direct(self):
        info = self.loader.lookup("qa_direct", "rag_first")
        assert info["agent"] == "retrieval"
        assert "prompts/rag_first" in info["needs"]

    def test_lookup_unknown_intent(self):
        info = self.loader.lookup("nonexistent", "diagnose")
        assert info["agent"] is None
        assert info["needs"] == []

    def test_compose_teach_loop_diagnose(self):
        result = self.loader.compose("teach_loop", "diagnose")
        assert "<root_rules>" in result
        assert "<agent_role>" in result
        assert "<node_instruction>" in result

    def test_compose_qa_direct_rag_first(self):
        result = self.loader.compose("qa_direct", "rag_first")
        assert "<root_rules>" in result
        assert "<agent_role>" in result
        assert "<node_instruction>" in result

    def test_compose_caches_files(self):
        self.loader.compose("teach_loop", "diagnose")
        assert len(self.loader._file_cache) > 0

    def test_clear_cache(self):
        self.loader.compose("teach_loop", "diagnose")
        self.loader.clear_cache()
        assert len(self.loader._file_cache) == 0
        assert self.loader._intent_map is None

    def test_default_creates_instance(self):
        loader = SpecLoader.default()
        assert loader.spec_dir.name == "specs"

    def test_di_instance_with_custom_dir(self, tmp_path):
        custom = tmp_path / "specs"
        custom.mkdir()
        (custom / "_root.prompt.md").write_text("<root_rules>custom</root_rules>", encoding="utf-8")
        loader = SpecLoader(custom)
        assert "custom" in loader.load_root()
