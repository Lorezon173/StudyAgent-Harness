---
name: orchestrator-agent
description: 编排 Agent 行为规范 — 当处理多 Agent 编排、SubGraph 调度时调用
---

# Orchestrator Agent 行为规范

## 角色定义

编排 Agent 是多 Agent 架构的调度中心，负责决定当前请求应由哪个 SubAgent 处理，并协调各 SubAgent 之间的数据流转。

## 图结构

```
orchestrate → summarize → END
```

## 节点职责

### orchestrate（编排决策）
- **读取**：`routing.intent`, `meta.stage`
- **写入**：`current_agent`
- **行为**：根据意图和当前阶段，决定激活哪个 SubAgent
- **调度规则**：

| 意图/阶段 | 目标 SubAgent |
|-----------|--------------|
| TEACH_LOOP | teaching_agent |
| QA_DIRECT | retrieval_agent |
| REVIEW / EVALUATE | eval_agent |
| 评估需求 | eval_agent |

### summarize（全局总结）
- **读取**：所有 sub-state
- **写入**：`teaching.summary`
- **行为**：汇总本次学习会话的整体结果
- **输出内容**：学习主题、掌握程度、建议下一步

## SubAgent 调度协议

编排 Agent 通过 `current_agent` 字段通知路由层激活哪个 SubGraph。SubAgent 执行完毕后，结果写回对应 sub-state，编排 Agent 读取后继续决策。

```
orchestrator ─→ current_agent="teaching" ─→ teaching_graph
                                         ← teaching.diagnosis, teaching.explanation
           ─→ current_agent="eval"      ─→ eval_graph
                                         ← evaluation.mastery_score
           ─→ current_agent="retrieval" ─→ retrieval_graph
                                         ← retrieval.rag_context
```

## 行为边界

- 编排 Agent 不执行业务逻辑，只做调度决策
- 不直接读写 teaching/retrieval/evaluation 的业务字段，只读 `current_agent` 和路由信息
- 一个会话轮次中最多调度 3 个 SubAgent，避免无限循环
- 如果 SubAgent 返回错误状态，编排 Agent 应路由到 recovery 而非重试

## 依赖服务

| 服务 | 用途 | 位置 |
|------|------|------|
| teaching_graph | 教学 SubAgent | `app/agent/multi_agent/teaching_graph.py` |
| eval_graph | 评估 SubAgent | `app/agent/multi_agent/eval_graph.py` |
| retrieval_graph | 检索 SubAgent | `app/agent/multi_agent/retrieval_graph.py` |

## 错误恢复

- SubAgent 执行失败 → 记录错误到 meta，路由到 recovery
- 调度循环（超过3次）→ 强制进入 summarize 并标注"会话异常结束"
- 未知意图 → 默认调度到 teaching_agent

## 测试场景

1. 教学调度：intent=TEACH_LOOP → current_agent="teaching"
2. 评估调度：intent=REVIEW → current_agent="eval"
3. 检索调度：intent=QA_DIRECT → current_agent="retrieval"
4. 多轮编排：教学完成→评估→总结
5. 错误降级：SubAgent 失败→recovery→总结
