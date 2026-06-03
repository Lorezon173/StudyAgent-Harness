# 根规范

所有 Agent/SubAgent 共享的行为底线。修改本文件时，必须同步修改 `_root.prompt.md`。

## 架构约束

- 四层单向依赖：API → Orchestration → Harness → Infrastructure，严禁反向
- 薄壳节点：读 state → 委托 harness → 写 sub-state，业务逻辑不在节点内
- safe_node 包装：所有节点必须通过 safe_node 装饰器注册

## State 读写契约

- 每个节点只写自己所属的 sub-state 命名空间
- 命名空间归属：routing / teaching / retrieval / evaluation / memory / meta
- 严禁跨命名空间写入（如 teaching 节点写 retrieval 字段）
- 读取其他命名空间允许
- 返回格式：`{"命名空间": {字段: 值}}`

## 路由决策

| 意图 | 入口节点 | 分支 |
|------|---------|------|
| TEACH_LOOP | history_check | 诊断→检索→讲解→复述检查→循环 |
| QA_DIRECT | rag_first | 检索→证据门控→回答策略 |
| REPLAN | replan → route_intent | 重新路由 |
| REVIEW | summarize | 直接总结 |

## 错误处理

- safe_node 捕获异常，自动路由到 recovery
- recovery 根据 ErrorKind 枚举选择恢复策略
- 严禁吞掉异常（except: pass）

## 可观测性

- 关键操作通过 Observability 单例记录 trace/metric/log
- 节点入口/出口记录 stage 变更到 meta.stage
