# Task10 第三轮修复实施与验证记录

## 当前结论

已完成本轮代码修改、定向验证和冻结后回归；**尚未完成全范围独立代码审查，也未完成真实服务验收**。本记录不是 Task10 完成或上线声明。

- 修改 `web/src/store/workspace.ts`：历史桥接失败时独立应用可信画像与有效活动观察，旧消息和分页前沿不发布部分结果；已有运行活动保持保守门禁。
- 修改 `web/src/store/workspaceController.ts`：加载与未关联继续分别保留失败时的独立领域；POST 后旧 GET 被淘汰时受控复查同一请求，较新加载尚未结束时先等待，校验账号、请求、payload 与 baseline 后才确认消息，不自动重复 POST。
- 修改 `web/src/pages/Chat.test.tsx`：增加业务路由、真实 store/controller、模拟网络的交错验证。未改后端或依赖，未覆盖用户 README/asset 的现有改动。

## 实际 RED/GREEN

- `review3-history-red.log`：切换返回后桥接 503，旧历史与游标保留而画像仍为旧值，exit 1；`review3-history-green.log` exit 0。后续 `review3-matrix.log` 包含再次点击历史同步、桥接成功并保留旧游标。
- `review3-continue-red.log`：继续未关联请求时桥接失败，新画像未更新，exit 1；`review3-continue-green.log` exit 0。`review3-continue-retry.log` 验证失败后再次继续、补齐历史并沿用旧游标，exit 0。
- `review3-post-red.log`：唯一 POST 后挂起 GET，切换会话触发较新观察并释放旧 GET，未能自动关联，exit 1；这将原静态推导变为模拟网络条件下的实测复现。首次 `review3-post-green.log` exit 1 的原因是测试数据将旧回复与新回复安排到同一 turn，关联校验正确报冲突；修正测试数据后 `review3-post-green2.log` exit 0。后续 `review3-post-matrix.log`、`review3-inflight-green.log` 覆盖完成、running、503、404 与保留本机副本，均 exit 0。
- `review3-inflight-red.log`：自动恢复抢占较新进行中活动观察，导致新 running 未合并，exit 1；`review3-inflight-green.log` 5 项通过、exit 0。新实现等待较新加载结束后再重查。
- `review3-auth-stale.log` 首次 401 测试将注销后路由重新创建的空 bucket 误判为失败；修正为验证旧消息、画像和错误均不再存在，之后 `review3-post-green2.log` 覆盖 401 换代及旧 load 迟到，exit 0。`review3-activity-check.log` 验证同一 load 的活动观察失效后保留较新 running，同时独立合并较新画像，exit 0。
- `review3-interim-build.log` 因请求恢复 baseline 联合类型未收窄失败 exit 2；修正后 `review3-interim-build2.log` exit 0，后续冻结构建另见下。

## 现有回归与范围

冻结后 `review3-final-suite.log`：11 个测试文件、296 项通过、exit 0；`review3-final-build.log` exit 0。冻结前后 46 项文件 SHA 见 `review3-source-before.json` 和 `review3-source-after.json`，差异 0。既有测试覆盖同 ID 多 writer、linked 精确清理与副本读写失败、账户变换、消息 ID 冲突、循环游标、上下翻并发以及原有活动门禁；本轮补测见上。README 已检查；本次是已有恢复机制的缺陷修复，没有新增 API 或使用步骤，为保护现有改动未修改 README。

以下组合没有本轮新增的专门业务测试：桥接先成功一页再失败时独立画像/活动组合；未关联继续桥接失败时账号切换及请求 attempt 变化的组合；自动重查期间请求被替换、较新 attempt 先完成或另一个 writer 同时变化的组合。既有测试分别覆盖部分基础边界，但不能视为这些组合均已证明。须交独立审查评估并按审查结论补测或修订；不以全量绿灯替代这些组合证据。

真实浏览器、模型问答、PostgreSQL 重启后消息读取、跨账号拒绝及 persisted=true 联合验收均未执行；模拟 fetch/Storage 不构成真实持久化验收。独立审查应对整个 Task10 而非仅本轮补丁进行，并核查错误、过期观察和恢复副本保护。
