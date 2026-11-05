# StudyAgent 工作区第一阶段：Task13 验收记录

本记录以[原 Task13 合同](../superpowers/plans/2026-10-23-study-workspace-core.md#task13跨层真实验收文档与分支审查)、[实施计划](study-workspace-goal/evidence/Task13/implementation-plan.md)和[独立证据审计](study-workspace-goal/evidence/Task13/acceptance-audit.md)为依据。功能与证据审计 PASS；本地交付尚未提交，Task13 为 VERIFIED_UNCOMMITTED、commit=null。验收基线 HEAD `3c9fae413309731b181e72475cf71c980531e7e4` 加审阅冻结的 17 项工作区增量；主运行 `0db65d3bcdba`。

| 需求与入口 | 实际结果及证据层次 | 记录 |
|---|---|---|
| A 的两主题三会话、旧题续答与真实模型上下文；正式本机 HTTP 登录、工作区和真实模型客户端 | 主 run 的正式浏览器验证恢复和续答；Tutor/Critic 真实见证核旧题、当前输入及其他会话标记隔离 | [浏览器与阶段结果](study-workspace-goal/evidence/Task13/real-browser-second-run-summary.md)、[审计](study-workspace-goal/evidence/Task13/acceptance-audit.md) |
| 同主题画像、当前节点与 revision；提交后消息、状态、请求和评分证据可读 | baseline 真实 HTTP 和 PostgreSQL 交叉读取四个 persisted 回合；共享/隔离及详情、摘要和浮卡 revision 按断言核验 | [基线日志](study-workspace-goal/evidence/Task13/real-baseline-round2.log)、[审计](study-workspace-goal/evidence/Task13/acceptance-audit.md) |
| 应用及同卷 PostgreSQL 重启读回 | 应用重启后读回通过；PG 重启使动态端口变化，首次登录 500 失败，按计划重启观察应用重新接入后通过。不能表述为自动无感恢复 | [阶段摘要](study-workspace-goal/evidence/Task13/real-browser-second-run-summary.md)、[重连记录](study-workspace-goal/evidence/Task13/pg-reconnected-isolation-summary.md) |
| 账号 B 替换 session/profile/node/library/request ID | 同 run 真实 HTTP 与 PG：13 个拒绝断言、自有资源正对照及 A 无副作用；受控 HTTP 断连与真实重试另标明 | [隔离日志](study-workspace-goal/evidence/Task13/real-isolation-round2.log)、[重连记录](study-workspace-goal/evidence/Task13/pg-reconnected-isolation-summary.md) |
| 双标签隔离、草稿备份退出及 B 读写 | 独立账号双标签真实浏览器与 HTTP；A 草稿离线故障为受控注入，检查未错误写入、本人备份及 B 后续读写 | [双标签日志](study-workspace-goal/evidence/Task13/real-two-tab-round3.log)、[重连记录](study-workspace-goal/evidence/Task13/pg-reconnected-isolation-summary.md) |
| 保存失败、冲突、租约与幂等 | 指定 67 项混合数据库集成回归，42 PostgreSQL、25 SQLite；真实 PG 与受控故障/时钟分别列证，SQLite 开启外键检查事务回滚 | [后端回归](study-workspace-goal/evidence/Task13/final-backend-regression.md)、[审计](study-workspace-goal/evidence/Task13/acceptance-audit.md) |

正式浏览器为 **26 passed**，其中 24 项受控 API、1 项 Task12 真实 HTTP、1 项 Task13 真实链路。默认后端 **1362 passed / 77 deselected**；指定数据库混合回归 67 passed；前端 16 文件 **452 passed**，构建通过。完整命令和结果见[后端回归](study-workspace-goal/evidence/Task13/final-backend-regression.md)、[前端回归](study-workspace-goal/evidence/Task13/account-final-web-regression.md)及[浏览器日志](study-workspace-goal/evidence/Task13/real-browser-second-run.log)。

固定 Ruff 0.17.1 全仓 exit 1，599 条既有诊断；按路径、规则码、消息逐项多重集比对，旧 605 减去本轮两文件的 6 条后与新 599 相同，新增 0 条。全仓 Ruff 未通过，见[独立计划审查](study-workspace-goal/evidence/Task13/local-closeout-plan-review.md)。

正式入口为 React/Vite 本机 HTTP，经 JWT 访问 `/api/auth`、`/api/chat`、`/api/sessions`、`/api/topic-profiles`、`/api/knowledge`；API 对私有资源执行归属检查。启动沿用项目 README 现有步骤，数据库使用 Alembic 迁移至 head。验收使用专用隔离库，重启复用同卷和同库；不得将本次本机验收推断为公网部署。

[候选审阅映射](study-workspace-goal/evidence/Task13/candidate-review-coverage.md)对应 17 项增量及 122 项继承审阅；原分支 1492 路径中 1356 项有跳过原因，不称全路径审阅通过。超长输入反馈限制、Task12 L1–L4 和独立 E2E 类型及联网安全审计限制保留。第二阶段网络/文件知识能力未实施；DEC-SESSION-001 的 B 扩展是独立候选，与本次账号 B 不同。历史失败记录未覆盖。原始账号凭据、模型提示和私有探针保留于私有运行边界，未纳入交付；需复查的脱敏日志及对应范围见审计。
