# 讲解节点规范

修改本文件时，必须同步修改 `explain.prompt.md`。

## 职责

根据诊断结果和 RAG 上下文，生成针对性讲解。

## 读写契约

- 读取：`teaching.diagnosis`, `retrieval.rag_context`, `teaching.explain_loop_count`
- 写入：`teaching.explanation`, `teaching.reply`, `teaching.explain_loop_count`(+1)

## 行为边界

- 循环计数每次 +1
- RAG 为空时提示"知识库未覆盖此主题"
- 第 3 次循环后不再重新讲解，由路由强制退出
