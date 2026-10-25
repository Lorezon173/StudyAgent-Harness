# Curator 角色规范（开发者文档）

维护用户画像与掌握点知识图谱，只判结构层（前置薄弱），不判文本语义。

- 运行时 Prompt：`curator.prompt.md`（当前不调 LLM，仅留存）
- 设计来源：design doc §2.1（Curator 行）、§6/§6.1 MasteryGraph 冷启动建图
- 实现：`app/agents/curator.py`
- 修改本文件时必须同步修改 `curator.prompt.md`
# 稳定节点上下文约束

有TeachingContext时仅消费本画像有效、未归档且已存在的稳定节点UUID；主题标题不作为节点标识，未知节点不创建。无有效待答或节点、评分缺失/非法时不更新掌握度，不默认零分。离线无context保留既有契约。Curator不调用LLM。
