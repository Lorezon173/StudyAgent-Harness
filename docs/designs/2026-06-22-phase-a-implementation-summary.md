# 阶段 A 实施总结：真向量检索（pgvector + OpenAI embedding）

> 实施日期：2026-06-22  
> 状态：✅ 核心代码完成 + 单元测试全绿，待 Docker 环境验证集成测试

---

## 实施目标

为 StudyAgent 的 RAG 系统引入真正的向量检索能力，替代原有的 FakeRAGStore 字符匹配逻辑，支持语义相似度检索。

**技术选型**：
- 向量数据库：PostgreSQL + pgvector 扩展
- Embedding 模型：OpenAI `text-embedding-3-small`（1536 维）
- 降级策略：sqlite 环境下退化为字符匹配（保持测试兼容性）

---

## 已完成模块

### ✅ 1. EmbeddingService（`app/infrastructure/rag/embedding.py`）

**职责**：统一的文本→向量入口

**关键设计**：
- 懒加载 embedding client（仿 LLMService 的 lazy property 模式）
- 空字段从 `settings` 兜底（复用 OpenAI 配置：`openai_api_key` / `openai_base_url`）
- 无状态，线程安全
- 空文本处理：返回零向量

**API**：
- `embed_one(text: str) -> list[float]`：单条文本转向量
- `embed_many(texts: list[str]) -> list[list[float]]`：批量转向量（过滤空文本，保持索引对应）
- `dim` 属性：返回向量维度（1536）

**测试覆盖**：11 个单元测试（`tests/unit/infrastructure/test_embedding.py`）
- 配置读取（默认 + 自定义）
- 定长向量返回（1536 维）
- 批量处理 + 空文本处理
- 懒加载机制验证
- 所有外部 API 调用已 mock（标注 `[MOCK:阶段A]`）

---

### ✅ 2. PgVectorProvider（`app/infrastructure/rag/pgvector_provider.py`）

**职责**：实现 `IndexProvider` 协议，提供真向量检索后端

**关键设计**：
- **sync/async 边界隔离**：向量表用同步 psycopg 连接（不与业务 `async_session` 混用），避免 async 污染
- **score 校准**：pgvector `<=>` 返回距离（越小越近），转成 `score = 1/(1+distance)` 使其落在 (0, 1] 区间且越大越相关
- **双模式支持**：
  - PostgreSQL：用 pgvector 的 `<=>` 算子计算余弦距离，近邻检索
  - SQLite：降级为简单字符匹配（仅用于单元测试，不依赖真实 embedding API）

**API**：
- `index(docs: list[dict])` → 批量 embed + 写入向量表
- `search(query: str, top_k: int) -> list[Chunk]` → embed query + 近邻检索
- `doc_count` 属性 → 已索引文档数

**测试覆盖**：18 个单元测试（`tests/unit/infrastructure/test_pgvector_provider.py`）
- URL 转换（async → sync 驱动）
- 索引写入（单个/批量/scope/user_id/metadata）
- 检索逻辑（sqlite 降级分支，字符匹配排序）
- score 校准公式验证
- 连接复用 + 空查询处理
- 所有 embedding 调用已 mock（FakeEmbeddingService）

---

### ✅ 3. VectorChunkTable（`app/models/tables.py`）

**字段设计**：
- `user_id` / `scope`：多用户 + global/personal 知识范围（对齐 `KnowledgeTable`）
- `content`：chunk 原文
- `embedding`：向量（PG 用 `pgvector.sqlalchemy.Vector(1536)`，sqlite 退化为 TEXT）
- `source`：来源标识（"vector" | "ocr" | "code"）
- `doc_id` / `metadata_json`：文档标识 + 元信息（file_path/page/chunk_idx 等）

**已修复问题**：
- ✅ `embedding` 列定义补全（使用 `pgvector.sqlalchemy.Vector(1536)`）
- ✅ `metadata` 保留字冲突（改为 `metadata_json`）

**迁移脚本**：`alembic/versions/20260622_add_vector_chunks_table.py`

---

### ✅ 4. 集成测试脚本（`tests/integration/test_pgvector_real.py`）

**用途**：用户装 Docker 后跑真实 PG + 真实 embedding API 验证

**前置条件**：
1. PostgreSQL + pgvector 已启动（Docker）：
   ```bash
   docker run --name pgvector-test -e POSTGRES_PASSWORD=test \
       -e POSTGRES_DB=study_agent_test -p 5432:5432 -d pgvector/pgvector:pg16
   ```
2. 环境变量已配置：
   ```bash
   export OPENAI_API_KEY="your-api-key"
   export TEST_PG_URL="postgresql+psycopg://postgres:test@localhost/study_agent_test"
   ```

**运行方式**：
```bash
pytest -m integration tests/integration/test_pgvector_real.py -v
```

**测试覆盖**：7 个集成测试
- 索引中文 chunk + 语义检索
- 语义相似度检索（非字面匹配）
- score 校准公式在真实数据上的表现
- metadata 保存与读取
- 空查询 + top_k 限制 + 批量索引

**标记说明**：
- `@pytest.mark.integration`：默认跳过，需 `pytest -m integration` 才运行
- `@pytest.mark.skipif`：无 PG 连接或 API key 时自动跳过

---

## 已验证行为

### 模块导入验证
所有新增模块导入验证通过：
- ✅ `from app.infrastructure.rag.embedding import EmbeddingService`
- ✅ `from app.infrastructure.rag.pgvector_provider import PgVectorProvider`
- ✅ `from app.models.tables import VectorChunkTable`

### 既有测试保持全绿
- ✅ `tests/unit/infrastructure/test_rag.py`：15 passed（RAGCoordinator 既有功能未被破坏）
- ✅ `tests/unit/infrastructure/test_embedding.py`：11 passed
- ✅ `tests/unit/infrastructure/test_pgvector_provider.py`：18 passed

---

## Mock 标注与切除计划

所有测试中的 mock 已按要求标注 `[MOCK:阶段A]`，并在文件头部 docstring 说明：
- **Mock 出处**：`langchain_openai.OpenAIEmbeddings.embed_documents`
- **Mock 标注**：每处 mock 前用 `# [MOCK:阶段A]` 前缀注释
- **切除方式**：用户配置真实 OpenAI API key + 启动 Docker PG 后，运行集成测试验证真实 API 调用

**快速定位 mock**：
```bash
grep -rn "MOCK:阶段A" tests/
```

---

## 配置项

新增配置项（`app/core/config.py`）：
- `rag_backend: str = "fake"`：RAG 后端选择（"fake" | "pgvector"）
  - `"fake"`：使用 FakeRAGStore（字符匹配，默认值，保持测试兼容）
  - `"pgvector"`：使用 PgVectorProvider（真向量检索）
- `embedding_model: str = "text-embedding-3-small"`：OpenAI embedding 模型
- `embedding_dim: int = 1536`：向量维度

---

## 待完成步骤（用户侧）

### 🔲 1. 启动 PostgreSQL + pgvector

```bash
docker run --name pgvector-studyagent \
  -e POSTGRES_PASSWORD=your_password \
  -e POSTGRES_DB=study_agent \
  -p 5432:5432 \
  -d pgvector/pgvector:pg16
```

### 🔲 2. 配置环境变量

```bash
# .env
DATABASE_URL=postgresql+asyncpg://postgres:your_password@localhost/study_agent
OPENAI_API_KEY=sk-...
RAG_BACKEND=pgvector
```

### 🔲 3. 运行数据库迁移

```bash
alembic upgrade head
```

### 🔲 4. 运行集成测试验证

```bash
export TEST_PG_URL="postgresql+psycopg://postgres:your_password@localhost/study_agent"
pytest -m integration tests/integration/test_pgvector_real.py -v
```

### 🔲 5. 切除 mock（可选）

集成测试全绿后，可删除单元测试中的 mock，改为调用真实 API（需权衡 CI 成本）。

---

## 文件清单

| 类型 | 路径 | 状态 |
|------|------|------|
| 源码 | `app/infrastructure/rag/embedding.py` | ✅ 已实现 |
| 源码 | `app/infrastructure/rag/pgvector_provider.py` | ✅ 已实现 |
| 源码 | `app/models/tables.py` | ✅ 已修复（embedding 列 + metadata_json） |
| 迁移 | `alembic/versions/20260622_add_vector_chunks_table.py` | ✅ 已生成 |
| 单测 | `tests/unit/infrastructure/test_embedding.py` | ✅ 11 passed |
| 单测 | `tests/unit/infrastructure/test_pgvector_provider.py` | ✅ 18 passed |
| 集成测试 | `tests/integration/test_pgvector_real.py` | ✅ 已实现（待 Docker 环境验证） |
| 配置 | `app/core/config.py` | ✅ 新增 `rag_backend` / `embedding_model` / `embedding_dim` |
| 文档 | `README.md` | ✅ 已更新（阶段 A 说明） |
| 总结 | `docs/designs/2026-06-22-phase-a-implementation-summary.md` | ✅ 本文档 |

---

## 架构影响

**依赖关系**（保持单向）：
```
RAGCoordinator (协调器)
  ↓ 依赖
PgVectorProvider (实现 IndexProvider 协议)
  ↓ 依赖
EmbeddingService (文本→向量)
  ↓ 依赖
langchain_openai.OpenAIEmbeddings (外部依赖)
```

**与既有系统集成**：
- RAGCoordinator 通过 `IndexProvider` 协议调用 PgVectorProvider
- 配置 `rag_backend=pgvector` 后，系统自动切换到真向量检索
- 降级兼容：sqlite 环境下自动退化为字符匹配（不破坏既有测试）

---

## 后续优化方向

1. **性能优化**：
   - 向量索引优化（IVFFlat / HNSW）
   - 批量写入性能调优
   - 连接池配置

2. **功能扩展**：
   - 混合检索（向量 + 关键词）
   - 多语言 embedding 模型支持
   - 向量缓存机制

3. **可观测性**：
   - 检索延迟监控
   - 召回质量指标
   - embedding API 成本追踪

4. **测试覆盖**：
   - 大规模数据性能测试
   - 多用户并发测试
   - 故障注入测试（PG 宕机、API 超时）

---

## 参考资源

- **pgvector 文档**：https://github.com/pgvector/pgvector
- **OpenAI Embeddings API**：https://platform.openai.com/docs/guides/embeddings
- **IndexProvider 协议定义**：`app/infrastructure/rag/coordinator.py`
- **阶段 A 设计文档**：（待补充链接）

---

**总结**：阶段 A 核心代码已完成并通过单元测试验证（29 个测试全绿），代码质量和测试覆盖率达标。待用户配置 Docker PG 环境后，运行集成测试验证真实向量检索能力，即可正式启用 `rag_backend=pgvector` 配置。
