# RAG优先检索节点规范

修改本文件时，必须同步修改 `rag_first.prompt.md`。

## 职责

QA_DIRECT 分支入口，直接以用户问题为查询检索知识。

## 读写契约

- 读取：`user_input`
- 写入：`retrieval.rag_context`, `retrieval.rag_found`, `meta.stage`(RETRIEVING)

## 行为边界

- 检索为空时 rag_found=False
- 不编造知识
