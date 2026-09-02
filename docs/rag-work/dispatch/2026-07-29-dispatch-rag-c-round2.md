# RAG-C 第二轮提示词（直接复制到 RAG-C 窗口）

你是 StudyAgent Harness「RAG 基础能力建设」的 **RAG-C 任务窗口**。主控已完成 C-08 复核：**spec 修订 provisional 通过**，你进入 Phase 2 编码。

## C-08 复核结果：✅ provisional 通过

主控复核（2026-07-29）：
- spec 结构完整，6 项已冻结决策（DEC-001/003/004/007/008/009）全部有专门章节落点（§A-§G）
- 验证状态表诚实标注未决项
- migration 事实已修正（正式 Alembic migration 存在，问题是 fixture 未消费）

**provisional 通过**：可进入编码；以下两项在编码时定义并经主控复核：
- §F composition 精确代码落点（C-07）
- §G 错误码集合与安全摘要文案枚举（DEC-009 边界已冻结，具体枚举待你定义）

## 本轮任务（Phase 2：C-09~C-11）

- [ ] **C-09** 扩展 visibility 上下文端到端传递并在 PG/SQLite 查询执行过滤（DEC-001 授权矩阵；过滤在排序/LIMIT 前）
- [ ] **C-10** 实现 provider outcome 与安全摘要（DEC-008 五态 `{ok, empty, degraded, failed, invalid-request}`；DEC-009 分类码+摘要对外、原始异常对内；移除 `retriever.py:58` 的 `str(exc)`；`coordinator.py:111-117` 异常不再静默吞没；枚举错误码集合）
- [ ] **C-11** online production 显式装配 `PgVectorProvider` + PostgreSQL 校验（DEC-007 fail-fast；fake/SQLite 仅限非在线路径）
- [ ] 定义 §F composition 入口精确代码落点（assembly/依赖注入）与校验实现，提交主控复核
- [ ] 定义 §G 错误码集合（如 `backend_unavailable/embedding_failed/db_error/invalid_request`）与安全摘要文案，提交主控复核
- [ ] `low_score` 重构为 `ok + quality=low` 子标记（同步修订 `tests/unit/agents/test_retriever.py:84-127` 断言）

## 回写要求

每完成一个 todo 即更新 `docs/rag-work/status/RAG-C.md`，附实现路径、测试命令与运行结果。§F/§G 定义稿单独提交主控复核。

## 禁止

- 在 §F/§G 主控复核前宣称 composition/outcome 完成
- 只改 seed 就宣称接通；Tutor 直连 Coordinator/Provider/Embedding/SQL
- 猜测 shared/course 语义；引入 query rewrite

## 完成后

简要报告：实现清单、测试结果、§F/§G 定义稿、待主控复核项。
