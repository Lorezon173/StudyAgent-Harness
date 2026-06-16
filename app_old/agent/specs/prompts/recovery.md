# 恢复节点规范

修改本文件时，必须同步修改 `recovery.prompt.md`。

## 职责

处理节点异常，根据错误类型选择恢复策略。

## 读写契约

- 读取：`meta.error`, `meta.error_kind`
- 写入：`meta.recovery_action`, `teaching.reply`

## 恢复策略

| ErrorKind | Action | 行为 |
|-----------|--------|------|
| RAG_TIMEOUT | SKIP_RETRIEVAL | 跳过检索，用 LLM 直接回答 |
| RAG_NO_RESULT | FALLBACK_LLM | 提示知识库不足，建议换主题 |
| LLM_ERROR | RETRY | 重试一次 |
| INPUT_INVALID | ABORT | 提示用户重新输入 |
| FATAL | ABORT | 通知系统异常 |

## 行为边界

- 恢复后必须给用户有意义的反馈
- 不静默失败
