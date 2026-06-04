# Curator 角色规范（开发者文档）

维护用户画像与掌握点知识图谱，只判结构层（前置薄弱），不判文本语义。

- 运行时 Prompt：`curator.prompt.md`（当前不调 LLM，仅留存）
- 设计来源：design doc §2.1（Curator 行）、§6/§6.1 MasteryGraph 冷启动建图
- 实现：`app/agents/curator.py`
- 修改本文件时必须同步修改 `curator.prompt.md`
