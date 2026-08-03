# RAG 与长期记忆系统升级 · 全阶段 Todolist

> 创建日期：2026-07-03  
> 来源追溯：`2026-06-16-rag-phase-a-plan.md` 第四层"下阶段规划存档"  
> 状态图例：✅ 已完成 | 🚧 进行中 | ⏳ 待启动 | ❌ 已废弃

---

## 阶段 A：真向量检索 + 统一 PG（2026-06-22 ~ 2026-07-03）

**目标**：把当前"假向量检索"接成"真语义向量检索"，存储统一到 PostgreSQL + pgvector。

### A.1 基础设施层（Infrastructure）
- [x] ✅ `EmbeddingService` 新建（`app/infrastructure/rag/embedding.py`）
  - 接口：`embed_one(text)` / `embed_many(texts)` / `dim`
  - 直接调 OpenAI SDK（绕过 langchain 预分词）
  - 分批调用（batch=10，方舟 API 限制）
- [x] ✅ `PgVectorProvider` 新建（`app/infrastructure/rag/pgvector_provider.py`）
  - 实现 `IndexProvider` 协议
  - sync/async 边界隔离（同步 psycopg 连接）
  - score 校准：`1/(1+distance)` 归一化到 (0,1]
- [x] ✅ `VectorChunkTable` 新建（`app/models/tables.py`）
  - 字段：id / user_id / scope / content / embedding(2048) / source / doc_id / metadata_json / created_at
  - `metadata_json` 规避 SQLAlchemy 保留字冲突
- [x] ✅ Alembic 迁移（`20260622_add_vector_chunks_table.py`）
  - PG: `vector(2048)` + `CREATE EXTENSION vector`
  - SQLite: 退化为 TEXT

### A.2 接线与配置
- [x] ✅ `RAGCoordinator` 接线（`coordinator.py`）
  - `settings.rag_backend` 开关切换 pgvector / fake
  - 保留 FakeRAGStore 作为测试替身
- [x] ✅ `Settings` 配置（`config.py`）
  - `embedding_model`: `doubao-embedding-vision`
  - `embedding_dim`: 2048
  - `rag_backend`: `"fake" | "pgvector"`
- [x] ✅ `.env` 配置
  - `OPENAI_BASE_URL`: 方舟端点 `https://ark.cn-beijing.volces.com/api/coding/v3`

### A.3 测试覆盖
- [x] ✅ 单元测试（44 passed）
  - `test_embedding.py` (11 tests, mock openai.OpenAI)
  - `test_pgvector_provider.py` (18 tests, sqlite 降级分支)
  - `test_rag.py` (15 tests, 既有 RAGCoordinator 兼容)
- [x] ✅ 集成测试（7 passed）
  - `test_pgvector_real.py`：真实 PG + 真实方舟 API
  - 中文语义检索 + score 校准 + metadata 保存 + 批量索引

### A.4 文档与 README
- [x] ✅ `docs/designs/2026-06-22-phase-a-implementation-summary.md`（实施总结）
- [x] ✅ README.md 更新（RAG 检索章节 + 技术栈表）

### A.5 Bug 修复历程（6 轮迭代）
- [x] ✅ metadata 列名冲突（SQLAlchemy 保留字 → metadata_json）
- [x] ✅ embedding 列缺失（补全 VectorChunkTable 定义）
- [x] ✅ SQLAlchemy 2.0 裸字符串 SQL 报错（改用 text() + 命名参数）
- [x] ✅ langchain_openai 预分词不兼容方舟 API（绕过，直接用 openai.OpenAI）
- [x] ✅ psycopg3 参数解析冲突（`::vector` → `CAST(:embedding AS vector)`）
- [x] ✅ 方舟 API 批量限制（embed_many 分批调用，batch=10）

### A.6 Mock 标注与切除计划
- [x] ✅ 所有 mock 标注 `[MOCK:阶段A]`
- [ ] ⏳ 集成测试全绿后，评估是否切除单测 mock（需权衡 CI 成本）

---

## 阶段 B-①：知识内容图谱（LightRAG 双层检索）

**目标**：把知识内容建成"实体关系图 + 向量"双层，支持 local（实体邻居）+ global（全局关系）检索，解决"知识脉络串联"。

**A 阶段已铺垫**：
- 向量已在 pgvector（LightRAG 原生支持 PG 存图）
- EmbeddingService 可复用
- 文档摄入接口 `IndexProvider.index` 可作为图谱抽取入口

### B1.1 实体/关系抽取管线
- [ ] ⏳ LLM 抽取 pipeline（输入 chunk → 输出 entities + relations）
- [ ] ⏳ 抽取 prompt 设计（few-shot 示例）
- [ ] ⏳ 抽取结果结构化（JSON schema）
- [ ] ⏳ 成本控制（batch 抽取 + token 预算）

### B1.2 图存储
- [ ] ⏳ PG 边表设计（entity_nodes / entity_edges）
- [ ] ⏳ Alembic 迁移
- [ ] ⏳ 图写入接口（GraphStore.add_entity / add_edge）
- [ ] ⏳ 图读取接口（GraphStore.get_neighbors / get_path）

### B1.3 双层检索
- [ ] ⏳ Local 检索（实体邻居 + 一跳扩展）
- [ ] ⏳ Global 检索（全局关系摘要）
- [ ] ⏳ 双层融合（local + global 结果加权合并）
- [ ] ⏳ 与现有 RAGCoordinator 融合（新 provider 或新 search mode）

### B1.4 决策待定
- [ ] ⏳ 是否引 Neo4j（倾向不引，用 PG）
- [ ] ⏳ 图抽取的 LLM 成本控制策略
- [ ] ⏳ 实体消歧与合并策略

---

## 阶段 B-②：掌握度图谱时序化 + 触发复习

**目标**：在用户主动请求时，基于**新栈**已练习节点的 `last_practiced_at` 计算只读的当前掌握度投影，返回可解释、稳定排序的复习建议。完整实施约束见 `docs/designs/2026-07-03-phase-b2-mastery-temporal-review-spec.md`（2026-07-15 已补迁移链与新栈 rollout 阻断项）。

**用户硬要求**：复习机制必须**用户可开关、参数可调、可主动调用**，不能强制自动触发。

**已确认边界**：
- 仅支持 `FEATURE_USE_NEW_AGENT_GRAPH=true` 的新栈；flag 关闭时 Review API 必须明确拒绝，**不动 legacy、不桥接旧数据、不以空建议伪装可用**。
- 只做 SQLAlchemy 事实源上的偏好配置与主动 API；不接入 Celery、定时任务、事件总线、Curator 改动或衰减写回。
- 查看建议不得改变 mastery、`last_practiced_at` 或 `practice_count`。

### B2.0 阻断性交付：历史 mastery 表 Alembic 链修复
- [ ] ⏳ 核实并记录当前 revision 链、head 与 M3 对 mastery 表的前置假设
- [ ] ⏳ 补齐 `mastery_nodes` / `mastery_edges` 在历史 Alembic 链中的创建责任
- [ ] ⏳ 验证空 PostgreSQL `alembic upgrade head`：两表先创建、再允许后续 alter，且结构与 ORM 一致
- [ ] ⏳ 明确迁移修复的 downgrade / rollback 行为

### B2.1 掌握度衰减函数
- [ ] ⏳ 三种只读衰减曲线（真半衰期指数 / 线性 / 阶梯）
- [ ] ⏳ 全局参数（半衰期 / 衰减率 / 阶梯参数）
- [ ] ⏳ 单元测试（含 `80, 7d, half_life=7d → ≈40`）

### B2.2 主动复习触发策略
- [ ] ⏳ 阈值 / 间隔 / 混合策略
- [ ] ⏳ `POST /api/review/trigger`（JWT 用户隔离）
- [ ] ⏳ 新栈可用性检查：flag 关闭时所有 Review API 返回明确受控错误
- [ ] ⏳ 冷启动节点排除、稳定优先级排序、前置薄弱原因

### B2.3 用户偏好存储
- [ ] ⏳ `review_preferences` SQLAlchemy 表 + Alembic 迁移（仅在 B2.0 修复后的 head 上新增）
- [ ] ⏳ 复习开关 / 曲线 / 触发阈值等参数化
- [ ] ⏳ `GET/PUT /api/review/preferences`

### B2.4 验收与复审
- [ ] ⏳ 新栈开关开启 / 关闭的 Review API 测试矩阵
- [ ] ⏳ 真实 SQLAlchemy happy-path + 干净 PostgreSQL Alembic 验证
- [ ] ⏳ B-② Spec 独立 review 复审通过后，才进入编码计划

### B2.5 后续讨论项（不纳入 MVP）
- [ ] ⏳ 单知识点可调粒度
- [ ] ⏳ UI 呈现（列表 / 卡片 / 日历）
- [ ] ⏳ 复习内容生成、效果追踪
- [ ] ⏳ 自动提醒（另立调度与通知 spec，不能假定 Celery 已可复用）

---

## 阶段 B-③：PDF 版面解析（更后）

**目标**：教材 PDF 的版面级解析，提取结构化知识（标题层级 / 表格 / 公式 / 图片说明）。

### B3.1 技术选型
- [ ] ⏳ ragflow DeepDoc 评估
- [ ] ⏳ LightRAG-MinerU 评估
- [ ] ⏳ 其他方案（marker / pymupdf4llm / unstructured）
- [ ] ⏳ 对比测试（准确率 / 速度 / 易用性）

### B3.2 集成
- [ ] ⏳ PDF 解析 Provider 实现
- [ ] ⏳ 与现有 `extractors/` 融合（惰性 import + 优雅降级）
- [ ] ⏳ 版面元素结构化（章节 / 段落 / 列表 / 表格）
- [ ] ⏳ 知识源质量评估（解析置信度 + 人工标注反馈）

### B3.3 决策待定
- [ ] ⏳ 按知识源实际质量需求再评估

---

## 总体进度概览

| 阶段 | 状态 | 完成度 | 预计工作量 |
|------|------|--------|-----------|
| **A: 真向量检索** | ✅ 已完成 | 100% | 4 小时（含 6 轮 bug 修复） |
| **B-①: LightRAG 双层检索** | ⏳ 待启动 | 0% | 预估 2-3 天（含 LLM 抽取 + 图存储 + 双层检索） |
| **B-②: 掌握度时序化 + 复习** | ⏳ 待启动 | 0% | 预估 2-3 天（含衰减函数 + 触发策略 + 用户偏好） |
| **B-③: PDF 版面解析** | ⏳ 待启动 | 0% | 预估 1-2 天（技术选型 + 集成） |

---

## 关键依赖关系

```
阶段 A (✅)
  ├─ 为 B-① 铺垫：pgvector + EmbeddingService + IndexProvider.index 接口
  ├─ 为 B-② 铺垫：MasteryGraph 已有 last_practiced_at 字段
  └─ 为 B-③ 铺垫：extractors/ 已有惰性 import 模式

阶段 B-① (⏳)
  └─ 依赖：A 阶段的 pgvector 基础设施

阶段 B-② (⏳)
  └─ 依赖：A 阶段的 MasteryGraph 字段（已就绪）

阶段 B-③ (⏳)
  └─ 依赖：A 阶段的 extractors/ 模式（已就绪）
```

---

## 下一步行动建议

**优先级排序**：
1. **B-②（掌握度时序化）**：用户硬要求（复习必须可选可调），且依赖已就绪（MasteryGraph 字段已有）
2. **B-①（LightRAG 双层检索）**：知识脉络串联，依赖 A 阶段铺垫（已完成）
3. **B-③（PDF 版面解析）**：按知识源质量需求再评估，优先级最低

**建议执行顺序**：
```
A (✅) → B-② (用户硬要求) → B-① (知识图谱) → B-③ (按需)
```

> ⚠️ **执行顺序修正提醒（2026-07-08 补充）**
>
> 本 todolist 制定时尚未发现新栈 RAG 接线断点。结合根目录 `TODO.md` 的 P0 梳理，**B-② 启动前应先修 P0**（Tutor 接检索结果 / `expand_query` 闭环 / `search` scope 过滤），否则 B-① 落地后会重现「图谱建好但 Tutor 不吃检索结果」的尴尬。
>
> 修正后顺序：`A (✅) → P0 接线修复 → B-② (用户硬要求) → B-① (知识图谱) → B-③ (按需)`
>
> P0 明细见根目录 `TODO.md`；本次会话完整盘点见 `docs/designs/2026-07-07-rag-three-stage-enhancement-review.md`。

---

**文档维护**：每完成一个阶段，更新本文件的 checkbox 状态，并在 `docs/claude-chat/` 新增交接文档。
