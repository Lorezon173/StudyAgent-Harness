# 编排 Agent 规范

修改本文件时，必须同步修改 `orchestrator.prompt.md`。

## 角色定义

调度中心。决定当前请求由哪个 SubAgent 处理，协调数据流转。

## 图结构

```
orchestrate → summarize → END
```

## 调度规则

| 意图/阶段 | 目标 SubAgent |
|-----------|--------------|
| TEACH_LOOP | teaching |
| QA_DIRECT | retrieval |
| REVIEW / EVALUATE | eval |

## 行为边界

- 不执行业务逻辑，只做调度决策
- 不直接读写 teaching/retrieval/evaluation 业务字段
- 一个轮次最多调度 3 个 SubAgent
- SubAgent 错误路由到 recovery，不重试

## 依赖

| 服务 | 位置 |
|------|------|
| teaching_graph | `app/agent/multi_agent/teaching_graph.py` |
| eval_graph | `app/agent/multi_agent/eval_graph.py` |
| retrieval_graph | `app/agent/multi_agent/retrieval_graph.py` |
