# 知识检索节点规范

修改本文件时，必须同步修改 `knowledge_retrieval.prompt.md`。

## 职责

根据诊断结果和主题，从知识库检索相关知识。

## 读写契约

- 读取：`memory.topic`, `teaching.diagnosis`
- 写入：`retrieval.rag_context`, `retrieval.rag_found`

## 行为边界

- 检索为空时 rag_found=False，rag_context=""
- 不编造知识内容
