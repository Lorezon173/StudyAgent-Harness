# Conductor 角色规范（开发者文档）

LLM 决策兜底，规则未覆盖时被 Orchestrator 召唤。只基于已有观察路由，不自产观察。

- 运行时 Prompt：`conductor.prompt.md`
- 设计来源：design doc §2.3（Conductor 特殊性）、§3.3 Orchestrator 内部结构
- 实现：`app/agents/conductor.py`
- 修改本文件时必须同步修改 `conductor.prompt.md`
