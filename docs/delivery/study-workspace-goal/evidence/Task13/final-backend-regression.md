# Task13 后端独立回归

本次记录测试运行，不替代 Task13 的真实浏览器、真实模型、65301 验收库、服务或 PostgreSQL 重启验收。候选 HEAD 为 `3c9fae413309731b181e72475cf71c980531e7e4`；当时工作区包含待审改动，不能把 HEAD 单独视作完整源码指纹。教学与评价四文件的实际 SHA-256 列于下表。三项命令并行启动，结果按各子进程实际退出码记录。

| 检查 | 实际命令 | 退出码 | 结果 |
| --- | --- | --- | --- |
| 默认测试 | `uv run pytest tests/ -q` | 0 | 1362 passed、77 deselected、1 warning；118.27 秒。[脱敏完整日志](final-backend-pytest.log) |
| 固定 Ruff | `uvx --offline --index-url https://pypi.tuna.tsinghua.edu.cn/simple --from ruff==0.17.1 ruff check .` | 1 | 599 条诊断，未通过；[脱敏完整日志](final-backend-ruff.log)。 |
| 指定数据库回归 | `uv run pytest -m integration -q tests/integration/test_workspace_migrations.py tests/integration/test_private_library_migrations.py tests/integration/test_topic_profiles_service.py tests/integration/test_workspace_sessions_service.py tests/integration/test_workspace_concurrency.py` | 0 | 67 passed；91.84 秒。[脱敏完整日志](final-backend-pg.log) |

默认配置按 pytest 的 addopts 排除 integration；77 项筛除不是通过。警告是 `tests/unit/api/test_api.py:5` 中 Starlette TestClient 使用 httpx 的弃用警告。指定数据库命令包含 SQLite 和 PostgreSQL 参数化分支；67 是该命令总通过数，不能全部标成 PostgreSQL 分支数。使用预先存在的、仅绑定本机 55440 的 `studyagent-goal-test-pg`、维护库 `goal_workspace` 和 `goal_test`，五组夹具创建 UUID 命名的新子库并在各自 finally 中删除；未重启共享容器或触碰本轮 65301 主验收库。各夹具的不同地址校验强度以源码为准，本次启动器额外核对容器、用户、维护库和绑定。未执行 resume/model 验收。

各子进程从独立环境启动，显式设置 `RAG_BACKEND=fake`、`RAG_ENABLED=false`、`OPENAI_API_KEY` 为空、`OPENAI_BASE_URL=http://127.0.0.1:9/v1`、`LANGFUSE_ENABLED=false`，使用私有运行目录的独立 SQLite 路径；`UV_NO_SYNC=1`、`UV_OFFLINE=1`。数据库凭据只从获授权容器配置加载至进程内。原始输出保存在 ignored `.superpowers/runtime/task13/backend-regression/`；归档前替换实际密码、编码后的密码、连接串密码段和 Bearer 值，并核对实际密码未留在归档文本中。此检查不能证明未知敏感值绝不存在。

Ruff 当前 599 项与此前 605 项中排除本次已修复的两个验收文件 6 项后的数量一致；仅按数量对账，不能据此宣称所有诊断逐条相同。先前记录及其局限见 [回归记录](regression-summary.md)。

| 文件 | SHA-256 |
| --- | --- |
| `app/agents/critic.py` | `69300f96f40c7a93d3087e186df29fa5214ef0739ef7aaa753741e684dd65331` |
| `app/harness/teaching_context.py` | `a7332c997f3490c0699bd6c9dc38892a4ae8e41c0efe3f70927d10c9fe632796` |
| `tests/unit/orchestration/test_conversation_context.py` | `27c7045a12f37b3c3d9efbb78a3009288a3fd20d487928138cc16bb3b260f33c` |
| `tests/integration/test_retriever_integration.py` | `b6a8937167836de1c31c50cfd09670658fc63c3c03c9ed94e6d9481ac5028c4b` |

| 日志 | 原始 SHA-256 | 脱敏归档 SHA-256 |
| --- | --- | --- |
| 默认 pytest | `75156fe3fe3ab36218a11b84c130ef3bfb6533e38b9d2cfdfcbbc91e4e719784` | `75156fe3fe3ab36218a11b84c130ef3bfb6533e38b9d2cfdfcbbc91e4e719784` |
| Ruff | `dbd6a1aec0229a4066a32d466dabfbcbd7916d2674994497c96019b012894f56` | `18ebd6d90b9c628c17f7492d6bfd297eb8f3f12bf9e0e9434bf954a9aa0f16d7` |
| 指定数据库回归 | `d8b213f559974a879d3fade75763c7acc3536779efaa024066cd6b5d4e8e502a` | `d8b213f559974a879d3fade75763c7acc3536779efaa024066cd6b5d4e8e502a` |
