# 会话交接文档 · RAG 与长期记忆系统升级

> 整理日期：2026-06-16
> 用途：跨窗口任务交接。新窗口读完本文件即可无缝接续，无需回溯原对话。
> 任务主线：升级 StudyAgent 的检索系统，支持长期记忆（学习辅助场景：注重长期记忆回顾、知识高度集中）。

---

## 一、当前进度（读这里就知道走到哪了）

```
[✓] 调研 7 个开源 RAG/记忆方案（含实时 star）
[✓] 出"现状 vs 方案"对比决策报告
[✓] 用户拍板 4 个决策（见第三节）
[✓] 出阶段 A 三层规划文档
[→] 等用户确认 2 个细节后进入编码   ← 现在卡在这里
[ ] 阶段 A 编码实现
[ ] 下阶段：LightRAG 双层检索 / 掌握度时序化复习
```

**下一步动作**：用户确认第五节的 2 个待定项后，按阶段 A 规划进入编码（编码优先用 subagent 执行，主会话审阅）。

---

## 二、产出文档清单（都已落盘，新窗口直接读）

| 文档 | 位置 | 内容 |
|---|---|---|
| 方案调研 | `docs/research/2026-06-15-rag-memory-frameworks-survey.md` | 7 个开源方案设计 + 实时 star + 初步选型 |
| 对比决策报告 | `docs/research/2026-06-16-current-vs-frameworks-decision-report.md` | 当前设计 vs 方案逐维度对比、3 条候选路线 |
| **阶段 A 三层规划** | `docs/designs/2026-06-16-rag-phase-a-plan.md` | ⭐ 编码前必读，含详细实施计划 + 下阶段存档 |
| 本交接文档 | `docs/claude-chat/2026-06-16-rag-memory-handoff.md` | 你正在读的这份 |

---

## 三、用户已拍板的 4 个决策（不可推翻，编码须遵守）

1. **先做路线 A** —— 把"假向量检索"接成"真语义向量检索"。
2. **知识内容侧（借鉴 LightRAG 双层检索）** —— 本阶段**不做**，已记录规划，**下阶段做**。
3. **掌握度图谱时序化 + 触发复习** —— 本阶段**不做**，下阶段做；**硬要求：必须做成用户可选、可调、可主动调用，不能强制自动触发**。后续讨论细节（衰减曲线、可调粒度、UI）。
4. **存储统一到 PostgreSQL** —— 本阶段就做，且要**为 LightRAG 落地铺垫基础**。

---

## 四、关键事实速查（全部已实读源码核实，可溯源）

### 检索侧现状
- 架构骨架完整：`RetrieverAgent`（机械层，`app/agents/retriever.py`）→ `RAGCoordinator`（多源聚合，`app/infrastructure/rag/coordinator.py:46`）→ 三 Provider（vector/ocr/code）。
- **★ 向量底座是假的**：`FakeRAGStore.query` 是字符子串计数（`store.py:10-17`）；`RAGStore.query` 是空壳 `return []`（`store.py:34-36`）。**没有真正的语义检索**。
- **依赖已就位**：`pyproject.toml` 已装 llama-index、chromadb、llama-index-embeddings-openai、pgvector、sbert-rerank、ragas。

### 记忆侧现状（分裂的两半）
- **学习者状态侧（成熟）**：`MasteryGraph`（`app/harness/mastery_graph.py`）有掌握度 0-100、边置信度演化（0.5/0.3→0.8）、前置薄弱检测（`find_weak_prereqs`）、`Curator` Agent 自动维护（`app/agents/curator.py`）。
- **知识内容侧（空白）**：`KnowledgeStore` 是内存 dict 假实现（`knowledge_store.py`）。**这是本次要补的主战场**。
- **关键区分**：`MasteryGraph` 是"知识点**掌握度**图谱"（学习者状态），**不是**"知识**内容**图谱"。

### 存储基础设施（已倒向 PG）
- `docker-compose.yml:3` = `pgvector/pgvector:pg16`。
- `database.py:41-42`：PG 下自动 `CREATE EXTENSION IF NOT EXISTS vector`。
- alembic 已就绪：`env.py` 用 `Base.metadata`，已有 1 条 init 迁移。
- **张力**：pyproject 装的是 chromadb，但 docker 基础设施是 pgvector → 规划已定**选 pgvector**（统一 PG + LightRAG 原生支持 PG）。

### 双栈并存（升级只动新栈）
- `chat.py:12` / `chat_stream.py:14` 仍 import 老栈 `app_old.agent.graph`，由 `feature_flags` 灰度。
- 升级**只针对新栈 `app/`**；`app_old/` 的 FTS5 记忆是历史包袱，不复用。

---

## 五、待用户确认的 2 个细节（编码前必须定）

1. **embedding 模型**：默认拟用 `text-embedding-3-small`（1536 维）。是否有指定的 embedding 模型/服务？（决定向量表维度，建表后改维度要重新迁移，须先定）
2. **测试默认后端**：拟用 `settings.rag_backend` 默认 `fake`（保住现有单测不依赖真 PG/网络），真 PG 检索走集成测试。是否认可？

---

## 六、阶段 A 编码范围速览（详见规划文档）

**新建**：
- `EmbeddingService`（`app/infrastructure/rag/embedding.py`）—— 文本→向量统一入口。
- `PgVectorProvider`（`app/infrastructure/rag/pgvector_provider.py`）—— 真向量检索后端，实现既有 `IndexProvider` 协议。
- 向量表模型（`app/models/tables.py` 增表）+ alembic 迁移。

**改动**：
- `RAGCoordinator`（接线默认 provider，签名不变）。
- `settings`（`config.py` 加 embedding/rag_backend 配置）。

**保持**：
- `FakeRAGStore`（测试仍用，不删）、`RetrieverAgent`（接口不变）、chromadb 依赖（暂留不用）。

### 两个实施风险点（规划已标注）
1. **sync/async 边界**：`IndexProvider.search` 是同步，PG 访问是 async。倾向给向量表单独用同步 psycopg 连接，避免缠绕。**实施第一个验证项**。
2. **score 阈值校准**：pgvector 返回距离（越小越近），要转成"越大越相关"的 score；现有 `retrieve()` 的 `avg>2→high`（`coordinator.py:148`）是为整数计数设计的，转向量后须重定 + 更新测试。

---

## 七、本项目硬约束（编码须遵守，来自 `.claude/rules/`）

- **中文沟通**。
- **四层单向依赖**：API→Orchestration→Harness→Infrastructure，禁反向。
- **薄壳节点 + safe_node + @with_spec**：节点只读 state→委托 harness→写 sub-state。
- **规范双文件同步**：改 `.md` 须同步改 `.prompt.md`。
- **模块开发须先三层规划、经用户确认才编码**（已完成规划，待确认）。
- **跑 pytest 必须 `< /dev/null`**（否则挂起，见项目记忆）。
- **README 维护**：每完成一个任务检查更新根 README。
- **编码优先用 subagent 执行，主会话规划+审阅**；写代码前先载入 `karpathy-guidelines` skill。
