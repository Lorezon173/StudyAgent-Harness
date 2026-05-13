---
globs: app/agent/**/*.py
description: 学习Agent框架根规范 — 编辑agent代码时自动加载
---

# StudyAgent 框架根规范（Claude Code 开发指引）

本规范适用于 `app/agent/` 下所有代码，作为开发时的约束指引。
运行时的 Agent 行为规范存储在 `app/agent/specs/` 目录。

## 架构约束

- **四层单向依赖**：API → Orchestration → Harness → Infrastructure，严禁反向依赖
- **薄壳节点**：节点只做「读 state → 委托 harness → 写 sub-state」，业务逻辑不写在节点内
- **safe_node 包装**：所有节点必须通过 `safe_node` 装饰器注册
- **@with_spec 声明**：所有节点必须通过 `@with_spec(intent, node)` 声明规范来源
- **system_prompt 来自 SpecLoader**：节点内不再硬编码 prompt，通过 `state["_system_prompt"]` 获取

## State 读写契约

- 每个节点只写自己所属的 sub-state 命名空间
- 严禁跨命名空间写入
- `_system_prompt` 是由 `@with_spec` 注入的临时字段，不写入持久化 state

## 规范文件同步规则（必须遵守）

项目采用双文件分离：`.md`（开发者规范）+ `.prompt.md`（LLM 运行时 Prompt）

**修改任何一个 `.md` 规范文件时，必须同步修改对应的 `.prompt.md` 文件。**

对应关系：
- `specs/_root.md` ↔ `specs/_root.prompt.md`
- `specs/agents/teaching.md` ↔ `specs/agents/teaching.prompt.md`
- `specs/prompts/diagnose.md` ↔ `specs/prompts/diagnose.prompt.md`
- （其他文件同理）

如果只改了规范没改 prompt，或者只改了 prompt 没改规范，视为不完整修改。

## 渐进式加载体系

```
层级0: specs/_root.prompt.md        → 始终加载（全局规则）
层级1: specs/agents/<name>.prompt.md → 路由后加载（角色定义）
层级2: specs/prompts/<name>.prompt.md → 节点执行时加载（精确指令）
```

SpecLoader 通过 `intent_map.yaml` 查询意图→资源映射，按需组合三层 prompt。
