from app.specs.loader import SpecLoader


def test_loader_compose_includes_root_and_agent():
    loader = SpecLoader()
    prompt = loader.compose("tutor", "tutor_ask")
    assert "全局规则" in prompt          # 来自 _root.prompt.md
    assert "Tutor" in prompt              # 来自 tutor.prompt.md


def test_loader_compose_extracts_first_word_intent_section():
    # 首词 intent：tutor_ask 在 "### tutor_ask / tutor_probe_prereq" 首位
    loader = SpecLoader()
    prompt = loader.compose("tutor", "tutor_ask")
    assert "Socratic" in prompt
    assert "当前任务: tutor_ask" in prompt


def test_loader_compose_extracts_non_first_word_intent_section():
    # 非首词 intent：tutor_probe_prereq 在合并标题第二位，必须能提取到同段落
    loader = SpecLoader()
    prompt = loader.compose("tutor", "tutor_probe_prereq")
    assert "当前任务: tutor_probe_prereq" in prompt
    assert "probe_prereq" in prompt       # 段落正文含 probe_prereq 说明


def test_loader_compose_non_first_word_re_explain():
    loader = SpecLoader()
    prompt = loader.compose("tutor", "tutor_re_explain")
    assert "当前任务: tutor_re_explain" in prompt
    assert "re_explain" in prompt


def test_loader_compose_non_first_word_correct():
    loader = SpecLoader()
    prompt = loader.compose("tutor", "tutor_correct")
    assert "当前任务: tutor_correct" in prompt
    assert "correct" in prompt


def test_loader_compose_critic_assess():
    loader = SpecLoader()
    prompt = loader.compose("critic", "critic_assess")
    assert "Critic" in prompt
    assert "mastery_level" in prompt
    assert "当前任务: critic_assess" in prompt


def test_loader_compose_conductor_decide():
    loader = SpecLoader()
    prompt = loader.compose("conductor", "conductor_decide")
    assert "Conductor" in prompt
    assert "observation" in prompt
    assert "当前任务: conductor_decide" in prompt


def test_loader_compose_unknown_agent_returns_root_only():
    loader = SpecLoader()
    prompt = loader.compose("nonexistent", "some_intent")
    assert "全局规则" in prompt           # 仍有根规范
    # 无 agent spec 时不应崩溃


def test_loader_compose_unknown_intent_still_includes_agent_spec():
    # intent 无对应段落时，仍返回 root + 完整 agent spec（fallback）
    loader = SpecLoader()
    prompt = loader.compose("tutor", "no_such_intent")
    assert "Tutor" in prompt
    # 无"当前任务"精确段落但不崩溃
