"""tests/eval/test_judge.py —— judge 适配层与不同族校验测试"""

import pytest

from app.eval import judge
from app.eval.judge import build_judge, infer_family


class TestInferFamily:
    def test_openai_models(self):
        assert infer_family("gpt-4o-mini") == "openai"
        assert infer_family("gpt-4o") == "openai"
        assert infer_family("text-embedding-3-small") == "openai"

    def test_anthropic_models(self):
        assert infer_family("claude-3-sonnet") == "anthropic"
        assert infer_family("claude-opus-4") == "anthropic"

    def test_unknown_models(self):
        assert infer_family("llama-3") == "unknown"
        assert infer_family("mystery-model") == "unknown"

    def test_substring_false_positives(self):
        """对抗用例：含 gpt/o1/text 子串但非 OpenAI 模型，不应误判。"""
        assert infer_family("sol-v1") == "unknown"        # 含 "o1" 子串
        assert infer_family("llama-gpt-style") == "unknown"  # 含 "gpt" 但不是前缀
        assert infer_family("context-model") == "unknown"  # 含 "text" 子串
        assert infer_family("retro1-x") == "unknown"       # 含 "o1" 子串

    def test_o1_real_models(self):
        """o1 系列真实模型应正确识别为 openai。"""
        assert infer_family("o1") == "openai"           # 裸 o1（基础系列名）
        assert infer_family("o1-mini") == "openai"
        assert infer_family("o1-preview") == "openai"


class TestBuildJudge:
    def test_different_family_passes(self, monkeypatch):
        """anthropic 被评 → openai judge 返回非 None。"""
        monkeypatch.setattr(judge.settings, "openai_api_key", "sk-test")
        monkeypatch.setattr(judge.settings, "openai_model", "gpt-4o-mini")

        handle = build_judge(target_agent_family="anthropic")
        assert handle is not None
        assert handle["family"] == "openai"
        assert handle["llm"] is not None
        assert handle["embeddings"] is not None

    def test_same_family_fails(self, monkeypatch):
        """openai 被评 → openai judge 同族返回 None。"""
        monkeypatch.setattr(judge.settings, "openai_api_key", "sk-test")
        monkeypatch.setattr(judge.settings, "openai_model", "gpt-4o-mini")

        assert build_judge(target_agent_family="openai") is None

    def test_no_key_returns_none(self, monkeypatch):
        """无 api_key → 返回 None（降级）。"""
        monkeypatch.setattr(judge.settings, "openai_api_key", "")
        monkeypatch.setattr(judge.settings, "openai_model", "gpt-4o-mini")

        assert build_judge(target_agent_family="anthropic") is None

    def test_unknown_family_returns_none(self, monkeypatch):
        """judge 模型为 unknown 族 → 保守返回 None。"""
        monkeypatch.setattr(judge.settings, "openai_api_key", "sk-test")
        monkeypatch.setattr(judge.settings, "openai_model", "llama-3-70b")

        assert build_judge(target_agent_family="anthropic") is None
