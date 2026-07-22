"""Prompt 模板 — system prompt 已迁移至 app/specs/ 目录

所有 system prompt 现在通过 SpecLoader 渐进式加载：
- 层级0: app/specs/_root.prompt.md
- 层级1: app/specs/agents/*.prompt.md
- 层级2: 从 app/specs/agents/*.prompt.md 中按 intent 段落抽取

本文件保留 user_prompt 模板，用于节点内构建 user_prompt 参数。
"""

# User prompt 模板（system prompt 由 SpecLoader 提供）

DIAGNOSE_USER = "主题：{topic}\n用户：{user_input}"
EXPLAIN_USER = "主题：{topic}\n诊断：{diagnosis}\n请讲解"
RESTATE_USER = "讲解：{explanation}\n用户复述：{user_input}"
FOLLOWUP_USER = "诊断：{diagnosis}\n复述评估：{eval_text}"
EVALUATE_USER = "诊断：{diagnosis}\n复述评估：{eval_text}"
SUMMARIZE_USER = "主题：{topic}\n掌握等级：{level}\n掌握分数：{score}\n理由：{rationale}"
ANSWER_USER = "知识：{context}\n用户问题：{question}"
INTENT_CLASSIFY_USER = "请对以下用户输入进行意图分类：{user_input}"
