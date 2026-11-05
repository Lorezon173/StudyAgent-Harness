# Task13 完成前独立证据审计

**结论　PASS（功能与证据，待本地交付）。** 当前候选的正式浏览器、真实模型续答、应用与 PostgreSQL 重启后读回、五类资源隔离、真实双标签隔离及分层回归达到 Task13 验收合同。首笔产品与验收材料提交、材料独审和第二笔状态账本提交尚待按收口计划执行，当前 Task13 仍为 IN_PROGRESS。 [原 Task13 合同](../../../../superpowers/plans/2026-10-23-study-workspace-core.md#task13跨层真实验收文档与分支审查) · [本地收口计划](local-closeout-plan.md)

## 正式链路与持久化

| 要求 | 实际入口和核验 | 结果 |
| --- | --- | --- |
| A 学习、切换、关闭后自动恢复旧会话及继续旧问题 | `npm --prefix web run e2e` 走正式本机 HTTP。主 run `0db65d3bcdba` 的清单包含两个真实账号，A 两主题三会话。检查 S1 真实待答问题、S2/S3 独立输入、S1 草稿 PATCH 成功回包与独立读回、新浏览器上下文默认登录后的自动会话恢复及不含旧标记的续答。 | exit 0，26 项通过，由 24 项受控 API 浏览器、1 项 Task12 真实 HTTP、1 项 Task13 真实链路组成。Task13 真实用例 44.5 秒。 |
| 真实模型实际收到正确上下文 | 以续答账号、会话、请求、attempt 与 run 绑定成功见证。独立核对记录中两条匹配调用分别来自 Tutor 与 Critic，均由真实客户端返回，`awaiting_response` 和旧题消息 ID、题干摘要匹配。两条均命中 S1 已提交历史及旧题，当前输入命中续答，两个提示参数中均无 S2/S3 标记。 | 同一运行的真实模型见证通过。 |
| 稳定知识点、画像共享和四轮原子保存 | `uv run pytest -m integration -q tests/integration/test_workspace_resume.py` 的 `baseline` 阶段以真实 JWT HTTP 和只读 PG 交叉核对。4 个回合都为 `completed`、`persisted=true`，各有配对用户和助手消息。S1 节点保持，续答有且仅有 1 条关联节点及回答的评分证据。S1/S2 同 T1，T1 revision 1→2，T2 revision 0→0；浏览器另核 T2 内容不变及 T1 详情、summary、snapshot 与实际浮卡 revision。PG 比对状态、消息、请求、草稿/版本和资料。 | exit 0，1 passed、1 阶段性 skip。 |
| 应用单独重启 | 同模块 `app_restarted` 阶段。成功 checkpoint 与原 run、容器、卷、库一致。应用身份改变，PG postmaster 时间保持，真实登录和原业务数据读回通过。 | exit 0，1 passed、1 阶段性 skip。 |
| 同卷 PostgreSQL 重启后读回 | PG 容器、卷、库和迁移 head 一致，postmaster 启动时刻改变。首次动态映射由 65301 改为 63149，旧应用真实登录返回 500、该次未读回。按独审计划只重启本轮观察应用接入新映射，未重建库或重迁；同 run 的成功 checkpoint 与重连阶段记录一致，原账号认证、业务数据和模型见证再次核对。 | 初次 exit 1 保留。重新接入后 exit 0，1 passed、1 阶段性 skip，证明重启持久化及重新接入后的读回。 |
| B 的五类资源替换与副作用 | 同模块 `isolation` 阶段使用 PG 成功 checkpoint 与原 A/B。B 先读自有资源并设置自有节点。受控 HTTP 断连取得 interrupted 请求，B 以实际 attempt/state version 重试，结果完成且持久化，两条消息经独立 PG 验证。替换 session/profile/node/library/request 形成 13 个拒绝断言，含 B 自有会话配 A 请求 ID，以及读和写路径。验证预期 403/404、响应无 A 合成标记、A 读回和 PG 状态一致。 | exit 0，1 passed、1 阶段性 skip。 |
| 双标签账号边界 | 独立合成账号、同源同一浏览器上下文两页，已审私有探针 v3。A 页受控离线草稿 PATCH 失败且无成功 ACK，独立在线快照确认未保存。B 完成真实登录后，旧 A 搜索 GET 和创建 POST 均未发出，提示及表单值可见，B 私有标记未显示给旧 A，未产生错账号写入。A 备份退出后匹配本人本机恢复记录，B 仍可经真实 HTTP 读取、新建并读回。 | v3 exit 0，`TASK13_TWO_TAB_PASS`。首轮 `block-a` 具体失败断言与根因仍未证实。 |

证据链接：[正式浏览器日志](real-browser-second-run.log) · [主运行阶段摘要](real-browser-second-run-summary.md) · [基线日志](real-baseline-round2.log) · [应用重启日志](real-app-restart-round2.log) · [旧 PG 失败](real-pg-restart-round2.log) · [重连与隔离摘要](pg-reconnected-isolation-summary.md) · [PG 成功复验](real-pg-reconnected-round2.log) · [隔离日志](real-isolation-round2.log) · [双标签日志](real-two-tab-round3.log)。

独立复核仅从私有清单、checkpoint、指纹和见证抽取计数、摘要匹配和布尔结果。归档的正式阶段日志仅含测试结果或固定码，三个应用阶段无观察器写入故障信号。PG 的成功结论以实际重新接入为条件，首轮端口漂移故障仍是有效历史证据。 [重连计划独审](pg-reconnect-plan-review.md) · [首轮浏览器与双标签记录](real-browser-first-run-summary.md) · [探针 v3 独审](two-tab-probe-code-review-v3.md)

## 分层回归与故障注入

- 默认 `uv run pytest tests/ -q` exit 0，1,362 passed、77 deselected、1 个 Starlette TestClient/httpx 弃用告警。SQLite 教学事务覆盖开启外键、父记录先 flush、整轮一次业务提交、第二条消息/证据/增量/快照/完成状态/提交故障回滚，以及同 ID 同负载重放、异负载拒绝和显式重试。 [后端结果和命令](final-backend-regression.md) · [默认测试日志](final-backend-pytest.log)
- 指定五个 integration 模块 exit 0，67 passed。按实际参数拆分为 42 PostgreSQL、25 SQLite。工作区迁移 21（9 PG、12 SQLite），私有库迁移 2（1/1），画像服务 8（4/4），工作区会话服务 16（8/8），专用并发模块 20（20 PG）。实际 PG 连接及锁等待验证画像 CAS/会话读写争用、并行评估、会话/请求唯一性、应用断连与最终提交的两种胜出顺序。受控提交故障分别验证未提交不留消息/评分证据和已提交后连接结果丢失仍可查回唯一结果。30 秒续租、180 秒租约、300 秒教学预算、最终锁等待后的租约检查及旧 attempt 栅栏由受控时钟与真实 PG 验证。 [指定集成日志](final-backend-pg.log) · [后端回归范围](final-backend-regression.md)
- `npm --prefix web test` exit 0，16 文件、452 项通过；`npm --prefix web run build` exit 0，TypeScript 与 Vite 完成。独立复算前端冻结文件 54/54 无漂移。草稿失败、版本冲突、前端状态隔离等受控回归与真实主运行分别计证。 [前端回归](account-final-web-regression.md)
- 固定 Ruff 0.17.1 全量 exit 1，599 条。独立按规范化路径、规则码与消息比较多重集，旧 605 中仅两份新验收文件的 6 条诊断消失，新增 0 条。599 条保留为当前分支的既有诊断，交付仍须列为全仓检查未通过。 [固定 Ruff 日志](final-backend-ruff.log) · [逐项比对](local-closeout-plan-review.md)

## 候选与交付边界

HEAD 为 `3c9fae413309731b181e72475cf71c980531e7e4`，本轮产品增量仍在工作区。主运行 189 个冻结文件实算零漂移，17/17 工作区产品与测试增量均匹配该运行的指纹及已审当前版本，分支另有 122 个沿用的不可变审阅路径。历史 1,356 个跳过路径保留逐项理由；两份收口文档待独立材料审查。私有探针指纹 `B1C7AA221666618A78386276FE9A654528ABA6814F3454301FE31345BF32453B` 单独核对，与 v3 独立审阅相符。原账号 High 经真实双标签验证，原两项教学 Medium 经独立代码复审与受控回归验证。超长输入反馈 Low 留作后续，README 旧知识库鉴权表述列入收口。 [候选审阅映射](candidate-review-coverage.md) · [不可变分支清单](branch-ocr-checklist.json)

账本的 Task10、Task11、Task12 均为 DONE，所指产品提交均为当前 HEAD 的祖先。历史任务的覆盖限制保留，包括 Task12 L1–L4、独立 E2E TypeScript 类型检查和联网依赖审计。DEC-SESSION-001 的 B 扩展为独立候选，与真实测试账号 B 分开，第二阶段网络/文件知识规划保持在第一阶段验收之外。 [状态账本](../../status.json) · [Task12 验收限制](../Task12/acceptance-summary.md)

收口仍需独立材料审查、保护 README 162 行及资产清单 34 行用户差异、按明确白名单提交产品和验收材料、核实际第一笔 SHA 及空索引，再提交状态账本并核第二笔 SHA 和直接父链。此审计未更改源码、正式环境、索引或完成状态。 [收口计划独审](local-closeout-plan-review.md)
