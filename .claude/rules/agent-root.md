---
globs: app/agent/**/*.py
description: 学习Agent框架根规范 — 编辑agent代码时自动加载
---

# LearningAgent 框架根规范

本规范适用于 `app/agent/` 下所有代码，作为所有 Agent/SubAgent 的共享契约。

## 架构约束

- **四层单向依赖**：API → Orchestration → Harness → Infrastructure，严禁反向依赖
- **薄壳节点**：节点只做「读 state → 委托 harness → 写 sub-state」，业务逻辑不写在节点内
- **safe_node 包装**：所有节点必须通过 `safe_node` 装饰器注册，统一错误处理与可观测性

## State 读写契约

- 每个节点只写入自己所属的 sub-state 命名空间（routing / teaching / retrieval / evaluation / memory / meta）
- 严禁跨命名空间写入（如 teaching 节点写入 retrieval 字段）
- 读取其他命名空间是允许的（如 evaluate 读取 teaching.diagnosis）
- 返回格式：`{"命名空间": {字段: 值}}`

## 路由决策规则

| 意图 | 入口节点 | 分支 |
|------|---------|------|
| TEACH_LOOP | history_check | 诊断→检索→讲解→复述检查→循环 |
| QA_DIRECT | rag_first | 检索→证据门控→回答策略 |
| REPLAN | replan → route_intent | 重新路由 |
| REVIEW | summarize | 直接总结 |

## 错误处理

- 节点异常由 `safe_node` 捕获，自动路由到 `recovery` 节点
- `recovery` 节点根据 `ErrorKind` 枚举选择恢复策略
- 严禁在节点内部吞掉异常（`except: pass`）

## 可观测性

- 所有关键操作通过 `Observability` 单例记录 trace/metric/log
- 节点入口/出口记录 stage 变更到 `meta.stage`

## 渐进式规范加载

当需要深入了解某个 SubAgent 的行为规范时，调用对应的 Skill：
- 教学 Agent：invoke Skill `teaching-agent`
- 评估 Agent：invoke Skill `eval-agent`
- 检索 Agent：invoke Skill `retrieval-agent`
- 编排 Agent：invoke Skill `orchestrator-agent`
