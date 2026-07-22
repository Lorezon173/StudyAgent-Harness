# app_old 老栈删除 spec

> **目标**：把已决策废弃的老栈 `app_old/` 整栈删除，使新栈 `app/`（事件驱动 5 Agent 协作环）成为唯一主体。
> **方法**：先解耦新栈对老栈的生产/测试硬依赖 → 验证新栈仍绿 → 再删老栈与 flag 机制 → 文档收尾。
> **前驱文档**：[docs/app_old_migration_plan.md](../app_old_migration_plan.md)（2026-06-02 迁移执行记录）
> **创建**：2026-07-17
> **历史背景说明**：本 spec 的“背景”“验证状态表”“资产清单”记录的是执行删除前的双栈事实；第 5 节完成后，`app_old/` 与 `FEATURE_USE_NEW_AGENT_GRAPH` 已删除，`app/` 是唯一运行栈。

---

## 一、背景

本节记录的是**删除前背景**：老栈 `app_old/`（旧 LangGraph 节点流，FakeLLM）已冻结，新栈 `app/`（事件驱动协作环，真实 LLM）是唯一活跃主体。彼时过渡期由 `FEATURE_USE_NEW_AGENT_GRAPH` flag 在请求时切换，老栈作为关 flag 的回退路径。

本 spec 已执行完成：flag 回退路径与老栈均已删除，项目现在仅运行新栈。

## 二、验证状态表（R1 · 已实测事实）

| 断言 | 验证方式 | 状态 |
|---|---|---|
| 新栈对老栈零依赖 | grep `app_old` in `app/agents\|orchestration\|harness` | ✅ 零引用 |
| 新栈端到端可独立跑 | `test_chat_feature_flag.py:test_chat_flag_on_uses_new_stack` | ✅ 有基线 |
| `assembly.py::run_new_agent_session` 完备 | Read 全文（5 Agent + Orchestrator 装配齐） | ✅ |
| flag 仅被 chat/chat_stream 调用 | grep `use_new_agent_graph` 全库 | ✅ 仅 2 处 |
| `/api/review` 路由不存在 | grep `review` in `app/api/` | ✅ 无文件 |
| `chat_multi.py` 不依赖老栈 | grep `app_old` in chat_multi.py | ✅ 无引用 |
| 前端消费 `stack` 字段 | grep `web/src/` → `TeachingStatus.tsx:51` | ✅ |
| conftest 顶层 import 是全局阻断点 | Read conftest.py:10 | ✅ |
| tests/unit/agent/ 全是老栈测试（9/9） | grep 每个文件 `from app_old` | ✅ |
| tests/unit/harness/ 老/新测试可分（7 老 / 9 新） | grep 每个文件 | ✅ |
| pyproject testpaths 未显式列老栈测试 | Read pyproject.toml:64 | ✅ `["tests"]` |

## 三、资产清单 + 三色血缘

### 🟡 改动（解耦）

| 文件 | 改动内容 |
|---|---|
| `app/api/chat.py` | 删 `:13` import、`:16` `_graph`、`:22` flag 判断、`:63-79` 老栈 else |
| `app/api/chat_stream.py` | 删 `:17/:20/:28/:102-122`（同构） |
| `tests/conftest.py` | 删 `:10` import、`:13-34` 老栈 fixture |
| `tests/unit/api/test_chat_anonymous.py` | 删 setenv / monkeypatch flag 残留 |
| `tests/unit/api/test_chat_persist.py` | 删 setenv / monkeypatch flag 残留 |
| `README.md` | 删双栈章节、flag 说明 |
| `CLAUDE.md` | 删单栈表老栈列、flag 地标 |
| `docs/asset-inventory.md` | 删 flag 资产行 |
| `docs/app_old_migration_plan.md` | 追加删除执行记录 |
| `.env.example` | 删 flag 示例行 |

### 🟡 改写（决策4：保留 API 端到端覆盖）

| 文件 | 改动 |
|---|---|
| `tests/unit/api/test_chat_feature_flag.py` | 改写为新栈 e2e（删 off 用例 + Fake，留 on 用例，去 flag 语义） |
| `tests/unit/api/test_chat_stream_feature_flag.py` | 同上 stream 版 |

### 🔴 删除

| 类别 | 文件 |
|---|---|
| 老栈源码 | `app_old/`（整目录，57 .py + specs） |
| flag 机制 | `app/core/feature_flags.py` |
| 老栈测试 | `tests/unit/agent/`（9 个）+ `tests/unit/harness/` 7 个 + `tests/unit/infrastructure/test_memory_store.py` |
| flag 测试 | `tests/unit/core/test_feature_flags.py` |
| parity 测试 | `tests/integration/test_plan_d_stack_parity.py`（对比语义失效） |
| 过时规范 | `.claude/rules/agent-root.md`（指向 app/agent/ 单数，全为老栈范式） |

### 🟢 保持

- `app/models/schemas.py` 的 `stack` 字段（保留恒为 `"new"`，前端在用）
- 新栈全部产物（agents/orchestration/harness 新文件/infrastructure 新文件）

## 四、决策记录

### D1：flag 机制 → 彻底删除
- 备选 B（保留恒走新栈）的"回退能力"在老栈删除后是伪命题（回退目标不存在）。
- 代价断言"删 flag 无副作用"已验证：flag 仅 chat/chat_stream 调用，review 端点不存在。

### D2：`stack` 字段 → 保留恒为 "new"
- 前端 `TeachingStatus.tsx:51` 实测在用；删字段需跨栈协同，收益不抵代价。

### D3：老栈测试 → 整体删除
- 老栈源码删除后测试无归属对象；git 历史已保留可追溯。

### D4：flag 端到端测试 → 改写保留
- `test_chat_flag_on_uses_new_stack` 是删老栈后唯一 API 级端到端测试，改写为「新栈 e2e」保留覆盖；其余 flag 测试删。

### D5：`agent-root.md` → 删除
- 内容全为老栈范式（safe_node/@with_spec/specs 渐进加载），新栈规范已在 Learned 架构文档。

## 五、分阶段执行计划

### Phase 1 · 新栈解耦
- 改 `chat.py`：去老栈 import + `_graph` 单例 + flag 判断 + else 分支
- 改 `chat_stream.py`：同构改动
- 验证：`app/api/` 零 `app_old` 引用；`python -c "import app.api.chat, app.api.chat_stream"` 成功

### Phase 2 · 测试基础设施解耦
- 改 `conftest.py`：去顶层 import + 老栈 fixture
- 删 17 个老栈测试（agent 9 + harness 7 + infra 1）
- 删 `test_feature_flags.py` + `test_plan_d_stack_parity.py`
- 改写 2 个 flag feature 测试为新栈 e2e
- 清理 `test_chat_anonymous` / `test_chat_persist` 的 flag 残留
- 验证：`pytest --collect-only` 无 ImportError

### Phase 3 · 删 flag + 删老栈
- 删 `app/core/feature_flags.py`
- `git rm -r app_old/`
- 验证：`python -c "from app.main import app"` 成功

### Phase 4 · 文档同步
- README / CLAUDE.md / asset-inventory / migration plan / .env.example / agent-root.md

### Phase 5 · 验收
- `uv run pytest tests/ -v` 全绿
- `python -c "from app.main import app"` 启动成功
- `grep -r app_old app/ tests/` 零结果

## 六、影响传播检查（R10）

| 改动 | 下游同步 |
|---|---|
| 删 `_graph = build_learning_graph()` | 仅 chat/chat_stream 用 ✅ |
| 删 `use_new_agent_graph()` | chat/chat_stream + 测试；review 不存在 ✅ |
| 删 `app_old.harness.state` | conftest + 17 老栈测试 ✅ |
| 保留 `stack="new"` | 前端显示"栈：new"，无破坏 ✅ |
| 删老栈测试 | harness 留 9 个新栈测试不依赖老栈 fixture ✅ |

## 七、验收标准

**降级路径**：删除过程中任一 Phase 测试红了，可 `git checkout` 回退该 Phase（老栈目录在 Phase 3 前仍在）。

**happy-path（核心链路真实执行）**：
1. `pytest tests/unit/api/test_chat_new_stack_e2e.py`（改写后）真实走 `POST /api/chat` → 5 Agent 协作环 → ChatResponse，断言 `stack=="new"` 且 reply 非空
2. `python -c "from app.main import app; print('ok')"` 真实 import 全链路
3. `grep -r "app_old" app/ tests/` 零结果（代码层彻底无残留）

## 八、待验证项（执行时确认）

- `.env`（用户本地，不在 git）：含 flag 行 → 完成后提示用户自行删，不主动改
