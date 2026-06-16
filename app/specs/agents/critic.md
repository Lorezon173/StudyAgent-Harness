# Critic 角色规范（开发者文档）

文本语义评估，只判语义层（掌握度/混淆/矛盾/置信度/RAG 质量），不读图谱、不做路由。

- 运行时 Prompt：`critic.prompt.md`
- 设计来源：design doc §2.1（Critic 行）、§2.4 职能正交、§3.6 证据评判
- 实现：`app/agents/critic.py`
- 修改本文件时必须同步修改 `critic.prompt.md`
