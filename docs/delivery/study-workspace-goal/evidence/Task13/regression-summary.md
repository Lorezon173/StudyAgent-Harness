# Task13 阶段回归记录

本轮不是最终验收。HEAD `3c9fae413309731b181e72475cf71c980531e7e4`；四项检查可与浏览器 E2E 脚本修订并行，未运行真实应用、Playwright、模型或数据库重启。源码在运行前后哈希一致：

| 文件 | SHA-256 |
| --- | --- |
| `web/src/api/profiles.ts` | `69860E6911CA98A36ED4F13077E04F28EF889757363F41AE1953A6355006DA52` |
| `web/src/pages/Profile.tsx` | `F0360B07A7157F1BC321FCF9C835674A7079A8F0A2A2600D8DE413A5D32F1AF5` |
| `web/src/pages/Profile.test.tsx` | `FF5655BF6430233AFDFC866BCDC64E9BE904744D7F0BF3918DCBA58672C904A4` |
| `web/src/components/profile/ProfileNodeControls.tsx` | `F107543368A62D8E5C0D12EA1C40E7069C54E6D504084A16E28779EF75A7912B` |
| `tests/integration/workspace_observer.py` | `58F53D4DAA53C75CC3ED33513A046380D9EA2F6EF3400A5493BC1E7EBD3F5116` |
| `tests/integration/test_workspace_resume.py` | `AA870991DB8DFC0BB2BF52AB6F1BC7297DC2111382C1A82959EA992BF98D8129` |

这些哈希与 Node UI、Python v2 独审记录一致；浏览器 E2E 文件不计入此次冻结。若后续修改前端，前端结果不自动适用于修改后源码。

| 命令 | 退出码 | 结果及日志 |
| --- | --- | --- |
| `uv run pytest tests/ -q` | 1 | 1339 passed、17 failed、77 deselected、1 warning，290.25 秒；[完整日志](regression-pytest.log)。 |
| `uvx --offline --index-url https://pypi.tuna.tsinghua.edu.cn/simple --from ruff==0.17.1 ruff check .` | 1 | 605 条诊断；[完整日志](regression-ruff.log)。 |
| `npm --prefix web test` | 0 | 16 个测试文件、439 项通过；[完整日志](regression-web-test.log)。 |
| `npm --prefix web run build` | 0 | TypeScript 和 Vite 构建通过；[完整日志](regression-web-build.log)。 |

版本：uv 0.7.21、Python 3.12.11、Node 24.11.0、npm 11.12.1、Ruff 0.17.1。pytest 按默认 addopts 排除 integration 标记，并非所有 integration 目录里的测试都有该标记；此轮实际 deselected 77。执行 pytest 时设置 `UV_NO_SYNC=1`，数据库指向独立本地 SQLite 文件，模型密钥使用合成占位、模型地址指向未监听的本地 9 端口、`RAG_ENABLED=false`，未将真实服务配置注入测试。

pytest 的 17 项失败分布在 `tests/integration/test_retriever_integration.py`（5）与 `tests/unit/infrastructure/test_rag.py`（12）；日志包含指向离线占位地址的 OpenAI 连接拒绝及断言失败。本轮环境可能影响这些结果，未将其裁定为既有缺陷或本轮回归；未自行重跑。原始私有日志保存在 ignored 运行目录；日志中的部分 Windows 中文异常文本发生编码乱码，但保留全部输出，无法恢复其原字节语义。

Ruff 新增两个 Python 文件各 3 项：`test_workspace_resume.py` 为 I001×1、SIM118×2；`workspace_observer.py` 为 I001×1、S110×1、BLE001×1。其余 599 项位于 175 个已跟踪 Python 文件，文件相对当前 HEAD 无工作区差异；只对照了源码状态，没有重跑基线 Ruff。日志以私有配置及本轮凭据做字符串脱敏检查，未命中；这不代替对未知敏感信息的人工审查。
