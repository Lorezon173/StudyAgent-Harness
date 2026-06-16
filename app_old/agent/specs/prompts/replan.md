# 重规划节点规范

修改本文件时，必须同步修改 `replan.prompt.md`。

## 职责

处理用户改变学习方向的请求，重置状态后重新路由。

## 读写契约

- 读取：`user_input`, `routing.intent`
- 写入：`routing.intent`, `meta.stage`(ROUTING)

## 行为边界

- 清除当前主题相关的 teaching/retrieval 状态
- 保留 memory 中的用户级信息
- 重定向回 route_intent 重新分类
